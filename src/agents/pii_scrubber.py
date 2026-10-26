import re


# Regular expressions for PII patterns
EMAIL_PATTERN = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+", flags=re.IGNORECASE)

# Indian & International phone numbers (e.g. +91 9876543210, +1-800-555-0199, 9876543210)
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\b\d{10}\b",
    flags=re.IGNORECASE,
)

# 12-digit numbers (e.g. Aadhaar card or long national IDs with or without spaces/dashes)
TWELVE_DIGIT_PATTERN = re.compile(
    r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b|\b\d{12}\b"
)

# Indian Permanent Account Number (PAN) format: 5 letters, 4 digits, 1 letter
PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", flags=re.IGNORECASE)


def scrub_pii(text: str) -> str:
    """
    Strips emails, phone numbers, 12-digit identifiers, and PAN numbers
    from text prior to any external OSINT search or external API invocation.
    Preserves all surrounding query terms and normalizes whitespace.
    """
    if not text:
        return ""

    scrubbed = EMAIL_PATTERN.sub("", text)
    scrubbed = PAN_PATTERN.sub("", scrubbed)
    scrubbed = TWELVE_DIGIT_PATTERN.sub("", scrubbed)
    scrubbed = PHONE_PATTERN.sub("", scrubbed)

    # Normalize excessive whitespace
    scrubbed = re.sub(r"\s+", " ", scrubbed).strip()
    return scrubbed
