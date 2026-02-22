"""Pydantic schemas for processing endpoints."""

from datetime import datetime
from pydantic import BaseModel


class ProcessingRequest(BaseModel):
    """Request body for starting processing."""
    generate_journals: bool = True
    include_unmatched_journals: bool = True


class MatchingSummary(BaseModel):
    total_transactions: int
    total_remittances: int
    auto_matched: int
    manual_review: int
    unmatched: int


class JournalSummary(BaseModel):
    entries_created: int
    from_matches: int
    from_unmatched: int


class ProcessingResponse(BaseModel):
    """Response from running the processing pipeline."""
    message: str
    matching: MatchingSummary
    journal: JournalSummary
    started_at: datetime
    completed_at: datetime | None = None
    errors: list[str]
