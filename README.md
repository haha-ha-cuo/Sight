# Sight

Vue 3 + Vite 前端与 Python Flask 后端的基础项目。后端使用 uv 管理依赖和虚拟环境，通过 PyMySQL 连接 MySQL。

## 目录结构

```text
Sight/
├── frontend/                 # Vue 3 + Vite（JavaScript）
│   ├── src/                  # 页面、组件和样式
│   ├── vite.config.js        # 开发服务器及 /api 代理
│   ├── package.json
│   └── package-lock.json     # 前端依赖锁文件
├── backend/
│   ├── main.py               # Flask 入口和健康检查接口
│   ├── db.py                 # MySQL 连接方法
│   ├── .env.example          # 本地环境变量示例
│   ├── .python-version       # 默认 Python 3.12
│   ├── pyproject.toml        # Python 项目和依赖声明
│   ├── uv.lock               # Python 依赖锁文件
│   └── .venv/                # uv 创建的虚拟环境，不提交版本控制
└── docs/                     # 项目文档
```

## 环境要求

- Node.js 22.12+（或 20.19+）及 npm。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)。项目默认使用 Python 3.12；本机没有对应解释器时，uv 可自动下载。
- MySQL 服务（建议 8.x）；仅启动应用和访问 `/api/health` 不需要数据库。

## 启动后端

在项目根目录打开终端：

```bash
cd backend
uv sync --locked
cp .env.example .env
```

编辑 `backend/.env`，填写自己的 MySQL 用户名、密码等信息，然后启动开发服务器：

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

## 启动前端

另开一个终端，在项目根目录执行：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://localhost:5173>。首页会自动检查后端连接，也可以点击按钮重新检查。

开发时，Vite 将 `/api` 请求代理到 `http://127.0.0.1:5001`。修改后端端口时，需要同步修改 `frontend/vite.config.js` 中的代理地址。

## MySQL 配置与验证

使用已有 MySQL 账号登录，创建数据库：

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

连接成功返回 HTTP 200 和 `status: "ok"`；数据库不可用或配置错误时，数据库检查返回 HTTP 503。该项目只提供连接示例，尚未创建业务数据表。

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
```

Vite 的 `/api` 代理仅用于开发服务器。部署 `frontend/dist` 或使用 `npm run preview` 时，需要另行配置 `/api` 到 Flask 的反向代理。请提交 `package-lock.json` 和 `uv.lock`，不要提交 `.venv`、`node_modules` 或包含真实密码的 `.env`。

初始化方式参考 [Vite 文档](https://vite.dev/guide/)、[uv 项目管理文档](https://docs.astral.sh/uv/guides/projects/) 和 [PyMySQL 安装说明](https://pymysql.readthedocs.io/en/latest/user/installation.html)。
