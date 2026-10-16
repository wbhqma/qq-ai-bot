"""保留旧导入入口；新代码使用 app.llm 的通用客户端。"""

from app.llm import LLMClient, ModelError

DeepSeekClient = LLMClient

__all__ = ["DeepSeekClient", "ModelError"]
