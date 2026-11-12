# API统一管理

`rss.py` 使用 Flask Blueprint 注册到 `main.py`。

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 应用健康检查，无需数据库 |
| `GET /api/rss/config` | 预设源、模型名称、provider 和 AI 是否可用；不返回密钥 |
| `POST /api/digests` | 生成阅读清单，登录后自动保存，匿名时不保存 |
| `GET /api/health/db` | MySQL 连接检查 |

```json
{
  "urls": ["https://sspai.com/feed"],
  "limit": 10,
  "mode": "feed",
  "demo": false
}
```

`urls` 最多 5 个，`limit` 是 1–20 的整数，`mode` 为 `feed`（订阅摘要）或 `ai`（AI 中文摘要）。`demo=true` 可省略 urls，使用内置示例；前端示例按钮固定使用 feed 模式。

返回 `generated_at`、实际 `mode`、`demo`、`overview`、`articles`、`sources`、`warnings`。文章包含 `id/title/url/source/published_at/feed_summary/summary/summary_kind`。时间为 UTC ISO 8601，页面按浏览器当地时区展示。

参数错误返回 400，全部源失败返回 502，所选模型服务未配置返回 503。部分源失败或模型失败时仍返回 200 和可用文章，同时附上 warnings。AI 失败后的实际 mode 为 feed。

```bash
curl http://127.0.0.1:5001/api/rss/config
curl -X POST http://127.0.0.1:5001/api/digests \
  -H 'Content-Type: application/json' \
  -d '{"demo":true,"limit":3}'
```

## 账号与个人工作台

| 方法 / 路径 | 用途 |
| --- | --- |
| `GET /api/auth/me` | 当前 user 与 csrf_token；未登录时 user 为 null |
| `POST /api/auth/register` | username / password，注册并自动登录 |
| `POST /api/auth/login` | 用户名密码登录 |
| `POST /api/auth/logout` | 注销登录 |
| `GET /api/agents` | 本人的 Agent 列表 |
| `POST /api/agents` | 新建 Agent：name / provider / model / system_prompt |
| `PUT /api/agents/{id}` | 修改本人的 Agent |
| `DELETE /api/agents/{id}` | 删除 Agent，保留原有会话配置快照 |
| `GET /api/conversations` | 本人最近 50 段对话 |
| `POST /api/conversations` | 根据 agent_id 创建会话 |
| `GET /api/conversations/{id}` | 会话及有序消息 |
| `POST /api/conversations/{id}/messages` | 提交 content，成功后保存本轮两条消息 |
| `DELETE /api/conversations/{id}` | 删除会话及消息 |
| `GET /api/sources` | 本人的订阅列表 |
| `POST /api/sources` | 保存 name / url，重复地址返回 409 |
| `DELETE /api/sources/{id}` | 删除本人订阅 |
| `GET /api/digests` | 本人最近 50 份阅读记录 |
| `GET /api/digests/{id}` | 读取完整清单 |
| `DELETE /api/digests/{id}` | 删除阅读记录 |

私有接口需登录，其他用户的记录 ID 返回 404。认证与私有写接口需先调用 `/api/auth/me` 获取 token，再通过 `X-CSRF-Token` 头提交；登录和注销会轮换 token。用户名为 3–32 位字母、数字或下划线并统一转小写；密码为 8–128 字符。接口不返回密码哈希或模型密钥。

登录后 `POST /api/digests` 可附 `agent_id`，使用本人的 Agent 模型和阅读偏好；返回结果增加持久化记录的 `id`。数据库写入失败返回 503，不将未保存的结果标记为已保存。聊天模型失败返回 503 且不保存本轮消息；并发会话更新返回 409。
