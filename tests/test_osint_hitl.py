import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.pii_scrubber import scrub_pii
from src.agents.search_tools import execute_osint_queries
from src.agents.cypher_queries import find_open_triangles, commit_bridge_edge
from src.agents.osint_graph import build_osint_graph, OSINTState
from src.hitl_bot.notifier import build_hitl_inline_keyboard, format_hitl_card_html
from src.hitl_bot.bot import is_authorized, handle_hitl_callback, set_osint_app
from src.contracts.schema import HITLEvidenceCard, RelationType, VerificationStatus
from src.config import settings
from src.db.neo4j_client import get_neo4j_driver


def test_pii_scrubber():
    """Verifies emails, phone numbers, 12-digit strings, and PAN numbers are stripped."""
    raw_query = "Rohan rohan@iitd.ac.in and Siddharth +91 9876543210 at IIT Delhi PAN: ABCDE1234F Aadhaar: 1234 5678 9012"
    cleaned = scrub_pii(raw_query)

    assert "rohan@iitd.ac.in" not in cleaned
    assert "9876543210" not in cleaned
    assert "+91" not in cleaned
    assert "ABCDE1234F" not in cleaned
    assert "1234 5678 9012" not in cleaned

    # Query keywords remain intact
    assert "Rohan" in cleaned
    assert "Siddharth" in cleaned
    assert "IIT Delhi" in cleaned


@pytest.mark.asyncio
async def test_search_tools_searxng_and_tavily_fallback():
    """Verifies SearXNG query and fallback to Tavily if SearXNG returns < 2 results."""
    with patch("httpx.AsyncClient.get") as mock_get, patch("httpx.AsyncClient.post") as mock_post:
        # SearXNG returns 1 result
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": [{"title": "Rohan & Siddharth paper", "url": "https://arxiv.org/abs/1234", "content": "IEEE paper"}]}
        )
        # Tavily returns 1 fallback result
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": [{"title": "Siddharth Profile", "url": "https://linkedin.com/in/siddharth", "content": "IIT Delhi alumnus"}]}
        )

        results = await execute_osint_queries(
            person_a="Rohan",
            person_b="Siddharth Verma",
            shared_org="IIT Delhi",
            searxng_url="http://localhost:8080",
            tavily_api_key="tvly-mock-key",
        )

        assert len(results) >= 2
        urls = [r["url"] for r in results]
        assert "https://arxiv.org/abs/1234" in urls
        assert "https://linkedin.com/in/siddharth" in urls


@pytest.mark.asyncio
async def test_open_triangles_and_verified_bridge_neo4j():
    """Integration test with live Neo4j: seeds open triangle and commits bridge edge."""
    driver = get_neo4j_driver()
    friend_uid = str(uuid.uuid4())
    target_uid = str(uuid.uuid4())
    org_name = "IIT Delhi Test Org"

    # Seed open triangle
    async with driver.session() as session:
        await session.run("""
            MERGE (u:Person {full_name: 'SELF_USER'})
            MERGE (f:Person {uid: $friend_uid, full_name: 'Rohan Sharma', reachability_tier: 1})
            MERGE (t:Person {uid: $target_uid, full_name: 'Siddharth Verma', reachability_tier: 2})
            MERGE (o:Organization {name: $org_name})
            MERGE (u)-[:KNOWS {verified: true}]->(f)
            MERGE (f)-[:STUDIED_AT]->(o)
            MERGE (t)-[:STUDIED_AT]->(o)
        """, friend_uid=friend_uid, target_uid=target_uid, org_name=org_name)

    # Detect open triangle
    triangles = await find_open_triangles(driver, limit=50)
    matching = [
        t for t in triangles
        if t["friend_uid"] == friend_uid and t["target_uid"] == target_uid
    ]
    assert len(matching) == 1
    assert matching[0]["shared_org"] == org_name
    assert matching[0]["friend_name"] == "Rohan Sharma"
    assert matching[0]["target_name"] == "Siddharth Verma"

    # Commit bridge edge
    committed = await commit_bridge_edge(
        driver=driver,
        friend_uid=friend_uid,
        target_uid=target_uid,
        relation_type="CO_AUTHORED_WITH",
        confidence_score=1.0,
        source_episode_id="test-card-1",
    )
    assert committed is True

    # Assert triangle is now closed (no longer returned as open triangle)
    triangles_after = await find_open_triangles(driver, limit=50)
    matching_after = [
        t for t in triangles_after
        if t["friend_uid"] == friend_uid and t["target_uid"] == target_uid
    ]
    assert len(matching_after) == 0


