"""Graph intelligence and pathfinding API endpoints for Lokachakra."""

from typing import Any, Dict, List, Optional
import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.contracts.schema import WarmPathResponse
from src.db.neo4j_client import get_neo4j_driver
from src.pathfinder.routing import find_warmest_path

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/graph", tags=["Graph"])


class CytoscapeElement(BaseModel):
    data: Dict[str, Any]


class CytoscapeMapResponse(BaseModel):
    nodes: List[CytoscapeElement]
    edges: List[CytoscapeElement]


class CareerHistoryItem(BaseModel):
    organization: str
    role: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_active: bool = True
    evidence_snippet: Optional[str] = None


class PersonConnectionItem(BaseModel):
    target_name: str
    target_uid: Optional[str] = None
    target_type: str = "Person"
    relation: str
    confidence_score: float
    verified: bool


class PersonDossierResponse(BaseModel):
    uid: str
    full_name: str
    reachability_tier: Optional[int] = None
    trust_score: float = 50.0
    current_org: Optional[str] = None
    current_role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    career_history: List[CareerHistoryItem] = Field(default_factory=list)
    connections: List[PersonConnectionItem] = Field(default_factory=list)
    evidence_snippets: List[str] = Field(default_factory=list)
    recommended_intro: Optional[str] = None


@router.get(
    "/map",
    response_model=CytoscapeMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve graph topology filtered by tier, formatted for Cytoscape.js",
)
async def get_graph_map(
    tier_max: int = Query(3, ge=1, le=4, description="Maximum reachability tier to return"),
) -> CytoscapeMapResponse:
    """Returns nodes and edges up to the specified reachability tier in Cytoscape.js format."""
    driver = get_neo4j_driver()
    nodes_map: Dict[str, CytoscapeElement] = {}
    edges_list: List[CytoscapeElement] = []

    cypher = """
    MATCH (n)
    WHERE (n:Person AND coalesce(n.reachability_tier, 1) <= $tier_max) OR n:Organization
    OPTIONAL MATCH (n)-[r]->(m)
    WHERE ((m:Person AND coalesce(m.reachability_tier, 1) <= $tier_max) OR m:Organization)
      AND coalesce(r.verified, true) = true
    RETURN
      properties(n) AS n_props,
      labels(n) AS n_labels,
      properties(r) AS r_props,
      type(r) AS r_type,
      properties(m) AS m_props,
      labels(m) AS m_labels
    """

    try:
        async with driver.session() as session:
            result = await session.run(cypher, {"tier_max": tier_max})
            records = await result.data()

            for rec in records:
                n_props = rec.get("n_props")
                if not n_props:
                    continue
                n_labels = rec.get("n_labels", [])
                is_n_org = "Organization" in n_labels
                n_id = str(n_props.get("uid") or n_props.get("name") or n_props.get("full_name"))
                n_name = n_props.get("name") if is_n_org else n_props.get("full_name", "Unknown")

                if n_id not in nodes_map:
                    nodes_map[n_id] = CytoscapeElement(
                        data={
                            "id": n_id,
                            "label": n_name,
                            "type": "Organization" if is_n_org else "Person",
                            "tier": n_props.get("reachability_tier"),
                            "trust_score": n_props.get("trust_score", 50.0),
                            "current_org": n_props.get("current_org"),
                            "current_role": n_props.get("current_role"),
                        }
                    )

                # Process edge & target if present
                r_props = rec.get("r_props")
                m_props = rec.get("m_props")
                if r_props is not None and m_props:
                    m_labels = rec.get("m_labels", [])
                    is_m_org = "Organization" in m_labels
                    m_id = str(m_props.get("uid") or m_props.get("name") or m_props.get("full_name"))
                    m_name = m_props.get("name") if is_m_org else m_props.get("full_name", "Unknown")

                    if m_id not in nodes_map:
                        nodes_map[m_id] = CytoscapeElement(
                            data={
                                "id": m_id,
                                "label": m_name,
                                "type": "Organization" if is_m_org else "Person",
                                "tier": m_props.get("reachability_tier"),
                                "trust_score": m_props.get("trust_score", 50.0),
                                "current_org": m_props.get("current_org"),
                                "current_role": m_props.get("current_role"),
                            }
                        )

                    r_type = rec.get("r_type", "RELATED_TO")
                    edge_id = f"{n_id}-{r_type}-{m_id}"

                    edges_list.append(
                        CytoscapeElement(
                            data={
                                "id": edge_id,
                                "source": n_id,
                                "target": m_id,
                                "label": r_type,
                                "confidence": r_props.get("confidence_score", 1.0),
                                "verified": r_props.get("verified", True),
                                "valid_from": r_props.get("valid_from"),
                                "valid_to": r_props.get("valid_to"),
                            }
                        )
                    )

        return CytoscapeMapResponse(
            nodes=list(nodes_map.values()),
            edges=edges_list,
        )
    except Exception as exc:
        logger.error("Failed to fetch graph map", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch graph map: {str(exc)}",
        )


