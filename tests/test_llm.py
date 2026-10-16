import json
import unittest

import httpx

from app.config import Settings
from app.llm import LLMClient, ModelError

MESSAGES = [
    {"role": "system", "content": "你叫哦鲸鲸"},
    {"role": "user", "content": "我叫小王"},
    {"role": "assistant", "content": "你好，小王"},
    {"role": "user", "content": "我叫什么？"},
]


class MultiProviderTests(unittest.IsolatedAsyncioTestCase):
    async def call_model(self, settings, response):
        captured = []

        def handler(request):
            captured.append(request)
            return httpx.Response(200, json=response)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            answer = await LLMClient(settings, client).complete(MESSAGES)
        return answer, captured[0], json.loads(captured[0].content)

    async def test_compatible_uses_configured_endpoint_key_and_only_applicable_parameters(self):
        for base in ("https://models.example/deployment/v1/", "https://models.example/deployment/v1/chat/completions"):
            with self.subTest(base=base):
                answer, request, body = await self.call_model(
                    Settings(llm_provider="compatible", llm_base_url=base, llm_model="custom-model",
                             llm_api_key="current-key", deepseek_api_key="legacy-key",
                             llm_max_tokens=4096, llm_extra_body={"enable_thinking": False}),
                    {"choices": [{"message": {"content": "小王", "reasoning_content": "hidden"}}]},
                )
                self.assertEqual(answer, "小王")
                self.assertEqual(str(request.url), "https://models.example/deployment/v1/chat/completions")
                self.assertEqual(request.headers["Authorization"], "Bearer current-key")
                self.assertEqual(body["messages"], MESSAGES)
                self.assertEqual(body["model"], "custom-model")
                self.assertEqual(body["max_tokens"], 4096)
                self.assertFalse(body["enable_thinking"])
                self.assertNotIn("thinking", body)

    async def test_ollama_can_run_without_an_api_key(self):
        answer, request, body = await self.call_model(
            Settings(llm_provider="ollama", llm_model="installed-model", deepseek_api_key="legacy-key"),
            {"choices": [{"message": {"content": "本机回复"}}]},
        )
        self.assertEqual(answer, "本机回复")
        self.assertEqual(str(request.url), "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("thinking", body)

    async def test_compatible_can_use_completion_token_parameter(self):
        _, _, body = await self.call_model(
            Settings(llm_provider="compatible", llm_base_url="https://models.example/v1",
                     llm_model="reasoning-model", llm_api_key="key",
                     llm_token_param="max_completion_tokens"),
            {"choices": [{"message": {"content": "回答"}}]},
        )
        self.assertEqual(body["max_completion_tokens"], 2048)
        self.assertNotIn("max_tokens", body)

    async def test_openai_responses_preserves_dialogue_and_only_returns_text(self):
        answer, request, body = await self.call_model(
            Settings(llm_provider="openai", llm_model="account-gpt-model", llm_api_key="openai-key"),
            {"output": [
                {"type": "reasoning", "summary": [{"text": "hidden reasoning"}]},
                {"type": "message", "content": [
                    {"type": "output_text", "text": "你叫"},
                    {"type": "output_text", "text": "小王"},
                ]},
            ]},
        )
        self.assertEqual(answer, "你叫小王")
        self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
        self.assertEqual(request.headers["Authorization"], "Bearer openai-key")
        self.assertEqual(body["instructions"], MESSAGES[0]["content"])
        self.assertEqual(body["input"], MESSAGES[1:])
        self.assertFalse(body["store"])
        self.assertEqual(body["max_output_tokens"], 2048)
        self.assertNotIn("max_tokens", body)

    async def test_claude_uses_messages_api_and_separate_system_prompt(self):
        answer, request, body = await self.call_model(
            Settings(llm_provider="anthropic", llm_base_url="https://api.anthropic.com",
                     llm_model="account-claude-model", llm_api_key="anthropic-key"),
            {"content": [{"type": "thinking", "thinking": "hidden"}, {"type": "text", "text": "小王"}]},
        )
        self.assertEqual(answer, "小王")
        self.assertEqual(str(request.url), "https://api.anthropic.com/v1/messages")
        self.assertEqual(request.headers["x-api-key"], "anthropic-key")
        self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
        self.assertEqual(body["system"], MESSAGES[0]["content"])
        self.assertEqual(body["messages"], MESSAGES[1:])

    async def test_gemini_converts_roles_and_does_not_place_key_in_url(self):
        answer, request, body = await self.call_model(
            Settings(llm_provider="gemini", llm_model="models/account-gemini-model",
                     llm_api_key="gemini-key", llm_extra_body={
                         "generationConfig": {"temperature": 0.6, "maxOutputTokens": 99999},
                     }),
            {"candidates": [{"content": {"parts": [
                {"thought": True, "text": "hidden"},
                {"text": "你叫"}, {"text": "小王"},
            ]}}]},
        )
        self.assertEqual(answer, "你叫小王")
        self.assertEqual(str(request.url), "https://generativelanguage.googleapis.com/v1beta/models/account-gemini-model:generateContent")
        self.assertNotIn("gemini-key", str(request.url))
        self.assertEqual(request.headers["x-goog-api-key"], "gemini-key")
        self.assertEqual([m["role"] for m in body["contents"]], ["user", "model", "user"])
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "你叫哦鲸鲸")
        self.assertEqual(body["generationConfig"], {"temperature": 0.6, "maxOutputTokens": 2048})

    async def test_missing_cloud_key_does_not_send_a_request(self):
        def forbidden(request):
            self.fail("An unconfigured cloud service must not receive a request")
        for provider in ("compatible", "openai", "anthropic", "gemini"):
            with self.subTest(provider=provider):
                async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
                    model = LLMClient(Settings(
                        llm_provider=provider, llm_base_url="https://service.example/v1",
                        llm_model="model", deepseek_api_key="legacy-key",
                    ), client)
                    with self.assertRaises(ModelError):
                        await model.complete(MESSAGES)

    async def test_malformed_responses_never_expose_original_data(self):
        cases = [
            ("compatible", {"choices": []}),
            ("openai", {"output": [{"type": "message", "content": None}]}),
            ("anthropic", {"content": [{"type": "text", "text": 5}]}),
            ("gemini", {"candidates": []}),
        ]
        for provider, response in cases:
            response["private_error"] = "private-response-data"
            with self.subTest(provider=provider):
                with self.assertRaises(ModelError) as error:
                    await self.call_model(Settings(
                        llm_provider=provider, llm_base_url="https://service.example/v1",
                        llm_model="model", llm_api_key="current-key",
                    ), response)
                self.assertNotIn("private-response-data", str(error.exception))