@pytest.mark.asyncio
async def test_osint_graph_interrupt_and_resume():
    """
    Mandatory Phase 5 verification test from specification:
    1. Compiles osint_graph with MemorySaver checkpointer.
    2. Simulates IEEE paper snippet co-authored by Rohan and Siddharth Verma at IIT Delhi.
    3. Invokes graph with thread_id="test-thread-1".
    4. Asserts graph pauses at human_verification_gate (state.next == ("human_verification_gate",)).
    5. Resumes graph with Command(resume="approve").
    6. Asserts commit_verified_bridge executes, returning human_decision == "approve" and confidence_score == 1.0.
    """
    checkpointer = MemorySaver()
    app = build_osint_graph(checkpointer=checkpointer)

    simulated_results = [
        {
            "title": "Graph Representation Learning for Networks",
            "url": "https://ieeexplore.ieee.org/document/9876543",
            "snippet": "Co-authored paper by Rohan Sharma and Siddharth Verma on Graph Neural Networks, Proceedings of IEEE 2024 at IIT Delhi.",
            "engine": "searxng",
        }
    ]

    initial_state: OSINTState = {
        "thread_id": "test-thread-1",
        "friend_uid": str(uuid.uuid4()),
        "friend_name": "Rohan Sharma",
        "target_uid": str(uuid.uuid4()),
        "target_name": "Siddharth Verma",
        "shared_org": "IIT Delhi",
        "search_results": simulated_results,
    }

    config = {"configurable": {"thread_id": "test-thread-1"}}

    # Step 1: Initial invocation pauses at human_verification_gate
    paused_result = await app.ainvoke(initial_state, config=config)
    checkpoint_state = await app.aget_state(config)

    assert checkpoint_state.next == ("human_verification_gate",)
    assert checkpoint_state.values.get("proposed_relation") == "CO_AUTHORED_WITH"
    assert checkpoint_state.values.get("confidence_score") >= 0.85
    assert "card_id" in checkpoint_state.values

    # Step 2: Resume with Command(resume="approve")
    resumed_result = await app.ainvoke(Command(resume="approve"), config=config)

    assert resumed_result.get("human_decision") == "approve"
    assert resumed_result.get("confidence_score") == 1.0

    final_state = await app.aget_state(config)
    assert final_state.next == ()


@pytest.mark.asyncio
async def test_osint_graph_low_confidence_routes_to_end():
    """Verifies that queries with low confidence (< 0.50) route directly to END without pausing."""
    checkpointer = MemorySaver()
    app = build_osint_graph(checkpointer=checkpointer)

    initial_state: OSINTState = {
        "thread_id": "test-thread-low-conf",
        "friend_uid": str(uuid.uuid4()),
        "friend_name": "Unknown Friend",
        "target_uid": str(uuid.uuid4()),
        "target_name": "Unknown Target",
        "shared_org": "Obscure Org",
        "search_results": [],
    }

    config = {"configurable": {"thread_id": "test-thread-low-conf"}}
    result = await app.ainvoke(initial_state, config=config)

    state = await app.aget_state(config)
    assert state.next == ()
    assert result.get("confidence_score") < 0.50
    assert "human_decision" not in result


