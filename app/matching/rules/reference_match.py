"""
Reference matching rule (Weight: 40 points).

Compares bank transaction's kundenreferenz against remittance advice's
document_number. This is the strongest matching signal — if references
match exactly, the payment almost certainly corresponds to the remittance.

Scoring:
  - Exact match (normalized): full weight (40 pts)
  - Reference found as substring in verwendungszweck: 75% weight (30 pts)
  - No match: 0 pts
"""

from app.models.bank_transaction import BankTransaction
from app.models.remittance_advice import RemittanceAdvice


def _normalize(value: str | None) -> str:
    """Strip whitespace, remove leading zeros, lowercase for comparison."""
    if not value:
        return ""
    return value.strip().lstrip("0").lower()


def score(
    transaction: BankTransaction,
    remittance: RemittanceAdvice,
    weight: float = 40.0,
) -> dict:
    """
    Score reference match between transaction and remittance.

    Returns:
        dict with keys: score (float), max_score (float), details (str)
    """
    ref_bank = _normalize(transaction.kundenreferenz)
    ref_remittance = _normalize(remittance.document_number)

    if not ref_bank or not ref_remittance:
        return {
            "score": 0.0,
            "max_score": weight,
            "details": "Missing reference on one or both sides",
        }

    # Exact match (after normalization)
    if ref_bank == ref_remittance:
        return {
            "score": weight,
            "max_score": weight,
            "details": f"Exact reference match: '{transaction.kundenreferenz}' == '{remittance.document_number}'",
        }

    # Check if remittance document_number appears in verwendungszweck
    verwendungszweck = _normalize(transaction.verwendungszweck)
    if verwendungszweck and ref_remittance in verwendungszweck:
        partial_score = weight * 0.75
        return {
            "score": partial_score,
            "max_score": weight,
            "details": f"Reference '{remittance.document_number}' found in verwendungszweck",
        }

    # Check if bank reference appears in remittance document number or vice versa
    if ref_bank in ref_remittance or ref_remittance in ref_bank:
        partial_score = weight * 0.5
        return {
            "score": partial_score,
            "max_score": weight,
            "details": f"Partial reference overlap: '{transaction.kundenreferenz}' ~ '{remittance.document_number}'",
        }

    return {
        "score": 0.0,
        "max_score": weight,
        "details": f"No reference match: '{transaction.kundenreferenz}' != '{remittance.document_number}'",
    }
