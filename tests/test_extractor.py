import pytest
from src.contracts.schema import (
    ReachabilityTier,
    RelationType,
    ExtractedPerson,
)
from src.ingestion.extractor import extract_episode
from src.ingestion.social_parsers import parse_linkedin_csv, parse_whatsapp_txt


@pytest.mark.asyncio
async def test_extractor_end_to_end():
    """Verify Section 7 & Phase 2 invariant extraction requirements:

    Input: 'Met Ankit from RVCE today. Turns out his roommate Vikram works at Stripe in Bengaluru, and Ankit left TCS last month.'
    Assertions:
    - SELF_USER, Ankit (Tier 1), and Vikram (Tier 2) are extracted in result.persons.
    - RVCE, Stripe, and TCS are extracted in result.organizations.
    - Edge (Ankit)-[WORKS_AT]->(TCS) has valid_to is not None.
    - Edge (Vikram)-[WORKS_AT]->(Stripe) has valid_to is None.
    """
    raw_text = (
        "Met Ankit from RVCE today. Turns out his roommate Vikram works at Stripe in Bengaluru, "
        "and Ankit left TCS last month."
    )
    result = await extract_episode(raw_text, source_type="voice_note", reference_date="2024-10-26")

    # 1. Assert Persons and Reachability Tiers
    person_map = {p.full_name: p for p in result.persons}
    assert any("SELF_USER" in name.upper() for name in person_map.keys()), (
        f"SELF_USER missing in extracted persons: {list(person_map.keys())}"
    )

    ankit = next((p for name, p in person_map.items() if "Ankit" in name), None)
    assert ankit is not None, f"Ankit missing in {list(person_map.keys())}"
    assert ankit.reachability_tier == ReachabilityTier.TIER_1_CLOSE, (
        f"Expected Ankit to be Tier 1, got {ankit.reachability_tier}"
    )

    vikram = next((p for name, p in person_map.items() if "Vikram" in name), None)
    assert vikram is not None, f"Vikram missing in {list(person_map.keys())}"
    assert vikram.reachability_tier == ReachabilityTier.TIER_2_WARM, (
        f"Expected Vikram to be Tier 2, got {vikram.reachability_tier}"
    )

    # 2. Assert Organizations
    org_names = [o.name.upper() for o in result.organizations]
    assert any("RVCE" in o for o in org_names), f"RVCE missing in {org_names}"
    assert any("STRIPE" in o for o in org_names), f"Stripe missing in {org_names}"
    assert any("TCS" in o for o in org_names), f"TCS missing in {org_names}"

    # 3. Assert Bi-Temporal WORKS_AT Edges
    tcs_edge = next(
        (
            e for e in result.edges
            if "ANKIT" in e.source_name.upper()
            and "TCS" in e.target_name.upper()
            and e.relation_type == RelationType.WORKS_AT
        ),
        None,
    )
    assert tcs_edge is not None, f"Edge (Ankit)-[WORKS_AT]->(TCS) not found in {result.edges}"
    assert tcs_edge.valid_to is not None, (
        f"Expected Ankit left TCS edge to have non-null valid_to, got {tcs_edge.valid_to}"
    )

    stripe_edge = next(
        (
            e for e in result.edges
            if "VIKRAM" in e.source_name.upper()
            and "STRIPE" in e.target_name.upper()
            and e.relation_type == RelationType.WORKS_AT
        ),
        None,
    )
    assert stripe_edge is not None, f"Edge (Vikram)-[WORKS_AT]->(Stripe) not found in {result.edges}"
    assert stripe_edge.valid_to is None, (
        f"Expected Vikram works at Stripe edge to have valid_to=None, got {stripe_edge.valid_to}"
    )


def test_linkedin_csv_parser(sample_linkedin_csv: str):
    """Verifies LinkedIn CSV parsing skips header disclaimers and maps fields cleanly."""
    persons = parse_linkedin_csv(sample_linkedin_csv)
    assert len(persons) == 2

    rohan = persons[0]
    assert rohan.full_name == "Rohan Verma"
    assert rohan.email == "rohan@example.com"
    assert rohan.current_org == "Razorpay"
    assert rohan.current_role == "Software Engineer"
    assert rohan.reachability_tier == ReachabilityTier.TIER_2_WARM
    assert rohan.trust_score == 45.0

    ananya = persons[1]
    assert ananya.full_name == "Ananya Iyer"
    assert ananya.email is None
    assert ananya.current_org == "Flipkart"
    assert ananya.current_role == "Product Manager"


def test_whatsapp_txt_parser(sample_whatsapp_chat: str):
    """Verifies WhatsApp multi-day chat aggregation."""
    daily_summaries = parse_whatsapp_txt(sample_whatsapp_chat)
    assert len(daily_summaries) == 2
    assert "Indiranagar" in daily_summaries[0]
    assert "Stripe" in daily_summaries[1]


def test_data_contract_normalization():
    """Verifies invariant normalization on email and phone numbers."""
    person = ExtractedPerson(
        full_name="Test User",
        email="  Alice.Bob@Example.COM  ",
        phone="+91-98765-43210",
    )
    assert person.email == "alice.bob@example.com"
    assert person.phone == "9876543210"
