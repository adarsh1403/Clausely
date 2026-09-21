# Clausely

Autonomous contract extraction and compliance auditing system with human-in-the-loop review.

Clausely processes SaaS and vendor agreements: it extracts structured contract fields, validates them against strict schemas, automatically self-corrects extraction errors using feedback prompts, and audits contract terms against corporate compliance rules. When high-risk clauses or persistent failures occur, it pauses execution and waits for human approval before saving.

Zero parameters are hardcoded. All model selections, retry limits, database locations, and compliance policy thresholds are fully configured through environment variables.

---

## Workflow

```text
[ Contract Document ]
         │
         ▼
[ Extract Raw Text ]
         │
         ▼
[ LLM Extraction Node ] ◄────────────────────┐
         │                                   │
         ▼                                   │
[ Pydantic Validation ]                      │
    │              │                         │
 (Valid)       (Invalid)                     │
    │              │                         │
    │              ▼                         │
    │      [ Retries < Max? ] ───(Yes)───────┘
    │              │
    │             (No)
    │              │
    ▼              ▼
[ Compliance ] [ Flag: Failed ]
   Auditor         │
    │              │
    ▼              ▼
[ High Risk or Failed? ]
    │              │
  (No)           (Yes)
    │              │
    │              ▼
    │      [ LangGraph interrupt() ]
    │      (Pauses at checkpoint)
    │              │
    │      [ Human Review API ]
    │      (Approve / Reject / Edit)
    │              │
    │      [ Resume Execution ]
    │              │
    ▼              ▼
    └──────┬───────┘
           ▼
    [ Save to SQLite ]
           ▼
      [ Complete ]
```

---

## Key Capabilities

* **Structured Extraction**: Extracts vendor, customer, dates, monetary values, governing law, and renewal terms into a typed Pydantic schema.
* **Self-Healing Reflection Loop**: When validation fails, the exact schema error is passed back to the LLM to correct its output without crashing.
* **Deterministic Compliance Auditing**: Policy checks (liability caps, notice periods, jurisdictions) run as pure Python logic against thresholds defined in `.env`.
* **Stateful Human-in-the-Loop**: Uses LangGraph checkpointing and `interrupt()` to hold execution state until a reviewer submits an approval, rejection, or edit.
* **100% Configurable**: No hardcoded models, limits, or policy rules. Everything is controlled via environment variables.

---

## Tech Stack

* **Language**: Python 3.11+
* **Framework**: FastAPI
* **Workflow Engine**: LangGraph
* **Validation**: Pydantic v2
* **Storage**: SQLite via SQLAlchemy
* **LLM Provider**: Google Gemini API (model configured via `.env`)
* **Testing**: Pytest

---

## Configuration

All runtime behavior is controlled by `.env`. Copy the example file to start:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Description | Example Default |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | `your-api-key` |
| `GEMINI_MODEL` | Gemini model name | `gemini-3.5-flash-lite` |
| `MAX_EXTRACTION_RETRIES` | Max self-correction attempts | `3` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./clausely.db` |
| `POLICY_MAX_LIABILITY_CAP_USD` | Max allowed liability cap | `500000` |
| `POLICY_LIABILITY_ANNUAL_MULTIPLE` | Max cap as a multiple of annual value | `2.0` |
| `POLICY_MIN_RENEWAL_NOTICE_DAYS` | Min required renewal notice days | `30` |
| `POLICY_MIN_TERMINATION_NOTICE_DAYS` | Min required termination notice days | `30` |
| `POLICY_APPROVED_JURISDICTIONS` | Comma-separated list of approved jurisdictions | `US-DE,US-NY,US-CA,UK` |
| `API_HOST` | API host interface | `0.0.0.0` |
| `API_PORT` | API port | `8000` |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/documents/upload` | Upload contract text/file and start processing |
| `GET` | `/documents/{id}` | Retrieve document status, extracted data, and compliance findings |
| `POST` | `/documents/{id}/review` | Submit human decision (`approve`, `reject`, `edit`) to resume workflow |
| `GET` | `/documents` | List all processed contracts with status filters |

---

## Setup & Running

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and supply your GEMINI_API_KEY
   ```

3. **Start the server**:
   ```bash
   uvicorn app.api:app --reload
   ```

4. **Interactive Docs**:
   Open `http://127.0.0.1:8000/docs` to test endpoints via Swagger UI.
