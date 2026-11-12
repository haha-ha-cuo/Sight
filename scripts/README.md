# 数据库脚本

在项目根目录执行：

```bash
uv sync --project backend --locked
uv run --project backend python scripts/init_db.py
```

脚本读取 `backend/.env` 的 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD` 和 `MYSQL_DATABASE`，创建缺少的数据库和业务表，不清空已有数据。当前本地配置为 `root`、空密码。

亦可在 `backend/` 下执行 `uv run flask --app main init-db`。两种入口共用 `database/models.py` 中的对象模型。重复运行不会修改已有表结构；后续字段变更需另做迁移脚本。
