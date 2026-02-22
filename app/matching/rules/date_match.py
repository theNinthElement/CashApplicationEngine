"""
Date proximity matching rule (Weight: 10 points).

Compares the bank transaction's buchungsdatum (booking date) against the
remittance advice's document_date. Payments typically arrive within a few
days of the remittance document date.

Scoring:
  - Same day: full weight (10 pts)
  - 1-10 days apart: linear decay (1 pt lost per day)
  - > 10 days apart: 0 pts
  - Missing date on remittance: 50% weight (benefit of the doubt)
"""

from app.models.bank_transaction import BankTransaction
from app.models.remittance_advice import RemittanceAdvice

# Maximum number of days apart before score drops to zero
MAX_DAY_DIFFERENCE = 10


def score(
    transaction: BankTransaction,
    remittance: RemittanceAdvice,
    weight: float = 10.0,
) -> dict:
    """
    Score date proximity between transaction and remittance.

    Returns:
        dict with keys: score (float), max_score (float), details (str)
    """
    bank_date = transaction.buchungsdatum
    remittance_date = remittance.document_date

    if bank_date is None:
        return {
            "score": 0.0,
            "max_score": weight,
            "details": "Missing booking date on transaction",
        }

    # If remittance has no date, give partial credit (many PDFs lack dates)
    if remittance_date is None:
        partial_score = round(weight * 0.5, 2)
        return {
            "score": partial_score,
            "max_score": weight,
            "details": "No date on remittance — partial credit given",
        }

    day_diff = abs((bank_date - remittance_date).days)

    if day_diff == 0:
        return {
            "score": weight,
            "max_score": weight,
            "details": f"Same date: {bank_date}",
        }

    if day_diff <= MAX_DAY_DIFFERENCE:
        # Linear decay: 1 point lost per day
        ratio = 1.0 - (day_diff / MAX_DAY_DIFFERENCE)
        matched_score = round(weight * ratio, 2)
        return {
            "score": matched_score,
            "max_score": weight,
            "details": f"Dates {day_diff} day(s) apart: bank={bank_date}, remittance={remittance_date}",
        }

    return {
        "score": 0.0,
        "max_score": weight,
        "details": f"Dates too far apart ({day_diff} days): bank={bank_date}, remittance={remittance_date}",
    }
