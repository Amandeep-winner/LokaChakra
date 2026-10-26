import uuid
from typing import TypedDict, List, Optional, Dict, Any
import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.base import BaseCheckpointSaver

from src.agents.search_tools import execute_osint_queries
from src.agents.cypher_queries import commit_bridge_edge
from src.hitl_bot.notifier import send_hitl_card
from src.db.neo4j_client import get_neo4j_driver
from src.db.postgres import async_session_factory, HITLEvidenceCardModel
from sqlalchemy import select

logger = structlog.get_logger(__name__)


class OSINTState(TypedDict, total=False):
    thread_id: str
    friend_uid: str
    friend_name: str
    target_uid: str
    target_name: str
    shared_org: str
    search_results: List[Dict[str, Any]]
    proposed_relation: str
    confidence_score: float
    evidence_summary: str
    source_urls: List[str]
    card_id: Optional[str]
    human_decision: Optional[str]


async def run_web_recon(state: OSINTState) -> Dict[str, Any]:
    """
    Step 1: Queries SearXNG (and Tavily fallback) for OSINT evidence connecting
    friend and target at shared organization.
    """
    friend_name = state.get("friend_name", "")
    target_name = state.get("target_name", "")
    shared_org = state.get("shared_org", "")

    # If search_results already provided (e.g., injected in tests or pre-computed), preserve them
    existing_results = state.get("search_results")
    if existing_results is not None and len(existing_results) > 0:
        return {"search_results": existing_results}

    results = await execute_osint_queries(
        person_a=friend_name,
        person_b=target_name,
        shared_org=shared_org,
    )
    return {"search_results": results}


def score_hypothesis(state: OSINTState) -> Dict[str, Any]:
    """
    Step 2: Evaluates search snippets for co-authorship, shared clubs, hackathon rosters,
    or overlapping tenure at companies/universities.
    """
    results = state.get("search_results", [])
    friend_name = state.get("friend_name", "").lower()
    target_name = state.get("target_name", "").lower()

    if not results:
        return {
            "proposed_relation": "CONNECTED_TO",
            "confidence_score": 0.20,
            "evidence_summary": "No public OSINT evidence discovered.",
            "source_urls": [],
            "card_id": state.get("card_id") or str(uuid.uuid4()),
        }

    best_score = 0.50
    best_relation = "WORKED_WITH"
    best_summary = ""
    source_urls = []

    paper_keywords = ["co-author", "paper", "ieee", "arxiv", "publication", "proceedings", "conference", "acm"]
    batch_keywords = ["classmate", "batchmate", "roommate", "hostel", "alumni", "department", "graduated", "campus"]
    work_keywords = ["colleague", "coworker", "team", "engineer", "lead", "worked together", "startup", "founder"]

    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        url = r.get("url", "")
        if url and url not in source_urls:
            source_urls.append(url)

        current_score = 0.55
        rel = "WORKED_WITH"

        # Check for co-authorship
        if any(kw in text for kw in paper_keywords):
            current_score = 0.88
            rel = "CO_AUTHORED_WITH"
        elif any(kw in text for kw in batch_keywords):
            current_score = 0.78
            rel = "BATCHMATE_OF"
        elif any(kw in text for kw in work_keywords):
            current_score = 0.75
            rel = "WORKED_WITH"

        # Boost score if both names are mentioned in the same snippet
        friend_tokens = [t for t in friend_name.split() if len(t) > 2]
        target_tokens = [t for t in target_name.split() if len(t) > 2]
        friend_match = any(t in text for t in friend_tokens)
        target_match = any(t in text for t in target_tokens)

        if friend_match and target_match:
            current_score += 0.10

        if current_score > best_score:
            best_score = min(current_score, 0.98)
            best_relation = rel
            best_summary = r.get("snippet", "") or r.get("title", "")

    card_id = state.get("card_id") or str(uuid.uuid4())
    return {
        "proposed_relation": best_relation,
        "confidence_score": best_score,
        "evidence_summary": best_summary or f"Potential {best_relation} connection at {state.get('shared_org', '')}.",
        "source_urls": source_urls,
        "card_id": card_id,
    }


def should_verify(state: OSINTState) -> str:
    """
    Conditional routing: if confidence < 0.50, end without human interruption.
    Otherwise, route to human_verification_gate.
    """
    if state.get("confidence_score", 0.0) < 0.50:
        return END
    return "human_verification_gate"


