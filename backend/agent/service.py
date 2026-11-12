"""请求内编排：采集 → URL 去重 → 可选 AI 摘要 → 返回。"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from agentscope.message import Msg, TextBlock

from agent.config import create_rss_agent
from agent.models import DigestSummary
from agent.tools import FeedError, fetch_feed, parse_feed

logger = logging.getLogger(__name__)


async def generate_digest(urls: list[str], limit: int, mode: str, demo: bool, config: dict) -> dict:
    sources, articles, warnings = [], [], []
    if demo:
        name, collected = parse_feed(
            Path(__file__).with_name("demo.xml").read_bytes(), "https://example.com/", limit
        )
        batches = [("demo", (name, collected))]
    else:
        results = await asyncio.gather(
            *(fetch_feed(url, limit) for url in urls), return_exceptions=True
        )
        batches = list(zip(urls, results, strict=True))
    seen = set()
    for url, result in batches:
        if isinstance(result, Exception):
            if not isinstance(result, FeedError):
                logger.error("Unexpected RSS error", exc_info=result)
            message = str(result) if isinstance(result, FeedError) else "信息源处理失败"
            sources.append({"url": url, "status": "error", "message": message, "count": 0})
            warnings.append(f"{url}：{message}")
            continue
        name, collected = result
        sources.append({"url": url, "name": name, "status": "ok", "count": len(collected)})
        for article in collected:
            if article.url not in seen:
                seen.add(article.url)
                articles.append(article)
    if not any(source["status"] == "ok" for source in sources):
        raise FeedError("所有信息源均抓取失败。" + "；".join(warnings))
    articles = articles[:limit]
    overview = f"本次读取 {len(sources)} 个信息源，去重后展示 {len(articles)} 条内容。"
    actual_mode = "feed"
    if mode == "ai" and articles:
        try:
            agent = create_rss_agent(config, articles)
            async with asyncio.timeout(90):
                reply = await agent.reply(
                    Msg(
                        name="user",
                        role="user",
                        content=[TextBlock(text="请读取本次 RSS 文章并生成中文摘要。")],
                    ),
                    structured_schema=DigestSummary,
                )
            summary = DigestSummary.model_validate(reply.structured_output)
            by_id = {item.article_id: item.summary.strip() for item in summary.articles}
            if (
                len(by_id) != len(summary.articles)
                or set(by_id) != {article.id for article in articles}
                or not all(by_id.values())
                or not summary.overview.strip()
            ):
                raise ValueError("摘要文章 ID 不匹配或内容为空")
            for article in articles:
                article.summary = by_id[article.id]
                article.summary_kind = "ai"
            overview = summary.overview
            actual_mode = "ai"
        except Exception:
            # 不向页面暴露服务商响应或密钥；仍保留已成功采集的内容。
            logger.warning("AI summary failed; returning feed summaries")
            warnings.append("AI 摘要暂不可用，已展示原始订阅摘要，请检查模型配置或稍后重试。")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": actual_mode,
        "demo": demo,
        "overview": overview,
        "articles": [article.to_dict() for article in articles],
        "sources": sources,
        "warnings": warnings,
    }
