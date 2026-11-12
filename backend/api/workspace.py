import asyncio
import hashlib

from flask import Blueprint, abort, current_app, g, jsonify
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from agent.chat import reply_to_conversation
from agent.config import PROVIDER_KEYS, ai_available
from agent.tools import FeedError, normalize_url
from api.accounts import json_body, login_required, owned, text_field
from database.models import AgentProfile, Conversation, DigestRecord, Message, RssSource, utcnow
from database.store import get_session

workspace_api = Blueprint("workspace", __name__)


def agent_fields(data: dict) -> dict:
    provider = text_field(data, "provider", 20)
    if provider not in PROVIDER_KEYS:
        abort(400, description="provider 仅支持 deepseek 或 dashscope")
    return {
        "name": text_field(data, "name", 60),
        "provider": provider,
        "model": text_field(data, "model", 100),
        "system_prompt": text_field(data, "system_prompt", 4000),
    }


@workspace_api.get("/api/agents")
@login_required
def agents():
    rows = get_session().scalars(
        select(AgentProfile)
        .where(AgentProfile.user_id == g.user.id)
        .order_by(AgentProfile.created_at)
    )
    return jsonify(agents=[row.public() for row in rows])


@workspace_api.post("/api/agents")
@login_required
def create_agent():
    fields = agent_fields(json_body())
    db = get_session()
    count = db.scalar(
        select(func.count()).select_from(AgentProfile).where(AgentProfile.user_id == g.user.id)
    )
    if count >= 20:
        abort(400, description="原型最多保存 20 个 Agent")
    profile = AgentProfile(user_id=g.user.id, **fields)
    db.add(profile)
    db.commit()
    return jsonify(agent=profile.public()), 201


@workspace_api.put("/api/agents/<id>")
@login_required
def update_agent(id):
    profile = owned(AgentProfile, id)
    for key, value in agent_fields(json_body()).items():
        setattr(profile, key, value)
    get_session().commit()
    return jsonify(agent=profile.public())


@workspace_api.delete("/api/agents/<id>")
@login_required
def remove_agent(id):
    profile = owned(AgentProfile, id)
    db = get_session()
    db.delete(profile)
    db.commit()
    return "", 204


@workspace_api.get("/api/conversations")
@login_required
def conversations():
    rows = get_session().scalars(
        select(Conversation)
        .where(Conversation.user_id == g.user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    return jsonify(conversations=[row.public() for row in rows])


@workspace_api.post("/api/conversations")
@login_required
def create_conversation():
    data = json_body()
    profile = owned(AgentProfile, text_field(data, "agent_id", 32))
    row = Conversation(
        user_id=g.user.id,
        agent_id=profile.id,
        agent_name=profile.name,
        provider=profile.provider,
        model=profile.model,
        system_prompt=profile.system_prompt,
    )
    db = get_session()
    db.add(row)
    db.commit()
    return jsonify(conversation=row.public(), messages=[]), 201


@workspace_api.get("/api/conversations/<id>")
@login_required
def conversation_detail(id):
    row = owned(Conversation, id)
    messages = get_session().scalars(
        select(Message).where(Message.conversation_id == row.id).order_by(Message.position)
    )
    return jsonify(conversation=row.public(), messages=[msg.public() for msg in messages])


@workspace_api.delete("/api/conversations/<id>")
@login_required
def remove_conversation(id):
    row = owned(Conversation, id)
    db = get_session()
    db.delete(row)
    db.commit()
    return "", 204


@workspace_api.post("/api/conversations/<id>/messages")
@login_required
def send_message(id):
    row = owned(Conversation, id)
    content = text_field(json_body(), "content", 6000)
    profile = {key: getattr(row, key) for key in ("provider", "model", "system_prompt")}
    config = dict(current_app.config)
    if not ai_available({**config, "SIGHT_PROVIDER": row.provider}):
        abort(503, description="该 Agent 的模型密钥未配置，请配置后重试")
    db = get_session()
    revision, user_id = row.revision, g.user.id
    recent = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == row.id)
            .order_by(Message.position.desc())
            .limit(20)
        )
    )
    history = [{"role": msg.role, "content": msg.content} for msg in reversed(recent)]
    while sum(len(msg["content"]) for msg in history) > 24000:
        history = history[2:]
    # 模型调用期间不占用数据库事务；提交时通过版本号避免并发覆盖。
    db.commit()
    try:
        answer = asyncio.run(reply_to_conversation(config, profile, history, content))
    except Exception:
        current_app.logger.warning("Chat model call failed")
        abort(503, description="模型暂不可用，本轮消息尚未保存，请稍后重试")
    changed = db.execute(
        update(Conversation)
        .where(
            Conversation.id == id,
            Conversation.user_id == user_id,
            Conversation.revision == revision,
        )
        .values(
            revision=revision + 2,
            title=content[:40] if revision == 0 else row.title,
            updated_at=utcnow(),
        ),
        execution_options={"synchronize_session": False},
    )
    if changed.rowcount != 1:
        db.rollback()
        abort(409, description="对话已变化，请重新打开后再发送")
    pair = [
        Message(conversation_id=id, position=revision + index + 1, role=role, content=text)
        for index, (role, text) in enumerate((("user", content), ("assistant", answer)))
    ]
    db.add_all(pair)
    db.commit()
    db.expire(row)
    return jsonify(conversation=row.public(), messages=[msg.public() for msg in pair]), 201


@workspace_api.get("/api/sources")
@login_required
def sources():
    rows = get_session().scalars(
        select(RssSource).where(RssSource.user_id == g.user.id).order_by(RssSource.created_at)
    )
    return jsonify(sources=[row.public() for row in rows])


@workspace_api.post("/api/sources")
@login_required
def create_source():
    data = json_body()
    name = text_field(data, "name", 80)
    try:
        url = normalize_url(text_field(data, "url", 2048))
    except FeedError as exc:
        abort(400, description=str(exc))
    db = get_session()
    count = db.scalar(
        select(func.count()).select_from(RssSource).where(RssSource.user_id == g.user.id)
    )
    if count >= 50:
        abort(400, description="原型最多保存 50 个订阅")
    row = RssSource(
        user_id=g.user.id, name=name, url=url, url_hash=hashlib.sha256(url.encode()).hexdigest()
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        abort(409, description="已保存该订阅地址")
    return jsonify(source=row.public()), 201


@workspace_api.delete("/api/sources/<id>")
@login_required
def remove_source(id):
    row = owned(RssSource, id)
    db = get_session()
    db.delete(row)
    db.commit()
    return "", 204


@workspace_api.get("/api/digests")
@login_required
def digests():
    rows = get_session().scalars(
        select(DigestRecord)
        .where(DigestRecord.user_id == g.user.id)
        .order_by(DigestRecord.created_at.desc())
        .limit(50)
    )
    return jsonify(digests=[row.public() for row in rows])


@workspace_api.get("/api/digests/<id>")
@login_required
def digest_detail(id):
    row = owned(DigestRecord, id)
    return jsonify({**row.payload, "id": row.id})


@workspace_api.delete("/api/digests/<id>")
@login_required
def remove_digest(id):
    row = owned(DigestRecord, id)
    db = get_session()
    db.delete(row)
    db.commit()
    return "", 204
