"""终端仅输出固定诊断摘要，不输出原始事件、凭证或异常堆栈。"""

import logging
import sys
from typing import Any, TextIO


def private_log_filter(record: dict[str, Any]) -> bool:
    message = str(record.get("message", "")).lower()
    exception = record.get("exception")
    try:
        detail = str(exception.value).lower() if exception else ""
    except Exception:
        detail = ""

    # 只用原文判断固定诊断分类，绝不把原文或异常对象写入输出。
    if "invalid appid or secret" in detail or "invalid appid or secret" in message:
        summary = "QQ 身份验证失败：请在本机检查同一机器人的 AppID 与 AppSecret。"
    elif "failed to get gateway info" in message:
        summary = "获取 QQ 网关失败：请检查 QQ 凭证和网络。"
    elif "nonebot is initializing" in message:
        summary = "机器人正在初始化。"
    elif "succeeded to load plugin" in message:
        summary = "插件已加载。"
    elif "failed to load plugin" in message:
        summary = "插件加载失败，请检查安装和配置。"
    elif "disconnected" in message or "connection closed" in message:
        summary = "QQ 连接已断开，等待框架重连。"
    elif "successfully connected" in message or "websocket connection established" in message:
        summary = "QQ 连接已建立。"
    elif record.get("name") == "plugins.qq_chat":
        summary = "QQ 消息处理失败，原始请求和异常详情已隐藏。"
    elif record.get("name") == "nonebot.message":
        summary = "QQ 事件已处理，消息内容和用户标识已隐藏。"
    else:
        summary = "运行事件：详细内容已隐藏。"

    record["message"] = summary
    record["exception"] = None
    record["extra"] = {}
    return True


def configure_private_logging(sink: TextIO | None = None) -> int:
    from nonebot.log import LoguruHandler, logger

    logger.remove()
    handler = logger.add(
        sink if sink is not None else sys.stdout,
        level="INFO",
        format="{time:MM-DD HH:mm:ss} [{level}] {message}",
        filter=private_log_filter,
        diagnose=False,
        backtrace=False,
    )
    # asyncio/httpx 等标准 logging 输出同样经过隐私过滤。
    logging.basicConfig(handlers=[LoguruHandler()], level=logging.WARNING, force=True)
    return handler
