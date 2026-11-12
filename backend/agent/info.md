# 新闻平台内部的AGENT架构
用阿里的agentscope

原型使用 AgentScope **2.x**，依赖锁文件当前锁定 `2.0.11`。

`config.py` 按 provider 创建 `DeepSeekCredential + DeepSeekChatModel` 或 `DashScopeCredential + DashScopeChatModel`，随后创建 `Agent(system_prompt=..., toolkit=Toolkit(tools=[FunctionTool(...)]))`。

采集在 `tools.py` 完成；`read_rss_articles` 工具仅返回本次请求已采集的文章，不能请求模型自行指定的 URL。`service.py` 调用 `agent.reply(..., structured_schema=DigestSummary)`，读取 `reply.structured_output`，校验文章 ID 集合后将摘要合并回原始文章；标题、链接和来源始终使用采集结果。

每个请求创建独立的 Agent 状态，不接数据库或持久化存储。
