import hashlib
from datetime import datetime, timezone
from typing import Optional, Any
from openai import AsyncOpenAI
import instructor
import structlog

from src.config import settings
from src.contracts.schema import (
    EpisodeExtractionResult,
    ExtractedPerson,
    ReachabilityTier,
)

logger = structlog.get_logger(__name__)


def get_instructor_client() -> instructor.Instructor:
    if settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
        openai_client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    elif settings.OPENAI_API_KEY:
        openai_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
        )
    else:
        openai_client = AsyncOpenAI(
            api_key="none",
            base_url="https://api.groq.com/openai/v1",
        )
    return instructor.from_openai(openai_client)


async def extract_episode(
    raw_text: str,
    source_type: str = "voice_note",
    reference_date: Optional[str] = None,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> EpisodeExtractionResult:
    """Extracts entities and temporal relationships from raw text or transcripts using an LLM."""
    ref_date = reference_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    episode_hash = hashlib.sha256(
        f"{source_type}:{raw_text.strip()}:{ref_date}".encode()
    ).hexdigest()

    system_prompt = f"""You are the Entity & Temporal Relationship Extractor for Lokachakra.
Today's Reference Date is: {ref_date}.
RULES:
1. Always represent the first-person speaker ("I", "me", "my") as a Person with full_name="SELF_USER" and reachability_tier=1.
2. Direct friends/colleagues mentioned as spoken to by SELF_USER get reachability_tier=1. Friends-of-friends (e.g., "Ankit's roommate Vikram") get reachability_tier=2. Distant targets get reachability_tier=3.
3. TEMPORAL LOGIC:
   - If the text says someone "used to work at X", "left X", or "ex-X", create a WORKS_AT edge with valid_to="{ref_date}".
   - If the text says someone "currently works at Y" or "just joined Y", create a WORKS_AT edge with valid_from="{ref_date}" and valid_to=null.
4. Every edge MUST include an exact evidence_snippet quoted from the input text."""

    user_prompt = f"Extract all persons, organizations, and temporal relationship edges from this transcript:\n\n{raw_text}"

    instructor_client = client or get_instructor_client()
    chosen_model = model or settings.LLM_MODEL or "llama-3.3-70b-versatile"

    try:
        result: EpisodeExtractionResult = await instructor_client.chat.completions.create(
            model=chosen_model,
            response_model=EpisodeExtractionResult,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
    except Exception as e:
        logger.error("LLM entity extraction failed", error=str(e), model=chosen_model)
        raise

    result.episode_hash = episode_hash
    result.raw_transcript = raw_text
    result.source_type = source_type

    # Ensure SELF_USER exists in extracted persons
    has_self_user = any(
        p.full_name.upper() in {"SELF_USER", settings.SELF_USER_NAME.upper()}
        for p in result.persons
    )
    if not has_self_user:
        result.persons.insert(
            0,
            ExtractedPerson(
                full_name="SELF_USER",
                reachability_tier=ReachabilityTier.TIER_1_CLOSE,
                trust_score=100.0,
            ),
        )

    return result
