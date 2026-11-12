"""原型对象模型与表结构；业务数据按用户归属隔离。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def iso(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def public(self) -> dict:
        return {"id": self.id, "username": self.username}


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    system_prompt: Mapped[str] = mapped_column(Text, default="你是中文资讯助手，回答简洁、准确。")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def public(self) -> dict:
        return {
            key: getattr(self, key) for key in ("id", "name", "provider", "model", "system_prompt")
        }


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(80), default="新对话")
    # 配置快照让既有对话不受 Agent 后续编辑或删除的影响。
    agent_name: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    system_prompt: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def public(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "provider": self.provider,
            "model": self.model,
            "updated_at": iso(self.updated_at),
        }


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "position"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def public(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": iso(self.created_at),
        }


class RssSource(Base):
    __tablename__ = "rss_sources"
    __table_args__ = (UniqueConstraint("user_id", "url_hash"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(2048))
    url_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "url": self.url}


class DigestRecord(Base):
    __tablename__ = "digest_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    overview: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def public(self) -> dict:
        return {
            "id": self.id,
            "overview": self.overview,
            "created_at": iso(self.created_at),
            "count": len(self.payload.get("articles", [])),
            "demo": self.payload.get("demo", False),
        }
