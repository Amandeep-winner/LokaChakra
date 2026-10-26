"""Module F Pathfinding Engine: Dynamic Weighted Dijkstra Routing.

Calculates the warmest path to a target person or organization by minimizing
edge traversal costs based on target node trust score, reachability tier,
and edge confidence.
"""

from typing import Any, Dict, List, Optional
import math
from neo4j import AsyncSession

from src.contracts.schema import PathStep, WarmPathResponse


def calculate_edge_cost(
    u_props: Dict[str, Any],
    v_props: Dict[str, Any],
    rel_props: Dict[str, Any],
) -> float:
    """Calculate dynamic edge traversal cost between u and v.

    Formula:
    edge_cost(u, v) = (100.0 / max(trust_score_v, 5.0)) * tier_multiplier_v * (1.0 / max(confidence_score_{u,v}, 0.1))
    Where:
    - tier_multiplier_v = 1.0 for Tier 1
    - tier_multiplier_v = 1.8 for Tier 2
    - tier_multiplier_v = 3.0 for Tier 3
    """
    raw_trust = v_props.get("trust_score")
    trust_score_v = float(raw_trust) if raw_trust is not None else 50.0

    raw_tier = v_props.get("reachability_tier")
    if raw_tier == 1:
        tier_multiplier_v = 1.0
    elif raw_tier == 2:
        tier_multiplier_v = 1.8
    elif raw_tier == 3:
        tier_multiplier_v = 3.0
    else:
        tier_multiplier_v = 1.0

    raw_conf = rel_props.get("confidence_score")
    confidence_score = float(raw_conf) if raw_conf is not None else 1.0

    trust_factor = 100.0 / max(trust_score_v, 5.0)
    conf_factor = 1.0 / max(confidence_score, 0.1)

    return trust_factor * tier_multiplier_v * conf_factor


def generate_warm_intro_script(steps: List[PathStep]) -> str:
    """Generate an actionable warm intro request message for the first Tier-1 bridge."""
    if len(steps) < 2:
        return ""

    bridge_name = steps[1].node_name
    target_node = steps[-1]
    target_name = target_node.node_name
    target_type = target_node.node_type

    target_suffix = f" at {target_name}" if target_type == "Organization" else f" ({target_name})"

    return (
        f"Hi {bridge_name}, hope you're doing well! "
        f"I noticed you are connected to {target_name}{target_suffix if target_type == 'Organization' else ''}. "
        f"I am currently exploring opportunities in this domain and would value a brief warm introduction "
        f"if you're open to it. Let me know if you can connect us!"
    )


async def find_warmest_path(session: AsyncSession, target_query: str) -> WarmPathResponse:
    """Locate target person or organization and compute the minimum-cost verified path

    from SELF_USER to the target up to 4 hops.
    """
    clean_query = target_query.strip()
    if not clean_query:
        return WarmPathResponse(
            target_query=target_query,
            total_cost=0.0,
            hop_count=0,
            steps=[],
            recommended_intro_script="",
        )

    # Cypher query searching 1 to 4 hops from SELF_USER to target person or organization
    cypher = """
    MATCH path = (start:Person {full_name: 'SELF_USER'})-[*1..4]-(target)
    WHERE (target:Person OR target:Organization)
      AND (
        toLower(target.full_name) CONTAINS toLower($target_query)
        OR toLower(target.name) CONTAINS toLower($target_query)
      )
      AND all(r IN relationships(path) WHERE coalesce(r.verified, true) = true)
    RETURN
      [n IN nodes(path) | {
        labels: labels(n),
        props: properties(n)
      }] AS path_nodes,
      [r IN relationships(path) | {
        type: type(r),
        props: properties(r)
      }] AS path_rels
    """

    result = await session.run(cypher, {"target_query": clean_query})
    records = await result.data()

    if not records:
        return WarmPathResponse(
            target_query=target_query,
            total_cost=0.0,
            hop_count=0,
            steps=[],
            recommended_intro_script="",
        )

    best_cost = math.inf
    best_steps: List[PathStep] = []

    for record in records:
        path_nodes = record["path_nodes"]
        path_rels = record["path_rels"]

        # Calculate path cost
        current_cost = 0.0
        candidate_steps: List[PathStep] = []

        num_nodes = len(path_nodes)
        for i in range(num_nodes):
            n = path_nodes[i]
            props = n["props"]
            labels = n["labels"]
            is_org = "Organization" in labels
            node_type = "Organization" if is_org else "Person"
            node_name = props.get("name") if is_org else props.get("full_name", "Unknown")
            node_uid = str(props.get("uid", node_name))

            reachability_tier = props.get("reachability_tier")
            raw_trust = props.get("trust_score")
            trust_score = float(raw_trust) if raw_trust is not None else None

            # Relationship to next node
            rel_to_next = None
            edge_conf = None
            if i < len(path_rels):
                r = path_rels[i]
                rel_to_next = r["type"]
                r_props = r["props"]
                raw_edge_conf = r_props.get("confidence_score")
                edge_conf = float(raw_edge_conf) if raw_edge_conf is not None else 1.0

                # Compute step cost from i to i+1
                next_props = path_nodes[i + 1]["props"]
                step_cost = calculate_edge_cost(props, next_props, r_props)
                current_cost += step_cost

            candidate_steps.append(
                PathStep(
                    node_uid=node_uid,
                    node_name=node_name,
                    node_type=node_type,
                    reachability_tier=reachability_tier,
                    trust_score=trust_score,
                    relation_to_next=rel_to_next,
                    edge_confidence=edge_conf,
                )
            )

        if current_cost < best_cost:
            best_cost = current_cost
            best_steps = candidate_steps

    intro_script = generate_warm_intro_script(best_steps)
    hop_count = max(0, len(best_steps) - 1)

    return WarmPathResponse(
        target_query=target_query,
        total_cost=round(best_cost, 4) if best_cost < math.inf else 0.0,
        hop_count=hop_count,
        steps=best_steps,
        recommended_intro_script=intro_script,
    )
