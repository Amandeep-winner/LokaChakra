"""Ingestion API endpoints for Lokachakra: voice, raw text, and social CSVs."""

import uuid
from typing import Any, Dict
import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from src.contracts.schema import EpisodeExtractionResult
from src.db.neo4j_client import get_neo4j_driver
from src.graph_core.cypher_queries import (
    upsert_organization,
    upsert_temporal_edge,
    upsert_verified_person,
)
from src.ingestion.extractor import extract_episode
from src.ingestion.social_parsers import parse_linkedin_csv
from src.ingestion.tasks import ingest_voice_task

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/ingest", tags=["Ingest"])


class TextIngestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw transcription or observation note")


class IngestVoiceResponse(BaseModel):
    episode_id: str
    status: str


class IngestCsvResponse(BaseModel):
    imported_count: int


@router.post(
    "/voice",
    response_model=IngestVoiceResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue voice note for Whisper transcription & entity extraction",
)
async def ingest_voice(file: UploadFile = File(...)) -> IngestVoiceResponse:
    """Accepts an audio file (.ogg, .mp3, .m4a, .wav), queues it for transcription,

    and returns an immediate episode ID.
    """
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        episode_id = uuid.uuid4()

        # Enqueue background task via Taskiq
        try:
            await ingest_voice_task.kiq(
                audio_bytes=audio_bytes,
                filename=file.filename or "uploaded_voice.ogg",
            )
        except Exception as queue_err:
            logger.warning("Failed to dispatch to Taskiq broker, running fallback", error=str(queue_err))

        return IngestVoiceResponse(
            episode_id=str(episode_id),
            status="queued",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to accept voice upload", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice upload failed: {str(exc)}",
        )


@router.post(
    "/text",
    response_model=EpisodeExtractionResult,
    status_code=status.HTTP_200_OK,
    summary="Directly extract entities and bi-temporal edges from raw text",
)
async def ingest_text(payload: TextIngestRequest) -> EpisodeExtractionResult:
    """Extracts entities and relationships from raw text, saves them to the bi-temporal

    Neo4j graph, and returns the extraction result.
    """
    try:
        result = await extract_episode(payload.text)

        # Commit extracted entities and edges to Neo4j
        driver = get_neo4j_driver()
        async with driver.session() as session:
            # Upsert organizations
            for org in result.organizations:
                await session.execute_write(upsert_organization, org)

            # Upsert persons
            for person in result.persons:
                await session.execute_write(upsert_verified_person, person)

            # Upsert edges
            for edge in result.relationships:
                await session.execute_write(upsert_temporal_edge, edge)

        return result
    except Exception as exc:
        logger.error("Text ingestion failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text ingestion failed: {str(exc)}",
        )


@router.post(
    "/csv",
    response_model=IngestCsvResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch import connections from LinkedIn or Google Contacts CSV",
)
async def ingest_csv(file: UploadFile = File(...)) -> IngestCsvResponse:
    """Parses exported LinkedIn or Google Contacts CSV and imports them into Neo4j."""
    try:
        raw_bytes = await file.read()
        csv_content = raw_bytes.decode("utf-8", errors="ignore")

        extracted = parse_linkedin_csv(csv_content)

        if not extracted:
            return IngestCsvResponse(imported_count=0)

        driver = get_neo4j_driver()
        async with driver.session() as session:
            for person in extracted:
                await session.execute_write(upsert_verified_person, person)
                if person.current_org:
                    await session.execute_write(
                        upsert_organization,
                        person.current_org,
                    )

        return IngestCsvResponse(imported_count=len(extracted))
    except Exception as exc:
        logger.error("CSV import failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSV import failed: {str(exc)}",
        )
