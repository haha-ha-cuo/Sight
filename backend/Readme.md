# 构想

## 第一阶段

用rss建立快速模型，整体流程如下：<br>

1、先编写agent，包含agent配置以及tools，实现对rss摘要抓取

2、编写后端路由

3、前端简单设计加展示

## 已实现的第一阶段原型

- `agent/tools.py`：HTTP 采集 RSS/Atom、纯文本清理、链接去重与 `FunctionTool` 只读工具。
- `agent/models.py`：请求内的文章对象和 AI 摘要结构，不映射数据库表。
- `agent/config.py`：AgentScope **2.x** `Agent` 工厂；通过 `SIGHT_PROVIDER` 选择 DeepSeek 官方或百炼。
- `agent/service.py`：并发采集、部分失败处理、可选 AI 摘要；每次请求创建独立 Agent，不持久化会话。
- `api/rss.py`：统一 Blueprint。Vue 页面提供源选择、自定义地址、搜索和 Markdown 导出。

### 本地启动

```bash
cd backend
uv sync --locked
cp .env.example .env  # 首次运行时复制，不要覆盖已有密钥配置
uv run flask --app main run --debug --host 127.0.0.1 --port 5001
```

另一个终端运行 `cd frontend && npm ci && npm run dev`，访问 <http://localhost:5173>。

不配置模型密钥时也能抓取 RSS 自带摘要。默认使用 DeepSeek 官方直连：

```dotenv
SIGHT_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的密钥
SIGHT_MODEL=deepseek-flash
```

百炼可设为 `SIGHT_PROVIDER=dashscope`、`DASHSCOPE_API_KEY=你的百炼密钥`、`SIGHT_MODEL=qwen-plus`。两个服务使用各自的 Credential 与 ChatModel，不会因修改模型名就自动切换接口。配置变更后重启后端。

### 格式化与审查

```bash
uv run ruff format .          # 格式化
uv run ruff format --check .  # 检查格式，不修改文件
uv run ruff check .           # 静态检查
uv run python -m unittest discover -s tests -v
make check                   # 格式检查 + Ruff + 全部测试
```

Ruff 规则在 `pyproject.toml`，覆盖基础错误、未使用导入、导入排序、Python 现代语法及常见缺陷。测试不连接数据库或外部模型；AgentScope 工具循环测试仅替换模型响应。

### 当前边界

- 不实现数据库录入、源配置保存、任务历史或定时调度；刷新页面后结果清空。原有数据库健康检查仍是可选的独立接口。
- 单次最多 5 个订阅地址，最终最多展示 20 篇。按源顺序读取，按规范化原文链接去重；没有语义去重或评分筛选。
- 只处理订阅标题和摘要，不抓取文章全文；AI 失败时保留订阅摘要并返回警告。
- 仅用于本机开发，默认绑定 `127.0.0.1`。采集请求限制响应大小、超时和重定向次数，拒绝本机与内网目标；兼容透明代理的 Fake-IP DNS。不是可直接公开部署的抓取代理。
- “查看示例”使用 `agent/demo.xml` 的内置演示条目，不代表实时新闻。

接口示例见 [api/info.md](api/info.md)。模型适配依据 [AgentScope 2.x 文档](https://docs.agentscope.io/latest/en/building-blocks/agent/overview) 和 [DeepSeek 官方接口说明](https://api-docs.deepseek.com/quick_start/agent_integrations/)。
