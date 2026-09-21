# Clausely — Product Requirements Document (PRD)

**Autonomous Contract Extraction & Compliance Auditor with Human-in-the-Loop**

---

## 1. Objective

Build an API system that extracts structured data from SaaS and vendor contracts, validates schema integrity with Pydantic, heals extraction errors using an LLM self-correction feedback loop, audits extracted terms against configurable compliance rules, and pauses execution via LangGraph state checkpointing when human review is required.

---

## 2. Core Design Principle: Zero Hardcoded Values

No model names, retry counts, database paths, or compliance thresholds are hardcoded in the codebase. Every parameter is read from environment variables via a centralized configuration module.

If a rate limit or threshold needs adjustment, it is modified in `.env` without changing source code.

---

## 3. Extraction Schema (`VendorContract`)

```python
class VendorContract(BaseModel):
    vendor_name: str
    customer_name: str
    effective_date: datetime.date
    expiration_date: datetime.date
    annual_value: float = Field(..., ge=0.0, description="Annual contract value in USD")
    liability_cap_amount: float = Field(..., ge=0.0, description="Total liability cap in USD")
    governing_law: str = Field(..., description="Jurisdiction code (e.g., US-DE, US-NY, US-CA, UK)")
    auto_renewal: bool
    renewal_notice_days: int = Field(default=0, ge=0, description="Days notice required to prevent renewal")
    termination_notice_days: int = Field(default=0, ge=0, description="Notice days for termination for convenience")
```

---

## 4. System Workflow & State Machine

The workflow runs on a LangGraph `StateGraph` backed by a durable SQLite checkpointer.

```text
[Input Document]
       │
       ▼
[extract_contract] ◄──────────────────────────────┐
       │                                          │
       ▼                                          │ (Invalid &
[validate_extraction]                             │  retries < MAX_EXTRACTION_RETRIES)
       │                                          │
       ├── (Validation Error) ──► [Self-Correct] ──┘
       │                                │
       │                         (retries >= MAX_EXTRACTION_RETRIES)
       │                                │
       ▼ (Valid)                        ▼
[audit_compliance]            [Flag: EXTRACTION_FAILED]
       │                                │
       ▼                                │
 [High Risk?]                           │
   │      │                             │
 (No)   (Yes)                           │
   │      └─────────────────────────────┤
   │                                    ▼
   │                         [human_review_interrupt]
   │                         (Pauses graph via interrupt())
   │                                    │
   │                          [Human Review API Call]
   │                          (Approve / Reject / Edit)
   │                                    │
   │                         [Resume Graph Execution]
   │                                    │
   ▼                                    ▼
[save_document] ────────────────────────┘
       │
       ▼
  [COMPLETED]
```

### Graph State (`ContractState`)

```python
class ContractState(TypedDict):
    document_id: str
    raw_text: str
    extracted_data: Optional[dict]
    validation_errors: list[str]
    retry_count: int
    compliance_findings: list[dict]
    requires_human_review: bool
    human_decision: Optional[str]  # "approve" | "reject" | "edit"
    reviewer_notes: Optional[str]
    status: str  # PENDING, PROCESSING, APPROVED, REVIEW_REQUIRED, REJECTED, FAILED
```

---

## 5. Node Logic & Execution Rules

### Node 1: `extract_contract`
* **Input**: `raw_text`, optional `validation_errors` from previous attempt.
* **LLM Call**: Calls Google Gemini using the model specified by `GEMINI_MODEL` in `.env`.
* **Prompting**:
  * On initial attempt (`retry_count == 0`): Requests extraction conforming strictly to the schema.
  * On retry (`retry_count > 0`): Injects the previous Pydantic `validation_errors` into the prompt, directing the model to correct the invalid fields.
* **Output**: Raw JSON string.

### Node 2: `validate_extraction`
* **Input**: Raw JSON string from `extract_contract`.
* **Logic**: Validates output against `VendorContract`.
  * **Valid**: Sets `extracted_data = model.model_dump()`, clears `validation_errors`, routes to `audit_compliance`.
  * **Invalid**: Extracts error messages, increments `retry_count`.
    * If `retry_count < MAX_EXTRACTION_RETRIES`: Routes back to `extract_contract`.
    * If `retry_count >= MAX_EXTRACTION_RETRIES`: Sets `status = "FAILED"`, `requires_human_review = True`, routes to `human_review_interrupt`.

