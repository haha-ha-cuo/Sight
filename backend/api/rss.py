import asyncio

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from agent.config import PROVIDER_KEYS, ai_available
from agent.service import generate_digest
from agent.tools import PRESET_SOURCES, FeedError, normalize_url

rss_api = Blueprint("rss", __name__)


@rss_api.get("/api/rss/config")
def rss_config():
    return jsonify(
        sources=PRESET_SOURCES,
        ai_available=ai_available(current_app.config),
        provider=current_app.config["SIGHT_PROVIDER"],
        model=current_app.config["SIGHT_MODEL"],
        max_sources=5,
        max_articles=20,
    )


@rss_api.post("/api/digests")
def create_digest():
    try:
        data = request.get_json()
    except (BadRequest, UnsupportedMediaType):
        return jsonify(message="请提交合法的 JSON 对象"), 400
    if not isinstance(data, dict):
        return jsonify(message="请提交 JSON 对象"), 400
    urls = data.get("urls", [])
    limit = data.get("limit", 10)
    mode = data.get("mode", "feed")
    demo = data.get("demo", False)
    if type(limit) is not int or not 1 <= limit <= 20:
        return jsonify(message="条数必须是 1–20 之间的整数"), 400
    if not isinstance(mode, str) or mode not in {"feed", "ai"}:
        return jsonify(message="mode 仅支持 feed 或 ai"), 400
    if type(demo) is not bool:
        return jsonify(message="demo 必须是布尔值"), 400
    if (
        not isinstance(urls, list)
        or len(urls) > 5
        or any(not isinstance(url, str) or len(url) > 2048 for url in urls)
        or (not demo and not urls)
    ):
        return jsonify(message="请提供 1–5 个 RSS/Atom 地址"), 400
    try:
        urls = list(dict.fromkeys(normalize_url(url) for url in urls))
    except FeedError as exc:
        return jsonify(message=str(exc)), 400
    if mode == "ai" and not ai_available(current_app.config):
        key = PROVIDER_KEYS.get(current_app.config["SIGHT_PROVIDER"])
        message = (
            f"AI 摘要尚未配置，请设置 {key} 或使用订阅摘要模式"
            if key
            else "SIGHT_PROVIDER 仅支持 deepseek 或 dashscope"
        )
        return jsonify(message=message), 503
    try:
        result = asyncio.run(generate_digest(urls, limit, mode, demo, dict(current_app.config)))
    except FeedError as exc:
        return jsonify(message=str(exc)), 502
    return jsonify(result)
