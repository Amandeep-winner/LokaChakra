"""Test suite for Module F: Dynamic Weighted Dijkstra Pathfinding, Trust Decay,

and API endpoints.
"""

from datetime import datetime, timezone
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from src.api.main import app
from src.contracts.schema import WarmPathResponse
from src.db.neo4j_client import get_neo4j_driver, close_neo4j_driver
from src.pathfinder.decay_cron import (
    apply_trust_decay,
    calculate_decayed_trust,
    find_decayed_bridge_alerts,
)
from src.pathfinder.routing import calculate_edge_cost, find_warmest_path


def test_edge_cost_formula():
    """Verifies edge_cost = (100 / max(trust, 5)) * tier_mult * (1 / max(conf, 0.1))."""
    # Tier 1 with trust 95, conf 1.0
    cost_t1 = calculate_edge_cost(
        u_props={"full_name": "SELF_USER"},
        v_props={"full_name": "Rohan", "trust_score": 95.0, "reachability_tier": 1},
        rel_props={"confidence_score": 1.0},
    )
    expected_t1 = (100.0 / 95.0) * 1.0 * (1.0 / 1.0)
    assert abs(cost_t1 - expected_t1) < 1e-4

    # Tier 2 with trust 20, conf 1.0 -> tier_mult = 1.8
    cost_t2 = calculate_edge_cost(
        u_props={"full_name": "SELF_USER"},
        v_props={"full_name": "Cold Acquaintance", "trust_score": 20.0, "reachability_tier": 2},
        rel_props={"confidence_score": 1.0},
    )
    expected_t2 = (100.0 / 20.0) * 1.8 * (1.0 / 1.0)
    assert abs(cost_t2 - expected_t2) < 1e-4
    assert cost_t2 > cost_t1


def test_decay_formula_and_floor():
    """Verifies T_new = max(10.0, T_0 * exp(-0.008 * delta_days))."""
    # 0 days elapsed -> no decay
    assert calculate_decayed_trust(80.0, 0) == 80.0

    # 100 days elapsed -> 80 * exp(-0.8) ~= 35.95
    decayed_100 = calculate_decayed_trust(80.0, 100)
    assert 35.0 < decayed_100 < 37.0

    # 1000 days elapsed -> hits floor of 10.0
    decayed_1000 = calculate_decayed_trust(80.0, 1000)
    assert decayed_1000 == 10.0


