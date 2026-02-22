"""File upload endpoints for bank statements, remittance PDFs, and emails."""
from collections import Counter

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.bank_transaction import BankTransaction, MatchStatus
from app.models.remittance_advice import RemittanceAdvice, RemittanceLineItem, RemittanceStatus
from app.parsers.bank_statement import parse_bank_statement
from app.parsers.remittance_pdf import parse_remittance_pdf
from app.parsers.email_parser import parse_emails
from app.api.v1.schemas.upload import (
    BankStatementUploadResponse,
    BankTransactionResponse,
    RemittanceUploadResponse,
    RemittanceAdviceResponse,
    RemittanceLineItemResponse,
    EmailUploadResponse,
    ParsedEmailResponse,
)

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("/bank-statement", response_model=BankStatementUploadResponse)
async def upload_bank_statement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and parse a German-format bank statement Excel file."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx or .xls)")

    content = await file.read()

    try:
        parsed = parse_bank_statement(content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse bank statement: {str(e)}")

    # Store transactions in database
    db_transactions = []
    for txn_data in parsed:
        txn = BankTransaction(
            buchungsdatum=txn_data.buchungsdatum,
            valutadatum=txn_data.valutadatum,
            betrag=txn_data.betrag,
            auftraggeber_empfaenger=txn_data.auftraggeber_empfaenger,
            kundenreferenz=txn_data.kundenreferenz,
            verwendungszweck=txn_data.verwendungszweck,
            buchungstext=txn_data.buchungstext,
            bic=txn_data.bic,
            iban=txn_data.iban,
            currency=txn_data.currency,
            match_status=MatchStatus.UNMATCHED,
        )
        db.add(txn)
        db_transactions.append(txn)

    db.commit()
    for txn in db_transactions:
        db.refresh(txn)

    return BankStatementUploadResponse(
        message=f"Successfully parsed {len(db_transactions)} transactions",
        file_name=file.filename,
        transactions_count=len(db_transactions),
        transactions=[
            BankTransactionResponse(
                id=str(txn.id),
                buchungsdatum=txn.buchungsdatum,
                valutadatum=txn.valutadatum,
                betrag=txn.betrag,
                auftraggeber_empfaenger=txn.auftraggeber_empfaenger,
                kundenreferenz=txn.kundenreferenz,
                verwendungszweck=txn.verwendungszweck,
                currency=txn.currency,
                match_status=txn.match_status.value,
            )
            for txn in db_transactions
        ],
    )


@router.post("/remittance", response_model=RemittanceUploadResponse)
async def upload_remittance(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and parse a remittance advice PDF."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF file (.pdf)")

    content = await file.read()

    try:
        parsed = parse_remittance_pdf(content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse remittance PDF: {str(e)}")

    # Store in database
    ra = RemittanceAdvice(
        document_number=parsed.document_number,
        sender_name=parsed.sender_name,
        sender_address=parsed.sender_address,
        document_date=parsed.document_date,
        total_gross_amount=parsed.total_gross_amount,
        total_discount=parsed.total_discount,
        total_net_amount=parsed.total_net_amount,
        currency=parsed.currency,
        match_status=RemittanceStatus.UNMATCHED,
        source_file=file.filename,
    )
    db.add(ra)
    db.flush()

    db_line_items = []
    for li_data in parsed.line_items:
        li = RemittanceLineItem(
            remittance_id=ra.id,
            line_number=li_data.line_number,
            ihre_belegnr=li_data.ihre_belegnr,
            referenz=li_data.referenz,
            bruttobetrag=li_data.bruttobetrag,
            zahlbetrag=li_data.zahlbetrag,
        )
        db.add(li)
        db_line_items.append(li)

    db.commit()
    db.refresh(ra)

    return RemittanceUploadResponse(
        message=f"Successfully parsed remittance advice {parsed.document_number} with {len(db_line_items)} line items",
        file_name=file.filename,
        remittance=RemittanceAdviceResponse(
            id=str(ra.id),
            document_number=ra.document_number,
            sender_name=ra.sender_name,
            document_date=ra.document_date,
            total_gross_amount=ra.total_gross_amount,
            total_discount=ra.total_discount,
            total_net_amount=ra.total_net_amount,
            currency=ra.currency,
            match_status=ra.match_status.value,
            line_items=[
                RemittanceLineItemResponse(
                    id=str(li.id),
                    line_number=li.line_number,
                    ihre_belegnr=li.ihre_belegnr,
                    referenz=li.referenz,
                    bruttobetrag=li.bruttobetrag,
                    zahlbetrag=li.zahlbetrag,
                )
                for li in ra.line_items
            ],
        ),
    )


@router.post("/emails", response_model=EmailUploadResponse)
async def upload_emails(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and classify emails from a JSON file."""
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a JSON file (.json)")

    content = await file.read()

    try:
        parsed = parse_emails(content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse emails: {str(e)}")

    # Build category summary
    categories = Counter(e.category for e in parsed)

    return EmailUploadResponse(
        message=f"Successfully classified {len(parsed)} emails",
        file_name=file.filename,
        emails_count=len(parsed),
        emails=[
            ParsedEmailResponse(
                id=e.id,
                received_at=e.received_at,
                sender=e.sender,
                subject=e.subject,
                category=e.category,
                invoice_references=e.invoice_references,
            )
            for e in parsed
        ],
        category_summary=dict(categories),
    )
