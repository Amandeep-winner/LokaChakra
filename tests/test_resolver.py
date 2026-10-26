"""Integration and unit tests for 3-tier entity resolution and bi-temporal graph core."""

import pytest
from uuid import uuid4

from src.contracts.schema import (
    EntityType,
    ExtractedEdge,
    ExtractedPerson,
    ReachabilityTier,
    RelationType,
    ResolutionAction,
)
from src.db.neo4j_client import get_neo4j_session, verify_neo4j_connectivity
from src.db.postgres import PersonStaging
from src.entity_resolution.embedder import (
    build_person_profile_text,
    embed_person,
)
from src.entity_resolution.resolver import (
    calculate_name_similarity,
    extract_normalized_orgs,
    normalize_org_name,
    resolve_person,
)
from src.graph_core.cypher_queries import (
    get_person_active_jobs,
    get_person_all_jobs,
    upsert_temporal_edge,
    upsert_verified_person,
)


class MockScalarResult:
    """Mock scalars query result."""

    def __init__(self, items):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class MockResult:
    """Mock query result returned by execute()."""

    def __init__(self, items):
        self._items = items

    def scalars(self):
        return MockScalarResult(self._items)


class MockAsyncSession:
    """Mock asynchronous SQLAlchemy session for isolated resolution testing."""

    def __init__(self, records=None):
        self.records = records or []
        self.added = []

    async def execute(self, stmt):
        if getattr(stmt, "whereclause", None) is not None:
            # Deterministic exact match query
            params = stmt.compile().params
            matched = []
            for r in self.records:
                for k, v in params.items():
                    if "email" in k and r.email == v:
                        matched.append(r)
                    elif "phone" in k and r.phone == v:
                        matched.append(r)
                    elif "linkedin" in k and r.linkedin_url == v:
                        matched.append(r)
            return MockResult(matched)
        # Probabilistic candidate retrieval query
        return MockResult(self.records)

    def add(self, item):
        self.added.append(item)
        if isinstance(item, PersonStaging):
            self.records.append(item)

    async def flush(self):
        pass


def test_build_person_profile_text():
    person = ExtractedPerson(
        full_name="Rohan Verma",
        aliases=["RV"],
        current_org="Razorpay",
        current_role="Staff Engineer",
        alumni_orgs=["IIT Bombay", "BITS"],
        location_city="Bengaluru",
    )
    profile_text = build_person_profile_text(person)
    assert "Rohan Verma" in profile_text
    assert "Razorpay" in profile_text
    assert "IIT Bombay" in profile_text
    assert "Bengaluru" in profile_text


def test_embed_person_dimensions():
    person = ExtractedPerson(
        full_name="Aditi Rao",
        current_org="Swiggy",
    )
    vec = embed_person(person)
    assert len(vec) == 384
    assert all(isinstance(val, float) for val in vec)


def test_institutional_normalization():
    assert normalize_org_name("IITB") == "iit bombay"
    assert normalize_org_name("iit bombay") == "iit bombay"
    assert normalize_org_name("RVCE") == "rvce bangalore"
    assert normalize_org_name("BITS Pilani") == "bits pilani"

    person = ExtractedPerson(
        full_name="Test Person",
        current_org="IITD",
        alumni_orgs=["RVCE", "Razorpay"],
    )
    normalized = extract_normalized_orgs(person)
    assert "iit delhi" in normalized
    assert "rvce bangalore" in normalized
    assert "razorpay" in normalized


def test_calculate_name_similarity():
    # Exact match
    assert calculate_name_similarity("Rahul Sharma", "Rahul Sharma") == 1.0

    # Initial prefix match boost
    sim_initial = calculate_name_similarity("R. Sharma", "Rahul Sharma")
    assert sim_initial >= 0.88

    # Unrelated name
    sim_unrelated = calculate_name_similarity("Zoya Khan", "Rahul Sharma")
    assert sim_unrelated < 0.55


@pytest.mark.asyncio
async def test_tier1_deterministic_exact_match():
    session = MockAsyncSession()
    existing_id = uuid4()
    existing_person = PersonStaging(
        uid=existing_id,
        full_name="Rahul Sharma",
        email="rahul@razorpay.com",
        current_org="Razorpay",
        alumni_orgs=["IIT Bombay"],
        reachability_tier=2,
        trust_score=50.0,
    )
    session.records.append(existing_person)

    # Incoming record has initial and exact email
    incoming = ExtractedPerson(
        full_name="R. S.",
        email="rahul@razorpay.com",
        current_role="Staff Architect",
    )
    result = await resolve_person(session, incoming, uuid4())

    assert result.action == ResolutionAction.AUTO_MERGE
    assert result.confidence_score == 1.0
    assert result.matched_uid == existing_id
    assert existing_person.current_role == "Staff Architect"


