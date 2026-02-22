"""
Company name matching rule (Weight: 15 points).

Fuzzy-matches the bank transaction's auftraggeber_empfaenger against the
remittance advice's sender_name using rapidfuzz. This handles OCR errors
(e.g., "Blke Team" → "Bike Team") and minor spelling variations common
in German company names.

Scoring:
  - Fuzzy ratio >= 90%: full weight (15 pts)
  - Fuzzy ratio 60-89%: proportional score
  - Fuzzy ratio < 60%: 0 pts (too dissimilar to be the same company)
"""

from rapidfuzz import fuzz

from app.models.bank_transaction import BankTransaction
from app.models.remittance_advice import RemittanceAdvice

# Below this threshold, names are considered too different
MIN_SIMILARITY_THRESHOLD = 60.0


def _normalize_company_name(name: str | None) -> str:
    """Normalize company name for comparison.

    Removes common German legal suffixes (GmbH, AG, etc.) and extra whitespace
    so that "Bike Team GmbH" and "Bike Team" compare as identical.
    """
    if not name:
        return ""

    normalized = name.strip().lower()

    # Remove common German legal form suffixes
    for suffix in ["gmbh", "ag", "e.v.", "kg", "ohg", "gbr", "mbh", "ug", "se"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
        # Also handle with leading space/comma
        for sep in [" ", ", ", " & "]:
            token = sep + suffix
            if normalized.endswith(token):
                normalized = normalized[: -len(token)].strip()

    return normalized.strip()


def score(
    transaction: BankTransaction,
    remittance: RemittanceAdvice,
    weight: float = 15.0,
) -> dict:
    """
    Score company name match between transaction and remittance.

    Returns:
        dict with keys: score (float), max_score (float), details (str)
    """
    bank_name = _normalize_company_name(transaction.auftraggeber_empfaenger)
    remittance_name = _normalize_company_name(remittance.sender_name)

    if not bank_name or not remittance_name:
        return {
            "score": 0.0,
            "max_score": weight,
            "details": "Missing company name on one or both sides",
        }

    # Use token_sort_ratio to handle word order differences
    # e.g., "Team Bike" vs "Bike Team" still scores high
    similarity = fuzz.token_sort_ratio(bank_name, remittance_name)

    if similarity >= 90.0:
        return {
            "score": weight,
            "max_score": weight,
            "details": f"Strong company match: '{transaction.auftraggeber_empfaenger}' ~ '{remittance.sender_name}' ({similarity:.0f}% similar)",
        }

    if similarity >= MIN_SIMILARITY_THRESHOLD:
        # Scale proportionally: 60% similarity = 0 pts, 90% = full weight
        ratio = (similarity - MIN_SIMILARITY_THRESHOLD) / (90.0 - MIN_SIMILARITY_THRESHOLD)
        matched_score = round(weight * ratio, 2)
        return {
            "score": matched_score,
            "max_score": weight,
            "details": f"Partial company match: '{transaction.auftraggeber_empfaenger}' ~ '{remittance.sender_name}' ({similarity:.0f}% similar)",
        }

    return {
        "score": 0.0,
        "max_score": weight,
        "details": f"Company mismatch: '{transaction.auftraggeber_empfaenger}' != '{remittance.sender_name}' ({similarity:.0f}% similar)",
    }