def test_telegram_notifier_formatting_and_keyboard():
    """Verifies HITL inline keyboard structure and HTML card formatting."""
    thread_id = "test-thread-telegram"
    card_id = str(uuid.uuid4())

    keyboard = build_hitl_inline_keyboard(thread_id=thread_id, card_id=card_id)
    assert len(keyboard.inline_keyboard) == 2

    # Row 1: Approve and Reject
    assert keyboard.inline_keyboard[0][0].text == "✅ Confirm & Lock"
    assert keyboard.inline_keyboard[0][0].callback_data == f"hitl:approve:{thread_id}:{card_id}"
    assert keyboard.inline_keyboard[0][1].text == "❌ Reject Match"
    assert keyboard.inline_keyboard[0][1].callback_data == f"hitl:reject:{thread_id}:{card_id}"

    # Row 2: Snooze
    assert keyboard.inline_keyboard[1][0].text == "🤔 Snooze"
    assert keyboard.inline_keyboard[1][0].callback_data == f"hitl:snooze:{thread_id}:{card_id}"

    card = HITLEvidenceCard(
        card_id=uuid.UUID(card_id),
        langgraph_thread_id=thread_id,
        action_type="HIDDEN_BRIDGE_DISCOVERY",
        subject_a_name="Rohan Sharma",
        subject_b_name="Siddharth Verma",
        proposed_relation=RelationType.CO_AUTHORED_WITH,
        confidence_score=0.92,
        evidence_summary="Co-authored IEEE 2024 paper on GNNs at IIT Delhi",
        source_urls=["https://ieeexplore.ieee.org/document/9876543"],
        status=VerificationStatus.PENDING_HITL,
    )

    html = format_hitl_card_html(card)
    assert "<b>Subject A:</b> Rohan Sharma" in html
    assert "<b>Subject B:</b> Siddharth Verma" in html
    assert "CO_AUTHORED_WITH" in html
    assert "92%" in html
    assert "https://ieeexplore.ieee.org/document/9876543" in html


def test_hitl_bot_authorization():
    """Verifies telegram bot sender ID authorization checks."""
    with patch.object(settings, "TELEGRAM_ALLOWED_USER_ID", 123456789):
        assert is_authorized(123456789) is True
        assert is_authorized(987654321) is False
        assert is_authorized(None) is False

    with patch.object(settings, "TELEGRAM_ALLOWED_USER_ID", None):
        assert is_authorized(123456789) is False


@pytest.mark.asyncio
async def test_hitl_bot_callback_resumes_graph():
    """Verifies telegram bot callback unpacks data and resumes the LangGraph workflow."""
    checkpointer = MemorySaver()
    app = build_osint_graph(checkpointer=checkpointer)
    set_osint_app(app)

    thread_id = "test-callback-thread"
    card_id = str(uuid.uuid4())

    initial_state: OSINTState = {
        "thread_id": thread_id,
        "friend_name": "Rohan",
        "target_name": "Siddharth",
        "shared_org": "IIT Delhi",
        "card_id": card_id,
        "search_results": [
            {
                "title": "IEEE Paper",
                "url": "https://arxiv.org",
                "snippet": "Co-authored paper by Rohan and Siddharth at IIT Delhi.",
                "engine": "searxng",
            }
        ],
    }

    # Pause graph
    await app.ainvoke(initial_state, config={"configurable": {"thread_id": thread_id}})

    # Create mock callback query
    mock_callback = AsyncMock()
    mock_callback.data = f"hitl:approve:{thread_id}:{card_id}"
    mock_callback.from_user.id = 99999
    mock_callback.message.text = "Initial Card Text"

    with patch.object(settings, "TELEGRAM_ALLOWED_USER_ID", 99999):
        await handle_hitl_callback(mock_callback)

    # Verify callback answered and message updated
    mock_callback.answer.assert_called_once()
    mock_callback.message.edit_text.assert_called_once()
    edit_call_text = mock_callback.message.edit_text.call_args[0][0]
    assert "APPROVE ✅" in edit_call_text

    # Verify graph reached completion
    final_state = await app.aget_state({"configurable": {"thread_id": thread_id}})
    assert final_state.next == ()
    assert final_state.values.get("human_decision") == "approve"
