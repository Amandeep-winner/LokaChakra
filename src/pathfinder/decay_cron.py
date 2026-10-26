"""Module F Relationship Decay Cron.

Executes nightly exponential trust decay on Tier 1 and Tier 2 connections
and detects top-degree network bridges whose trust scores have dropped below
the critical threshold.
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
import structlog
from neo4j import AsyncSession

from src.db.neo4j_client import get_neo4j_driver

logger = structlog.get_logger(__name__)


def calculate_decayed_trust(
    initial_trust: float,
    days_elapsed: float,
    decay_rate: float = 0.008,
    min_trust: float = 10.0,
) -> float:
    """Calculate decayed trust score using exponential decay formula.

    T_new = max(min_trust, T_0 * exp(-decay_rate * delta_days))
    """
    if days_elapsed <= 0:
        return initial_trust

    decayed = initial_trust * math.exp(-decay_rate * days_elapsed)
    return round(max(min_trust, decayed), 2)


async def apply_trust_decay(
    session: AsyncSession,
    reference_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Decay trust scores for all Tier 1 and Tier 2 individuals in Neo4j

    based on days elapsed since last_contacted_date.
    """
    if reference_date is None:
        ref_dt = datetime.now(timezone.utc)
    else:
        ref_dt = reference_date if reference_date.tzinfo else reference_date.replace(tzinfo=timezone.utc)

    # Fetch all Tier 1 and Tier 2 persons
    fetch_cypher = """
    MATCH (p:Person)
    WHERE p.reachability_tier IN [1, 2] AND p.full_name <> 'SELF_USER'
    RETURN p.uid AS uid, p.full_name AS full_name, p.trust_score AS trust_score,
           p.last_contacted_date AS last_contacted_date, p.created_at AS created_at
    """
    res = await session.run(fetch_cypher)
    records = await res.data()

    updated_count = 0
    decay_details: List[Dict[str, Any]] = []

    for rec in records:
        uid = rec["uid"]
        name = rec["full_name"]
        t_0 = float(rec["trust_score"]) if rec["trust_score"] is not None else 50.0

        raw_contact = rec["last_contacted_date"] or rec["created_at"]
        if raw_contact:
            if isinstance(raw_contact, str):
                try:
                    last_dt = datetime.fromisoformat(raw_contact.replace("Z", "+00:00"))
                except ValueError:
                    last_dt = ref_dt
            elif isinstance(raw_contact, datetime):
                last_dt = raw_contact if raw_contact.tzinfo else raw_contact.replace(tzinfo=timezone.utc)
            else:
                last_dt = ref_dt
        else:
            last_dt = ref_dt

        delta_days = max(0.0, (ref_dt - last_dt).total_seconds() / 86400.0)
        t_new = calculate_decayed_trust(t_0, delta_days)

        if t_new != t_0:
            update_cypher = """
            MATCH (p:Person {uid: $uid})
            SET p.trust_score = $t_new,
                p.last_decay_calculated_at = $decay_time
            """
            await session.run(
                update_cypher,
                {
                    "uid": uid,
                    "t_new": t_new,
                    "decay_time": ref_dt.isoformat(),
                },
            )
            updated_count += 1
            decay_details.append(
                {
                    "uid": uid,
                    "full_name": name,
                    "old_trust": t_0,
                    "new_trust": t_new,
                    "delta_days": round(delta_days, 1),
                }
            )

    logger.info("apply_trust_decay_completed", updated_count=updated_count, total_evaluated=len(records))
    return {
        "status": "success",
        "evaluated_count": len(records),
        "updated_count": updated_count,
        "decay_details": decay_details,
    }


async def find_decayed_bridge_alerts(
    session: AsyncSession,
    trust_threshold: float = 55.0,
    top_percentile: float = 0.15,
) -> List[Dict[str, Any]]:
    """Identify nodes in top percentile of network degree/bridge connectivity

    whose trust_score drops below trust_threshold.
    """
    degree_cypher = """
    MATCH (p:Person)
    WHERE p.reachability_tier IN [1, 2] AND p.full_name <> 'SELF_USER'
    OPTIONAL MATCH (p)-[r]-()
    WITH p, count(r) AS degree
    ORDER BY degree DESC
    RETURN p.uid AS uid, p.full_name AS full_name, p.trust_score AS trust_score,
           p.reachability_tier AS reachability_tier, degree
    """
    res = await session.run(degree_cypher)
    records = await res.data()

    if not records:
        return []

    cutoff_index = max(1, math.ceil(len(records) * top_percentile))
    top_bridges = records[:cutoff_index]

    alerts: List[Dict[str, Any]] = []
    for bridge in top_bridges:
        raw_trust = bridge["trust_score"]
        trust_score = float(raw_trust) if raw_trust is not None else 50.0
        if trust_score < trust_threshold:
            alerts.append(
                {
                    "uid": bridge["uid"],
                    "full_name": bridge["full_name"],
                    "reachability_tier": bridge["reachability_tier"],
                    "degree": bridge["degree"],
                    "trust_score": trust_score,
                    "alert_message": (
                        f"Network bridge warning: {bridge['full_name']} (degree {bridge['degree']}) "
                        f"has decayed to trust score {trust_score:.1f} (below threshold {trust_threshold}). "
                        f"Consider scheduling a re-connection note."
                    ),
                }
            )

    return alerts


async def run_nightly_decay_job() -> Dict[str, Any]:
    """Execute complete nightly decay procedure and generate alerts."""
    driver = get_neo4j_driver()
    async with driver.session() as session:
        decay_result = await apply_trust_decay(session)
        bridge_alerts = await find_decayed_bridge_alerts(session)

    return {
        "decay_summary": decay_result,
        "bridge_alerts": bridge_alerts,
        "alert_count": len(bridge_alerts),
    }
