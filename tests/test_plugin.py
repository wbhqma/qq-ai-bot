import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
from nonebot.adapters.qq import GroupAtMessageCreateEvent, GroupMessageCreateEvent

from app.chat import ChatService
from app.config import Settings


class PluginTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        nonebot.init(driver="~none", log_level="WARNING")
        cls.plugin = nonebot.load_plugin("plugins.qq_chat").module

    def make_event(self, event_type=GroupAtMessageCreateEvent, *, bot_author=False):
        return event_type(
            id="test-message", content="/ping", timestamp="2026-10-16T12:00:00+08:00",
            group_id="test-group-number", group_openid="test-group",
            author={"id": "test-author", "bot": bot_author, "member_openid": "test-member", "member_role": "owner"},
        )

    async def test_only_group_mentions_match(self):
        bot = SimpleNamespace(self_id="test-bot")
        self.assertTrue(await self.plugin.chat.rule(bot, self.make_event(), {}))
        self.assertFalse(await self.plugin.chat.rule(bot, self.make_event(GroupMessageCreateEvent), {}))

    async def test_real_adapter_event_can_reply_with_original_event(self):
        bot = SimpleNamespace(self_id="test-bot", send=AsyncMock())
        service = ChatService(Settings(), SimpleNamespace())
        self.plugin.set_service(service)
        event = self.make_event()
        await self.plugin.handle_group_message(bot, event)
        bot.send.assert_awaited_once_with(event, "我在线！可以 @我 聊天，或发 /帮助。")

    async def test_other_groups_and_bot_authors_are_ignored(self):
        bot = SimpleNamespace(self_id="test-bot", send=AsyncMock())
        self.plugin.set_service(ChatService(Settings(allowed_groups=frozenset({"another-group"})), SimpleNamespace()))
        await self.plugin.handle_group_message(bot, self.make_event())
        self.plugin.set_service(ChatService(Settings(), SimpleNamespace()))
        await self.plugin.handle_group_message(bot, self.make_event(bot_author=True))
        bot.send.assert_not_awaited()
