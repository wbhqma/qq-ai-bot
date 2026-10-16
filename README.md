# qq-ai-bot

基于 Python、NoneBot2 和 QQ 官方机器人接口的群聊 AI。群成员 @机器人时，调用所配置的模型回答，并记住该成员在该群的近期对话。默认名称为“哦鲸鲸”。

当前处于首版开发阶段：已提供多模型协议适配、离线测试与启动自检，真实 QQ 群收发和模型调用仍需用运行者自己的账号联调。

## 功能

- 只处理群内 @机器人的消息。
- 按“机器人 + 群 + 用户”隔离近期记忆，支持清空自己的对话。
- 同一事件去重，重复文字的新消息照常处理。
- 单人冷却、同一会话忙碌提示、最多 3 个并行模型请求。
- 模型超时和鉴权失败等情况返回简短提示；发送成功后才记录一轮对话。
- 本地配置向导，密钥输入不回显；离线自检不连接 QQ 或调用模型。
- 支持 DeepSeek、OpenAI Responses、Claude Messages、Gemini GenerateContent，以及 Chat Completions 兼容接口和本机 Ollama。

## 准备

1. 安装 Python 3.11 或更高版本。当前兼容目标为 3.11–3.14，推荐使用 3.12 或 3.14。
2. 在 [QQ 开放平台](https://q.qq.com/)创建官方机器人，取得 AppID、AppSecret，并按控制台允许的范围加入测试群。账号认证状态、可加入的群及事件权限以控制台为准。
3. 准备所选模型服务的 API Key、API 地址和可调用的模型 ID；本机 Ollama 可不填密钥。云模型调用由运行者自己的账户付费。

机器人使用 WebSocket 主动连接平台。当前实现采用适配器的群 @事件模式；请先确认平台已授予相应能力。未在 QQ 登录器或其他协议端中接入个人 QQ 号。

以下命令均在**项目根目录**执行。下载源码 ZIP 并解压即可使用，不需要先配置 Git。

## Windows 快速启动

在项目目录打开 PowerShell：

```powershell
.\setup.ps1
.\start.ps1 -Check
.\start.ps1
```

首次正常启动会提示在本机填写 QQ 凭证、机器人名字、模型接入方式、API 地址、模型名称和对应密钥，保存到 `.env`。之后更换模型或凭证可运行：

```powershell
.\configure.ps1
```

安装脚本会寻找可运行的 Python。若没有找到，可显式指定已安装的解释器，再运行安装：

```powershell
$env:QQBOT_PYTHON = 'C:\path\to\python.exe'
.\setup.ps1
```

如果系统限制运行 PowerShell 脚本，也可直接使用下面的 Python 命令，虚拟环境的解释器路径改用 `.venv\Scripts\python.exe`。

## Linux / macOS，或手动安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python bot.py --check
.venv/bin/python configure.py
.venv/bin/python bot.py
```

停止机器人按 `Ctrl+C`。保持进程运行才能持续回复。

`requirements.txt` 固定直接依赖；`requirements.lock` 固定完整依赖版本，Windows 专用依赖带平台条件。它不包含下载源和哈希，更新依赖后需重新检查依赖关系与平台兼容性。

## 在群里试用

所有命令都需要先 @机器人：

| 消息 | 用途 |
| --- | --- |
| `@机器人 /ping` | 检查 QQ 收发，不调用模型 |
| `@机器人 你好，介绍一下自己` | 调用模型聊天 |
| `@机器人 我刚才问了什么` | 检查当前用户的近期记忆 |
| `@机器人 /清空` | 清空自己在当前群的记忆 |
| `@机器人 /帮助` | 查看帮助 |

先确认 `/ping` 能回复，再测试 AI。如果 `/ping` 也没有响应，先检查进程、平台凭证、群权限和事件模式。

## 配置

可以使用向导，也可以复制 `.env.example` 为 `.env` 后编辑。已设置的系统环境变量优先于 `.env`。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BOT_NAME` | `哦鲸鲸` | AI 自称的名字，可自定义；留空使用默认值 |
| `QQ_APP_ID` | 空 | 官方机器人 AppID，正常启动必填 |
| `QQ_APP_SECRET` | 空 | 官方机器人 AppSecret，正常启动必填 |
| `LLM_PROVIDER` | `deepseek` | `deepseek` / `compatible` / `openai` / `anthropic` / `gemini` / `ollama` |
| `LLM_BASE_URL` | 由接入方式决定 | API 根地址；`compatible` 必填，其余提供默认地址 |
| `LLM_MODEL` | DeepSeek 为 `deepseek-flash` | 其他接入方式必须填写账号可调用或本机已安装的模型 ID |
| `LLM_API_KEY` | 空 | 当前模型服务的密钥；本机 Ollama 可留空；不填云模型密钥仍可测试 `/ping` |
| `LLM_MAX_TOKENS` | `2048` | 模型输出预算，整数 16–32768；还需符合具体模型的上限 |
| `LLM_EXTRA_BODY` | `{}` | 可选的模型专用请求参数，JSON 对象，不能覆盖核心消息及输出上限 |
| `LLM_TOKEN_PARAM` | `max_tokens` | 仅 `compatible` 使用；可改成部分推理模型要求的 `max_completion_tokens` |
| `HISTORY_TURNS` | `6` | 保留完整对话轮数，整数 0–10，0 表示不保留 |
| `COOLDOWN_SECONDS` | `3` | 每个会话两次模型请求的间隔，0–60 秒 |
| `QQ_ALLOWED_GROUPS` | 空 | 允许的 `group_openid`，多个用英文逗号分隔；留空不额外限制 |

`group_openid` 是平台提供的标识，并非 QQ 群号。AI 默认叫“哦鲸鲸”，可在 `.env` 设置 `BOT_NAME=你喜欢的名字`，或运行配置向导修改；重启后生效。此项控制发给模型的名字，不会修改 QQ 平台资料卡昵称。性格设定在 `app/persona.py`。

记忆只保存在进程内，重启清空；超过一小时未使用的会话会在后续请求时清理，最多保留 256 个会话。每个会话同时受轮数和 12000 字符上限约束；字符数不是模型的 token 数。当前最多接收 1800 字符的提问，模型输出预算由 `LLM_MAX_TOKENS` 控制，发到群里的过长文本截短至约 1200 字符。部分模型的输出预算也包含推理 token，出现空回复时可结合平台返回状态调整预算。

## 选择模型服务

程序按协议接入，不以服务商白名单限制模型。当前配置一套模型服务，修改后重启生效。

| 服务 | `LLM_PROVIDER` | `LLM_BASE_URL` |
| --- | --- | --- |
| DeepSeek 官方 | `deepseek` | 默认 `https://api.deepseek.com` |
| OpenAI GPT 模型 | `openai` | 默认 `https://api.openai.com/v1`，使用 Responses API |
| Anthropic Claude | `anthropic` | 默认 `https://api.anthropic.com/v1`，使用 Messages API |
| Google Gemini | `gemini` | 默认 `https://generativelanguage.googleapis.com/v1beta`，使用 GenerateContent |
| 阿里云百炼千问等 | `compatible` | 按地域填写，例如 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 腾讯云 TokenHub | `compatible` | 按地域填写，例如 `https://tokenhub.tencentmaas.com/v1` |
| 本机 Ollama | `ollama` | 默认 `http://localhost:11434/v1` |
| 其他兼容网关或模型平台 | `compatible` | 填该服务的 Chat Completions API 根地址 |

各服务的 API Key、地域和模型 ID 必须配套，模型名称以该账号实际可调用列表为准。兼容接口的地址通常包含 `/v1`，程序追加 `/chat/completions`，也接受包含该后缀的完整地址；Claude 也接受服务根地址或完整 `/v1/messages` 地址。Gemini 填到 `/v1beta` 这一层，不填写带模型名的完整请求地址。

例如切换千问，在本机 `.env` 中填写：

```dotenv
LLM_PROVIDER=compatible
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
LLM_API_KEY=替换为同地域的百炼APIKey
```

该示例按量接口及模型需由账号开通；API 地址以自己的控制台为准。也可在向导选择 `openai`、`anthropic` 或 `gemini`，保留默认 API 地址，再输入对应模型 ID 和密钥。

ChatGPT 是应用，接入它对应的 GPT 模型使用 OpenAI API。WorkBuddy 也是应用；如持有它所使用的 TokenHub 等模型服务的 API 凭证，配置该服务的地址、模型和密钥。应用登录信息或订阅凭证不能当作本项目的通用模型 API 凭证。

模型专用参数可通过 `.env` 添加，例如千问模型支持时关闭思考：

```dotenv
LLM_EXTRA_BODY={"enable_thinking":false}
```

具体参数以所选模型文档为准。DeepSeek 默认发送关闭思考的参数，其他接入方式不会自动收到 DeepSeek 专用字段。额外参数不能覆盖 `model`、消息、人设、流式开关、存储开关或 token 上限；Gemini 的 `generationConfig` 可以补充参数，但输出上限仍以 `LLM_MAX_TOKENS` 为准。

原来的 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 仍可在 DeepSeek 官方地址下使用；新 `LLM_*` 值优先。运行配置向导保存后会迁移成通用字段。向导切换服务商或地址时不沿用旧密钥及模型专用参数，请重新填写对应服务的密钥。

当前实现面向非流式文本对话。图片、语音、工具调用、专用云平台鉴权等能力仍需相应适配；不能仅凭“有 API Key”保证任意接口直接可用。

协议依据：[OpenAI 文本生成](https://developers.openai.com/api/docs/guides/text)、[Claude Messages](https://platform.claude.com/docs/en/api/messages/create)、[Gemini GenerateContent](https://ai.google.dev/api/generate-content)、[百炼兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[腾讯 TokenHub](https://cloud.tencent.com/document/product/1823/130078)、[Ollama 兼容接口](https://docs.ollama.com/api/openai-compatibility)。接口和可用模型可能变化，联调时以当前官方文档与账号权限为准。

## 数据与凭证

用户的问题和该会话保留的近期内容会发送给所配置的模型服务。请让使用者了解这一点，并避免发送敏感信息。OpenAI 接入默认设置 `store=false`，其他平台的数据处理方式以其服务说明为准。

真实凭证仅写入本机 `.env`；`.env.example` 中的 AppID、密钥和群标识必须留空。配置向导不回显 AppID、密钥或已保存的名字、地址、模型名称，自检与配置对象的字符串表示也隐藏这些值。

运行日志只显示固定的诊断摘要，不输出聊天内容、账号/群标识、请求体、原始异常及含本机路径的堆栈。近期对话只保存在进程内存中，`/清空` 可清除当前用户在当前群的记录；重启后记录消失。用户主动发给机器人的问题与附带历史仍会发送到所选模型服务。

`.env`、密钥文件、聊天数据、日志、数据库和备份已加入 Git 忽略规则。发布前运行 `python scripts/check_privacy.py`；它会检查公开候选文件、示例配置和常见泄露模式，只报告文件位置，不打印匹配内容。扫描不能识别所有个人信息；手工打包、截图和复制文件仍需避开本机配置。凭证一旦暴露，应到对应平台重置，仅删除文件无法撤回已经泄露的凭证。

## 开发与检查

Windows：

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts/check_privacy.py
.\start.ps1 -Check
```

Linux / macOS 将解释器路径换成 `.venv/bin/python`。测试使用模拟模型和模拟 QQ 发送，不需要真实凭证，也不会发群消息或消耗模型额度。

仓库提供 GitHub Actions 配置，计划在 Ubuntu / Windows、Python 3.11 / 3.14 上运行同样的检查。工作流是否通过，以仓库实际运行结果为准。

```text
bot.py               启动、适配器注册、插件装配
configure.py         本机凭证向导
app/config.py        环境配置
app/chat.py          对话记忆、限流、去重
app/llm.py           多模型协议、请求与错误处理
app/deepseek.py      旧导入入口兼容
app/persona.py       机器人人设
app/privacy.py       终端日志隐私保护
scripts/check_privacy.py 公开文件隐私检查
plugins/qq_chat.py   QQ 群 @事件入口
tests/              离线行为测试
```

扩展插件与贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。框架和适配器的用法以 [NoneBot 文档](https://nonebot.dev/docs/)及 [QQ 适配器文档](https://github.com/nonebot/adapter-qq)为准。

## 后续方向

- 首先完成真实群内收发、连续聊天和重启恢复的人工验证。
- 增加一个独立的小插件，例如掷骰子或签到，再完善插件加载与配置。
- 根据实际使用情况增加可配置的人设、更多模型专用能力或持久记忆。

## 许可证

项目采用 [MIT License](LICENSE)。NoneBot2、QQ 适配器及其他依赖保留各自的许可证；QQ 平台和模型服务的使用条件由对应服务商规定。
