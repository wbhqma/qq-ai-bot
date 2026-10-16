import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.config import Settings
from app.llm import ChatModel, ModelError
from app.persona import build_system_prompt

SessionKey = tuple[str, str, str]  # 机器人、群、发送者的 OpenID
Send = Callable[[str], Awaitable[object]]

HELP = "@我 加上问题，就能聊天。\n/ping：检查在线\n/清空：忘记你在本群的对话\n/帮助：查看用法\n我只记得近期对话，重启后会清空。"


@dataclass
class Session:
    messages: list[dict[str, str]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_call: float = float("-inf")
    touched: float = field(default_factory=time.monotonic)


class ChatService:
    def __init__(self, settings: Settings, model: ChatModel):
        self.settings = settings
        self.model = model
        self.sessions: OrderedDict[SessionKey, Session] = OrderedDict()
        self.seen: OrderedDict[tuple[str, str, str], float] = OrderedDict()
        self.capacity = asyncio.Semaphore(3)

    def _session(self, key: SessionKey) -> Session:
        now = time.monotonic()
        for old_key, session in list(self.sessions.items()):
            if now - session.touched > 3600 and not session.lock.locked():
                del self.sessions[old_key]
        if key not in self.sessions:
            if len(self.sessions) >= 256:
                removable = next((k for k, s in self.sessions.items() if not s.lock.locked()), None)
                if removable is None:
                    raise ModelError("现在有点忙，稍等一下再叫我。")
                del self.sessions[removable]
            self.sessions[key] = Session()
        session = self.sessions[key]
        session.touched = now
        self.sessions.move_to_end(key)
        return session

    def _claim(self, key: tuple[str, str, str]) -> bool:
        now = time.monotonic()
        while self.seen and now - next(iter(self.seen.values())) > 300:
            self.seen.popitem(last=False)
        if key in self.seen:
            return False
        self.seen[key] = now
        while len(self.seen) > 2048:
            self.seen.popitem(last=False)
        return True

    async def handle(self, key: SessionKey, message_id: str, text: str, send: Send) -> bool:
        # 消息 ID 只用于去重；文本相同而 ID 不同的消息仍分别处理。
        event_key = (key[0], key[1], message_id)
        if not self._claim(event_key):
            return False
        sent = False
        try:
            try:
                await self._handle(key, text.strip(), send)
            except ModelError as error:
                await send(str(error))
            sent = True
            return True
        finally:
            if not sent:
                # QQ 发送失败时允许该事件重新投递；失败回复不写进对话历史。
                self.seen.pop(event_key, None)

    async def _handle(self, key: SessionKey, text: str, send: Send) -> None:
        if text in ("/帮助", "/help", "帮助") or not text:
            await send(HELP)
            return
        if text in ("/ping", "ping"):
            await send("我在线！可以 @我 聊天，或发 /帮助。")
            return
        if len(text) > 1800:
            await send("这段有点长，请缩短到 1800 字以内再发给我。")
            return

        session = self._session(key)
        if text in ("/清空", "/reset", "清空记忆"):
            async with session.lock:
                session.messages.clear()
                await send("已经忘记你在这个群里的近期对话，我们重新聊！")
            return
        if session.lock.locked():
            await send("我还在回答你上一条消息，稍等一下。")
            return

        async with session.lock:
            if time.monotonic() - session.last_call < self.settings.cooldown_seconds:
                await send("慢一点点，过几秒再问我吧。")
                return
            try:
                async with asyncio.timeout(5):
                    await self.capacity.acquire()
            except TimeoutError:
                raise ModelError("我正在回答其他问题，稍等一下再试。") from None
            try:
                session.last_call = time.monotonic()
                messages = [
                    {"role": "system", "content": build_system_prompt(self.settings.bot_name)},
                    *[dict(m) for m in session.messages],
                    {"role": "user", "content": text},
                ]
                answer = await self.model.complete(messages)
                await send(answer)
                # 只在真正发回群后记录一轮，避免历史里出现未送达的回答。
                session.messages.extend([
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": answer},
                ])
                while session.messages and (
                    len(session.messages) > self.settings.history_turns * 2
                    or sum(len(m["content"]) for m in session.messages) > 12000
                ):
                    del session.messages[:2]
            finally:
                self.capacity.release()
