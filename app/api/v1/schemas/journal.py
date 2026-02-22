"""Pydantic schemas for journal entry endpoints."""

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class JournalEntryResponse(BaseModel):
    """Single journal entry."""
    id: str
    match_id: str | None = None
    company_code: str
    posting_date: date
    document_date: date
    document_type: str
    line_number: int
    gl_account: str
    debit: Decimal | None = None
    credit: Decimal | None = None
    currency: str
    item_text: str | None = None
    created_at: datetime


class JournalListResponse(BaseModel):
    """List of journal entries with summary."""
    total: int
    total_debit: Decimal
    total_credit: Decimal
    entries: list[JournalEntryResponse]


class JournalExportResponse(BaseModel):
    """Response after exporting journal entries."""
    message: str
    file_name: str
    entries_exported: int
