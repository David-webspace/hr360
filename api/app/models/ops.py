from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.models.base import Base, Timestamped


class PolicyDocument(Base, Timestamped):
    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(16))
    effective_from: Mapped[date] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(16))  # handbook / law / faq


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("policy_documents.id", ondelete="CASCADE"), index=True)
    section_path: Mapped[str] = mapped_column(String(128))  # 第三章 > 第12條
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))

    __table_args__ = (
        Index("ix_policy_chunks_text_trgm", "text", postgresql_using="gin", postgresql_ops={"text": "gin_trgm_ops"}),
    )


class Conversation(Base, Timestamped):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(128))


class Message(Base, Timestamped):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    text: Mapped[str] = mapped_column(Text)  # 給模型的對話記憶只用這欄文字，不含工具原始輸出
    # 只給畫面還原用（請假單卡片、出處、耗時），不會送回模型
    meta: Mapped[dict | None] = mapped_column(JSONB)


class Ticket(Base, Timestamped):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    category: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))  # open / in_progress / resolved / closed
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    roles: Mapped[list] = mapped_column(JSONB)
    channel: Mapped[str] = mapped_column(String(8))  # web / mcp / api
    event: Mapped[str] = mapped_column(String(32))  # chat / tool / login / approve ...
    question: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(48))
    model: Mapped[str | None] = mapped_column(String(64))
    routed_by: Mapped[str | None] = mapped_column(String(32))
    tools: Mapped[list | None] = mapped_column(JSONB)
    denied: Mapped[bool] = mapped_column(Boolean, default=False)
    deny_reason: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    grounding_ok: Mapped[bool | None] = mapped_column(Boolean)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))


class EvalRun(Base, Timestamped):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(64))
    case_id: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(32))
    numeric_ok: Mapped[bool | None] = mapped_column(Boolean)
    semantic_ok: Mapped[bool | None] = mapped_column(Boolean)
    leaked: Mapped[bool] = mapped_column(Boolean, default=False)
    refused_ok: Mapped[bool | None] = mapped_column(Boolean)
    action_ok: Mapped[bool | None] = mapped_column(Boolean)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSONB)
