# 数据库

先建立对象模型，再使用

# 数据库要存哪些东西

1、用户用的agent信息
2、用户的对话记录
3、用户账号密码
4、Rss一些信息（待定）

## 第二阶段原型

使用 SQLAlchemy 对象模型与 MySQL，定义位于 `models.py`。

| 对象 / 表 | 内容 |
| --- | --- |
| `User` / `users` | 用户名、密码哈希、创建时间 |
| `AgentProfile` / `agent_profiles` | 用户所属 Agent 的名称、模型服务、模型和系统提示词 |
| `Conversation` / `conversations` | 用户所属会话、标题、Agent 配置快照、更新时间和并发版本号 |
| `Message` / `messages` | 对话内按顺序排列的用户消息和助手回复 |
| `RssSource` / `rss_sources` | 用户保存的订阅名称、URL 和 URL 去重哈希 |
| `DigestRecord` / `digest_records` | 阅读清单及完整 JSON 结果，包含文章、摘要和来源 |

一名用户可以拥有多个 Agent、会话、订阅和阅读记录；一段会话包含多条消息。所有私有接口按登录用户过滤，其他用户的记录返回 404。

### 建库建表

在 `backend/.env` 配置 MySQL；当前本地使用 root、空密码。项目根目录运行：

```bash
uv run --project backend python scripts/init_db.py
```

脚本创建缺少的数据库和 6 张业务表，重复执行保留已有数据。也可在 backend 下执行 `uv run flask --app main init-db`。两种入口共用对象模型，不自动修改已有表结构；后续字段变更需添加迁移脚本。

### 保存规则

- 密码仅保存 Werkzeug 生成的哈希；模型密钥仍留在后端 `.env`，不进入用户配置表。
- 注册后创建默认资讯助手；签名 Cookie 保存登录状态，写操作校验 CSRF Token。
- 新对话保留 Agent 配置快照；编辑或删除 Agent 后，旧会话仍使用原配置。
- 模型成功回复后，一次事务保存本轮用户消息和助手回复；失败不保存半轮对话。并发版本冲突返回 409。
- 每次推理最多带入最近 20 条普通文本消息，并限制历史字符总量；不恢复数据库中的工具执行状态。
- 登录后生成的阅读清单自动保存；示例也会保存并标注。匿名阅读可继续使用，但不保存。
- 对话和阅读记录列表显示最近 50 条。
- 自动化测试使用隔离 SQLite 库验证持久化、权限与事务；实际开发使用 MySQL。
