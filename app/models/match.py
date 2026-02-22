import uuid
import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.compat import UUID, JSONB

from app.db.base import Base


class MatchType(str, enum.Enum):
    AUTO_EXACT = "auto_exact"
    AUTO_FUZZY = "auto_fuzzy"
    MANUAL = "manual"


class Match(Base):
    """Match between a bank transaction and remittance advice."""

    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(), ForeignKey("bank_transactions.id"), nullable=False
    )
    remittance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(), ForeignKey("remittance_advices.id"), nullable=False
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType), nullable=False)
    match_details: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Approval tracking
    approved: Mapped[bool] = mapped_column(default=False)
    approved_by: Mapped[str] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    transaction: Mapped["BankTransaction"] = relationship(
        "BankTransaction", back_populates="matches"
    )
    remittance: Mapped["RemittanceAdvice"] = relationship(
        "RemittanceAdvice", back_populates="matches"
    )
    journal_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry", back_populates="match", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Match {self.id}: {self.confidence_score}% ({self.match_type.value})>"