async def human_verification_gate(state: OSINTState) -> Dict[str, Any]:
    """
    Step 3: Persists HITLEvidenceCard to DB, notifies Telegram HITL bus,
    and pauses execution with interrupt() waiting for human confirmation.
    """
    card_id_str = state.get("card_id") or str(uuid.uuid4())
    thread_id = state.get("thread_id", str(uuid.uuid4()))

    card_data = {
        "card_id": card_id_str,
        "langgraph_thread_id": thread_id,
        "action_type": "HIDDEN_BRIDGE_DISCOVERY",
        "subject_a_uid": state.get("friend_uid"),
        "subject_a_name": state.get("friend_name", ""),
        "subject_b_uid": state.get("target_uid"),
        "subject_b_name": state.get("target_name", ""),
        "proposed_relation": state.get("proposed_relation", "CONNECTED_TO"),
        "confidence_score": state.get("confidence_score", 0.5),
        "evidence_summary": state.get("evidence_summary", ""),
        "source_urls": state.get("source_urls", []),
    }

    # Persist to PostgreSQL if database connection is available
    try:
        async with async_session_factory() as session:
            db_card = HITLEvidenceCardModel(
                card_id=uuid.UUID(card_id_str),
                langgraph_thread_id=thread_id,
                action_type=card_data["action_type"],
                subject_a_uid=uuid.UUID(card_data["subject_a_uid"]) if card_data.get("subject_a_uid") else None,
                subject_a_name=card_data["subject_a_name"],
                subject_b_uid=uuid.UUID(card_data["subject_b_uid"]) if card_data.get("subject_b_uid") else None,
                subject_b_name=card_data["subject_b_name"],
                proposed_relation=card_data["proposed_relation"],
                confidence_score=card_data["confidence_score"],
                evidence_summary=card_data["evidence_summary"],
                source_urls=card_data["source_urls"],
                status="pending_hitl",
            )
            session.add(db_card)
            await session.commit()
    except Exception as exc:
        logger.debug("Database card persistence skipped or unavailable", error=str(exc))

    # Send notification card to Telegram HITL bot
    try:
        await send_hitl_card(card_data)
    except Exception as exc:
        logger.warning("Telegram HITL card notification skipped or failed", error=str(exc))

    # LangGraph interrupt: pauses workflow and waits for Command(resume=decision)
    human_decision = interrupt({
        "card_id": card_id_str,
        "summary": state.get("evidence_summary", ""),
    })

    return {
        "card_id": card_id_str,
        "human_decision": human_decision,
    }


async def commit_verified_bridge(state: OSINTState) -> Dict[str, Any]:
    """
    Step 4: Executes when resumed. If human approves, commits the verified edge
    to Neo4j and updates card status in PostgreSQL.
    """
    decision = state.get("human_decision", "")
    card_id = state.get("card_id")
    friend_uid = state.get("friend_uid")
    target_uid = state.get("target_uid")
    relation_type = state.get("proposed_relation", "WORKED_WITH")

    logger.info("Resumed in commit_verified_bridge", decision=decision, card_id=card_id)

    if decision == "approve":
        # Commit to Neo4j if driver is available
        try:
            driver = get_neo4j_driver()
            if friend_uid and target_uid:
                await commit_bridge_edge(
                    driver=driver,
                    friend_uid=friend_uid,
                    target_uid=target_uid,
                    relation_type=relation_type,
                    confidence_score=1.0,
                    source_episode_id=card_id,
                )
        except Exception as exc:
            logger.warning("Neo4j commit bridge failed or skipped", error=str(exc))

        # Update PostgreSQL card status
        try:
            async with async_session_factory() as session:
                if card_id:
                    stmt = select(HITLEvidenceCardModel).where(
                        HITLEvidenceCardModel.card_id == uuid.UUID(card_id)
                    )
                    res = await session.execute(stmt)
                    card_model = res.scalar_one_or_none()
                    if card_model:
                        card_model.status = "verified"
                        await session.commit()
        except Exception as exc:
            logger.debug("PostgreSQL status update skipped or failed", error=str(exc))

        return {
            "confidence_score": 1.0,
            "human_decision": "approve",
        }

    # Snooze or reject
    try:
        async with async_session_factory() as session:
            if card_id:
                stmt = select(HITLEvidenceCardModel).where(
                    HITLEvidenceCardModel.card_id == uuid.UUID(card_id)
                )
                res = await session.execute(stmt)
                card_model = res.scalar_one_or_none()
                if card_model:
                    card_model.status = "rejected" if decision == "reject" else "snoozed"
                    await session.commit()
    except Exception as exc:
        logger.debug("PostgreSQL status update skipped or failed", error=str(exc))

    return {
        "human_decision": decision,
    }


def build_osint_graph(checkpointer: Optional[BaseCheckpointSaver] = None):
    """
    Constructs and compiles the OSINT StateGraph.
    """
    workflow = StateGraph(OSINTState)

    workflow.add_node("run_web_recon", run_web_recon)
    workflow.add_node("score_hypothesis", score_hypothesis)
    workflow.add_node("human_verification_gate", human_verification_gate)
    workflow.add_node("commit_verified_bridge", commit_verified_bridge)

    workflow.add_edge(START, "run_web_recon")
    workflow.add_edge("run_web_recon", "score_hypothesis")

    workflow.add_conditional_edges(
        "score_hypothesis",
        should_verify,
        {
            "human_verification_gate": "human_verification_gate",
            END: END,
        },
    )

    workflow.add_edge("human_verification_gate", "commit_verified_bridge")
    workflow.add_edge("commit_verified_bridge", END)

    return workflow.compile(checkpointer=checkpointer)
