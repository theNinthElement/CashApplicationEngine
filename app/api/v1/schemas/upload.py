"""Pydantic schemas for upload and parsing responses."""
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


# --- Bank Statement Schemas ---

class BankTransactionResponse(BaseModel):
    id: str
    buchungsdatum: date
    valutadatum: date | None = None
    betrag: Decimal
    auftraggeber_empfaenger: str | None = None
    kundenreferenz: str | None = None
    verwendungszweck: str | None = None
    currency: str
    match_status: str

    class Config:
        from_attributes = True


class BankStatementUploadResponse(BaseModel):
    message: str
    file_name: str
    transactions_count: int
    transactions: list[BankTransactionResponse]


# --- Remittance Advice Schemas ---

class RemittanceLineItemResponse(BaseModel):
    id: str
    line_number: int
    ihre_belegnr: str | None = None
    referenz: str | None = None
    bruttobetrag: Decimal | None = None
    zahlbetrag: Decimal

    class Config:
        from_attributes = True


class RemittanceAdviceResponse(BaseModel):
    id: str
    document_number: str
    sender_name: str | None = None
    document_date: date | None = None
    total_gross_amount: Decimal | None = None
    total_discount: Decimal | None = None
    total_net_amount: Decimal
    currency: str
    match_status: str
    line_items: list[RemittanceLineItemResponse]

    class Config:
        from_attributes = True


class RemittanceUploadResponse(BaseModel):
    message: str
    file_name: str
    remittance: RemittanceAdviceResponse


# --- Email Schemas ---

class ParsedEmailResponse(BaseModel):
    id: str
    received_at: datetime | None = None
    sender: str
    subject: str
    category: str
    invoice_references: list[str]


class EmailUploadResponse(BaseModel):
    message: str
    file_name: str
    emails_count: int
    emails: list[ParsedEmailResponse]
    category_summary: dict[str, int]
