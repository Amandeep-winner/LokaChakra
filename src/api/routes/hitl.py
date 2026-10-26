"""Human-In-The-Loop (HITL) resolution endpoints for Lokachakra."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from langgraph.types import Command

from src.contracts.schema import HITLEvidenceCard, RelationType, VerificationStatus
from src.db.postgres import HITLEvidenceCardModel, async_session_factory
from src.hitl_bot.bot import get_osint_app

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/hitl", tags=["HITL"])


class ResolveHITLRequest(BaseModel):
    card_id: str = Field(..., description="UUID of the HITL evidence card")
    thread_id: Optional[str] = Field(None, description="LangGraph thread ID")
    action: str = Field(..., pattern="^(approve|reject)$", description="approve or reject")


class ResolveHITLResponse(BaseModel):
    status: str
    card_id: str
    decision: str


@router.get(
    "/pending",
    response_model=List[HITLEvidenceCard],
    status_code=status.HTTP_200_OK,
    summary="List all pending HITL verification evidence cards",
)
async def get_pending_hitl() -> List[HITLEvidenceCard]:
    """Retrieves all pending HITL evidence cards from PostgreSQL."""
    try:
        async with async_session_factory() as session:
            stmt = (
                select(HITLEvidenceCardModel)
                .where(HITLEvidenceCardModel.status == "pending_hitl")
                .order_by(HITLEvidenceCardModel.created_at.desc())
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            cards: List[HITLEvidenceCard] = []
            for r in records:
                try:
                    rel_type = RelationType(r.proposed_relation)
                except ValueError:
                    rel_type = RelationType.KNOWS_PERSON

                cards.append(
                    HITLEvidenceCard(
                        card_id=r.card_id,
                        langgraph_thread_id=r.langgraph_thread_id,
                        action_type=r.action_type,
                        subject_a_uid=r.subject_a_uid,
                        subject_a_name=r.subject_a_name,
                        subject_b_uid=r.subject_b_uid,
                        subject_b_name=r.subject_b_name,
                        proposed_relation=rel_type,
                        confidence_score=r.confidence_score,
                        evidence_summary=r.evidence_summary,
                        source_urls=r.source_urls or [],
                        status=VerificationStatus.PENDING_HITL,
                        created_at=r.created_at,
                    )
                )

            return cards
    except Exception as exc:
        logger.error("Failed to fetch pending HITL cards", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch pending cards: {str(exc)}",
        )


@router.post(
    "/resolve",
    response_model=ResolveHITLResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve a HITL verification card and resume the LangGraph workflow",
)
async def resolve_hitl(payload: ResolveHITLRequest) -> ResolveHITLResponse:
    """Approve or reject a pending verification hypothesis and resumes LangGraph."""
    try:
        card_uuid = uuid.UUID(payload.card_id)
        new_status = "resolved_approved" if payload.action == "approve" else "resolved_rejected"
        resolved_time = datetime.now(timezone.utc)

        # Update record in PostgreSQL
        async with async_session_factory() as session:
            update_stmt = (
                update(HITLEvidenceCardModel)
                .where(HITLEvidenceCardModel.card_id == card_uuid)
                .values(status=new_status, resolved_at=resolved_time)
            )
            await session.execute(update_stmt)
            await session.commit()

        # If a thread_id is specified, resume the LangGraph OSINT state graph
        if payload.thread_id:
            try:
                osint_app = get_osint_app()
                await osint_app.ainvoke(
                    Command(resume=payload.action),
                    config={"configurable": {"thread_id": payload.thread_id}},
                )
            except Exception as graph_err:
                logger.warning(
                    "Resuming LangGraph thread encountered a non-critical error or already resumed",
                    thread_id=payload.thread_id,
                    error=str(graph_err),
                )

        return ResolveHITLResponse(
            status="success",
            card_id=payload.card_id,
            decision=payload.action,
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid card UUID: {str(ve)}",
        )
    except Exception as exc:
        logger.error("Failed to resolve HITL card", card_id=payload.card_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve HITL card: {str(exc)}",
        )
