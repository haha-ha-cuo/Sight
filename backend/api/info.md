# API统一管理

`rss.py` 使用 Flask Blueprint 注册到 `main.py`。

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 应用健康检查，无需数据库 |
| `GET /api/rss/config` | 预设源、模型名称、provider 和 AI 是否可用；不返回密钥 |
| `POST /api/digests` | 同步采集并生成一次阅读清单，不保存结果 |
| `GET /api/health/db` | 原有可选数据库检查，原型不调用 |

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
