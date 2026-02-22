"""Parser for JSON email files — classifies emails and extracts invoice references."""
import re
import json
from datetime import datetime
from dataclasses import dataclass


class EmailCategory:
    REMITTANCE_ADVICE = "remittance_advice"
    PAYMENT_NOTIFICATION = "payment_notification"
    SHORT_PAYMENT = "short_payment"
    INVOICE_REQUEST = "invoice_request"
    PAYMENT_ON_HOLD = "payment_on_hold"
    PRICING_DISPUTE = "pricing_dispute"
    PAYMENT_CONFIRMATION = "payment_confirmation"
    STATEMENT_REQUEST = "statement_request"
    PARTIAL_PAYMENT = "partial_payment"
    CREDIT_NOTE_REQUEST = "credit_note_request"
    OTHER = "other"


# Keywords to category mapping (checked against subject + body)
_CLASSIFICATION_RULES = [
    (EmailCategory.REMITTANCE_ADVICE, [
        r"zahlungsavis", r"remittance\s+advice", r"payment\s+advice",
    ]),
    (EmailCategory.SHORT_PAYMENT, [
        r"short\s+payment", r"deduct", r"promo\s+deduction",
    ]),
    (EmailCategory.PAYMENT_ON_HOLD, [
        r"on\s+hold", r"missing\s+pod", r"proof\s+of\s+delivery",
    ]),
    (EmailCategory.PRICING_DISPUTE, [
        r"pricing\s+discrepancy", r"price\s+dispute", r"invoiced\s+.*price",
    ]),
    (EmailCategory.INVOICE_REQUEST, [
        r"invoice\s+copy\s+request", r"resend\s+.*invoice",
    ]),
    (EmailCategory.PAYMENT_CONFIRMATION, [
        r"payment\s+confirmation\s+request",
    ]),
    (EmailCategory.STATEMENT_REQUEST, [
        r"statement\s+of\s+account",
    ]),
    (EmailCategory.PARTIAL_PAYMENT, [
        r"partial\s+payment",
    ]),
    (EmailCategory.CREDIT_NOTE_REQUEST, [
        r"credit\s+note\s+required", r"credit\s+note\s+request",
    ]),
    (EmailCategory.PAYMENT_NOTIFICATION, [
        r"payment\s+sent", r"payment\s+.*transfer", r"payment\s+initiated",
    ]),
]


@dataclass
class ParsedEmail:
    """Parsed and classified email."""
    id: str
    received_at: datetime | None
    sender: str
    subject: str
    body: str
    category: str
    invoice_references: list[str]


def parse_emails(file_content: bytes) -> list[ParsedEmail]:
    """Parse a JSON file containing emails.

    Args:
        file_content: Raw bytes of the JSON file.

    Returns:
        List of parsed and classified emails.
    """
    data = json.loads(file_content)

    # Handle both {"emails": [...]} and direct list format
    if isinstance(data, dict) and "emails" in data:
        emails_raw = data["emails"]
    elif isinstance(data, list):
        emails_raw = data
    else:
        raise ValueError("Invalid email JSON format. Expected {'emails': [...]} or [...]")

    results = []
    for email_data in emails_raw:
        parsed = _parse_single_email(email_data)
        results.append(parsed)

    return results


def _parse_single_email(email_data: dict) -> ParsedEmail:
    """Parse and classify a single email."""
    email_id = email_data.get("id", "")
    sender = email_data.get("from", "")
    subject = email_data.get("subject", "")
    body = email_data.get("body", "")

    # Parse received timestamp
    received_at = None
    raw_date = email_data.get("receivedAt")
    if raw_date:
        try:
            received_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    # Classify
    category = _classify_email(subject, body)

    # Extract invoice references
    invoice_refs = _extract_invoice_references(subject, body)

    return ParsedEmail(
        id=email_id,
        received_at=received_at,
        sender=sender,
        subject=subject,
        body=body,
        category=category,
        invoice_references=invoice_refs,
    )


def _classify_email(subject: str, body: str) -> str:
    """Classify email based on subject and body keywords."""
    combined = f"{subject} {body}".lower()

    for category, patterns in _CLASSIFICATION_RULES:
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return category

    return EmailCategory.OTHER


def _extract_invoice_references(subject: str, body: str) -> list[str]:
    """Extract invoice/reference numbers from email text."""
    combined = f"{subject} {body}"
    refs = set()

    # Match INV-NNNNN pattern
    for match in re.finditer(r"INV-(\d+)", combined):
        refs.add(f"INV-{match.group(1)}")

    # Match "Invoice reference: XXXX"
    for match in re.finditer(r"[Ii]nvoice\s+reference:\s*(\S+)", combined):
        ref = match.group(1).rstrip(".")
        refs.add(ref)

    # Match standalone reference patterns (e.g., "10003839")
    for match in re.finditer(r"(?:Ref|Reference|Nr)[.:]?\s*(\d{5,})", combined):
        refs.add(match.group(1))

    return sorted(refs)
