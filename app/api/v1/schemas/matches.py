"""Pydantic schemas for match endpoints."""

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class MatchRuleDetail(BaseModel):
    score: float
    max_score: float
    details: str


class MatchDetailResponse(BaseModel):
    total_score: float
    max_possible: float
    rules: dict[str, MatchRuleDetail]


class MatchTransactionSummary(BaseModel):
    """Embedded bank transaction info inside a match response."""
    id: str
    buchungsdatum: date
    betrag: Decimal
    auftraggeber_empfaenger: str | None = None
    kundenreferenz: str | None = None
    currency: str


class MatchRemittanceSummary(BaseModel):
    """Embedded remittance info inside a match response."""
    id: str
    document_number: str
    sender_name: str | None = None
    total_net_amount: Decimal
    line_items_count: int


class MatchResponse(BaseModel):
    """Single match record."""
    id: str
    confidence_score: Decimal
    match_type: str
    match_details: MatchDetailResponse | None = None
    approved: bool
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    transaction: MatchTransactionSummary
    remittance: MatchRemittanceSummary


class MatchListResponse(BaseModel):
    """List of matches with count."""
    total: int
    matches: list[MatchResponse]


class MatchApproveRequest(BaseModel):
    """Request body for approving a match."""
    approved_by: str


class ManualMatchRequest(BaseModel):
    """Request body for creating a manual match."""
    transaction_id: str
    remittance_id: str
    approved_by: str | None = None
