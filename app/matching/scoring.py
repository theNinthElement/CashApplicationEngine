"""
Scoring combiner — runs all matching rules and produces a total score.

Takes a bank transaction and remittance advice pair, executes all 4 rules
with their configured weights, and returns a combined score (0-100) with
a per-rule breakdown for auditability.
"""

from dataclasses import dataclass, field

from app.config import get_settings
from app.models.bank_transaction import BankTransaction
from app.models.remittance_advice import RemittanceAdvice
from app.matching.rules import reference_match, amount_match, company_match, date_match


@dataclass
class ScoreResult:
    """Result of scoring a transaction/remittance pair."""

    total_score: float
    max_possible: float
    rule_scores: dict = field(default_factory=dict)

    @property
    def percentage(self) -> float:
        if self.max_possible == 0:
            return 0.0
        return round((self.total_score / self.max_possible) * 100, 2)


def score_pair(
    transaction: BankTransaction,
    remittance: RemittanceAdvice,
) -> ScoreResult:
    """
    Score a transaction/remittance pair using all matching rules.

    Weights are loaded from application settings (config.py).

    Returns:
        ScoreResult with total score, max possible, and per-rule breakdown.
    """
    settings = get_settings()

    rules = [
        ("reference", reference_match.score, settings.reference_match_weight),
        ("amount", amount_match.score, settings.amount_match_weight),
        ("company", company_match.score, settings.company_match_weight),
        ("date", date_match.score, settings.date_match_weight),
    ]

    rule_scores = {}
    total_score = 0.0
    max_possible = 0.0

    for rule_name, rule_fn, weight in rules:
        if rule_name == "amount":
            result = rule_fn(
                transaction,
                remittance,
                weight=weight,
                tolerance_percent=settings.amount_tolerance_percent,
            )
        else:
            result = rule_fn(transaction, remittance, weight=weight)

        rule_scores[rule_name] = result
        total_score += result["score"]
        max_possible += result["max_score"]

    return ScoreResult(
        total_score=round(total_score, 2),
        max_possible=round(max_possible, 2),
        rule_scores=rule_scores,
    )
