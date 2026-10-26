import csv
import io
import re
from typing import List, Dict
from src.contracts.schema import ExtractedPerson, ReachabilityTier


def parse_linkedin_csv(csv_content: str) -> List[ExtractedPerson]:
    """Parses exported LinkedIn Connections.csv, skipping disclaimer headers,

    and extracts ExtractedPerson records.
    """
    lines = csv_content.splitlines()
    header_idx = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith("First Name"):
            header_idx = idx
            break

    if header_idx == -1:
        # Try raw DictReader if First Name is right at row 0
        reader = csv.DictReader(io.StringIO(csv_content))
    else:
        cleaned_csv = "\n".join(lines[header_idx:])
        reader = csv.DictReader(io.StringIO(cleaned_csv))

    persons: List[ExtractedPerson] = []
    for row in reader:
        first = (row.get("First Name") or "").strip()
        last = (row.get("Last Name") or "").strip()
        full_name = f"{first} {last}".strip()
        if not full_name:
            continue

        raw_url = (row.get("URL") or "").strip()
        linkedin_url = raw_url if raw_url else None

        raw_email = (row.get("Email Address") or "").strip()
        email = raw_email if raw_email else None

        raw_company = (row.get("Company") or "").strip()
        company = raw_company if raw_company else None

        raw_position = (row.get("Position") or "").strip()
        position = raw_position if raw_position else None

        person = ExtractedPerson(
            full_name=full_name,
            linkedin_url=linkedin_url,
            email=email,
            current_org=company,
            current_role=position,
            reachability_tier=ReachabilityTier.TIER_2_WARM,
            trust_score=45.0,
        )
        persons.append(person)

    return persons


# Regex matching common WhatsApp export timestamps
WHATSAPP_TIMESTAMP_REGEX = re.compile(
    r"^\[?(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)\]?(?:\s+-\s+|\s*:\s*|\s+)(.*)$"
)


def parse_whatsapp_txt(chat_txt: str) -> List[str]:
    """Groups consecutive WhatsApp export messages by date into coherent daily summary strings."""
    daily_messages: Dict[str, List[str]] = {}
    current_date: str = "Unknown Date"

    for line in chat_txt.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue

        match = WHATSAPP_TIMESTAMP_REGEX.match(trimmed)
        if match:
            date_str, _, body = match.groups()
            current_date = date_str
            if current_date not in daily_messages:
                daily_messages[current_date] = []
            if body.strip():
                daily_messages[current_date].append(body.strip())
        else:
            # Continuation of previous message
            if current_date not in daily_messages:
                daily_messages[current_date] = []
            daily_messages[current_date].append(trimmed)

    daily_summaries: List[str] = []
    for date_key, messages in daily_messages.items():
        if messages:
            summary = f"Date: {date_key}\n" + "\n".join(messages)
            daily_summaries.append(summary)

    return daily_summaries