@pytest.mark.asyncio
async def test_pathfinder_warmest_path_selection():
    """Seeds two competing paths to 'Peak XV':

    Path A (Low Trust): SELF_USER -> Cold Acquaintance (trust=20, tier=2) -> Siddharth -> Peak XV
    Path B (High Trust): SELF_USER -> Best Friend Rohan (trust=95, tier=1) -> Siddharth -> Peak XV
    Asserts find_warmest_path routes through 'Best Friend Rohan' with lower total cost.
    """
    driver = get_neo4j_driver()
    rohan_uid = str(uuid.uuid4())
    cold_uid = str(uuid.uuid4())
    siddharth_uid = str(uuid.uuid4())
    org_uid = str(uuid.uuid4())

    async with driver.session() as session:
        # Clean up any conflicting test nodes
        await session.run("MATCH (n:Person {full_name: 'Best Friend Rohan'}) DETACH DELETE n")
        await session.run("MATCH (n:Person {full_name: 'Cold Acquaintance'}) DETACH DELETE n")
        await session.run("MATCH (n:Person {full_name: 'Siddharth Path Target'}) DETACH DELETE n")
        await session.run("MATCH (o:Organization {name: 'Peak XV Test'}) DETACH DELETE o")

        # Seed SELF_USER
        await session.run("MERGE (:Person {full_name: 'SELF_USER', reachability_tier: 0, trust_score: 100.0})")

        # Seed Path A intermediate node (Cold Acquaintance: Tier 2, Trust 20.0)
        await session.run(
            """
            CREATE (c:Person {
                uid: $uid,
                full_name: 'Cold Acquaintance',
                reachability_tier: 2,
                trust_score: 20.0
            })
            """,
            {"uid": cold_uid},
        )

        # Seed Path B intermediate node (Best Friend Rohan: Tier 1, Trust 95.0)
        await session.run(
            """
            CREATE (r:Person {
                uid: $uid,
                full_name: 'Best Friend Rohan',
                reachability_tier: 1,
                trust_score: 95.0
            })
            """,
            {"uid": rohan_uid},
        )

        # Seed Siddharth and Peak XV Test
        await session.run(
            """
            CREATE (s:Person {
                uid: $s_uid,
                full_name: 'Siddharth Path Target',
                reachability_tier: 2,
                trust_score: 60.0
            })
            CREATE (o:Organization {
                uid: $o_uid,
                name: 'Peak XV Test',
                org_type: 'firm'
            })
            """,
            {"s_uid": siddharth_uid, "o_uid": org_uid},
        )

        # Connect edges for Path A: SELF -> Cold -> Siddharth -> Peak XV
        await session.run(
            """
            MATCH (u:Person {full_name: 'SELF_USER'})
            MATCH (c:Person {uid: $c_uid})
            MATCH (s:Person {uid: $s_uid})
            MATCH (o:Organization {uid: $o_uid})
            CREATE (u)-[:KNOWS_PERSON {confidence_score: 1.0, verified: true}]->(c)
            CREATE (c)-[:COLLEAGUE_OF {confidence_score: 1.0, verified: true}]->(s)
            CREATE (s)-[:WORKS_AT {confidence_score: 1.0, verified: true}]->(o)
            """,
            {"c_uid": cold_uid, "s_uid": siddharth_uid, "o_uid": org_uid},
        )

        # Connect edges for Path B: SELF -> Rohan -> Siddharth -> Peak XV
        await session.run(
            """
            MATCH (u:Person {full_name: 'SELF_USER'})
            MATCH (r:Person {uid: $r_uid})
            MATCH (s:Person {uid: $s_uid})
            CREATE (u)-[:KNOWS_PERSON {confidence_score: 1.0, verified: true}]->(r)
            CREATE (r)-[:ALUM_OF {confidence_score: 1.0, verified: true}]->(s)
            """,
            {"r_uid": rohan_uid, "s_uid": siddharth_uid},
        )

        # Run pathfinding
        response: WarmPathResponse = await find_warmest_path(session, "Peak XV Test")

        # Clean up test nodes
        await session.run("MATCH (n:Person {uid: $uid}) DETACH DELETE n", {"uid": rohan_uid})
        await session.run("MATCH (n:Person {uid: $uid}) DETACH DELETE n", {"uid": cold_uid})
        await session.run("MATCH (n:Person {uid: $uid}) DETACH DELETE n", {"uid": siddharth_uid})
        await session.run("MATCH (o:Organization {uid: $uid}) DETACH DELETE o", {"uid": org_uid})

    # Assertions
    assert response is not None
    assert response.target_query == "Peak XV Test"
    assert response.hop_count == 3
    step_names = [s.node_name for s in response.steps]

    # Best Friend Rohan must be chosen over Cold Acquaintance
    assert "Best Friend Rohan" in step_names
    assert "Cold Acquaintance" not in step_names
    assert step_names[-1] == "Peak XV Test"

    # Actionable intro script
    assert "Best Friend Rohan" in response.recommended_intro_script
    assert "Peak XV Test" in response.recommended_intro_script

    await close_neo4j_driver()


@pytest.mark.asyncio
async def test_neo4j_trust_decay_and_alerts():
    """Tests live Neo4j decay execution and bridge degree alerting."""
    driver = get_neo4j_driver()
    person_uid = str(uuid.uuid4())

    async with driver.session() as session:
        # Create person with last_contacted_date 120 days ago
        await session.run(
            """
            CREATE (p:Person {
                uid: $uid,
                full_name: 'Decay Target',
                reachability_tier: 1,
                trust_score: 80.0,
                last_contacted_date: '2025-01-01T00:00:00+00:00'
            })
            """,
            {"uid": person_uid},
        )

        # Apply decay with reference date 100 days after
        ref_dt = datetime(2025, 4, 11, tzinfo=timezone.utc)
        decay_res = await apply_trust_decay(session, reference_date=ref_dt)
        assert decay_res["status"] == "success"

        # Check bridge alert function
        alerts = await find_decayed_bridge_alerts(session, trust_threshold=90.0, top_percentile=1.0)
        assert isinstance(alerts, list)

        # Cleanup
        await session.run("MATCH (p:Person {uid: $uid}) DETACH DELETE p", {"uid": person_uid})

    await close_neo4j_driver()


@pytest.mark.asyncio
async def test_fastapi_rest_endpoints():
    """Tests REST API endpoints using httpx AsyncClient."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "ok"

        # Graph map endpoint
        res_map = await client.get("/api/v1/graph/map?tier_max=3")
        assert res_map.status_code == 200
        map_json = res_map.json()
        assert "nodes" in map_json
        assert "edges" in map_json

        # HITL pending endpoint
        res_hitl = await client.get("/api/v1/hitl/pending")
        assert res_hitl.status_code == 200
        assert isinstance(res_hitl.json(), list)

    await close_neo4j_driver()
