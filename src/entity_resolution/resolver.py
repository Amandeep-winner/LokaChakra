"""Three-tier entity resolution engine for identity deduplication.

Implements:
1. Tier 1: Deterministic exact match on email, phone, or LinkedIn URL (S = 1.0).
2. Tier 2: Probabilistic + FastEmbed vector cosine + RapidFuzz Jaro-Winkler hybrid match:
   S = 0.45 * N_sim + 0.35 * V_sim + 0.20 * I_shared
3. Decision gates:
   - S >= 0.95 -> AUTO_MERGE
   - 0.65 <= S < 0.95 -> QUEUE_HITL
   - S < 0.65 -> CREATE_NEW_NODE
"""

import math
import re
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from rapidfuzz.distance import JaroWinkler
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.schema import (
    ExtractedPerson,
    HITLEvidenceCard,
    RelationType,
    ResolutionAction,
    ResolutionResult,
    VerificationStatus,
)
from src.db.postgres import HITLEvidenceCardModel, PersonStaging
from src.entity_resolution.embedder import embed_person

INSTITUTION_ALIASES: Dict[str, str] = {
    "iitb": "iit bombay",
    "iit bombay": "iit bombay",
    "iitd": "iit delhi",
    "iit delhi": "iit delhi",
    "iitr": "iit roorkee",
    "iit roorkee": "iit roorkee",
    "iitk": "iit kanpur",
    "iit kanpur": "iit kanpur",
    "iitm": "iit madras",
    "iit madras": "iit madras",
    "iitkgp": "iit kharagpur",
    "iit kharagpur": "iit kharagpur",
    "bits": "bits pilani",
    "bits pilani": "bits pilani",
    "rvce": "rvce bangalore",
    "rv college of engineering": "rvce bangalore",
    "r.v. college of engineering": "rvce bangalore",
    "nitk": "nit surathkal",
    "nit surathkal": "nit surathkal",
    "nitw": "nit warangal",
    "nit warangal": "nit warangal",
}


def normalize_org_name(org: str) -> str:
    """Normalize organization or college name to canonical form."""
    cleaned = re.sub(r"[^\w\s]", "", org.lower()).strip()
    return INSTITUTION_ALIASES.get(cleaned, cleaned)


def extract_normalized_orgs(person: ExtractedPerson | PersonStaging) -> Set[str]:
    """Extract and normalize all organization references for a person."""
    orgs: Set[str] = set()
    current_org = getattr(person, "current_org", None)
    if current_org:
        normalized = normalize_org_name(current_org)
        if normalized:
            orgs.add(normalized)

    alumni_orgs = getattr(person, "alumni_orgs", None) or []
    for org in alumni_orgs:
        normalized = normalize_org_name(org)
        if normalized:
            orgs.add(normalized)
    return orgs


def calculate_name_similarity(name1: str, name2: str) -> float:
    """Compute normalized name similarity with initial and prefix boost."""
    clean1 = re.sub(r"[^\w\s]", "", name1.lower()).strip()
    clean2 = re.sub(r"[^\w\s]", "", name2.lower()).strip()

    if clean1 == clean2:
        return 1.0

    base_sim = JaroWinkler.normalized_similarity(clean1, clean2)

    toks1 = clean1.split()
    toks2 = clean2.split()

    if len(toks1) >= 2 and len(toks2) >= 2:
        # Check initial matching when surnames match (e.g. "R Sharma" vs "Rahul Sharma")
        if toks1[-1] == toks2[-1]:
            first1, first2 = toks1[0], toks2[0]
            if (len(first1) == 1 and first2.startswith(first1)) or (
                len(first2) == 1 and first1.startswith(first2)
            ):
                base_sim = max(base_sim, 0.88)

    # Prefix match boost
    if clean1.startswith(clean2) or clean2.startswith(clean1):
        base_sim = max(base_sim, 0.90)

    return min(1.0, base_sim)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    sim = dot / (norm1 * norm2)
    return max(0.0, min(1.0, float(sim)))


def merge_staging_record(existing: PersonStaging, incoming: ExtractedPerson) -> None:
    """Merge newly discovered non-null attributes into an existing staging record."""
    if incoming.current_org and not existing.current_org:
        existing.current_org = incoming.current_org
    if incoming.current_role and not existing.current_role:
        existing.current_role = incoming.current_role
    if incoming.location_city and not existing.location_city:
        existing.location_city = incoming.location_city
    if incoming.github_handle and not existing.github_handle:
        existing.github_handle = incoming.github_handle
    if incoming.x_handle and not existing.x_handle:
        existing.x_handle = incoming.x_handle
    if incoming.email and not existing.email:
        existing.email = incoming.email
    if incoming.phone and not existing.phone:
        existing.phone = incoming.phone
    if incoming.linkedin_url and not existing.linkedin_url:
        existing.linkedin_url = incoming.linkedin_url

    # Merge lists
    existing_aliases = set(existing.aliases or [])
    existing_aliases.update(incoming.aliases or [])
    existing.aliases = list(existing_aliases)

    existing_alumni = set(existing.alumni_orgs or [])
    existing_alumni.update(incoming.alumni_orgs or [])
    existing.alumni_orgs = list(existing_alumni)

    # Trust score preservation
    existing.trust_score = max(existing.trust_score, incoming.trust_score)


