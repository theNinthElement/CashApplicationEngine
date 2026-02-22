"""
Journal entry generator.

Creates General Ledger journal entries from matched (and optionally unmatched)
bank transactions. Output format matches Sample Journal Entry.xlsx exactly:

  Company Code | Posting Date | Document Date | Document Type |
  Line Number  | GL Account   | Debit         | Credit        |
  Currency     | Item Text

Two generation paths:
  1. Matched transactions (have remittance PDF):
     → One entry per remittance line item
     → Amount from line_item.zahlbetrag
     → Item text = "{ihre_belegnr}/{referenz}"

  2. Unmatched transactions (no remittance):
     → Single entry from bank statement
     → Amount from abs(bank.betrag)
     → Item text = bank.kundenreferenz

Debit/Credit logic:
  - bank.betrag < 0 (outgoing) → CREDIT
  - bank.betrag > 0 (incoming) → DEBIT
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models.bank_transaction import BankTransaction, MatchStatus
from app.models.match import Match
from app.models.journal_entry import JournalEntry

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Summary of a journal generation run."""

    entries_created: int = 0
    matches_processed: int = 0
    unmatched_processed: int = 0
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entries_created": self.entries_created,
            "matches_processed": self.matches_processed,
            "unmatched_processed": self.unmatched_processed,
            "errors": self.errors,
        }


def generate_journal_entries(
    db: Session,
    include_unmatched: bool = True,
) -> GenerationResult:
    """
    Generate journal entries for all matches that don't have entries yet,
    and optionally for unmatched transactions.

    Args:
        db: SQLAlchemy session
        include_unmatched: If True, also generate entries for unmatched transactions

    Returns:
        GenerationResult with counts and any errors.
    """
    settings = get_settings()
    result = GenerationResult()

    # Global line number counter — entries are numbered sequentially across
    # the entire batch, just like in the sample journal Excel file
    line_number = 1

    # ─── Path 1: Matched transactions ───────────────────────────────────
    # Load matches that don't have journal entries yet.
    # Eager-load the transaction, remittance, and line items so we have
    # all data in memory without extra DB round-trips.
    matches = (
        db.query(Match)
        .options(
            joinedload(Match.transaction),
            joinedload(Match.remittance).joinedload(
                __import__("app.models.remittance_advice", fromlist=["RemittanceAdvice"])
                .RemittanceAdvice.line_items
            ),
        )
        .filter(~Match.journal_entries.any())  # no entries generated yet
        .all()
    )

    for match in matches:
        try:
            txn = match.transaction
            remittance = match.remittance

            # For each line item in the remittance PDF, create one journal entry.
            # This is the core accounting logic: each invoice being paid gets its
            # own GL line so accountants can reconcile individual invoices.
            for line_item in remittance.line_items:
                entry = _create_entry_from_line_item(
                    match=match,
                    txn=txn,
                    line_item=line_item,
                    line_number=line_number,
                    settings=settings,
                )
                db.add(entry)
                line_number += 1
                result.entries_created += 1

            result.matches_processed += 1
            logger.info(
                "Generated %d entries for match %s (txn: %s ↔ rem: %s)",
                len(remittance.line_items),
                match.id,
                txn.auftraggeber_empfaenger,
                remittance.document_number,
            )

        except Exception as e:
            logger.error("Error generating entries for match %s: %s", match.id, e)
            result.errors.append(f"Match {match.id}: {str(e)}")

    # ─── Path 2: Unmatched transactions ─────────────────────────────────
    # These have no remittance PDF, so we create a single entry per transaction
    # using the bank statement data directly. This ensures every bank movement
    # has a corresponding GL entry.
    if include_unmatched:
        unmatched_txns = (
            db.query(BankTransaction)
            .filter(BankTransaction.match_status == MatchStatus.UNMATCHED)
            .all()
        )

        for txn in unmatched_txns:
            # Skip if journal entries already exist for this transaction
            # (via a previous generation run)
            existing = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.item_text == (txn.kundenreferenz or ""),
                    JournalEntry.posting_date == txn.buchungsdatum,
                    JournalEntry.match_id.is_(None),
                )
                .first()
            )
            if existing:
                continue

            try:
                entry = _create_entry_from_transaction(
                    txn=txn,
                    line_number=line_number,
                    settings=settings,
                )
                db.add(entry)
                line_number += 1
                result.entries_created += 1
                result.unmatched_processed += 1

            except Exception as e:
                logger.error("Error generating entry for txn %s: %s", txn.id, e)
                result.errors.append(f"Transaction {txn.id}: {str(e)}")

    db.commit()

    logger.info(
        "Journal generation complete: %d entries (%d from matches, %d from unmatched)",
        result.entries_created,
        result.matches_processed,
        result.unmatched_processed,
    )

    return result


def _create_entry_from_line_item(match, txn, line_item, line_number, settings):
    """
    Create a journal entry from a remittance line item.

    The amount comes from line_item.zahlbetrag (payment amount for this invoice).
    Item text format: "{ihre_belegnr}/{referenz}" — e.g., "970003839/38000383"
    This format lets accountants trace back to the original invoice number and
    payment reference.
    """
    amount = abs(line_item.zahlbetrag)

    # Build item_text from invoice number and reference
    # Some line items may have one or both fields missing
    parts = []
    if line_item.ihre_belegnr:
        parts.append(str(line_item.ihre_belegnr))
    if line_item.referenz:
        parts.append(str(line_item.referenz))
    item_text = "/".join(parts) if parts else f"Match-{match.id}"

    # Debit/Credit: negative bank amount = outgoing = CREDIT
    debit, credit = _determine_debit_credit(txn.betrag, amount)

    return JournalEntry(
        match_id=match.id,
        remittance_line_id=line_item.id,
        company_code=settings.default_company_code,
        posting_date=txn.buchungsdatum,
        document_date=txn.buchungsdatum,
        document_type=settings.default_document_type,
        line_number=line_number,
        gl_account=settings.default_gl_account,
        debit=debit,
        credit=credit,
        currency=txn.currency or settings.default_currency,
        item_text=item_text,
    )


def _create_entry_from_transaction(txn, line_number, settings):
    """
    Create a journal entry from an unmatched bank transaction.

    No remittance PDF exists, so we use the bank reference as item_text
    and the full transaction amount.
    """
    amount = abs(txn.betrag)
    item_text = txn.kundenreferenz or txn.verwendungszweck or ""
    debit, credit = _determine_debit_credit(txn.betrag, amount)

    return JournalEntry(
        match_id=None,
        remittance_line_id=None,
        company_code=settings.default_company_code,
        posting_date=txn.buchungsdatum,
        document_date=txn.buchungsdatum,
        document_type=settings.default_document_type,
        line_number=line_number,
        gl_account=settings.default_gl_account,
        debit=debit,
        credit=credit,
        currency=txn.currency or settings.default_currency,
        item_text=item_text,
    )


def _determine_debit_credit(
    bank_betrag: Decimal, amount: Decimal
) -> tuple[Decimal | None, Decimal | None]:
    """
    Determine whether an amount goes to debit or credit.

    The rule (from Sample Journal Entry.xlsx):
      - bank.betrag < 0 (money leaving the account, outgoing payment) → CREDIT
      - bank.betrag > 0 (money entering the account, incoming payment) → DEBIT

    Returns:
        (debit, credit) tuple — one is the amount, the other is None.
    """
    if bank_betrag < 0:
        return None, amount  # CREDIT (outgoing)
    else:
        return amount, None  # DEBIT (incoming)
