# Clausely

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-black.svg)](https://langchain-ai.github.io/langgraph/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Tests Passing](https://img.shields.io/badge/tests-59%20passed-brightgreen.svg)]()

> **Autonomous contract extraction and compliance auditing system with stateful human-in-the-loop review.**

Clausely processes SaaS and vendor agreements automatically. It parses contract text or PDF files, extracts structured fields using LLMs, validates data against strict Pydantic schemas, self-corrects extraction errors using feedback prompts, and audits contract terms against corporate compliance rules. When high-risk clauses or validation failures occur, Clausely pauses execution at a durable checkpoint and waits for human approval before persisting results.

---

## Architecture & Workflow

```text
               ┌───────────────────────┐
               │   Contract Document   │
               │      (PDF / Text)     │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │   Extract Raw Text    │
               │   (pypdf / UTF-8)     │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
        ┌─────►│  LLM Extraction Node  │
        │      │   (Google Gemini)     │
        │      └───────────┬───────────┘
        │                  │
        │                  ▼
        │      ┌───────────────────────┐
        │      │  Pydantic Validation  │
        │      └──────┬─────────┬──────┘
        │             │         │
    (Retry)        (Valid)  (Invalid)
        │             │         │
        │             │         ▼
        │             │   [ Retries < Max? ]
        │             │    │              │
        └─────────────┴────┘             (No)
                      │                   │
                      ▼                   ▼
           ┌──────────────────────┐  ┌───────────────┐
           │  Compliance Auditor  │  │ Status: FAILED│
           │ (Pure Python Rules)  │  └───────┬───────┘
           └──────────┬───────────┘          │
                      │                      │
                      ▼                      │
           [ High Risk Detected? ]           │
             │                 │             │
            (No)             (Yes)           │
             │                 │             │
             │                 ▼             ▼
             │       ┌───────────────────────────────┐
             │       │    LangGraph interrupt()      │
             │       │    (Durable SQLite State)     │
             │       └───────────────┬───────────────┘
             │                       │
             │                       ▼
             │       ┌───────────────────────────────┐
             │       │       Human Review API        │
             │       │   (Approve / Reject / Edit)   │
             │       └───────────────┬───────────────┘
             │                       │
             │                       ▼
             │       ┌───────────────────────────────┐
             │       │       Resume Execution        │
             │       └───────────────┬───────────────┘
             │                       │
             ▼                       ▼
      ┌──────────────────────────────────────────────┐
      │             Save to Database                 │
      │           (SQLite via SQLAlchemy)            │
      └──────────────────────┬───────────────────────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │  Processing Complete  │
                 └───────────────────────┘
```

---

## Key Features

* **Structured Data Extraction:** Parses vendor name, customer name, effective dates, annual contract value, liability caps, governing law, and notice periods into typed Pydantic models.
* **Self-Healing Reflection Loop:** If LLM extraction produces invalid fields or incorrect types, validation errors are fed directly back into the LLM prompt for automatic correction up to a configurable retry limit.
* **Deterministic Compliance Engine:** Audits liability caps, governing law jurisdictions, renewal notice periods, and termination notice periods using explicit business logic.
* **Stateful Human-in-the-Loop (HITL):** Uses LangGraph checkpoints and `interrupt()` to pause workflow threads for high-risk contracts or exhausted retries until a reviewer approves, rejects, or edits fields via the API.
* **100% Configurable:** No hardcoded policy rules, retry thresholds, or model identifiers. Everything is driven by environment variables.
* **Clean & Simple Codebase:** Written following explicit, novice-friendly code style without unnecessary layers, wrappers, or over-engineered abstractions.

---

## Tech Stack

* **Language:** Python 3.11+
* **Framework:** FastAPI
* **Workflow Engine:** LangGraph (with SQLite checkpointer)
* **LLM Provider:** Google Gemini API via `langchain-google-genai`
* **Data Validation:** Pydantic v2 & Pydantic Settings
* **Database & ORM:** SQLite & SQLAlchemy 2.0
* **PDF Parsing:** pypdf
* **Testing:** Pytest

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/Clausely.git
cd Clausely
```

### 2. Create and Activate a Virtual Environment

```bash
# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example `.env` file and set your Google Gemini API key:

```bash
cp .env.example .env
```

Edit `.env`:
```ini
GEMINI_API_KEY="your-gemini-api-key"
GEMINI_MODEL="gemini-3.5-flash-lite"
```

### 5. Run the Server

Start the API using the `main.py` entrypoint:

```bash
python main.py
```

Or using `uvicorn` directly:
```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

Open interactive Swagger documentation at **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## Configuration Reference

All application parameters are configured via environment variables or a local `.env` file:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | `string` | `"your-api-key"` | Google Gemini API key |
| `GEMINI_MODEL` | `string` | `"gemini-3.5-flash-lite"` | Gemini model identifier |
| `MAX_EXTRACTION_RETRIES` | `integer` | `3` | Maximum self-correction attempts on schema validation error |
| `DATABASE_URL` | `string` | `"sqlite:///./clausely.db"` | SQLAlchemy database connection string |
| `POLICY_MAX_LIABILITY_CAP_USD` | `float` | `500000.0` | Maximum allowable liability cap amount in USD |
| `POLICY_LIABILITY_ANNUAL_MULTIPLE` | `float` | `2.0` | Maximum liability cap as a multiple of annual contract value |
| `POLICY_MIN_RENEWAL_NOTICE_DAYS` | `integer` | `30` | Minimum notice days required before automatic contract renewal |
| `POLICY_MIN_TERMINATION_NOTICE_DAYS`| `integer` | `30` | Minimum notice days required for termination for convenience |
| `POLICY_APPROVED_JURISDICTIONS` | `string` | `"US-DE,US-NY,US-CA,UK"` | Comma-separated list of approved governing law jurisdictions |
| `API_HOST` | `string` | `"0.0.0.0"` | Host interface for FastAPI server |
| `API_PORT` | `integer` | `8000` | Port for FastAPI server |

---

## API Reference

### 1. Upload Document
Upload contract text or a PDF file to begin processing.

* **Endpoint:** `POST /documents/upload`
* **Content-Type:** `multipart/form-data`

**Request Parameters:**
* `file` (optional): Uploaded file (`.pdf` or `.txt`)
* `raw_text` (optional): Raw contract text string
* `filename` (optional): Document filename (default: `contract.txt`)

**Example Request:**
```bash
curl -X POST "http://127.0.0.1:8000/documents/upload" \
  -F "raw_text=This Master Services Agreement is entered into by Acme Corp and Global Inc..." \
  -F "filename=agreement.txt"
```

**Response:**
```json
{
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "PROCESSING"
}
```

---

### 2. Get Document Status
Retrieve processing status, extracted contract data, compliance findings, and review notes.

* **Endpoint:** `GET /documents/{document_id}`

**Example Request:**
```bash
curl -X GET "http://127.0.0.1:8000/documents/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
```

**Response:**
```json
{
  "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "filename": "agreement.txt",
  "status": "REVIEW_REQUIRED",
  "requires_human_review": true,
  "retry_count": 0,
  "extracted_data": {
    "vendor_name": "Acme Corp",
    "customer_name": "Global Inc",
    "effective_date": "2025-01-01",
    "expiration_date": "2026-01-01",
    "annual_value": 100000.0,
    "liability_cap_amount": 600000.0,
    "governing_law": "US-DE",
    "auto_renewal": true,
    "renewal_notice_days": 30,
    "termination_notice_days": 30
  },
  "compliance_findings": [
    {
      "rule": "LIABILITY_CAP",
      "severity": "HIGH",
      "passed": false,
      "message": "Liability cap ($600,000.00) exceeds maximum allowed threshold ($200,000.00)."
    },
    {
      "rule": "RENEWAL_NOTICE",
      "severity": "MEDIUM",
      "passed": true,
      "message": "Renewal notice (30 days) meets minimum requirement (30 days)."
    },
    {
      "rule": "GOVERNING_LAW",
      "severity": "HIGH",
      "passed": true,
      "message": "Governing law (US-DE) is in the approved list (US-DE, US-NY, US-CA, UK)."
    },
    {
      "rule": "TERMINATION_NOTICE",
      "severity": "LOW",
      "passed": true,
      "message": "Termination notice (30 days) meets minimum requirement (30 days)."
    }
  ],
  "reviewer_decision": null,
  "reviewer_notes": null
}
```

---

### 3. Review Contract (Human-in-the-Loop)
Submit a decision to resume a paused contract workflow.

* **Endpoint:** `POST /documents/{document_id}/review`
* **Content-Type:** `application/json`

**Decision Options:**
* `"approve"`: Mark contract as approved.
* `"reject"`: Mark contract as rejected.
* `"edit"`: Update extracted fields and re-run compliance audit.

**Example Request:**
```bash
curl -X POST "http://127.0.0.1:8000/documents/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/review" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "edit",
    "edited_data": {
      "liability_cap_amount": 200000.0
    },
    "notes": "Negotiated reduced liability cap with vendor."
  }'
