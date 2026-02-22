"""
Amount matching rule (Weight: 35 points).

Compares the absolute value of the bank transaction's betrag against the
remittance advice's total_net_amount. Financial amounts should match
closely — a 1% tolerance handles rounding and minor bank fee differences.

Scoring:
  - Exact match: full weight (35 pts)
  - Within tolerance (default 1%): proportional score based on closeness
  - Beyond tolerance: 0 pts
"""

from decimal import Decimal

from app.models.bank_transaction import BankTransaction
from app.models.remittance_advice import RemittanceAdvice


def score(
    transaction: BankTransaction,
    remittance: RemittanceAdvice,
    weight: float = 35.0,
    tolerance_percent: float = 0.01,
) -> dict:
    """
    Score amount match between transaction and remittance.

    Args:
        transaction: Bank transaction (betrag may be negative for outgoing)
        remittance: Remittance advice with total_net_amount
        weight: Maximum score for this rule
        tolerance_percent: Acceptable deviation as a fraction (0.01 = 1%)

    Returns:
        dict with keys: score (float), max_score (float), details (str)
    """
    bank_amount = abs(transaction.betrag) if transaction.betrag is not None else None
    remittance_amount = remittance.total_net_amount

    if bank_amount is None or remittance_amount is None:
        return {
            "score": 0.0,
            "max_score": weight,
            "details": "Missing amount on one or both sides",
        }

    remittance_amount = abs(remittance_amount)

    # Avoid division by zero
    if remittance_amount == Decimal("0") and bank_amount == Decimal("0"):
        return {
            "score": weight,
            "max_score": weight,
            "details": "Both amounts are zero — exact match",
        }

    if remittance_amount == Decimal("0"):
        return {
            "score": 0.0,
            "max_score": weight,
            "details": f"Remittance amount is zero, bank amount is {bank_amount}",
        }

    # Calculate percentage difference relative to remittance amount
    difference = abs(bank_amount - remittance_amount)
    pct_diff = float(difference / remittance_amount)

    # Exact match
    if difference == Decimal("0"):
        return {
            "score": weight,
            "max_score": weight,
            "details": f"Exact amount match: {bank_amount}",
        }

    # Within tolerance — score proportionally (closer = higher)
    if pct_diff <= tolerance_percent:
        # Linear interpolation: 0% diff = full score, tolerance% diff = 50% score
        ratio = 1.0 - (pct_diff / tolerance_percent) * 0.5
        matched_score = round(weight * ratio, 2)
        return {
            "score": matched_score,
            "max_score": weight,
            "details": f"Amount within tolerance: |{bank_amount} - {remittance_amount}| = {difference} ({pct_diff:.4%} diff)",
        }

    return {
        "score": 0.0,
        "max_score": weight,
        "details": f"Amount mismatch: |{bank_amount} - {remittance_amount}| = {difference} ({pct_diff:.2%} diff, exceeds {tolerance_percent:.0%} tolerance)",
    }
