"""Processing endpoints — trigger matching and journal generation."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.processing_service import run_processing
from app.api.v1.schemas.processing import (
    ProcessingRequest,
    ProcessingResponse,
    MatchingSummary,
    JournalSummary,
)

router = APIRouter(prefix="/processing", tags=["Processing"])


@router.post("/start", response_model=ProcessingResponse)
def start_processing(
    request: ProcessingRequest = ProcessingRequest(),
    db: Session = Depends(get_db),
):
    """
    Run the full cash application pipeline:
    1. Match unmatched bank transactions to remittance advices
    2. Generate journal entries from matches (and optionally unmatched)

    Call this after uploading bank statements and remittance PDFs.
    """
    result = run_processing(
        db,
        generate_journals=request.generate_journals,
        include_unmatched_journals=request.include_unmatched_journals,
    )

    return ProcessingResponse(
        message=f"Processing complete: {result.auto_matched} auto-matched, {result.journal_entries_created} journal entries created",
        matching=MatchingSummary(
            total_transactions=result.total_transactions,
            total_remittances=result.total_remittances,
            auto_matched=result.auto_matched,
            manual_review=result.manual_review,
            unmatched=result.unmatched,
        ),
        journal=JournalSummary(
            entries_created=result.journal_entries_created,
            from_matches=result.matches_with_journals,
            from_unmatched=result.unmatched_with_journals,
        ),
        started_at=result.started_at,
        completed_at=result.completed_at,
        errors=result.errors,
    )
