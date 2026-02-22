# CashApplicationEngine

Build a working end-to-end program that ingests bank statements and remittance documents, matches payments to invoices, and generates accounting entries ready for the general ledger.

## Overview

The Cash Application Engine automates the cash application process by:

1. **Ingesting** German-format bank statements (Excel)
2. **Parsing** remittance advice PDFs (with OCR)
3. **Matching** payments to invoices using multi-criteria rules
4. **Generating** journal entries for General Ledger posting

## Technology Stack

| Component      | Technology                    |
|----------------|-------------------------------|
| Framework      | FastAPI (async REST API)      |
| Database       | PostgreSQL                    |
| ORM            | SQLAlchemy 2.0 + Alembic      |
| Excel Parsing  | pandas + openpyxl             |
| PDF/OCR        | pdfplumber + pytesseract      |
| Fuzzy Matching | rapidfuzz                     |
| Validation     | Pydantic v2                   |
| Testing        | pytest + pytest-asyncio       |

## Project Structure

```
cash_application_engine/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Settings (env-based)
│   ├── api/v1/
│   │   ├── endpoints/
│   │   │   ├── upload.py       # File upload
│   │   │   ├── processing.py   # Trigger matching
│   │   │   ├── matches.py      # Match results
│   │   │   └── journal.py      # Journal entries
│   │   └── schemas/            # Pydantic models
│   ├── models/                 # SQLAlchemy models
│   │   ├── bank_transaction.py
│   │   ├── remittance_advice.py
│   │   ├── match.py
│   │   └── journal_entry.py
│   ├── parsers/
│   │   ├── bank_statement.py   # Excel parser (German format)
│   │   ├── remittance_pdf.py   # PDF + OCR parser
│   │   └── email_parser.py     # JSON email parser
│   ├── matching/
│   │   ├── engine.py           # Main orchestrator
│   │   ├── rules/              # Individual matching rules
│   │   │   ├── reference_match.py
│   │   │   ├── amount_match.py
│   │   │   ├── company_match.py
│   │   │   └── date_match.py
│   │   └── scoring.py          # Confidence calculation
│   ├── journal/
│   │   └── generator.py        # Create GL entries
│   ├── services/
│   │   └── processing_service.py  # Pipeline orchestration
│   └── db/
│       ├── session.py
│       └── repositories/
├── alembic/                    # DB migrations
├── tests/
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Database Schema

### bank_transactions

| Column                  | Type        | Description                           |
|-------------------------|-------------|---------------------------------------|
| id                      | UUID        | Primary key                           |
| buchungsdatum           | DATE        | Booking date                          |
| betrag                  | DECIMAL     | Amount (negative = outgoing)          |
| auftraggeber_empfaenger | VARCHAR     | Payer/recipient name                  |
| kundenreferenz          | VARCHAR     | Customer reference (key for matching) |
| verwendungszweck        | TEXT        | Purpose/reference text                |
| currency                | VARCHAR(3)  | Currency code                         |
| match_status            | ENUM        | unmatched/matched/manual_review       |

### remittance_advices

| Column           | Type        | Description                        |
|------------------|-------------|------------------------------------|
| id               | UUID        | Primary key                        |
| document_number  | VARCHAR     | PDF document number (e.g., "10003839") |
| sender_name      | VARCHAR     | Payer company name                 |
| total_net_amount | DECIMAL     | Payment total                      |
| match_status     | ENUM        | Status                             |

### remittance_line_items

| Column        | Type    | Description                |
|---------------|---------|----------------------------|
| id            | UUID    | Primary key                |
| remittance_id | UUID    | FK to remittance_advices   |
| ihre_belegnr  | VARCHAR | Invoice number             |
| referenz      | VARCHAR | Reference code             |
| skonto        | DECIMAL | Discount amount            |
| bruttobetrag  | DECIMAL | Gross amount               |
| zahlbetrag    | DECIMAL | Net payment amount         |

### matches

| Column           | Type    | Description                        |
|------------------|---------|------------------------------------|
| id               | UUID    | Primary key                        |
| transaction_id   | UUID    | FK to bank_transactions            |
| remittance_id    | UUID    | FK to remittance_advices           |
| confidence_score | DECIMAL | 0-100 match confidence             |
| match_type       | ENUM    | auto_exact/auto_fuzzy/manual       |
| match_details    | JSONB   | Rule breakdown                     |

### journal_entries

| Column            | Type        | Description                              |
|-------------------|-------------|------------------------------------------|
| id                | UUID        | Primary key                              |
| match_id          | UUID        | FK to matches                            |
| remittance_line_id| UUID        | FK to remittance_line_items (nullable)   |
| company_code      | VARCHAR     | "1000"                                   |
| posting_date      | DATE        | From transaction.buchungsdatum           |
| document_date     | DATE        | Same as posting_date                     |
| document_type     | VARCHAR     | "SA" (Standard Accounting)               |
| line_number       | INTEGER     | Sequential within document               |
| gl_account        | VARCHAR     | "100000"                                 |
| debit             | DECIMAL     | Amount (for incoming payments)           |
| credit            | DECIMAL     | Amount (for outgoing payments)           |
| currency          | VARCHAR(3)  | "EUR"                                    |
| item_text         | VARCHAR     | "{ihre_belegnr}/{referenz}" or bank ref  |

## Matching Algorithm

### Rules & Weights (Total: 100 points)

| Rule            | Weight | Logic                                      |
|-----------------|--------|--------------------------------------------|
| Reference Match | 40     | `kundenreferenz == document_number`        |
| Amount Match    | 35     | `|betrag| == total_net_amount` (±tolerance)|
| Company Match   | 15     | Fuzzy match sender_name (rapidfuzz)        |
| Date Match      | 10     | Booking date proximity to document date    |

### Confidence Thresholds

| Score Range | Action                |
|-------------|-----------------------|
| >= 85       | Auto-match            |
| 60-84       | Manual review required|
| < 60        | Unmatched             |

### Example Match (from sample data)

```
Bank Transaction:
  - auftraggeber_empfaenger: "Bike Team GmbH"
  - betrag: -38,935.25 EUR
  - kundenreferenz: "10003839"

