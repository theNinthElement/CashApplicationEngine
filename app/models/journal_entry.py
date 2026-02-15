import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Date, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class JournalEntry(Base):
    """General ledger journal entry."""

    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id"), nullable=True
    )
    remittance_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remittance_line_items.id"), nullable=True
    )

    # Journal entry fields (matching Sample Journal Entry.xlsx format)
    company_code: Mapped[str] = mapped_column(String(10), default="1000")
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    document_type: Mapped[str] = mapped_column(String(10), default="SA")
    line_number: Mapped[int] = mapped_column(nullable=False)
    gl_account: Mapped[str] = mapped_column(String(20), default="100000")
    debit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=True)
    credit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    item_text: Mapped[str] = mapped_column(String(255), nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    match: Mapped["Match"] = relationship("Match", back_populates="journal_entries")
    remittance_line: Mapped["RemittanceLineItem"] = relationship(
        "RemittanceLineItem", back_populates="journal_entries"
    )

    def __repr__(self) -> str:
        amount = self.debit if self.debit else self.credit
        side = "DR" if self.debit else "CR"
        return f"<JournalEntry {self.line_number}: {side} {amount}>"
