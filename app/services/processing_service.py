"""
Processing service — orchestrates the full cash application pipeline.

Called by the /processing/start endpoint. Runs in sequence:
  1. Matching engine (score transactions against remittances)
  2. Journal generation (create GL entries from matches)

Keeps the API layer thin by encapsulating the pipeline logic here.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.matching.engine import run_matching
from app.journal.generator import generate_journal_entries

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Full pipeline result combining matching + journal generation."""

    # Matching results
    total_transactions: int = 0
    total_remittances: int = 0
    auto_matched: int = 0
    manual_review: int = 0
    unmatched: int = 0

    # Journal results
    journal_entries_created: int = 0
    matches_with_journals: int = 0
    unmatched_with_journals: int = 0

    # Metadata
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "matching": {
                "total_transactions": self.total_transactions,
                "total_remittances": self.total_remittances,
                "auto_matched": self.auto_matched,
                "manual_review": self.manual_review,
                "unmatched": self.unmatched,
            },
            "journal": {
                "entries_created": self.journal_entries_created,
                "from_matches": self.matches_with_journals,
                "from_unmatched": self.unmatched_with_journals,
            },
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "errors": self.errors,
        }


def run_processing(
    db: Session,
    generate_journals: bool = True,
    include_unmatched_journals: bool = True,
) -> ProcessingResult:
    """
    Run the full cash application pipeline.

    Args:
        db: SQLAlchemy session
        generate_journals: Whether to generate journal entries after matching
        include_unmatched_journals: Whether to create journal entries for
                                    unmatched transactions too

    Returns:
        ProcessingResult with combined matching + journal stats.
    """
    result = ProcessingResult()

    # ── Step 1: Run matching engine ──
    logger.info("Starting matching engine...")
    match_result = run_matching(db)

    result.total_transactions = match_result.total_transactions
    result.total_remittances = match_result.total_remittances
    result.auto_matched = match_result.auto_matched
    result.manual_review = match_result.manual_review
    result.unmatched = match_result.unmatched
    result.errors.extend(match_result.errors)

    # ── Step 2: Generate journal entries ──
    if generate_journals:
        logger.info("Starting journal generation...")
        journal_result = generate_journal_entries(
            db, include_unmatched=include_unmatched_journals
        )

        result.journal_entries_created = journal_result.entries_created
        result.matches_with_journals = journal_result.matches_processed
        result.unmatched_with_journals = journal_result.unmatched_processed
        result.errors.extend(journal_result.errors)

    result.completed_at = datetime.utcnow()

    logger.info(
        "Processing complete: %d matched, %d review, %d unmatched, %d journal entries",
        result.auto_matched,
        result.manual_review,
        result.unmatched,
        result.journal_entries_created,
    )

    return result
