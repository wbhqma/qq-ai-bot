import argparse
import json

import nonebot
from nonebot.adapters.qq import Adapter
from nonebot.adapters.qq.config import Intents

from app.chat import ChatService
from app.config import Settings
from app.llm import LLMClient
from app.privacy import configure_private_logging


def build_bot(settings: Settings, *, offline: bool = False) -> None:
    configure_private_logging()
    # 按此版本适配器的实际字段关闭无关事件，只开 QQ 群/单聊事件订阅位。
    # 插件再只接收群 @类型，从而不处理单聊。
    intent = {name: name == "c2c_group_at_messages" for name in Intents.model_fields}
    accounts = [] if offline else [{
        "id": settings.qq_app_id,
        "secret": settings.qq_app_secret,
        "intent": intent,
        "use_websocket": True,
    }]
    nonebot.init(
        driver="~none+~httpx+~websockets",
        log_level="INFO",
        qq_bots=accounts,
    )
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)
    plugin = nonebot.load_plugin("plugins.qq_chat")
    if plugin is None:
        raise RuntimeError("聊天插件加载失败。")
    model = LLMClient(settings)
    plugin.module.set_service(ChatService(settings, model))
    driver.on_shutdown(model.close)


def main() -> int:
    configure_private_logging()
    parser = argparse.ArgumentParser(description="QQ 群 AI 聊天机器人")
    parser.add_argument("--check", action="store_true", help="检查配置与插件，不连接 QQ 或模型")
    args = parser.parse_args()
    try:
        settings = Settings.load()
        if args.check:
            print(json.dumps(settings.status(), ensure_ascii=False, indent=2))
            build_bot(settings, offline=True)
            print("离线自检通过：QQ 适配器与聊天插件已加载；没有连接 QQ 或调用模型。")
            return 0
        settings.validate_qq()
        build_bot(settings)
        print("正在连接 QQ。连接成功后，在测试群 @机器人 /ping，然后试着聊天。")
        nonebot.run()
    except ValueError:
        print("配置需要调整：请检查本机 .env 的字段格式、模型名称和 API 地址；配置内容已隐藏。")
        return 2
    except KeyboardInterrupt:
        print("机器人已停止。")
        return 0
    except Exception:
        nonebot.logger.exception("机器人启动或运行失败。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
