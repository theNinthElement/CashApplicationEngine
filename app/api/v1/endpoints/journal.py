"""Journal entry endpoints — list entries and export to Excel."""

import io
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import pandas as pd

from app.db.session import get_db
from app.models.journal_entry import JournalEntry
from app.api.v1.schemas.journal import (
    JournalEntryResponse,
    JournalListResponse,
    JournalExportResponse,
)

router = APIRouter(prefix="/journal-entries", tags=["Journal Entries"])


@router.get("", response_model=JournalListResponse)
def list_journal_entries(
    match_id: str | None = Query(None, description="Filter by match ID"),
    db: Session = Depends(get_db),
):
    """
    List all journal entries, optionally filtered by match.

    Returns entries ordered by line number, with debit/credit totals.
    """
    query = db.query(JournalEntry)

    if match_id:
        query = query.filter(JournalEntry.match_id == match_id)

    entries = query.order_by(JournalEntry.line_number).all()

    total_debit = sum(e.debit for e in entries if e.debit) or Decimal("0")
    total_credit = sum(e.credit for e in entries if e.credit) or Decimal("0")

    return JournalListResponse(
        total=len(entries),
        total_debit=total_debit,
        total_credit=total_credit,
        entries=[
            JournalEntryResponse(
                id=str(e.id),
                match_id=str(e.match_id) if e.match_id else None,
                company_code=e.company_code,
                posting_date=e.posting_date,
                document_date=e.document_date,
                document_type=e.document_type,
                line_number=e.line_number,
                gl_account=e.gl_account,
                debit=e.debit,
                credit=e.credit,
                currency=e.currency,
                item_text=e.item_text,
                created_at=e.created_at,
            )
            for e in entries
        ],
    )


@router.get("/export")
def export_journal_entries(
    match_id: str | None = Query(None, description="Filter by match ID"),
    db: Session = Depends(get_db),
):
    """
    Export journal entries to Excel format.

    Produces an .xlsx file with the same 10-column structure as
    Sample Journal Entry.xlsx — ready for ERP import.
    """
    query = db.query(JournalEntry)

    if match_id:
        query = query.filter(JournalEntry.match_id == match_id)

    entries = query.order_by(JournalEntry.line_number).all()

    # Build DataFrame matching the Sample Journal Entry format exactly
    rows = []
    for e in entries:
        rows.append({
            "Company Code": int(e.company_code) if e.company_code.isdigit() else e.company_code,
            "Posting Date": e.posting_date,
            "Document Date": e.document_date,
            "Document Type": e.document_type,
            "Line Number": e.line_number,
            "GL Account": int(e.gl_account) if e.gl_account.isdigit() else e.gl_account,
            "Debit": float(e.debit) if e.debit else None,
            "Credit": float(e.credit) if e.credit else None,
            "Currency": e.currency,
            "Item Text": e.item_text,
        })

    df = pd.DataFrame(rows)

    # Write to Excel in memory
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, sheet_name="Journal Entries")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=journal_entries.xlsx"
        },
    )
