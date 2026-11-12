# 构想

## 第一阶段

用rss建立快速模型，整体流程如下：<br>

1、先编写agent，包含agent配置以及tools，实现对rss摘要抓取

2、编写后端路由

3、前端简单设计加展示

## 已实现的原型

- `agent/tools.py`：HTTP 采集 RSS/Atom、纯文本清理、链接去重与 `FunctionTool` 只读工具。
- `agent/models.py`：RSS 请求内的文章对象和 AI 摘要结构。
- `agent/config.py`：AgentScope **2.x** `Agent` 工厂；通过 `SIGHT_PROVIDER` 选择 DeepSeek 官方或百炼。
- `agent/service.py`：并发采集、部分失败处理、可选 AI 摘要；每次请求创建独立 Agent。`agent/chat.py` 根据保存的普通文本历史恢复对话上下文。
- `api/rss.py`、`api/accounts.py`、`api/workspace.py`：RSS、注册登录和个人工作台接口。
- `database/models.py`、`database/store.py`：对象模型、MySQL 存储与初始化；根目录脚本见 `scripts/init_db.py`。

### 本地启动

```bash
cd backend
uv sync --locked
cp -n .env.example .env  # 首次配置，不覆盖已有文件
# 配好 MySQL 后创建数据库与表
uv run python ../scripts/init_db.py
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

Ruff 规则在 `pyproject.toml`，覆盖基础错误、未使用导入、导入排序、Python 现代语法及常见缺陷。测试使用隔离 SQLite 库，不连接本机 MySQL 或外部模型；AgentScope 工具循环测试仅替换模型响应。

### 当前边界

- 已加入注册登录、Agent 管理、对话历史、订阅与阅读记录保存。未登录时仍可匿名阅读，但不保存结果。
- 暂不实现密码重置、邮件验证和定时任务；仅用于本地原型。
- 单次最多 5 个订阅地址，最终最多展示 20 篇。按源顺序读取，按规范化原文链接去重；没有语义去重或评分筛选。
- 只处理订阅标题和摘要，不抓取文章全文；AI 失败时保留订阅摘要并返回警告。
- 仅用于本机开发，默认绑定 `127.0.0.1`。采集请求限制响应大小、超时和重定向次数，拒绝本机与内网目标；兼容透明代理的 Fake-IP DNS。不是可直接公开部署的抓取代理。
- “查看示例”使用 `agent/demo.xml` 的内置演示条目，不代表实时新闻。

接口示例见 [api/info.md](api/info.md)。模型适配依据 [AgentScope 2.x 文档](https://docs.agentscope.io/latest/en/building-blocks/agent/overview) 和 [DeepSeek 官方接口说明](https://api-docs.deepseek.com/quick_start/agent_integrations/)。

## 第二阶段演示

1. 点击右上角“登录 / 注册”，注册账号并获得默认资讯助手。
2. 在“Agent 管理”添加或编辑模型、名称与系统提示词。
3. 在“对话”选择 Agent 并新建会话，发送消息；刷新后从历史列表重新打开。
4. 在“RSS 阅读”保存订阅，选择阅读 Agent 并生成清单。
5. 在“阅读记录”重新打开历史清单并导出 Markdown。

建库建表见 [脚本说明](../scripts/README.md)，表结构与保存规则见 [数据库说明](database/info.md)。会话签名密钥默认生成到已忽略的 `instance/session.key`，重启后仍有效；可通过 `SIGHT_SECRET_KEY` 指定。`make check` 同时检查后端与 scripts 文件夹。
