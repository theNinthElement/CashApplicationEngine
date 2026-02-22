"""Match endpoints — list, approve, and manually create matches."""

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.bank_transaction import BankTransaction, MatchStatus
from app.models.remittance_advice import RemittanceAdvice, RemittanceStatus
from app.models.match import Match, MatchType
from app.matching.scoring import score_pair
from app.api.v1.schemas.matches import (
    MatchResponse,
    MatchListResponse,
    MatchApproveRequest,
    MatchDetailResponse,
    MatchRuleDetail,
    MatchTransactionSummary,
    MatchRemittanceSummary,
    ManualMatchRequest,
)

router = APIRouter(prefix="/matches", tags=["Matches"])


def _match_to_response(match: Match) -> MatchResponse:
    """Convert a Match ORM object to a MatchResponse schema."""
    txn = match.transaction
    rem = match.remittance

    # Parse match_details JSONB into structured response
    detail_response = None
    if match.match_details:
        detail_response = MatchDetailResponse(
            total_score=match.match_details.get("total_score", 0),
            max_possible=match.match_details.get("max_possible", 0),
            rules={
                name: MatchRuleDetail(**rule_data)
                for name, rule_data in match.match_details.get("rules", {}).items()
            },
        )

    return MatchResponse(
        id=str(match.id),
        confidence_score=match.confidence_score,
        match_type=match.match_type.value,
        match_details=detail_response,
        approved=match.approved,
        approved_by=match.approved_by,
        approved_at=match.approved_at,
        created_at=match.created_at,
        transaction=MatchTransactionSummary(
            id=str(txn.id),
            buchungsdatum=txn.buchungsdatum,
            betrag=txn.betrag,
            auftraggeber_empfaenger=txn.auftraggeber_empfaenger,
            kundenreferenz=txn.kundenreferenz,
            currency=txn.currency,
        ),
        remittance=MatchRemittanceSummary(
            id=str(rem.id),
            document_number=rem.document_number,
            sender_name=rem.sender_name,
            total_net_amount=rem.total_net_amount,
            line_items_count=len(rem.line_items),
        ),
    )


@router.get("", response_model=MatchListResponse)
def list_matches(
    match_type: str | None = Query(None, description="Filter by match type: auto_exact, auto_fuzzy, manual"),
    approved: bool | None = Query(None, description="Filter by approval status"),
    db: Session = Depends(get_db),
):
    """
    List all matches with optional filtering.

    Use match_type to see only auto or manual matches.
    Use approved=false to see matches awaiting approval.
    """
    query = (
        db.query(Match)
        .options(
            joinedload(Match.transaction),
            joinedload(Match.remittance).joinedload(RemittanceAdvice.line_items),
        )
    )

    if match_type:
        try:
            mt = MatchType(match_type)
            query = query.filter(Match.match_type == mt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid match_type '{match_type}'. Use: auto_exact, auto_fuzzy, manual",
            )

    if approved is not None:
        query = query.filter(Match.approved == approved)

    matches = query.order_by(Match.created_at.desc()).all()

    return MatchListResponse(
        total=len(matches),
        matches=[_match_to_response(m) for m in matches],
    )


@router.get("/{match_id}", response_model=MatchResponse)
def get_match(
    match_id: str,
    db: Session = Depends(get_db),
):
    """Get a single match by ID with full details."""
    match = (
        db.query(Match)
        .options(
            joinedload(Match.transaction),
            joinedload(Match.remittance).joinedload(RemittanceAdvice.line_items),
        )
        .filter(Match.id == match_id)
        .first()
    )

    if not match:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    return _match_to_response(match)


@router.put("/{match_id}/approve", response_model=MatchResponse)
def approve_match(
    match_id: str,
    request: MatchApproveRequest,
    db: Session = Depends(get_db),
):
    """
    Approve a match (typically one in manual_review status).

    This updates the match as approved, sets the transaction to MATCHED,
    and sets the remittance to MATCHED.
    """
    match = (
        db.query(Match)
        .options(
            joinedload(Match.transaction),
            joinedload(Match.remittance).joinedload(RemittanceAdvice.line_items),
        )
        .filter(Match.id == match_id)
        .first()
    )

    if not match:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    if match.approved:
        raise HTTPException(status_code=400, detail="Match is already approved")

    # Approve the match
    match.approved = True
    match.approved_by = request.approved_by
    match.approved_at = datetime.utcnow()

    # Update statuses on both sides
    match.transaction.match_status = MatchStatus.MATCHED
    match.remittance.match_status = RemittanceStatus.MATCHED

    db.commit()
    db.refresh(match)

    return _match_to_response(match)


@router.post("/manual", response_model=MatchResponse)
def create_manual_match(
    request: ManualMatchRequest,
    db: Session = Depends(get_db),
):
    """
    Create a manual match between a transaction and remittance.

    Use this when the automatic engine didn't match something that should
    be matched. The system still scores the pair so you can see why the
    engine missed it.
    """
    txn = db.query(BankTransaction).filter(BankTransaction.id == request.transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail=f"Transaction {request.transaction_id} not found")

    rem = (
        db.query(RemittanceAdvice)
        .options(joinedload(RemittanceAdvice.line_items))
        .filter(RemittanceAdvice.id == request.remittance_id)
        .first()
    )
    if not rem:
        raise HTTPException(status_code=404, detail=f"Remittance {request.remittance_id} not found")

    # Score the pair for auditability (even though it's manual)
    score_result = score_pair(txn, rem)

    match = Match(
        transaction_id=txn.id,
        remittance_id=rem.id,
        confidence_score=Decimal(str(score_result.total_score)),
        match_type=MatchType.MANUAL,
        match_details={
            "total_score": score_result.total_score,
            "max_possible": score_result.max_possible,
            "rules": {
                name: {
                    "score": rule["score"],
                    "max_score": rule["max_score"],
                    "details": rule["details"],
                }
                for name, rule in score_result.rule_scores.items()
            },
        },
        approved=bool(request.approved_by),
        approved_by=request.approved_by,
        approved_at=datetime.utcnow() if request.approved_by else None,
    )
    db.add(match)

    txn.match_status = MatchStatus.MATCHED
    rem.match_status = RemittanceStatus.MATCHED

    db.commit()
    db.refresh(match)

    # Re-load with relationships for response
    match = (
        db.query(Match)
        .options(
            joinedload(Match.transaction),
            joinedload(Match.remittance).joinedload(RemittanceAdvice.line_items),
        )
        .filter(Match.id == match.id)
        .first()
    )

    return _match_to_response(match)