```

**Response:**
```json
{
  "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "APPROVED",
  "requires_human_review": true,
  "reviewer_decision": "edit",
  "reviewer_notes": "Negotiated reduced liability cap with vendor."
}
```

---

### 4. List Documents
List all documents in the system with optional status filtering.

* **Endpoint:** `GET /documents?status=APPROVED`

---

## Compliance Policy Rules

| Rule | Severity | Condition | Action if Violated |
| :--- | :--- | :--- | :--- |
| **Liability Cap** | `HIGH` | Cap $\le \min(\text{Annual Value} \times \text{Multiple}, \text{Max USD})$ | Triggers `REVIEW_REQUIRED` |
| **Governing Law** | `HIGH` | Jurisdiction in approved whitelist | Triggers `REVIEW_REQUIRED` |
| **Renewal Notice** | `MEDIUM`| Notice days $\ge \text{Min Renewal Notice Days}$ | Flags finding in audit log |
| **Termination Notice** | `LOW` | Notice days $\ge \text{Min Termination Notice Days}$ | Flags finding in audit log |

---

## Running Tests

Run the full automated test suite:

```bash
pytest -v
```

Run test suite with short summary:
```bash
pytest -q
```

---

## Project Structure

```text
Clausely/
├── app/                        # Application source code
│   ├── workflow/               # LangGraph workflow definitions
│   │   ├── __init__.py
│   │   ├── graph.py            # Graph assembly & state machine routing
│   │   ├── nodes.py            # Workflow execution nodes
│   │   └── state.py            # ContractState TypedDict
│   ├── __init__.py
│   ├── api.py                  # FastAPI route handlers & lifespan
│   ├── compliance.py           # Deterministic compliance policy rules
│   ├── config.py               # Pydantic Settings & environment loader
│   ├── database.py             # SQLAlchemy engine & session factory
│   ├── extractor.py            # Raw text and PDF extraction utilities
│   ├── llm.py                  # Gemini LLM client & prompt builders
│   ├── models.py               # SQLAlchemy declarative models
│   ├── repository.py           # Database CRUD helpers
│   ├── schemas.py              # Pydantic data validation schemas
│   └── validation.py           # Pydantic validation & retry execution
├── tests/                      # Automated test suite
│   ├── fixtures/               # Test contract files (.txt)
│   ├── test_api.py             # FastAPI endpoint integration tests
│   ├── test_compliance.py      # Compliance policy rule tests
│   ├── test_config.py          # Settings & environment tests
│   ├── test_database.py        # Database session and schema tests
│   ├── test_e2e.py             # End-to-end contract pipeline tests
│   ├── test_extractor.py       # Text and PDF extractor tests
│   ├── test_hitl.py            # Human-in-the-loop checkpoint tests
│   ├── test_llm.py             # LLM prompt and response parsing tests
│   ├── test_schemas.py         # Pydantic schema validation tests
│   ├── test_validation.py      # Validation retry loop tests
│   └── test_workflow.py        # LangGraph state machine tests
├── .env.example                # Example environment configuration
├── .gitignore                  # Git ignore rules for Python, SQLite & secrets
├── AUDIT_REPORT.md             # Detailed project audit report
├── CONTRIBUTING.md             # Contributor guidelines & setup instructions
├── LICENSE                     # MIT License
├── main.py                     # Root startup entrypoint
├── README.md                   # Project documentation
└── requirements.txt            # Python package dependencies
```

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to set up your local development environment, run tests, and submit pull requests.

---

## License

This project is open source and available under the [MIT License](LICENSE).