async def resolve_person(
    session: AsyncSession,
    incoming: ExtractedPerson,
    episode_id: UUID,
) -> ResolutionResult:
    """Execute three-tier entity resolution pipeline on an incoming extracted person."""
    # ---------------------------------------------------------
    # Tier 1: Deterministic Exact Match (S = 1.0)
    # ---------------------------------------------------------
    clauses = []
    if incoming.email:
        clauses.append(PersonStaging.email == incoming.email)
    if incoming.phone:
        clauses.append(PersonStaging.phone == incoming.phone)
    if incoming.linkedin_url:
        clauses.append(PersonStaging.linkedin_url == incoming.linkedin_url)

    if clauses:
        stmt = select(PersonStaging).where(or_(*clauses))
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            merge_staging_record(existing, incoming)
            await session.flush()
            return ResolutionResult(
                action=ResolutionAction.AUTO_MERGE,
                matched_uid=existing.uid,
                confidence_score=1.0,
            )

    # ---------------------------------------------------------
    # Tier 2: Probabilistic + Vector Hybrid Match
    # ---------------------------------------------------------
    incoming_vec = embed_person(incoming)

    # Retrieve candidate staging records
    try:
        # Attempt pgvector cosine distance ordering if supported by dialect
        stmt = (
            select(PersonStaging)
            .order_by(PersonStaging.embedding.cosine_distance(incoming_vec))
            .limit(10)
        )
        res = await session.execute(stmt)
        candidates = list(res.scalars().all())
    except Exception:
        # Fallback for standard environments / in-memory sessions without pgvector C extension
        stmt = select(PersonStaging).limit(50)
        res = await session.execute(stmt)
        candidates = list(res.scalars().all())

    incoming_orgs = extract_normalized_orgs(incoming)

    best_score = 0.0
    best_candidate: Optional[PersonStaging] = None
    best_breakdown: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    for c in candidates:
        n_sim = calculate_name_similarity(incoming.full_name, c.full_name)

        # Vector similarity
        if c.embedding is not None:
            c_vec = list(c.embedding)
            v_sim = cosine_similarity(incoming_vec, c_vec)
        else:
            v_sim = 0.0

        # Institutional overlap
        c_orgs = extract_normalized_orgs(c)
        shared_orgs = incoming_orgs.intersection(c_orgs)
        i_shared = 1.0 if len(shared_orgs) > 0 else 0.0

        composite_score = 0.45 * n_sim + 0.35 * v_sim + 0.20 * i_shared

        if composite_score > best_score:
            best_score = composite_score
            best_candidate = c
            best_breakdown = (n_sim, v_sim, i_shared)

    # ---------------------------------------------------------
    # Decision Thresholds
    # ---------------------------------------------------------
    if best_candidate is not None and best_score >= 0.95:
        merge_staging_record(best_candidate, incoming)
        await session.flush()
        return ResolutionResult(
            action=ResolutionAction.AUTO_MERGE,
            matched_uid=best_candidate.uid,
            confidence_score=round(best_score, 4),
        )

    if best_candidate is not None and 0.65 <= best_score < 0.95:
        card_id = uuid4()
        thread_id = f"thread_{episode_id}_{incoming.uid}"
        n_sim, v_sim, i_shared = best_breakdown

        evidence_text = (
            f"Probabilistic identity candidate match (score: {best_score:.3f}). "
            f"Name similarity: {n_sim:.2f}, Vector similarity: {v_sim:.2f}, Shared institutional context: {i_shared == 1.0}."
        )

        hitl_model = HITLEvidenceCardModel(
            card_id=card_id,
            langgraph_thread_id=thread_id,
            action_type="ENTITY_MERGE",
            subject_a_uid=incoming.uid,
            subject_a_name=incoming.full_name,
            subject_b_uid=best_candidate.uid,
            subject_b_name=best_candidate.full_name,
            proposed_relation=RelationType.KNOWS.value,
            confidence_score=round(best_score, 4),
            evidence_summary=evidence_text,
            source_urls=[],
            status="pending_hitl",
        )
        session.add(hitl_model)
        await session.flush()

        pydantic_card = HITLEvidenceCard(
            card_id=card_id,
            langgraph_thread_id=thread_id,
            action_type="ENTITY_MERGE",
            subject_a_uid=incoming.uid,
            subject_a_name=incoming.full_name,
            subject_b_uid=best_candidate.uid,
            subject_b_name=best_candidate.full_name,
            proposed_relation=RelationType.KNOWS,
            confidence_score=round(best_score, 4),
            evidence_summary=evidence_text,
            source_urls=[],
            status=VerificationStatus.PENDING_HITL,
        )

        return ResolutionResult(
            action=ResolutionAction.QUEUE_HITL,
            matched_uid=best_candidate.uid,
            confidence_score=round(best_score, 4),
            hitl_card=pydantic_card,
        )

    # Score < 0.65 or no candidates: create new node in staging
    new_staging = PersonStaging(
        uid=incoming.uid,
        full_name=incoming.full_name,
        aliases=incoming.aliases,
        email=incoming.email,
        phone=incoming.phone,
        linkedin_url=incoming.linkedin_url,
        github_handle=incoming.github_handle,
        x_handle=incoming.x_handle,
        current_org=incoming.current_org,
        current_role=incoming.current_role,
        alumni_orgs=incoming.alumni_orgs,
        location_city=incoming.location_city,
        reachability_tier=incoming.reachability_tier.value,
        trust_score=incoming.trust_score,
        verified=False,
        embedding=incoming_vec,
    )
    session.add(new_staging)
    await session.flush()

    return ResolutionResult(
        action=ResolutionAction.CREATE_NEW_NODE,
        matched_uid=incoming.uid,
        confidence_score=round(best_score, 4),
    )
