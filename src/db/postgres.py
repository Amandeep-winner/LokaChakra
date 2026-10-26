from datetime import datetime, timezone
from typing import AsyncGenerator, Optional, List
import uuid

from sqlalchemy import (
    String,
    Text,
    Float,
    SmallInteger,
    Boolean,
    DateTime,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from src.config import settings


class Base(DeclarativeBase):
    pass


class IngestionEpisode(Base):
    __tablename__ = "ingestion_episodes"

    episode_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    episode_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROCESSING")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class PersonStaging(Base):
    __tablename__ = "person_staging"

    uid: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    github_handle: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    x_handle: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    current_org: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    current_role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    alumni_orgs: Mapped[list] = mapped_column(JSONB, default=list)
    location_city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reachability_tier: Mapped[int] = mapped_column(SmallInteger, default=2)
    trust_score: Mapped[float] = mapped_column(Float, default=50.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(384), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class HITLEvidenceCardModel(Base):
    __tablename__ = "hitl_evidence_cards"

    card_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    langgraph_thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_a_uid: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    subject_a_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_b_uid: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    subject_b_name: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_relation: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_urls: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_hitl")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


engine = create_async_engine(
    settings.POSTGRES_URI,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_postgres_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
