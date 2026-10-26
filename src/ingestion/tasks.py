import hashlib
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import structlog
from sqlalchemy import select

from src.db.redis_broker import broker, send_to_dlq
from src.db.postgres import async_session_factory, IngestionEpisode, PersonStaging
from src.ingestion.transcriber import transcribe_audio
from src.ingestion.extractor import extract_episode
from src.ingestion.social_parsers import parse_linkedin_csv
from src.contracts.schema import EpisodeExtractionResult

logger = structlog.get_logger(__name__)


@broker.task(task_name="ingest_voice_task")
async def ingest_voice_task(
    audio_bytes: bytes,
    message_id: Optional[int] = None,
    filename: str = "voice.ogg",
) -> dict:
    """Processes inbound voice notes: transcribes via Groq/faster-whisper,

    extracts entities & temporal edges, and stores episode idempotently.
    """
    try:
        raw_text = await transcribe_audio(audio_bytes, filename=filename)
        extraction = await extract_episode(raw_text, source_type="voice_note")
        episode_id = await save_episode_idempotent(extraction)
        return {
            "status": "COMPLETED",
            "episode_id": str(episode_id),
            "transcript": raw_text,
            "message_id": message_id,
        }
    except Exception as e:
        logger.error("ingest_voice_task failed", error=str(e), message_id=message_id)
        await send_to_dlq("ingest_voice_task", {"message_id": message_id}, str(e))
        raise


@broker.task(task_name="ingest_text_task")
async def ingest_text_task(
    raw_text: str,
    source_type: str = "text_note",
    reference_date: Optional[str] = None,
) -> dict:
    """Processes inbound text notes: extracts entities & temporal edges,

    and stores episode idempotently.
    """
    try:
        extraction = await extract_episode(
            raw_text, source_type=source_type, reference_date=reference_date
        )
        episode_id = await save_episode_idempotent(extraction)
        return {
            "status": "COMPLETED",
            "episode_id": str(episode_id),
            "transcript": raw_text,
            "person_count": len(extraction.persons),
            "edge_count": len(extraction.edges),
        }
    except Exception as e:
        logger.error("ingest_text_task failed", error=str(e), source_type=source_type)
        await send_to_dlq("ingest_text_task", {"raw_text": raw_text[:200]}, str(e))
        raise


@broker.task(task_name="ingest_csv_task")
async def ingest_csv_task(csv_content: str, filename: str = "Connections.csv") -> dict:
    """Parses exported LinkedIn Connections CSV and stages candidate persons."""
    try:
        persons = parse_linkedin_csv(csv_content)
        count = 0
        async with async_session_factory() as session:
            for p in persons:
                # Stage person into person_staging
                stmt = select(PersonStaging).where(
                    (PersonStaging.linkedin_url == p.linkedin_url)
                    if p.linkedin_url
                    else (PersonStaging.full_name == p.full_name)
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if not existing:
                    staging = PersonStaging(
                        uid=p.uid,
                        full_name=p.full_name,
                        aliases=p.aliases,
                        email=p.email,
                        phone=p.phone,
                        linkedin_url=p.linkedin_url,
                        github_handle=p.github_handle,
                        x_handle=p.x_handle,
                        current_org=p.current_org,
                        current_role=p.current_role,
                        alumni_orgs=p.alumni_orgs,
                        location_city=p.location_city,
                        reachability_tier=int(p.reachability_tier),
                        trust_score=p.trust_score,
                        verified=False,
                    )
                    session.add(staging)
                    count += 1
            await session.commit()

        return {"status": "COMPLETED", "imported_count": count}
    except Exception as e:
        logger.error("ingest_csv_task failed", error=str(e), filename=filename)
        await send_to_dlq("ingest_csv_task", {"filename": filename}, str(e))
        raise


async def save_episode_idempotent(extraction: EpisodeExtractionResult) -> uuid.UUID:
    """Enforces INV-02: Deterministic episode hash checking and persistence."""
    captured_date_iso = extraction.captured_at.strftime("%Y-%m-%d")
    computed_hash = hashlib.sha256(
        f"{extraction.source_type}:{extraction.raw_transcript.strip()}:{captured_date_iso}".encode()
    ).hexdigest()

    async with async_session_factory() as session:
        # Check if hash already exists
        stmt = select(IngestionEpisode).where(
            IngestionEpisode.episode_hash == computed_hash
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            logger.info(
                "Idempotency hit: episode already processed",
                episode_hash=computed_hash,
                episode_id=str(existing.episode_id),
            )
            return existing.episode_id

        # Insert new episode
        new_episode = IngestionEpisode(
            episode_id=extraction.episode_id,
            episode_hash=computed_hash,
            source_type=extraction.source_type,
            raw_transcript=extraction.raw_transcript,
            status="COMPLETED",
            captured_at=extraction.captured_at,
        )
        session.add(new_episode)
        await session.commit()
        return new_episode.episode_id
