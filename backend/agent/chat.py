"""按会话配置快照构建 Agent；只重放普通文本消息，不恢复可执行工具状态。"""

import asyncio

from agentscope.agent import Agent, ReActConfig
from agentscope.message import Msg, TextBlock

from agent.config import create_model


async def reply_to_conversation(
    config: dict, profile: dict, history: list[dict], content: str
) -> str:
    settings = {**config, "SIGHT_PROVIDER": profile["provider"], "SIGHT_MODEL": profile["model"]}
    agent = Agent(
        name="SightChat",
        system_prompt=profile["system_prompt"],
        model=create_model(settings),
        react_config=ReActConfig(max_iters=2, interruption_raise_cancelled_error=True),
    )
    messages = [
        Msg(name=item["role"], role=item["role"], content=[TextBlock(text=item["content"])])
        for item in [*history, {"role": "user", "content": content}]
    ]
    async with asyncio.timeout(90):
        response = await agent.reply(messages)
    text = response.get_text_content()
    if response.error or not text or not text.strip():
        raise ValueError("模型未返回有效文本")
    return text.strip()[:16000]
