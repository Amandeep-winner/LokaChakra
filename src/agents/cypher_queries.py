from typing import List, Dict, Any, Optional
import structlog
from neo4j import AsyncDriver

logger = structlog.get_logger(__name__)

OPEN_TRIANGLE_QUERY = """
MATCH (u:Person {full_name: 'SELF_USER'})-[:KNOWS|BATCHMATE_OF|ROOMMATE_OF|WORKED_WITH]->(friend:Person)
WHERE friend.reachability_tier = 1
MATCH (friend)-[r1:WORKS_AT|STUDIED_AT]->(org:Organization)<-[r2:WORKS_AT|STUDIED_AT]-(target:Person)
WHERE friend.uid <> target.uid
  AND target.full_name <> 'SELF_USER'
  AND NOT (friend)-[:KNOWS|BATCHMATE_OF|ROOMMATE_OF|WORKED_WITH|CO_AUTHORED_WITH]-(target)
RETURN friend.uid AS friend_uid, friend.full_name AS friend_name,
       target.uid AS target_uid, target.full_name AS target_name,
       org.name AS shared_org
LIMIT $limit
"""

ALLOWED_RELATION_TYPES = {
    "CO_AUTHORED_WITH": "CO_AUTHORED_WITH",
    "BATCHMATE_OF": "BATCHMATE_OF",
    "WORKED_WITH": "WORKED_WITH",
    "ROOMMATE_OF": "ROOMMATE_OF",
    "KNOWS": "KNOWS",
}


async def find_open_triangles(
    driver: AsyncDriver,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Finds open triangles where a Tier-1 friend and a Tier-2/3 target shared an organization
    (College or Company) but currently have no direct relationship edge between them.
    """
    async with driver.session() as session:
        result = await session.run(OPEN_TRIANGLE_QUERY, limit=limit)
        records = await result.data()
        logger.info("Found open triangles", count=len(records))
        return records


async def commit_bridge_edge(
    driver: AsyncDriver,
    friend_uid: str,
    target_uid: str,
    relation_type: str = "WORKED_WITH",
    confidence_score: float = 1.0,
    source_episode_id: Optional[str] = None,
) -> bool:
    """
    Creates or merges a verified relationship edge between friend and target
    in Neo4j with verified=true, confidence_score=1.0, and source_episode_id.
    """
    rel_type = ALLOWED_RELATION_TYPES.get(relation_type.upper(), "KNOWS")
    cypher_query = f"""
    MATCH (source:Person {{uid: $friend_uid}})
    MATCH (target:Person {{uid: $target_uid}})
    MERGE (source)-[r:{rel_type}]->(target)
    SET r.verified = true,
        r.confidence_score = $confidence_score,
        r.source_episode_id = $source_episode_id,
        r.updated_at = datetime()
    RETURN count(r) AS created_count
    """
    async with driver.session() as session:
        result = await session.run(
            cypher_query,
            friend_uid=friend_uid,
            target_uid=target_uid,
            confidence_score=confidence_score,
            source_episode_id=source_episode_id,
        )
        record = await result.single()
        created = record["created_count"] > 0 if record else False
        logger.info(
            "Committed verified bridge edge",
            friend_uid=friend_uid,
            target_uid=target_uid,
            relation_type=rel_type,
            created=created,
        )
        return created
