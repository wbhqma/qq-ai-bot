from typing import Any, Protocol

import httpx

from app.config import Settings


class ModelError(Exception):
    """可向群成员展示的简短失败提示，不包含原始响应或密钥。"""


class ChatModel(Protocol):
    async def complete(self, messages: list[dict[str, str]]) -> str: ...


class LLMClient:
    """适配文本对话协议；上层会话逻辑不依赖服务商。"""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.config = settings.resolve_llm()
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10))
        self.owns_client = client is None

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    def _request(self, messages: list[dict[str, str]]) -> tuple[dict[str, str], dict[str, Any]]:
        config = self.config
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        dialogue = [dict(m) for m in messages if m["role"] != "system"]
        if config.provider == "openai":
            # 手动传入完整近期上下文，不依赖平台保存的会话 ID。
            return headers, {
                "model": config.model, "instructions": system, "input": dialogue,
                "max_output_tokens": config.max_tokens, "stream": False, "store": False,
            }
        if config.provider == "anthropic":
            headers = {"x-api-key": config.api_key, "anthropic-version": "2023-06-01"}
            return headers, {
                "model": config.model, "system": system, "messages": dialogue,
                "max_tokens": config.max_tokens, "stream": False,
            }
        if config.provider == "gemini":
            return {"x-goog-api-key": config.api_key}, {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [
                    {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in dialogue
                ],
                "generationConfig": {"maxOutputTokens": config.max_tokens},
            }
        token_param = config.token_param if config.provider == "compatible" else "max_tokens"
        payload: dict[str, Any] = {
            "model": config.model, "messages": messages,
            "stream": False, token_param: config.max_tokens,
        }
        if config.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        return headers, payload

    def _answer(self, data: dict[str, Any]) -> str:
        if self.config.provider == "openai":
            return "".join(
                part["text"] for item in data["output"] if item.get("type") == "message"
                for part in item["content"] if part.get("type") == "output_text"
            )
        if self.config.provider == "anthropic":
            return "".join(part["text"] for part in data["content"] if part.get("type") == "text")
        if self.config.provider == "gemini":
            return "".join(
                part["text"] for part in data["candidates"][0]["content"]["parts"]
                if "text" in part and not part.get("thought", False)
            )
        return data["choices"][0]["message"]["content"]

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.config.api_key and self.config.provider != "ollama":
            raise ModelError("我还没接上 AI 服务，管理员配置好后就能聊天。先试试 /ping 吧。")
        headers, payload = self._request(messages)
        if self.config.provider == "gemini":
            generation = {
                **payload["generationConfig"],
                **self.config.extra_body.get("generationConfig", {}),
                "maxOutputTokens": self.config.max_tokens,
            }
            payload.update(self.config.extra_body)
            payload["generationConfig"] = generation
        else:
            payload.update(self.config.extra_body)
        try:
            response = await self.client.post(self.config.endpoint, headers=headers, json=payload)
            if response.status_code in (401, 403):
                raise ModelError("AI 服务鉴权失败，请管理员检查模型配置。")
            if response.status_code == 402:
                raise ModelError("AI 服务额度不足，请管理员检查账户。")
            if response.status_code in (400, 404, 422):
                raise ModelError("AI 服务不接受当前配置，请管理员检查接口地址、模型名称和参数兼容性。")
            if response.status_code == 429:
                raise ModelError("AI 服务有点忙，请稍后再问一次。")
            response.raise_for_status()
            answer = self._answer(response.json())
            if not isinstance(answer, str) or not answer.strip():
                raise ModelError("AI 服务没有返回可用文本，可能因输出预算或内容限制，请管理员检查模型配置。")
            answer = answer.strip()
            return answer if len(answer) <= 1200 else answer[:1180] + "\n（回复较长，已截断）"
        except httpx.TimeoutException:
            raise ModelError("这次回答超时了，稍后再试试。") from None
        except httpx.HTTPError:
            raise ModelError("暂时连不上 AI 服务，请稍后再试。") from None
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise ModelError("AI 服务没有返回可用的文本，请换个问法或稍后再试。") from None