### Node 3: `audit_compliance`
* **Input**: `extracted_data`.
* **Logic**: Pure Python checks against thresholds loaded from environment variables:
  1. **Liability Cap**: `liability_cap_amount <= min(POLICY_LIABILITY_ANNUAL_MULTIPLE * annual_value, POLICY_MAX_LIABILITY_CAP_USD)`. Severity: **HIGH**.
  2. **Renewal Notice**: If `auto_renewal == True`, `renewal_notice_days >= POLICY_MIN_RENEWAL_NOTICE_DAYS`. Severity: **MEDIUM**.
  3. **Governing Law**: `governing_law in POLICY_APPROVED_JURISDICTIONS`. Severity: **HIGH**.
  4. **Termination Notice**: `termination_notice_days >= POLICY_MIN_TERMINATION_NOTICE_DAYS`. Severity: **LOW**.
* **Routing**:
  * Any **HIGH** severity violation sets `requires_human_review = True`, `status = "REVIEW_REQUIRED"`, routes to `human_review_interrupt`.
  * Otherwise, sets `status = "APPROVED"`, routes to `save_document`.

### Node 4: `human_review_interrupt`
* **Input**: Current graph state.
* **Logic**: Calls LangGraph `interrupt()`, suspending execution and persisting state to the SQLite checkpointer.
* **Resumption**: Triggered via `POST /documents/{id}/review`:
  * `approve` → sets `status = "APPROVED"`.
  * `reject` → sets `status = "REJECTED"`.
  * `edit` → merges reviewer edits, re-audits compliance, sets `status = "APPROVED"`.
* Routes to `save_document`.

### Node 5: `save_document`
* **Input**: Final state.
* **Logic**: Updates the document record in SQLite with final status, extracted fields, audit findings, and reviewer logs.

---

## 6. Persistence Model

### `documents` Table
* `id` (`String`, Primary Key): Document UUID.
* `filename` (`String`): File or document title.
* `raw_text` (`Text`): Source contract text.
* `status` (`String`): `PENDING`, `PROCESSING`, `APPROVED`, `REVIEW_REQUIRED`, `REJECTED`, `FAILED`.
* `extracted_data` (`JSON`, Nullable): Final structured data.
* `compliance_findings` (`JSON`, Nullable): Array of audit findings.
* `retry_count` (`Integer`): Number of self-correction attempts made.
* `requires_human_review` (`Boolean`).
* `reviewer_decision` (`String`, Nullable): `approve`, `reject`, `edit`.
* `reviewer_notes` (`Text`, Nullable).
* `created_at` (`DateTime`).
* `updated_at` (`DateTime`).

---

## 7. REST API Endpoints

1. `POST /documents/upload`
   * Uploads text or PDF file, initializes database record, triggers graph processing.
   * Returns: `document_id`, `status: "PROCESSING"`.

2. `GET /documents/{id}`
   * Returns full record: status, extracted data, compliance findings, review notes.

3. `POST /documents/{id}/review`
   * Body: `{"decision": "approve | reject | edit", "edited_data": {...}, "notes": "..."}`.
   * Resumes the paused LangGraph workflow and saves terminal state.

4. `GET /documents`
   * Lists all processed documents with status filtering.

---

## 8. Configuration Parameters (`.env`)

```ini
# LLM Provider
GEMINI_API_KEY="your-api-key"
GEMINI_MODEL="gemini-3.5-flash-lite"

# Workflow & Self-Healing
MAX_EXTRACTION_RETRIES=3

# Database
DATABASE_URL="sqlite:///./clausely.db"

# Compliance Policy Rules
POLICY_MAX_LIABILITY_CAP_USD=500000
POLICY_LIABILITY_ANNUAL_MULTIPLE=2.0
POLICY_MIN_RENEWAL_NOTICE_DAYS=30
POLICY_MIN_TERMINATION_NOTICE_DAYS=30
POLICY_APPROVED_JURISDICTIONS="US-DE,US-NY,US-CA,UK"

# Server
API_HOST="0.0.0.0"
API_PORT=8000
```

---

## 9. Explicitly Out of Scope

* Hardcoded fallback models or hardcoded policy rules.
* User authentication and multi-tenancy.
* Scanned OCR (only machine-readable text/PDFs supported).
* Custom frontend UI (FastAPI Swagger UI serves as the interface).