@router.get(
    "/path",
    response_model=WarmPathResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute lowest-cost warmest path from SELF_USER to target",
)
async def get_warm_path(
    target: str = Query(..., min_length=1, description="Target person or organization name"),
) -> WarmPathResponse:
    """Finds the lowest-cost path from SELF_USER to the given target up to 4 hops."""
    driver = get_neo4j_driver()
    try:
        async with driver.session() as session:
            response = await find_warmest_path(session, target)
            return response
    except Exception as exc:
        logger.error("Pathfinding query failed", target=target, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pathfinding failed: {str(exc)}",
        )


@router.get(
    "/person/{uid}",
    response_model=PersonDossierResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch complete person dossier with temporal career history and provenance",
)
async def get_person_dossier(uid: str) -> PersonDossierResponse:
    """Fetches full details, temporal career history, and connected relationships for a person."""
    driver = get_neo4j_driver()
    cypher = """
    MATCH (p:Person)
    WHERE p.uid = $uid OR p.full_name = $uid
    OPTIONAL MATCH (p)-[r]-(m)
    RETURN
      properties(p) AS p_props,
      labels(p) AS p_labels,
      properties(r) AS r_props,
      type(r) AS r_type,
      properties(m) AS m_props,
      labels(m) AS m_labels
    """

    try:
        async with driver.session() as session:
            result = await session.run(cypher, {"uid": uid})
            records = await result.data()

            if not records or not records[0].get("p_props"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Person with UID or name '{uid}' not found",
                )

            person_props = records[0]["p_props"]
            full_name = person_props.get("full_name", "Unknown")
            reachability_tier = person_props.get("reachability_tier")
            raw_trust = person_props.get("trust_score")
            trust_score = float(raw_trust) if raw_trust is not None else 50.0

            career_history: List[CareerHistoryItem] = []
            connections: List[PersonConnectionItem] = []
            snippets: List[str] = []

            for rec in records:
                r_props = rec.get("r_props")
                m_props = rec.get("m_props")
                if r_props is None or not m_props:
                    continue

                r_type = rec.get("r_type", "RELATED_TO")
                m_labels = rec.get("m_labels", [])
                is_org = "Organization" in m_labels

                evidence = r_props.get("evidence_snippet")
                if evidence and evidence not in snippets:
                    snippets.append(evidence)

                if r_type == "WORKS_AT" and is_org:
                    career_history.append(
                        CareerHistoryItem(
                            organization=m_props.get("name", "Unknown Org"),
                            role=r_props.get("role", person_props.get("current_role")),
                            valid_from=r_props.get("valid_from"),
                            valid_to=r_props.get("valid_to"),
                            is_active=(r_props.get("valid_to") is None),
                            evidence_snippet=evidence,
                        )
                    )
                else:
                    target_name = m_props.get("name") if is_org else m_props.get("full_name", "Unknown")
                    connections.append(
                        PersonConnectionItem(
                            target_name=target_name,
                            target_uid=str(m_props.get("uid") or target_name),
                            target_type="Organization" if is_org else "Person",
                            relation=r_type,
                            confidence_score=float(r_props.get("confidence_score", 1.0)),
                            verified=bool(r_props.get("verified", True)),
                        )
                    )

            recommended_intro = (
                f"Hi {full_name}, hope all is well! I noticed your recent work and wanted to reconnect..."
            )

            return PersonDossierResponse(
                uid=str(person_props.get("uid") or uid),
                full_name=full_name,
                reachability_tier=reachability_tier,
                trust_score=trust_score,
                current_org=person_props.get("current_org"),
                current_role=person_props.get("current_role"),
                email=person_props.get("email"),
                phone=person_props.get("phone"),
                career_history=career_history,
                connections=connections,
                evidence_snippets=snippets,
                recommended_intro=recommended_intro,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to retrieve person dossier", uid=uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve dossier: {str(exc)}",
        )