@pytest.mark.asyncio
async def test_tier2_probabilistic_hitl_queue():
    session = MockAsyncSession()
    existing_id = uuid4()
    anchor = ExtractedPerson(
        full_name="Rahul Sharma",
        current_org="Razorpay",
        alumni_orgs=["IIT Bombay"],
    )
    existing_person = PersonStaging(
        uid=existing_id,
        full_name=anchor.full_name,
        current_org=anchor.current_org,
        alumni_orgs=anchor.alumni_orgs,
        reachability_tier=2,
        trust_score=50.0,
        embedding=embed_person(anchor),
    )
    session.records.append(existing_person)

    # Incoming has name initial ("R. Sharma") and abbreviation ("IITB")
    incoming = ExtractedPerson(
        full_name="R. Sharma",
        alumni_orgs=["IITB"],
    )
    result = await resolve_person(session, incoming, uuid4())

    assert result.action == ResolutionAction.QUEUE_HITL
    assert 0.65 <= result.confidence_score < 0.95
    assert result.matched_uid == existing_id
    assert result.hitl_card is not None
    assert result.hitl_card.subject_a_name == "R. Sharma"
    assert result.hitl_card.subject_b_name == "Rahul Sharma"


@pytest.mark.asyncio
async def test_tier3_new_entity_creation():
    session = MockAsyncSession()
    existing_id = uuid4()
    anchor = ExtractedPerson(
        full_name="Rahul Sharma",
        current_org="Razorpay",
        alumni_orgs=["IIT Bombay"],
    )
    existing_person = PersonStaging(
        uid=existing_id,
        full_name=anchor.full_name,
        current_org=anchor.current_org,
        alumni_orgs=anchor.alumni_orgs,
        reachability_tier=2,
        trust_score=50.0,
        embedding=embed_person(anchor),
    )
    session.records.append(existing_person)

    # Incoming is an entirely distinct person
    incoming = ExtractedPerson(
        full_name="Zoya Khan",
        current_org="Zepto",
        alumni_orgs=["St. Stephens"],
    )
    result = await resolve_person(session, incoming, uuid4())

    assert result.action == ResolutionAction.CREATE_NEW_NODE
    assert result.confidence_score < 0.65
    assert result.matched_uid == incoming.uid


@pytest.mark.asyncio
async def test_bitemporal_job_switch_closing():
    # Only run if Neo4j is available
    neo4j_ready = await verify_neo4j_connectivity()
    if not neo4j_ready:
        pytest.skip("Neo4j instance is not reachable")

    test_uid = uuid4()
    person = ExtractedPerson(
        uid=test_uid,
        full_name="Aarav Mehra",
        current_org="Google",
        reachability_tier=ReachabilityTier.TIER_1_CLOSE,
        trust_score=80.0,
    )

    async with get_neo4j_session() as session:
        # 1. Upsert person
        await session.execute_write(upsert_verified_person, person, True)

        # 2. Add first job at Google (valid_to is None)
        edge1 = ExtractedEdge(
            source_name="Aarav Mehra",
            source_type=EntityType.PERSON,
            target_name="Google",
            target_type=EntityType.ORGANIZATION,
            relation_type=RelationType.WORKS_AT,
            valid_from="2021-06-01",
            valid_to=None,
            evidence_snippet="Joined Google as SWE in 2021",
        )
        await session.execute_write(
            upsert_temporal_edge,
            str(test_uid),
            "Google",
            edge1,
            str(uuid4()),
        )

        active_jobs = await session.execute_read(get_person_active_jobs, str(test_uid))
        active_org_names = [j["org_name"] for j in active_jobs]
        assert "Google" in active_org_names

        # 3. Add second job at OpenAI (active job switch)
        edge2 = ExtractedEdge(
            source_name="Aarav Mehra",
            source_type=EntityType.PERSON,
            target_name="OpenAI",
            target_type=EntityType.ORGANIZATION,
            relation_type=RelationType.WORKS_AT,
            valid_from="2024-10-01",
            valid_to=None,
            evidence_snippet="Recently moved to OpenAI",
        )
        await session.execute_write(
            upsert_temporal_edge,
            str(test_uid),
            "OpenAI",
            edge2,
            str(uuid4()),
        )

        # 4. Verify Google job is closed and OpenAI is active
        active_jobs_after = await session.execute_read(get_person_active_jobs, str(test_uid))
        active_orgs_after = [j["org_name"] for j in active_jobs_after]
        assert active_orgs_after == ["OpenAI"]

        all_jobs = await session.execute_read(get_person_all_jobs, str(test_uid))
        google_job = next(j for j in all_jobs if j["org_name"] == "Google")
        openai_job = next(j for j in all_jobs if j["org_name"] == "OpenAI")

        assert google_job["valid_to"] is not None
        assert openai_job["valid_to"] is None
