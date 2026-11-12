# Sight

Vue 3 + Vite 前端与 Python Flask 后端的 RSS 资讯原型。后端使用 uv 管理依赖，通过 AgentScope 2.x 调用 DeepSeek 生成中文摘要。

当前已支持 RSS/Atom 采集、链接去重、订阅摘要／AI 摘要、页面搜索与 Markdown 导出。现已加入注册登录、个人 Agent 配置、对话历史、RSS 订阅和阅读记录，登录后的业务数据存入 MySQL。匿名阅读仍可使用，不保存结果。

## 目录结构

```text
Sight/
├── frontend/                 # Vue 3 + Vite（JavaScript）
│   ├── src/                  # 页面、组件和样式
│   ├── vite.config.js        # 开发服务器及 /api 代理
│   ├── package.json
│   └── package-lock.json     # 前端依赖锁文件
├── backend/
│   ├── main.py               # Flask 入口、配置及健康检查接口
│   ├── agent/                # AgentScope 2.x 配置、采集工具、对象模型和编排
│   ├── api/rss.py            # RSS 配置与摘要接口
│   ├── tests/                # RSS、API 与 Agent 工具调用测试
│   ├── Makefile              # format / lint / test / check
│   ├── database/             # 业务对象模型与 SQLAlchemy 存储
│   ├── db.py                 # MySQL 健康检查连接方法
│   ├── .env.example          # 本地环境变量示例
│   ├── .python-version       # 默认 Python 3.12
│   ├── pyproject.toml        # Python 项目和依赖声明
│   ├── uv.lock               # Python 依赖锁文件
│   └── .venv/                # uv 创建的虚拟环境，不提交版本控制
├── scripts/                  # 数据库初始化脚本
└── docs/                     # 项目文档
```

## 环境要求

- Node.js 22.12+（或 20.19+）及 npm。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)。项目默认使用 Python 3.12；本机没有对应解释器时，uv 可自动下载。
- MySQL：账号及个人数据功能需要数据库；匿名 RSS 阅读仍可独立使用。

## 启动后端

在项目根目录打开终端：

```bash
cd backend
uv sync --locked
cp -n .env.example .env
# 配置 MySQL 后创建数据库和表
uv run python ../scripts/init_db.py
```

默认使用订阅摘要，可直接启动。启用 DeepSeek AI 中文摘要时，在 `backend/.env` 中配置：

```dotenv
SIGHT_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的DeepSeek密钥
SIGHT_MODEL=deepseek-flash
```

密钥仅由后端读取。修改配置后重启后端。然后启动开发服务器：

```bash
uv run flask --app main run --debug --host 127.0.0.1 --port 5001
```

后端地址：<http://127.0.0.1:5001>。使用 5001 端口，避免 macOS 上常见的 5000 端口占用。开发服务器和调试模式仅用于本地开发。

`uv sync` 会在 `backend/.venv` 中安装锁定的依赖，`uv run` 会自动使用该环境，无需手动激活。需要在终端或 IDE 中直接使用时：

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell（复制配置使用 Copy-Item .env.example .env）
.venv\Scripts\Activate.ps1
```

已包含以下 Python 依赖：

| 依赖 | 用途 |
| --- | --- |
| Flask | Web 框架及 API 服务 |
| PyMySQL[rsa] | MySQL 驱动，包含 MySQL 8 常用认证方式所需的加密依赖 |
| python-dotenv | 加载 `backend/.env` 配置 |
| AgentScope 2.x | 使用 `Agent`、`FunctionTool`、`Toolkit` 与结构化输出组织摘要流程 |
| feedparser / httpx | 解析 RSS/Atom 与请求信息源 |
| Ruff（开发依赖） | Python 格式化及静态检查 |

## 启动前端

另开一个终端，在项目根目录执行：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://localhost:5173>。选择信息源，点击“生成阅读清单”；也可点击“查看示例”，无需外部网络或模型密钥即可体验页面。示例是内置演示数据，页面会明确标识。

AI 摘要基于订阅中提供的标题和摘要，不抓取文章全文；失败时提示并回退到订阅摘要。接口和实现范围见 [后端说明](backend/Readme.md)。

开发时，Vite 将 `/api` 请求代理到 `http://127.0.0.1:5001`。修改后端端口时，需要同步修改 `frontend/vite.config.js` 中的代理地址。

## MySQL 配置与初始化

先设置 `backend/.env` 中的 MySQL 配置。当前本地使用 root、空密码。推荐在项目根目录通过脚本建库建表：

```bash
uv run --project backend python scripts/init_db.py
```

脚本可重复执行，创建缺少的数据库和 6 张业务表，保留已有数据。详见 [脚本说明](scripts/README.md) 与 [对象模型说明](backend/database/info.md)。如需手动建库，可使用：

```bash
mysql -u root -p
```

```sql
CREATE DATABASE IF NOT EXISTS sight
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

将 `backend/.env` 中的 `MYSQL_DATABASE` 设置为 `sight`，其他配置与实际 MySQL 服务保持一致。密码包含 `#` 等特殊字符时，请用引号包裹环境变量值。配置修改后重启后端。

```bash
# 应用健康检查：无需 MySQL
curl http://127.0.0.1:5001/api/health

# 数据库健康检查：连接配置的数据库并执行 SELECT 1
curl http://127.0.0.1:5001/api/health/db
```

连接成功返回 HTTP 200 和 `status: "ok"`；数据库不可用或配置错误时，数据库检查返回 HTTP 503。业务表包括 users、agent_profiles、conversations、messages、rss_sources 和 digest_records。

## 常用命令

```bash
# frontend/ 下执行：构建与本地预览
npm run build
npm run preview

# backend/ 下执行：增删依赖并同步虚拟环境、更新 uv.lock
uv add 包名
uv remove 包名

# backend/ 下执行：验证 Flask 和 MySQL 驱动可导入
uv run python -c "import flask, pymysql; print('依赖安装正常')"

# backend/ 下执行：格式化、静态检查、测试
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv run python -m unittest discover -s tests -v

# macOS / Linux 也可在 backend/ 下一次完成上述只读检查
make check
```

Vite 的 `/api` 代理仅用于开发服务器。部署 `frontend/dist` 或使用 `npm run preview` 时，需要另行配置 `/api` 到 Flask 的反向代理。请提交 `package-lock.json` 和 `uv.lock`，不要提交 `.venv`、`node_modules` 或包含真实密码的 `.env`。

初始化方式参考 [Vite 文档](https://vite.dev/guide/)、[uv 项目管理文档](https://docs.astral.sh/uv/guides/projects/) 和 [PyMySQL 安装说明](https://pymysql.readthedocs.io/en/latest/user/installation.html)。

## 个人工作台

右上角注册或登录后，可管理自己的 Agent、发起对话并恢复历史、保存 RSS 订阅，以及重新打开生成过的阅读清单。注册会创建默认资讯助手；模型密钥仍使用后端配置。密码仅保存哈希值，用户之间的数据隔离。当前为本机运行原型，暂不包含密码找回、邮件验证或定时调度。
