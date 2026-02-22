"""
Matching engine orchestrator.

Queries the database for unmatched bank transactions and remittance advices,
scores all possible pairs using the scoring module, applies thresholds, and
creates Match records. Uses greedy best-match assignment to ensure each
transaction and remittance is matched at most once.

Flow:
  1. Load unmatched transactions and remittances from DB
  2. Score every (transaction, remittance) pair
  3. Sort all pairs by score descending
  4. Greedy assignment: take highest-scoring pair, mark both as used, repeat
  5. Create Match records for pairs above threshold
  6. Update match_status on transactions and remittances
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models.bank_transaction import BankTransaction, MatchStatus
from app.models.remittance_advice import RemittanceAdvice, RemittanceStatus
from app.models.match import Match, MatchType
from app.matching.scoring import score_pair, ScoreResult

logger = logging.getLogger(__name__)


@dataclass
class MatchCandidate:
    """A scored transaction/remittance pair."""

    transaction: BankTransaction
    remittance: RemittanceAdvice
    score_result: ScoreResult


@dataclass
class MatchingResult:
    """Summary of a matching run."""

    total_transactions: int = 0
    total_remittances: int = 0
    auto_matched: int = 0
    manual_review: int = 0
    unmatched: int = 0
    matches_created: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_transactions": self.total_transactions,
            "total_remittances": self.total_remittances,
            "auto_matched": self.auto_matched,
            "manual_review": self.manual_review,
            "unmatched": self.unmatched,
            "matches_created": len(self.matches_created),
            "errors": self.errors,
        }


def run_matching(db: Session) -> MatchingResult:
    """
    Run the full matching pipeline.

    Args:
        db: SQLAlchemy session

    Returns:
        MatchingResult with counts and created match IDs.
    """
    settings = get_settings()
    result = MatchingResult()

    # Step 1: Load unmatched records
    transactions = (
        db.query(BankTransaction)
        .filter(BankTransaction.match_status == MatchStatus.UNMATCHED)
        .all()
    )

    remittances = (
        db.query(RemittanceAdvice)
        .options(joinedload(RemittanceAdvice.line_items))
        .filter(RemittanceAdvice.match_status == RemittanceStatus.UNMATCHED)
        .all()
    )

    result.total_transactions = len(transactions)
    result.total_remittances = len(remittances)

    logger.info(
        "Starting matching: %d transactions x %d remittances",
        len(transactions),
        len(remittances),
    )

    if not transactions or not remittances:
        logger.info("Nothing to match — no unmatched records on one or both sides")
        result.unmatched = len(transactions)
        return result

    # Step 2: Score all pairs
    candidates: list[MatchCandidate] = []

    for txn in transactions:
        for rem in remittances:
            try:
                score_result = score_pair(txn, rem)
                candidates.append(
                    MatchCandidate(
                        transaction=txn,
                        remittance=rem,
                        score_result=score_result,
                    )
                )
            except Exception as e:
                logger.error(
                    "Error scoring pair txn=%s / rem=%s: %s",
                    txn.id,
                    rem.id,
                    str(e),
                )
                result.errors.append(
                    f"Scoring error for txn {txn.id} / rem {rem.id}: {str(e)}"
                )

    # Step 3: Sort by total score descending (greedy best-match-first)
    candidates.sort(key=lambda c: c.score_result.total_score, reverse=True)

    # Step 4: Greedy assignment — each transaction and remittance matched at most once
    matched_txn_ids: set = set()
    matched_rem_ids: set = set()

    for candidate in candidates:
        txn = candidate.transaction
        rem = candidate.remittance
        score = candidate.score_result.total_score

        # Skip if either side is already matched in this run
        if txn.id in matched_txn_ids or rem.id in matched_rem_ids:
            continue

        # Determine match type based on thresholds
        if score >= settings.auto_match_threshold:
            match_type = _determine_match_type(candidate.score_result)
            _create_match(db, candidate, match_type)
            txn.match_status = MatchStatus.MATCHED
            rem.match_status = RemittanceStatus.MATCHED
            matched_txn_ids.add(txn.id)
            matched_rem_ids.add(rem.id)
            result.auto_matched += 1
            result.matches_created.append(str(txn.id))
            logger.info(
                "Auto-matched: txn %s ↔ rem %s (score: %.1f, type: %s)",
                txn.id,
                rem.document_number,
                score,
                match_type.value,
            )

        elif score >= settings.manual_review_threshold:
            match_type = MatchType.AUTO_FUZZY
            _create_match(db, candidate, match_type)
            txn.match_status = MatchStatus.MANUAL_REVIEW
            # Don't mark remittance as matched yet — needs human approval
            matched_txn_ids.add(txn.id)
            matched_rem_ids.add(rem.id)
            result.manual_review += 1
            result.matches_created.append(str(txn.id))
            logger.info(
                "Manual review: txn %s ↔ rem %s (score: %.1f)",
                txn.id,
                rem.document_number,
                score,
            )

    # Count remaining unmatched
    result.unmatched = len(transactions) - len(matched_txn_ids)

    # Commit all changes
    db.commit()

    logger.info(
        "Matching complete: %d auto, %d review, %d unmatched",
        result.auto_matched,
        result.manual_review,
        result.unmatched,
    )

    return result


def _determine_match_type(score_result: ScoreResult) -> MatchType:
    """Determine if match is exact or fuzzy based on rule scores.

    AUTO_EXACT: reference rule scored full points (exact reference match)
    AUTO_FUZZY: matched via fuzzy/partial rules
    """
    ref_score = score_result.rule_scores.get("reference", {})
    if ref_score.get("score", 0) == ref_score.get("max_score", 0) and ref_score.get("max_score", 0) > 0:
        return MatchType.AUTO_EXACT
    return MatchType.AUTO_FUZZY


def _create_match(
    db: Session,
    candidate: MatchCandidate,
    match_type: MatchType,
) -> Match:
    """Create a Match record in the database."""
    match = Match(
        transaction_id=candidate.transaction.id,
        remittance_id=candidate.remittance.id,
        confidence_score=candidate.score_result.total_score,
        match_type=match_type,
        match_details={
            "total_score": candidate.score_result.total_score,
            "max_possible": candidate.score_result.max_possible,
            "rules": {
                name: {
                    "score": rule["score"],
                    "max_score": rule["max_score"],
                    "details": rule["details"],
                }
                for name, rule in candidate.score_result.rule_scores.items()
            },
        },
    )
    db.add(match)
    return match
