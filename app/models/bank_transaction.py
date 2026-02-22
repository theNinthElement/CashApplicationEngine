import uuid
import enum
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Text, Date, DateTime, Numeric, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.compat import UUID

from app.db.base import Base


class MatchStatus(str, enum.Enum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"
    MANUAL_REVIEW = "manual_review"


class BankTransaction(Base):
    """Bank statement transaction record."""

    __tablename__ = "bank_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(), primary_key=True, default=uuid.uuid4
    )
    buchungsdatum: Mapped[date] = mapped_column(Date, nullable=False)
    betrag: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    auftraggeber_empfaenger: Mapped[str] = mapped_column(String(255), nullable=True)
    kundenreferenz: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    verwendungszweck: Mapped[str] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    match_status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus), default=MatchStatus.UNMATCHED
    )

    # Additional fields from bank statement
    valutadatum: Mapped[date] = mapped_column(Date, nullable=True)
    buchungstext: Mapped[str] = mapped_column(String(255), nullable=True)
    bic: Mapped[str] = mapped_column(String(11), nullable=True)
    iban: Mapped[str] = mapped_column(String(34), nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    matches: Mapped[list["Match"]] = relationship(
        "Match", back_populates="transaction", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BankTransaction {self.id}: {self.betrag} {self.currency}>"
