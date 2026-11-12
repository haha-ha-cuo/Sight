"""RSS/Atom 采集与 AgentScope 2.x 只读工具。"""

import asyncio
import hashlib
import ipaddress
import json
import re
import socket
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import httpx
from agentscope.message import TextBlock
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, ToolResponse

from agent.models import Article

MAX_FEED_BYTES = 2 * 1024 * 1024
FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")
PRESET_SOURCES = [
    {"name": "少数派", "url": "https://sspai.com/feed"},
    {"name": "阮一峰的网络日志", "url": "https://www.ruanyifeng.com/blog/atom.xml"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
]


class FeedError(ValueError):
    """可以直接向用户展示的信息源错误。"""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str, max_length: int = 1600) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:max_length]


def normalize_url(value: str) -> bytes | Any:
    """只接受不带认证信息的 HTTP(S) URL，并去掉片段用于去重。"""
    try:
        parts = urlsplit(value.strip())
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 80, 443}
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, "")
        )
    except ValueError as exc:
        raise FeedError("请输入有效的 HTTP(S) 地址，仅支持 80/443 端口且不能含账号密码") from exc


async def _require_public_host(url: str) -> None:
    parts = urlsplit(url)
    try:
        ipaddress.ip_address(parts.hostname)
        is_hostname = False
    except ValueError:
        is_hostname = True
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, parts.hostname, parts.port or 443, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise FeedError("无法解析信息源域名") from exc
    # 本机透明代理的 Fake-IP DNS 会把公开域名解析到此保留网段。
    # 仅对域名解析结果兼容该网段，直接输入保留 IP 仍然拒绝。
    ips = [ipaddress.ip_address(address[4][0]) for address in addresses]
    if not ips or any(
        not ip.is_global and not (is_hostname and ip in FAKE_IP_NETWORK) for ip in ips
    ):
        raise FeedError("仅支持公网信息源，不能访问本机或内网地址")


def parse_feed(content: bytes, source_url: str, limit: int) -> tuple[str, list[Article]]:
    # RSS 不需要 DTD；拒绝实体声明，避免恶意 XML。
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", content, re.IGNORECASE):
        raise FeedError("信息源含不支持的 XML 实体声明")
    feed = feedparser.parse(content)
    if not feed.version or feed.bozo:
        raise FeedError("响应不是有效的 RSS/Atom，请检查订阅地址")
    source_name = plain_text(feed.feed.get("title", "")) or source_url
    articles = []
    seen = set()
    for entry in feed.entries:
        try:
            url = normalize_url(urljoin(source_url, entry.get("link", "")))
        except FeedError:
            continue
        if not entry.get("link") or url in seen:
            continue
        seen.add(url)
        summary = plain_text(entry.get("summary", ""))
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        articles.append(
            Article(
                id=hashlib.sha256(url.encode()).hexdigest()[:16],
                title=plain_text(entry.get("title", ""), 300) or "无标题",
                url=url,
                source=source_name,
                published_at=(
                    datetime(*published[:6], tzinfo=UTC).isoformat() if published else None
                ),
                feed_summary=summary,
                summary=summary or "该订阅条目未提供摘要，请查看原文。",
            )
        )
        if len(articles) >= limit:
            break
    return source_name, articles


async def fetch_feed(url: str, limit: int) -> tuple[str, list[Article]]:
    url = normalize_url(url)
    try:
        # 环境代理可能访问内网，原型只直接请求公开信息源。
        async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
            for _ in range(4):
                await _require_public_host(url)
                async with client.stream(
                    "GET", url, headers={"User-Agent": "Sight-RSS-Prototype/0.1"}
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FeedError("信息源重定向缺少目标地址")
                        url = normalize_url(urljoin(url, location))
                        continue
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_FEED_BYTES:
                            raise FeedError("信息源超过 2 MB，请更换较小的订阅源")
                    return parse_feed(bytes(content), url, limit)
            raise FeedError("信息源重定向次数过多")
    except httpx.TimeoutException as exc:
        raise FeedError("信息源请求超时，请稍后重试") from exc
    except httpx.HTTPStatusError as exc:
        raise FeedError(f"信息源返回 HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise FeedError("无法连接信息源，请检查地址或网络") from exc


def rss_tool(articles: list[Article]) -> FunctionTool:
    """将本次采集结果绑定到工具，模型不能请求其他 URL 或执行写操作。"""

    async def read_rss_articles() -> ToolResponse:
        """读取本次请求采集的 RSS 文章，包含 ID、标题、原文链接和订阅摘要。"""
        return ToolResponse(
            content=[
                TextBlock(text=json.dumps([a.to_dict() for a in articles], ensure_ascii=False))
            ]
        )

    return FunctionTool(
        read_rss_articles,
        is_read_only=True,
        permission=PermissionDecision(
            behavior=PermissionBehavior.ALLOW, message="只读取本次请求已采集的 RSS 数据"
        ),
    )
