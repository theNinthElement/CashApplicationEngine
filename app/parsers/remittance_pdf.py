"""Parser for remittance advice PDFs using OCR."""
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from dataclasses import dataclass, field

import pdfplumber
from PIL import Image

# tessdata path for OCR
TESSDATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tessdata"))


def _get_tesserocr():
    """Lazy import tesserocr — only needed when actually parsing PDFs."""
    os.environ.setdefault("TESSDATA_PREFIX", TESSDATA_DIR)
    try:
        import tesserocr
        return tesserocr
    except ImportError:
        raise ImportError(
            "tesserocr is required for PDF parsing. Install it with: pip install tesserocr"
        )


@dataclass
class RemittanceLineItemData:
    """Parsed remittance line item."""
    line_number: int
    ihre_belegnr: str | None
    referenz: str | None
    bruttobetrag: Decimal | None
    zahlbetrag: Decimal


@dataclass
class RemittanceAdviceData:
    """Parsed remittance advice document."""
    document_number: str
    sender_name: str | None
    sender_address: str | None
    document_date: date | None
    total_gross_amount: Decimal | None
    total_discount: Decimal | None
    total_net_amount: Decimal
    currency: str
    line_items: list[RemittanceLineItemData] = field(default_factory=list)


def parse_remittance_pdf(file_content: bytes) -> RemittanceAdviceData:
    """Parse a remittance advice PDF using OCR.

    Args:
        file_content: Raw bytes of the PDF file.

    Returns:
        Parsed remittance advice with line items.
    """
    text = _extract_text_from_pdf(file_content)
    return _parse_remittance_text(text)


