"""Neo4j Cypher queries for the bi-temporal relationship graph core.

Supports:
- Verified and unverified Person and Organization node upserts.
- Bi-temporal edge creation with confidence, validity periods, and provenance.
- INV-01: Automatic closing of old WORKS_AT edges upon job transitions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neo4j import AsyncTransaction

from src.contracts.schema import (
    EntityType,
    ExtractedEdge,
    ExtractedOrganization,
    ExtractedPerson,
    RelationType,
)

# Allowed relation types for parameterized Cypher query templating
ALLOWED_RELATION_TYPES = {rel.value for rel in RelationType}


async def upsert_organization(
    tx: AsyncTransaction,
    org: ExtractedOrganization | str,
    org_type: str = "company",
    location_city: Optional[str] = None,
) -> str:
    """Upsert an Organization node into Neo4j."""
    if isinstance(org, ExtractedOrganization):
        name = org.name.strip()
        org_type = org.org_type
        location_city = org.location_city
    else:
        name = str(org).strip()

    cypher = """
    MERGE (o:Organization {name: $name})
    ON CREATE SET
        o.org_type = $org_type,
        o.location_city = $location_city,
        o.created_at = datetime(),
        o.updated_at = datetime()
    ON MATCH SET
        o.org_type = coalesce($org_type, o.org_type),
        o.location_city = coalesce($location_city, o.location_city),
        o.updated_at = datetime()
    RETURN o.name AS name
    """
    result = await tx.run(
        cypher,
        name=name,
        org_type=org_type,
        location_city=location_city,
    )
    record = await result.single()
    return record["name"] if record else name


async def upsert_verified_person(
    tx: AsyncTransaction,
    person: ExtractedPerson,
    verified: bool = True,
) -> str:
    """Upsert a Person node into Neo4j with full bi-temporal and reachability metadata."""
    cypher = """
    MERGE (p:Person {uid: $uid})
    ON CREATE SET
        p.full_name = $full_name,
        p.current_org = $current_org,
        p.current_role = $current_role,
        p.location_city = $location_city,
        p.reachability_tier = $reachability_tier,
        p.trust_score = $trust_score,
        p.verified = $verified,
        p.aliases = $aliases,
        p.created_at = datetime(),
        p.updated_at = datetime()
    ON MATCH SET
        p.full_name = coalesce($full_name, p.full_name),
        p.current_org = coalesce($current_org, p.current_org),
        p.current_role = coalesce($current_role, p.current_role),
        p.location_city = coalesce($location_city, p.location_city),
        p.reachability_tier = coalesce($reachability_tier, p.reachability_tier),
        p.trust_score = coalesce($trust_score, p.trust_score),
        p.verified = CASE WHEN $verified THEN true ELSE p.verified END,
        p.aliases = $aliases,
        p.updated_at = datetime()
    RETURN p.uid AS uid
    """
    uid_str = str(person.uid)
    result = await tx.run(
        cypher,
        uid=uid_str,
        full_name=person.full_name,
        current_org=person.current_org,
        current_role=person.current_role,
        location_city=person.location_city,
        reachability_tier=person.reachability_tier.value,
        trust_score=float(person.trust_score),
        verified=verified,
        aliases=person.aliases or [],
    )
    record = await result.single()
    return record["uid"] if record else uid_str


async def upsert_temporal_edge(
    tx: AsyncTransaction,
    source_uid: str,
    target_id: str,
    edge: ExtractedEdge,
    episode_id: str,
    verified: bool = True,
    current_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Upsert a directed temporal edge with bi-temporal validity and job transition closing."""
    rel_type_val = edge.relation_type.value
    if rel_type_val not in ALLOWED_RELATION_TYPES:
        raise ValueError(f"Invalid relation type: {rel_type_val}")

    if not current_date:
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # -------------------------------------------------------------
    # Case A: Target is an Organization (e.g. WORKS_AT, STUDIED_AT)
    # -------------------------------------------------------------
    if (
        edge.target_type == EntityType.ORGANIZATION
        or edge.relation_type in {RelationType.WORKS_AT, RelationType.STUDIED_AT}
    ):
        target_org_name = target_id.strip()

        # Rule INV-01: Close previous active WORKS_AT edge if moving to a new org
        if edge.relation_type == RelationType.WORKS_AT and edge.valid_to is None:
            close_old_job_cypher = """
            MATCH (p:Person {uid: $source_uid})-[old_r:WORKS_AT]->(old_org:Organization)
            WHERE old_org.name <> $target_org_name AND old_r.valid_to IS NULL
            SET old_r.valid_to = $current_date,
                old_r.updated_at = datetime()
            RETURN count(old_r) AS closed_count
            """
            await tx.run(
                close_old_job_cypher,
                source_uid=str(source_uid),
                target_org_name=target_org_name,
                current_date=current_date,
            )

        # Merge target Organization and create temporal edge
        upsert_edge_cypher = f"""
        MATCH (p:Person {{uid: $source_uid}})
        MERGE (o:Organization {{name: $target_org_name}})
        MERGE (p)-[r:{rel_type_val}]->(o)
        ON CREATE SET
            r.valid_from = $valid_from,
            r.valid_to = $valid_to,
            r.confidence_score = $confidence_score,
            r.strength = $strength,
            r.source_episode_id = $episode_id,
            r.evidence_snippet = $evidence_snippet,
            r.verified = $verified,
            r.created_at = datetime(),
            r.updated_at = datetime()
        ON MATCH SET
            r.valid_from = coalesce($valid_from, r.valid_from),
            r.valid_to = $valid_to,
            r.confidence_score = $confidence_score,
            r.strength = $strength,
            r.source_episode_id = $episode_id,
            r.evidence_snippet = $evidence_snippet,
            r.verified = CASE WHEN $verified THEN true ELSE r.verified END,
            r.updated_at = datetime()
        RETURN type(r) AS rel_type, r.valid_from AS valid_from, r.valid_to AS valid_to
        """
        result = await tx.run(
            upsert_edge_cypher,
            source_uid=str(source_uid),
            target_org_name=target_org_name,
            valid_from=edge.valid_from,
            valid_to=edge.valid_to,
            confidence_score=float(edge.confidence_score),
            strength=float(edge.strength),
            episode_id=str(episode_id),
            evidence_snippet=edge.evidence_snippet,
            verified=verified,
        )
        record = await result.single()
        return dict(record) if record else {}

    # -------------------------------------------------------------
    # Case B: Target is a Person
    # -------------------------------------------------------------
    target_person_uid = target_id.strip()
    upsert_person_edge_cypher = f"""
    MATCH (p1:Person {{uid: $source_uid}})
    MERGE (p2:Person {{uid: $target_person_uid}})
    ON CREATE SET
        p2.full_name = $target_name,
        p2.verified = false,
        p2.reachability_tier = 2,
        p2.trust_score = 40.0,
        p2.created_at = datetime(),
        p2.updated_at = datetime()
    MERGE (p1)-[r:{rel_type_val}]->(p2)
    ON CREATE SET
        r.valid_from = $valid_from,
        r.valid_to = $valid_to,
        r.confidence_score = $confidence_score,
        r.strength = $strength,
        r.source_episode_id = $episode_id,
        r.evidence_snippet = $evidence_snippet,
        r.verified = $verified,
        r.created_at = datetime(),
        r.updated_at = datetime()
    ON MATCH SET
        r.valid_from = coalesce($valid_from, r.valid_from),
        r.valid_to = $valid_to,
        r.confidence_score = $confidence_score,
        r.strength = $strength,
        r.source_episode_id = $episode_id,
        r.evidence_snippet = $evidence_snippet,
        r.verified = CASE WHEN $verified THEN true ELSE r.verified END,
        r.updated_at = datetime()
    RETURN type(r) AS rel_type, r.valid_from AS valid_from, r.valid_to AS valid_to
    """
    result = await tx.run(
        upsert_person_edge_cypher,
        source_uid=str(source_uid),
        target_person_uid=target_person_uid,
        target_name=edge.target_name,
        valid_from=edge.valid_from,
        valid_to=edge.valid_to,
        confidence_score=float(edge.confidence_score),
        strength=float(edge.strength),
        episode_id=str(episode_id),
        evidence_snippet=edge.evidence_snippet,
        verified=verified,
    )
    record = await result.single()
    return dict(record) if record else {}