Remittance Advice:
  - document_number: "10003839"
  - sender_name: "Bike Team GmbH"
  - total_net_amount: 38,935.25 EUR

Score: 40 (ref) + 35 (amount) + 15 (company) + 10 (date) = 100 points
Result: AUTO-MATCH
```

## Journal Entry Output

### Output Format (10 columns)

```
Company Code | Posting Date | Document Date | Document Type | Line Number | GL Account | Debit | Credit | Currency | Item Text
```

### Entry Generation Rules

1. **Matched Transactions with Remittance PDF**: Create ONE journal entry PER remittance line item
   - Amount = `zahlbetrag` from line item
   - Item Text = `{ihre_belegnr}/{referenz}` (e.g., "970003839/38000383")

2. **Debit vs Credit Logic**:
   - Bank `betrag < 0` (negative/outgoing) → **CREDIT** entry
   - Bank `betrag > 0` (positive/incoming) → **DEBIT** entry

3. **Unmatched Transactions**: Create single journal entry using bank statement data
   - Item Text = `kundenreferenz` from bank statement

### Example Output (Bike Team GmbH Match)

| Line | GL Account | Debit | Credit    | Item Text              |
|------|------------|-------|-----------|------------------------|
| 1    | 100000     | -     | 2,474.78  | 970003839/38000383     |
| 2    | 100000     | -     | 4,589.00  | 970003539/ZT38000383   |
| 3    | 100000     | -     | 10,115.45 | 970003839/538000383    |
| 4    | 100000     | -     | 11,898.98 | 970006839/800383       |
| 5    | 100000     | -     | 7,892.23  | 970003839/P38083       |
| 6    | 100000     | -     | 759.36    | 970007839/8000383      |
| 7    | 100000     | -     | 1,205.45  | 970009839/383          |
| **Total** |       |       | **38,935.25** |                    |

## API Endpoints

| Method | Endpoint                        | Description           |
|--------|--------------------------------|-----------------------|
| POST   | `/api/v1/upload/bank-statement`| Upload Excel          |
| POST   | `/api/v1/upload/remittance`    | Upload PDF            |
| POST   | `/api/v1/processing/start`     | Trigger matching      |
| GET    | `/api/v1/processing/{id}/status`| Check status         |
| GET    | `/api/v1/matches`              | List matches          |
| PUT    | `/api/v1/matches/{id}`         | Update/approve match  |
| POST   | `/api/v1/matches/manual`       | Create manual match   |
| GET    | `/api/v1/journal-entries`      | List entries          |
| POST   | `/api/v1/journal-entries/export`| Export to Excel      |

## Implementation Phases

### Phase 1: Foundation
- Initialize project structure with FastAPI
- Set up PostgreSQL + SQLAlchemy + Alembic
- Create database models and run migrations
- Implement basic health endpoint

### Phase 2: Parsers
- **Bank Statement Parser** (`parsers/bank_statement.py`)
  - Parse German column headers (Buchungsdatum, Betrag, etc.)
  - Handle German number format (comma decimal)
  - Extract reference from Verwendungszweck

- **Remittance PDF Parser** (`parsers/remittance_pdf.py`)
  - OCR with pytesseract/pdfplumber
  - Extract header (document_number, sender, totals)
  - Parse line item table (invoices, discounts)

- **Email Parser** (`parsers/email_parser.py`)
  - Parse JSON format
  - Classify email types
  - Extract invoice references

### Phase 3: Matching Engine
- Implement matching rules:
  - `rules/reference_match.py` - exact reference matching
  - `rules/amount_match.py` - amount with tolerance
  - `rules/company_match.py` - fuzzy name matching
  - `rules/date_match.py` - date proximity

- Create `matching/engine.py` orchestrator
  - Find candidates
  - Score and rank
  - Apply thresholds

### Phase 4: Journal Generation
- Implement `journal/generator.py`
- For matched transactions: one entry per remittance line item
- For unmatched transactions: single entry from bank statement
- Apply debit/credit logic based on amount sign

### Phase 5: API & Integration
- Complete REST endpoints
- Implement processing pipeline service
- Add export functionality (Excel/CSV)

### Phase 6: Testing
- Unit tests for parsers and matching rules
- Integration tests with sample data
- API endpoint tests

## Sample Files

| File | Description |
|------|-------------|
| `Samples/Sample Bank Statement.xlsx` | German format with Kundenreferenz "10003839" |
| `Samples/Sample Payment Advice.pdf` | Document #10003839, 7 line items, total 38,935.25 EUR |
| `Samples/Sample Journal Entry.xlsx` | Expected output format |
| `Samples/Sample Emails.json` | Email classification patterns |

## Getting Started

```bash
# Clone the repository
git clone <repo-url>
cd CashApplicationEngine

# Start services
docker-compose up -d

# Run migrations
alembic upgrade head

# Start the API
uvicorn app.main:app --reload
```

## Testing with Sample Data
#start the server locally
python3 -m uvicorn app.main:app --reload --port 8000


```bash
# Upload bank statement
curl -X POST -F "file=@Samples/Sample Bank Statement.xlsx" \
  http://localhost:8000/api/v1/upload/bank-statement

# Upload remittance
curl -X POST -F "file=@Samples/Sample Payment Advice.pdf" \
  http://localhost:8000/api/v1/upload/remittance

# Start processing
curl -X POST http://localhost:8000/api/v1/processing/start \
  -H "Content-Type: application/json" \
  -d '{"bank_statement_id": "...", "remittance_ids": ["..."]}'

# Check results
curl http://localhost:8000/api/v1/matches
curl http://localhost:8000/api/v1/journal-entries
```