def _extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF, using OCR for image-based PDFs."""
    with pdfplumber.open(BytesIO(file_content)) as pdf:
        all_text = []
        for page in pdf.pages:
            # Try direct text extraction first
            text = page.extract_text()
            if text and len(text.strip()) > 50:
                all_text.append(text)
            else:
                # Fall back to OCR
                img = page.to_image(resolution=300)
                pil_img = img.original
                tesserocr = _get_tesserocr()
                ocr_text = tesserocr.image_to_text(pil_img, lang="deu+eng")
                all_text.append(ocr_text)

    return "\n".join(all_text)


def _parse_remittance_text(text: str) -> RemittanceAdviceData:
    """Parse OCR text into structured remittance advice data."""
    # Extract document number (e.g., "10003839")
    document_number = _extract_document_number(text)

    # Extract sender name
    sender_name = _extract_sender_name(text)

    # Extract document date
    document_date = _extract_date(text)

    # Extract currency
    currency = "EUR"
    if "USD" in text:
        currency = "USD"

    # Extract line items and totals
    line_items = _extract_line_items(text)

    # Calculate totals — prefer Gesamtsumme from document, fallback to sum of line items
    gesamtsumme = _extract_gesamtsumme(text)
    line_item_sum = sum(li.zahlbetrag for li in line_items) if line_items else Decimal("0")
    total_net = gesamtsumme if gesamtsumme else line_item_sum

    # Gross totals from line items (may be unreliable due to OCR)
    total_gross = None
    total_discount = None

    return RemittanceAdviceData(
        document_number=document_number,
        sender_name=sender_name,
        sender_address=_extract_sender_address(text),
        document_date=document_date,
        total_gross_amount=total_gross,
        total_discount=total_discount,
        total_net_amount=total_net,
        currency=currency,
        line_items=line_items,
    )


def _extract_document_number(text: str) -> str:
    """Extract document/Nummer from remittance text."""
    # Look for "Nummer" followed by a number
    match = re.search(r"Nummer\s*\n?\s*(\d{5,})", text)
    if match:
        return match.group(1)

    # Look for "Nr." or "Nr" followed by a number
    match = re.search(r"Nr\.?\s*(\d{5,})", text)
    if match:
        return match.group(1)

    # Look for standalone large number near top of document
    lines = text.split("\n")
    for line in lines[:20]:
        match = re.match(r"^\s*(\d{7,})\s*$", line.strip())
        if match:
            return match.group(1)

    raise ValueError("Could not extract document number from remittance PDF")


def _extract_sender_name(text: str) -> str | None:
    """Extract sender company name from first line."""
    lines = text.strip().split("\n")
    for line in lines[:3]:
        line = line.strip()
        # Look for company names (containing GmbH, KG, AG, etc.)
        if re.search(r"(GmbH|KG|AG|Inc|Ltd|Corp)", line, re.IGNORECASE):
            # Clean up OCR artifacts — take the company name part
            name = re.split(r"[.,]", line)[0].strip()
            # Fix common OCR errors
            name = name.replace("Blke", "Bike").replace("Slke", "Bike")
            return name
    return None


def _extract_sender_address(text: str) -> str | None:
    """Extract sender address from header lines."""
    lines = text.strip().split("\n")
    # First line typically has "Company. Address. City"
    if lines:
        first_line = lines[0].strip()
        parts = re.split(r"\.\s+", first_line)
        if len(parts) >= 2:
            # Join address parts (skip company name)
            return ", ".join(parts[1:])
    return None


def _extract_date(text: str) -> date | None:
    """Extract document date from text."""
    # Look for date in DD.MM.YYYY format
    matches = re.findall(r"(\d{2})\.?(\d{2})\.?(\d{4})", text)
    for day, month, year in matches:
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            continue
    return None


def _parse_german_decimal(value: str) -> Decimal | None:
    """Parse a German-format decimal number (e.g., '2.474,78' or '2474,78').

    Handles common OCR errors like 'B' for '8', spaces in numbers, etc.
    """
    if not value:
        return None

    value = value.strip()

    # Fix common OCR letter-to-digit substitutions
    ocr_fixes = {"B": "8", "O": "0", "l": "1", "I": "1", "S": "5", "Z": "2"}
    cleaned = ""
    for ch in value:
        if ch in ocr_fixes:
            cleaned += ocr_fixes[ch]
        else:
            cleaned += ch
    value = cleaned

    # Remove spaces (OCR may insert them: "4 52000" → "452000")
    value = value.replace(" ", "")

    # Remove any remaining non-numeric chars except . , -
    value = re.sub(r"[^\d.,-]", "", value)
    if not value or not re.search(r"\d", value):
        return None

    try:
        # German format: dots as thousands separator, comma as decimal
        if "," in value:
            value = value.replace(".", "").replace(",", ".")
        return Decimal(value)
    except InvalidOperation:
        return None


def _extract_line_items(text: str) -> list[RemittanceLineItemData]:
    """Extract line items from the remittance text.

    OCR often produces columnar output where invoice numbers, references,
    and amounts appear in separate sections rather than on the same line.
    This parser handles both row-based and columnar layouts.
    """
    lines = text.split("\n")

    # Strategy 1: Try row-based extraction first (invoice + ref + amounts on same line)
    items = _extract_line_items_row_based(lines)
    if items:
        return items

    # Strategy 2: Columnar extraction — find each column section separately
    return _extract_line_items_columnar(lines)


def _extract_line_items_row_based(lines: list[str]) -> list[RemittanceLineItemData]:
    """Try to extract line items where all fields are on the same line."""
    items = []
    line_number = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Match: invoice_number  reference  [date]  brutto_amount  zahl_amount
        match = re.match(
            r"(\d{9,})\s+(\S+)\s+.*?(\d[\d.,]+)\s+(\d[\d.,]+)\s*$",
            line
        )
        if match:
            zahl = _parse_german_decimal(match.group(4))
            if zahl:
                line_number += 1
                items.append(RemittanceLineItemData(
                    line_number=line_number,
                    ihre_belegnr=match.group(1),
                    referenz=match.group(2),
                    bruttobetrag=_parse_german_decimal(match.group(3)),
                    zahlbetrag=zahl,
                ))
    return items


def _extract_line_items_columnar(lines: list[str]) -> list[RemittanceLineItemData]:
    """Extract line items from columnar OCR layout.

    The OCR text has separate sections for:
    - Ihre Belegnr. / Referenz (invoice numbers and references)
    - Bruttobetrag (gross amounts)
    - Zahlbetrag (payment amounts)
    """
    # Find section markers
    belegnr_section = _find_section_after(lines, r"Ihre\s+Belegnr|Belegnr")
    ref_section = _find_section_after(lines, r"Gesamtsumme")
    brutto_section = _find_section_after(lines, r"Bruttobetrag")
    zahl_section = _find_section_after(lines, r"^Zahlbetrag$")

    if not zahl_section:
        return []

    # Parse invoice numbers and references from the belegnr section
    invoice_refs = _parse_invoice_ref_section(belegnr_section)

    # Fill in missing references from the section after Gesamtsumme
    if ref_section:
        ref_values = [l.strip() for l in ref_section if l.strip() and not l.strip().startswith("Zahlungs")]
        ref_idx = 0
        for i, (inv, ref) in enumerate(invoice_refs):
            if ref is None and ref_idx < len(ref_values):
                invoice_refs[i] = (inv, ref_values[ref_idx])
                ref_idx += 1

    # Parse amounts
    brutto_amounts = _parse_amount_section(brutto_section)
    zahl_amounts = _parse_amount_section(zahl_section)

    if not zahl_amounts:
        return []

    # Build line items — align by count
    # The last entry in each section is often the total (Gesamtsumme)
    # Remove totals if present (when count matches invoice_refs)
    item_count = len(invoice_refs) if invoice_refs else len(zahl_amounts)

    # If amounts have one extra entry, the last is the total
    if len(zahl_amounts) == item_count + 1:
        zahl_amounts = zahl_amounts[:-1]
    if len(brutto_amounts) == item_count + 1:
        brutto_amounts = brutto_amounts[:-1]

    items = []
    for i in range(min(item_count, len(zahl_amounts))):
        ihre_belegnr = None
        referenz = None
        if i < len(invoice_refs):
            ihre_belegnr = invoice_refs[i][0]
            referenz = invoice_refs[i][1]

        brutto = brutto_amounts[i] if i < len(brutto_amounts) else None
        zahl = zahl_amounts[i]

        if zahl:
            items.append(RemittanceLineItemData(
                line_number=i + 1,
                ihre_belegnr=ihre_belegnr,
                referenz=referenz,
                bruttobetrag=brutto,
                zahlbetrag=zahl,
            ))

    return items


def _find_section_after(lines: list[str], header_pattern: str) -> list[str]:
    """Find non-empty lines after a header until the next section or large gap."""
    result = []
    found_header = False
    blank_count = 0
    for line in lines:
        stripped = line.strip()
        if not found_header:
            if re.search(header_pattern, stripped, re.IGNORECASE):
                found_header = True
                blank_count = 0
            continue

        if not stripped:
            blank_count += 1
            # Stop after 2+ consecutive blank lines (section boundary)
            if blank_count >= 2:
                break
            continue

        blank_count = 0

        # Stop at next known section header
        if re.match(r"^(Bruttobetrag|Zahlbetrag|Belegdatum|Datum\s+Wahr|Zahlungsbeleg)", stripped):
            break

        result.append(stripped)

    return result


def _parse_invoice_ref_section(section_lines: list[str]) -> list[tuple[str | None, str | None]]:
    """Parse invoice number + reference pairs from the belegnr section.

    Lines may contain:
    - "970003839" (invoice only, reference on a separate line below Gesamtsumme)
    - "970003839 P380583" (invoice + reference on same line)
    """
    pairs = []
    for line in section_lines:
        line = line.strip()
        if not line or line.lower().startswith("gesamt"):
            break

        # Invoice number + reference on same line
        match = re.match(r"(\S+)\s+(\S+)\s*$", line)
        if match:
            pairs.append((match.group(1), match.group(2)))
            continue

        # Invoice/reference number only
        if line and not re.search(r"[a-df-zA-DF-Z]{3,}", line):  # skip text lines
            pairs.append((line, None))
            continue

    return pairs


def _parse_amount_section(section_lines: list[str]) -> list[Decimal | None]:
    """Parse German-format amounts from a section."""
    amounts = []
    for line in section_lines:
        line = line.strip()
        if not line:
            continue
        amount = _parse_german_decimal(line)
        if amount is not None:
            amounts.append(amount)
    return amounts


def _extract_gesamtsumme(text: str) -> Decimal | None:
    """Extract total amount from the Zahlbetrag section (last entry is total)."""
    lines = text.split("\n")
    zahl_section = _find_section_after(lines, r"^Zahlbetrag$")
    if not zahl_section:
        return None

    # The last amount in the Zahlbetrag section is the Gesamtsumme
    amounts = _parse_amount_section(zahl_section)
    if amounts:
        return amounts[-1]

    return None
