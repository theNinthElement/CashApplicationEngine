import uuid
import enum
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Text, Date, DateTime, Numeric, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.compat import UUID

from app.db.base import Base


class RemittanceStatus(str, enum.Enum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"
    PARTIAL = "partial"


class RemittanceAdvice(Base):
    """Remittance advice document header."""

    __tablename__ = "remittance_advices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(), primary_key=True, default=uuid.uuid4
    )
    document_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=True)
    sender_address: Mapped[str] = mapped_column(Text, nullable=True)
    document_date: Mapped[date] = mapped_column(Date, nullable=True)
    total_gross_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=True)
    total_discount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=True)
    total_net_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    match_status: Mapped[RemittanceStatus] = mapped_column(
        Enum(RemittanceStatus), default=RemittanceStatus.UNMATCHED
    )

    # Source file info
    source_file: Mapped[str] = mapped_column(String(255), nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    line_items: Mapped[list["RemittanceLineItem"]] = relationship(
        "RemittanceLineItem", back_populates="remittance", cascade="all, delete-orphan"
    )
    matches: Mapped[list["Match"]] = relationship(
        "Match", back_populates="remittance", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RemittanceAdvice {self.document_number}: {self.total_net_amount}>"


class RemittanceLineItem(Base):
    """Individual line item within a remittance advice."""

    __tablename__ = "remittance_line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(), primary_key=True, default=uuid.uuid4
    )
    remittance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(), ForeignKey("remittance_advices.id"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    ihre_belegnr: Mapped[str] = mapped_column(String(50), nullable=True)
    referenz: Mapped[str] = mapped_column(String(50), nullable=True)
    skonto: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=True, default=0)
    bruttobetrag: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=True)
    zahlbetrag: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    remittance: Mapped["RemittanceAdvice"] = relationship(
        "RemittanceAdvice", back_populates="line_items"
    )
    journal_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry", back_populates="remittance_line"
    )

    def __repr__(self) -> str:
        return f"<RemittanceLineItem {self.ihre_belegnr}: {self.zahlbetrag}>"
