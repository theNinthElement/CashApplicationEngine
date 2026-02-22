"""Parser for German-format bank statement Excel files."""
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from dataclasses import dataclass

import pandas as pd


@dataclass
class BankTransactionData:
    """Parsed bank transaction record."""
    buchungsdatum: date
    valutadatum: date | None
    betrag: Decimal
    auftraggeber_empfaenger: str | None
    kundenreferenz: str | None
    verwendungszweck: str | None
    buchungstext: str | None
    bic: str | None
    iban: str | None
    currency: str


# Map German column names to our field names
COLUMN_MAP = {
    "Buchungsdatum": "buchungsdatum",
    "Valutadatum": "valutadatum",
    "Betrag": "betrag",
    "Auftraggeber/Empfänger": "auftraggeber_empfaenger",
    "Kundenreferenz": "kundenreferenz",
    "Verwendungszweck": "verwendungszweck",
    "Buchungstext": "buchungstext",
    "BIC": "bic",
    "IBAN": "iban",
    "Währung": "currency",
}


def parse_bank_statement(file_content: bytes) -> list[BankTransactionData]:
    """Parse a German-format bank statement Excel file.

    Args:
        file_content: Raw bytes of the Excel file.

    Returns:
        List of parsed bank transaction records.
    """
    df = pd.read_excel(BytesIO(file_content))

    # Validate required columns exist
    missing = {"Buchungsdatum", "Betrag"} - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    transactions = []
    for _, row in df.iterrows():
        # Parse amount — handle German comma format if stored as string
        betrag = row["Betrag"]
        if isinstance(betrag, str):
            betrag = betrag.replace(".", "").replace(",", ".")
        betrag = Decimal(str(betrag))

        # Parse dates
        buchungsdatum = pd.Timestamp(row["Buchungsdatum"]).date()
        valutadatum = None
        if "Valutadatum" in df.columns and pd.notna(row.get("Valutadatum")):
            valutadatum = pd.Timestamp(row["Valutadatum"]).date()

        # Parse kundenreferenz — may be numeric
        kundenreferenz = None
        if "Kundenreferenz" in df.columns and pd.notna(row.get("Kundenreferenz")):
            kundenreferenz = str(row["Kundenreferenz"]).strip()

        # Currency
        currency = "EUR"
        if "Währung" in df.columns and pd.notna(row.get("Währung")):
            currency = str(row["Währung"]).strip()

        txn = BankTransactionData(
            buchungsdatum=buchungsdatum,
            valutadatum=valutadatum,
            betrag=betrag,
            auftraggeber_empfaenger=_safe_str(row.get("Auftraggeber/Empfänger")),
            kundenreferenz=kundenreferenz,
            verwendungszweck=_safe_str(row.get("Verwendungszweck")),
            buchungstext=_safe_str(row.get("Buchungstext")),
            bic=_safe_str(row.get("BIC")),
            iban=_safe_str(row.get("IBAN")),
            currency=currency,
        )
        transactions.append(txn)

    return transactions


def _safe_str(value) -> str | None:
    """Convert value to string, returning None for NaN/None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value).strip()
