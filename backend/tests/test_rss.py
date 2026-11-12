import json
import socket
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from agentscope.message import ToolCallBlock, ToolResultBlock
from agentscope.model import ChatResponse, DeepSeekChatModel

from agent.config import create_rss_agent
from agent.service import generate_digest
from agent.tools import FeedError, _require_public_host, fetch_feed, normalize_url, parse_feed
from main import create_app

DEMO = Path(__file__).parents[1].joinpath("agent/demo.xml").read_bytes()
CONFIG = {
    "SIGHT_PROVIDER": "deepseek",
    "SIGHT_MODEL": "deepseek-flash",
    "DEEPSEEK_API_KEY": "test-not-a-real-key",
    "DASHSCOPE_API_KEY": "",
}
ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
<entry><title>Article</title><id>urn:1</id><link href="https://example.com/one#top"/>
<updated>2026-11-12T00:00:00Z</updated>
<summary type="html">&lt;p&gt;Hello &amp;amp; world&lt;/p&gt;</summary></entry>
<entry><title>Duplicate</title><link href="https://example.com/one"/></entry>
<entry><title>Unsafe</title><link href="javascript:alert(1)"/></entry></feed>"""


class ParserTests(unittest.TestCase):
    def test_rss_and_limit(self):
        name, articles = parse_feed(DEMO, "https://example.com/", 2)
        self.assertIn("示例", name)
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].summary_kind, "feed")

    def test_atom_sanitizing_dates_and_deduplication(self):
        name, articles = parse_feed(ATOM, "https://example.com/feed", 20)
        self.assertEqual(name, "Atom")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].summary, "Hello & world")
        self.assertEqual(articles[0].url, "https://example.com/one")
        self.assertEqual(articles[0].published_at, "2026-11-12T00:00:00+00:00")

    def test_invalid_feed_and_entities(self):
        for content in [b"<html>not a feed</html>", b"<!DOCTYPE rss><rss/>", b"<rss>"]:
            with self.subTest(content=content), self.assertRaises(FeedError):
                parse_feed(content, "https://example.com/", 10)

    def test_url_validation(self):
        for url in [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "https://x:invalid/",
            "https://user:pass@example.com/",
            "https://x:5000/",
            "https://x/\n",
        ]:
            with self.subTest(url=url), self.assertRaises(FeedError):
                normalize_url(url)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_and_proxy_dns(self):
        for url, ip, allowed in [
            ("http://localhost/", "127.0.0.1", False),
            ("http://example.com/", "10.0.0.1", False),
            ("http://example.com/", "198.18.0.20", True),
            ("http://198.18.0.20/", "198.18.0.20", False),
            ("https://example.com/", "93.184.215.14", True),
        ]:
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]
            with (
                self.subTest(url=url, ip=ip),
                patch("agent.tools.socket.getaddrinfo", return_value=addresses),
            ):
                if allowed:
                    await _require_public_host(url)
                else:
                    with self.assertRaises(FeedError):
                        await _require_public_host(url)

    async def test_fetch_redirect_and_public_host_check(self):
        def handler(request):
            if request.url.path == "/":
                return httpx.Response(302, headers={"location": "/feed"})
            return httpx.Response(200, content=DEMO)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with (
            patch("agent.tools.httpx.AsyncClient", return_value=client),
            patch("agent.tools._require_public_host", new_callable=AsyncMock) as check,
        ):
            _, articles = await fetch_feed("https://example.com/", 2)
        self.assertEqual(len(articles), 2)
        self.assertEqual(check.await_count, 2)

    async def test_fetch_size_limit(self):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 1025))
        )
        with (
            patch("agent.tools.httpx.AsyncClient", return_value=client),
            patch("agent.tools._require_public_host", new_callable=AsyncMock),
            patch("agent.tools.MAX_FEED_BYTES", 1024),
        ):
            with self.assertRaisesRegex(FeedError, "2 MB"):
                await fetch_feed("https://example.com/", 1)

    async def test_partial_failure_and_cross_source_deduplication(self):
        parsed = parse_feed(DEMO, "https://example.com/", 3)
        with patch(
            "agent.service.fetch_feed",
            new=AsyncMock(side_effect=[parsed, parsed, FeedError("超时")]),
        ):
            result = await generate_digest(
                ["https://a.com/", "https://b.com/", "https://c.com/"], 20, "feed", False, CONFIG
            )
        self.assertEqual(len(result["articles"]), 3)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["sources"][2]["status"], "error")

    async def test_all_sources_failed(self):
        with patch("agent.service.fetch_feed", new=AsyncMock(side_effect=FeedError("超时"))):
            with self.assertRaises(FeedError):
                await generate_digest(["https://example.com/"], 10, "feed", False, CONFIG)

    async def test_empty_feed_skips_model(self):
        with (
            patch("agent.service.fetch_feed", new=AsyncMock(return_value=("Empty", []))),
            patch("agent.service.create_rss_agent") as factory,
        ):
            result = await generate_digest(["https://example.com/"], 10, "ai", False, CONFIG)
        self.assertEqual(result["articles"], [])
        factory.assert_not_called()

    async def test_model_failure_keeps_feed_summaries(self):
        with patch("agent.service.create_rss_agent", side_effect=RuntimeError("provider failed")):
            result = await generate_digest([], 1, "ai", True, CONFIG)
        self.assertEqual(result["mode"], "feed")
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["articles"][0]["summary_kind"], "feed")

    async def test_invalid_model_article_ids_fall_back(self):
        agent = AsyncMock()
        agent.reply.return_value.structured_output = {
            "overview": "overview",
            "articles": [{"article_id": "invented", "summary": "summary"}],
        }
        with patch("agent.service.create_rss_agent", return_value=agent):
            result = await generate_digest([], 1, "ai", True, CONFIG)
        self.assertEqual(result["mode"], "feed")
        self.assertTrue(result["warnings"])

    async def test_real_agentscope_2_tool_and_structured_output_loop(self):
        _, articles = parse_feed(DEMO, "https://example.com/", 1)
        agent = create_rss_agent(CONFIG, articles)
        self.assertIsInstance(agent.model, DeepSeekChatModel)
        self.assertEqual(agent.model.credential.base_url, "https://api.deepseek.com")
        received_data = []

        async def fake_api(model_name, messages, **kwargs):
            # 只替换外部模型响应，真正运行 Agent、权限、工具和结构化输出。
            tool_results = [
                block
                for msg in messages
                for block in msg.content
                if isinstance(block, ToolResultBlock) and block.name == "read_rss_articles"
            ]
            if not tool_results:
                block = ToolCallBlock(id="read-1", name="read_rss_articles", input="{}")
            else:
                received_data.extend(tool_results)
                block = ToolCallBlock(
                    id="summary-1",
                    name="GenerateStructuredOutput",
                    input=json.dumps(
                        {
                            "overview": "本次关注 RSS 原型。",
                            "articles": [
                                {
                                    "article_id": articles[0].id,
                                    "summary": "通过 RSS 验证采集与展示链路。",
                                }
                            ],
                        }
                    ),
                )
            return ChatResponse(content=[block], is_last=True)

        with (
            patch.object(agent.model, "_call_api", side_effect=fake_api),
            patch("agent.service.create_rss_agent", return_value=agent),
        ):
            result = await generate_digest([], 1, "ai", True, CONFIG)
        self.assertTrue(received_data)
        self.assertEqual(result["mode"], "ai")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["articles"][0]["summary"], "通过 RSS 验证采集与展示链路。")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            SIGHT_PROVIDER="deepseek",
            SIGHT_MODEL="deepseek-flash",
            DEEPSEEK_API_KEY="",
            DASHSCOPE_API_KEY="",
        )
        self.client = self.app.test_client()
        db = patch("main.get_connection", side_effect=AssertionError("RSS 原型不得访问数据库"))
        db.start()
        self.addCleanup(db.stop)

    def test_demo_and_health_without_database(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        response = self.client.post("/api/digests", json={"demo": True, "limit": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["articles"]), 2)
        self.assertTrue(response.json["demo"])

    def test_config_never_exposes_keys(self):
        self.app.config["DEEPSEEK_API_KEY"] = "private-test-key"
        response = self.client.get("/api/rss/config")
        self.assertTrue(response.json["ai_available"])
        self.assertNotIn("private-test-key", response.get_data(as_text=True))
        self.app.config["SIGHT_PROVIDER"] = "dashscope"
        self.assertFalse(self.client.get("/api/rss/config").json["ai_available"])

    def test_invalid_request_shapes(self):
        for payload in [
            [],
            {},
            {"demo": "true"},
            {"demo": True, "mode": []},
            {"demo": True, "limit": True},
            {"demo": True, "limit": 21},
            {"urls": "https://example.com"},
            {"urls": [1]},
            {"urls": ["file:///test"]},
            {"urls": ["https://example.com"] * 6},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/digests", json=payload).status_code, 400)

    def test_malformed_json(self):
        response = self.client.post("/api/digests", data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/api/digests", data="abc").status_code, 400)

    def test_ai_requires_selected_provider_key(self):
        self.app.config["DASHSCOPE_API_KEY"] = "unrelated-provider-key"
        response = self.client.post("/api/digests", json={"demo": True, "mode": "ai"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("DEEPSEEK_API_KEY", response.json["message"])

    def test_feed_failure_is_502(self):
        with patch("agent.service.fetch_feed", new=AsyncMock(side_effect=FeedError("失败"))):
            response = self.client.post("/api/digests", json={"urls": ["https://example.com/"]})
        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