async def get_person_by_uid(tx: AsyncTransaction, uid: str) -> Optional[Dict[str, Any]]:
    """Fetch a Person node by its UID."""
    cypher = """
    MATCH (p:Person {uid: $uid})
    RETURN p.uid AS uid,
           p.full_name AS full_name,
           p.current_org AS current_org,
           p.current_role AS current_role,
           p.location_city AS location_city,
           p.reachability_tier AS reachability_tier,
           p.trust_score AS trust_score,
           p.verified AS verified
    """
    result = await tx.run(cypher, uid=str(uid))
    record = await result.single()
    return dict(record) if record else None


async def get_person_active_jobs(tx: AsyncTransaction, uid: str) -> List[Dict[str, Any]]:
    """Retrieve all active WORKS_AT edges for a Person."""
    cypher = """
    MATCH (p:Person {uid: $uid})-[r:WORKS_AT]->(o:Organization)
    WHERE r.valid_to IS NULL
    RETURN o.name AS org_name, r.valid_from AS valid_from, r.confidence_score AS confidence_score
    """
    result = await tx.run(cypher, uid=str(uid))
    records = await result.data()
    return records


async def get_person_all_jobs(tx: AsyncTransaction, uid: str) -> List[Dict[str, Any]]:
    """Retrieve all WORKS_AT edges (both active and historical) for a Person."""
    cypher = """
    MATCH (p:Person {uid: $uid})-[r:WORKS_AT]->(o:Organization)
    RETURN o.name AS org_name,
           r.valid_from AS valid_from,
           r.valid_to AS valid_to,
           r.evidence_snippet AS evidence_snippet
    ORDER BY r.valid_from DESC
    """
    result = await tx.run(cypher, uid=str(uid))
    records = await result.data()
    return records
