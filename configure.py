import json
from getpass import getpass

from dotenv import dotenv_values

from app.config import DEFAULT_BOT_NAME, DEEPSEEK_URLS, LLM_DEFAULTS, ROOT, Settings


def configure() -> int:
    path = ROOT / ".env"
    values = dict(dotenv_values(path, encoding="utf-8")) if path.exists() else {}
    print("在本机配置机器人。AppID 和密钥输入不回显；已有值可留空保留。")
    for name, title, secret in (
        ("QQ_APP_ID", "QQ AppID（开发设置里的应用 ID）", True),
        ("QQ_APP_SECRET", "QQ AppSecret", True),
    ):
        hint = " [已保存，留空保留]" if values.get(name) else ""
        prompt = title + hint + "："
        value = (getpass(prompt) if secret else input(prompt)).strip()
        if value:
            values[name] = value
    current_name = values.get("BOT_NAME") or DEFAULT_BOT_NAME
    values["BOT_NAME"] = input("机器人名字（留空保留；已有名字不回显）：").strip() or current_name
    old_provider = (values.get("LLM_PROVIDER") or "deepseek").strip().lower()
    print("接入方式：deepseek；compatible（千问等兼容接口）；openai（GPT）；anthropic（Claude）；gemini；ollama（本机）。")
    provider_hint = old_provider if old_provider in LLM_DEFAULTS else "需重新选择"
    provider = input(f"模型接入方式 [{provider_hint}]：").strip().lower() or old_provider
    if provider not in LLM_DEFAULTS:
        print("接入方式无效，请选择上方列出的名称；本次未写入配置。")
        return 2
    default_url, default_model = LLM_DEFAULTS[provider]
    same_provider = provider == old_provider
    current_url = (values.get("LLM_BASE_URL") if same_provider else "") or default_url
    current_model = (values.get("LLM_MODEL") if same_provider else "") or default_model
    current_key = (values.get("LLM_API_KEY") if same_provider else "") or ""
    if provider == "deepseek" and same_provider:
        current_model = values.get("LLM_MODEL") or values.get("DEEPSEEK_MODEL") or default_model
        if current_url.rstrip("/") in DEEPSEEK_URLS:
            current_key = current_key or values.get("DEEPSEEK_API_KEY") or ""
    base_url = input("API 地址（留空保留或使用该接入方式的默认地址；已有地址不回显）：").strip() or current_url
    model_name = input("模型名称（留空保留或使用该接入方式的默认模型；已有名称不回显）：").strip() or current_model
    endpoint_changed = base_url.rstrip("/") != current_url.rstrip("/")
    if endpoint_changed:
        current_key = ""
        print("API 地址已改变，请填写对应服务的密钥；不沿用旧地址的密钥。")
    key_hint = "已保存，留空保留" if current_key else "可稍后填写；本机 Ollama 可留空"
    api_key = getpass(f"当前模型服务 API Key（{key_hint}）：").strip() or current_key
    values.update(LLM_PROVIDER=provider, LLM_BASE_URL=base_url, LLM_MODEL=model_name, LLM_API_KEY=api_key)
    # 将旧 DeepSeek 配置迁移为当前服务的通用配置，清空密钥时不会又回退到旧变量。
    values.pop("DEEPSEEK_API_KEY", None)
    values.pop("DEEPSEEK_MODEL", None)
    if not same_provider or endpoint_changed:
        # 专用请求参数不能自动带到另一个协议/平台。
        values.pop("LLM_EXTRA_BODY", None)
        values.pop("LLM_TOKEN_PARAM", None)
    try:
        Settings(llm_provider=provider, llm_base_url=base_url, llm_model=model_name, llm_api_key=api_key).resolve_llm()
    except ValueError:
        print("模型配置需要调整：请检查 API 地址、模型名称和接入方式；本次未写入配置。")
        return 2
    if not str(values.get("QQ_APP_ID", "")).isdigit() or not values.get("QQ_APP_SECRET"):
        print("QQ AppID 应为数字，AppSecret 不能为空；本次未写入配置。")
        return 2
    for name, default in (
        ("LLM_MAX_TOKENS", "2048"), ("LLM_EXTRA_BODY", "{}"),
        ("LLM_TOKEN_PARAM", "max_tokens"),
        ("HISTORY_TURNS", "6"), ("COOLDOWN_SECONDS", "3"), ("QQ_ALLOWED_GROUPS", ""),
    ):
        values.setdefault(name, default)
    text = "# 本机凭证配置，请勿提交到 Git 或上传到学习文档。\n"
    text += "\n".join(f"{name}={json.dumps(value or '', ensure_ascii=False)}" for name, value in values.items())
    path.write_text(text + "\n", encoding="utf-8")
    print("配置已保存到本项目 .env；没有打印任何密钥。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(configure())
    except (KeyboardInterrupt, EOFError):
        print("\n已取消配置。")
        raise SystemExit(1)
    except Exception:
        print("配置失败：请检查本机文件权限和依赖安装；错误详情已隐藏。")
        raise SystemExit(1)
