from nonebot import logger, on_type
from nonebot.adapters.qq import Bot, GroupAtMessageCreateEvent

from app.chat import ChatService

# 只监听“群里 @机器人”的事件。普通群消息、私聊均不触发本插件。
chat = on_type(GroupAtMessageCreateEvent, priority=10, block=True)
service: ChatService | None = None


def set_service(value: ChatService) -> None:
    global service
    service = value


@chat.handle()
async def handle_group_message(bot: Bot, event: GroupAtMessageCreateEvent) -> None:
    if service is None or event.author.bot:
        return
    group = event.group_openid
    if service.settings.allowed_groups and group not in service.settings.allowed_groups:
        return
    key = (str(bot.self_id), group, event.get_user_id())
    try:
        await service.handle(
            key,
            event.id,
            event.get_plaintext(),
            lambda text: bot.send(event, text),
        )
    except Exception as error:
        # 不输出异常原文：其中可能包含请求数据或平台响应。
        logger.warning("QQ群回复失败，错误类型：{}", type(error).__name__)
