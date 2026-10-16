import asyncio
import json
import unittest
from dataclasses import replace

import httpx

from app.chat import ChatService
from app.config import Settings
from app.deepseek import DeepSeekClient, ModelError


class FakeModel:
    def __init__(self):
        self.calls = []
        self.error = None

    async def complete(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return "回答：" + messages[-1]["content"]


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.model = FakeModel()
        self.settings = Settings(cooldown_seconds=0)
        self.service = ChatService(self.settings, self.model)
        self.sent = []
        self.key = ("test-bot", "group-a", "user-a")

    async def send(self, text):
        self.sent.append(text)

    async def test_configured_name_reaches_model_system_message(self):
        for number, name in enumerate((Settings().bot_name, "自定义鲸鲸")):
            self.service.settings = replace(self.settings, bot_name=name)
            await self.service.handle(self.key, f"name-{number}", "你叫什么？", self.send)
            system = self.model.calls[-1][0]
            self.assertEqual(system["role"], "system")
            # 人设允许自行修改；验证名字传入，不限定后续标点，也不在失败时打印整段人设。
            self.assertTrue(system["content"].startswith(f"你叫{name}"), "系统提示应包含配置的机器人名字")

    async def test_duplicate_event_ignored_but_duplicate_content_preserved(self):
        await self.service.handle(self.key, "m1", "你好", self.send)
        self.assertFalse(await self.service.handle(self.key, "m1", "你好", self.send))
        await self.service.handle(self.key, "m2", "你好", self.send)
        self.assertEqual(len(self.model.calls), 2)
        self.assertEqual([m["role"] for m in self.model.calls[1]], ["system", "user", "assistant", "user"])
        self.assertEqual(len(self.sent), 2)

    async def test_group_and_user_memory_are_isolated(self):
        for number, key in enumerate((self.key, ("test-bot", "group-b", "user-a"), ("test-bot", "group-a", "user-b"))):
            await self.service.handle(key, f"m{number}", "我的秘密", self.send)
        self.assertEqual([len(call) for call in self.model.calls], [2, 2, 2])

    async def test_reset_only_clears_requesting_users_current_group(self):
        other = ("test-bot", "group-a", "user-b")
        await self.service.handle(self.key, "m1", "你好", self.send)
        await self.service.handle(other, "m2", "另一个人", self.send)
        await self.service.handle(self.key, "m3", "/清空", self.send)
        await self.service.handle(self.key, "m4", "重新开始", self.send)
        self.assertEqual(len(self.model.calls[-1]), 2)
        self.assertEqual(len(self.service.sessions[other].messages), 2)

    async def test_history_is_bounded_in_complete_turns(self):
        self.service.settings = replace(self.settings, history_turns=2)
        for number in range(8):
            await self.service.handle(self.key, str(number), str(number), self.send)
        history = self.service.sessions[self.key].messages
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "user", "assistant"])
        self.assertEqual(history[0]["content"], "6")

    async def test_model_failure_does_not_poison_history(self):
        self.model.error = ModelError("模型暂时不可用")
        await self.service.handle(self.key, "m1", "你好", self.send)
        self.assertEqual(self.sent, ["模型暂时不可用"])
        self.assertEqual(self.service.sessions[self.key].messages, [])

    async def test_send_failure_can_retry_without_committing_history(self):
        async def failing_send(text):
            raise RuntimeError("QQ send failed")
        with self.assertRaises(RuntimeError):
            await self.service.handle(self.key, "m1", "你好", failing_send)
        self.assertEqual(self.service.sessions[self.key].messages, [])
        self.assertTrue(await self.service.handle(self.key, "m1", "你好", self.send))
        self.assertEqual(len(self.service.sessions[self.key].messages), 2)

    async def test_help_ping_and_oversized_input_do_not_call_model(self):
        for number, text in enumerate(("/帮助", "/ping", "", "字" * 1801)):
            await self.service.handle(self.key, str(number), text, self.send)
        self.assertEqual(self.model.calls, [])
        self.assertEqual(len(self.sent), 4)

    async def test_cooldown_prevents_extra_model_call(self):
        self.service.settings = replace(self.settings, cooldown_seconds=3)
        await self.service.handle(self.key, "m1", "你好", self.send)
        await self.service.handle(self.key, "m2", "再问", self.send)
        self.assertEqual(len(self.model.calls), 1)
        self.assertIn("过几秒", self.sent[-1])

    async def test_in_flight_message_does_not_mix_history(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow_model(messages):
            entered.set()
            await release.wait()
            return "第一条的回复"
        self.model.complete = slow_model
        first = asyncio.create_task(self.service.handle(self.key, "m1", "第一条", self.send))
        await entered.wait()
        await self.service.handle(self.key, "m2", "第二条", self.send)
        release.set()
        await first
        self.assertEqual(self.sent, ["我还在回答你上一条消息，稍等一下。", "第一条的回复"])
        self.assertEqual(self.service.sessions[self.key].messages[0]["content"], "第一条")


class DeepSeekTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_request_shape_and_final_text_only(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "你好！", "reasoning_content": "不应发给群的字段"}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            model = DeepSeekClient(Settings(deepseek_api_key="test-key"), client)
            self.assertEqual(await model.complete([{"role": "user", "content": "你好"}]), "你好！")
        payload = json.loads(requests[0].content)
        self.assertEqual(str(requests[0].url), "https://api.deepseek.com/chat/completions")
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(requests[0].headers["Authorization"], "Bearer test-key")

    async def test_http_failures_have_safe_messages(self):
        for status in (401, 402, 429, 500):
            with self.subTest(status=status):
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, text="private-error-body"))) as client:
                    model = DeepSeekClient(Settings(deepseek_api_key="test-key"), client)
                    with self.assertRaises(ModelError) as error:
                        await model.complete([])
                    self.assertNotIn("private-error-body", str(error.exception))

    async def test_timeout_and_empty_response_are_handled(self):
        def timeout(request):
            raise httpx.ReadTimeout("private timeout", request=request)
        handlers = (timeout, lambda request: httpx.Response(200, json={"choices": []}))
        for handler in handlers:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ModelError):
                    await DeepSeekClient(Settings(deepseek_api_key="test-key"), client).complete([])


if __name__ == "__main__":
    unittest.main()
