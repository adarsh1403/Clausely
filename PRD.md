# Clausely — Autonomous Contract Extraction & Compliance Auditor

**Product Requirements Document (Final)**

---

## 1. Product Goal

Build a multi-tenant API system that accepts business contracts, identifies their type, extracts structured data, validates it, checks it against company-defined compliance rules, automatically retries failed extractions, and pauses for human review on high-risk exceptions — with full traceability, test coverage, and measured accuracy.

---

## 2. Supported Contract Types

1. **SaaS / Vendor Agreement**
2. **NDA**
3. **Professional Services Agreement (PSA)**

An unsupported contract type returns HTTP `422` with error code `UNSUPPORTED_CONTRACT_TYPE`. It is a request-time error, not a stored document status.

---

## 3. Users & Roles

The user is a **company administrator** or **contract reviewer**.

| Role | Can do |
|---|---|
| `admin` | Manage policies, add users, submit/process documents, review |
| `reviewer` | Submit/process documents, perform human review |

Each user belongs to exactly one company.

**User entity:**
```json
{
  "id": "usr_123",
  "email": "",
  "password_hash": "",
  "role": "admin | reviewer",
  "company_id": "comp_456",
  "created_at": ""
}
```

---

## 4. Authentication & Multi-Tenancy

- JWT-based auth. Payload: `{ user_id, company_id, role, exp }`.
- `POST /auth/register` creates a new company **and** its first admin user in one call.
- `POST /auth/login` authenticates an existing user and returns a JWT.
- `POST /companies/{id}/users` (admin-only) adds additional users to an existing company.
- **Every database query is scoped by `company_id` resolved from the JWT** — enforced at the query layer, not just the API gate. No code path may return or reference another company's data.

---

## 5. Input

```
PDF contract (machine-readable text)
company_id (resolved from JWT, not client-supplied)
```

Before processing: compute a file hash and check for a duplicate under the same `company_id`. If found, return the existing `document_id` instead of reprocessing.

---

## 6. Extraction Schema (Design Principle)

Every field a compliance rule can touch is typed — number, boolean, enum, or date. Free text is never used in rule evaluation; it's kept as reference-only context.

Every extracted field carries:
- The typed value
- `source_excerpt` — exact contract text it was extracted from
- `confidence` — model's self-reported score (0–1)

**`governing_law`** is constrained to a fixed jurisdiction enum list (e.g., US state codes + common non-US jurisdictions), maintained as static reference data — not free text — so the `in` operator has guaranteed valid values to compare against.

### SaaS / Vendor
```json
{
  "parties": [{ "role": "vendor", "name": "" }, { "role": "customer", "name": "" }],
  "effective_date": "2026-01-01",
  "expiration_date": "2027-01-01",
  "contract_value": { "amount": 0, "currency": "USD" },
  "payment_terms_days": 30,
  "auto_renewal": { "enabled": true, "notice_days": 60 },
  "termination_notice_days": 30,
  "sla_uptime_percent": 99.9,
  "liability_cap": { "amount": 0, "currency": "USD" },
  "has_dpa_clause": true,
  "governing_law": "US-DE"
}
```

### NDA
```json
{
  "parties": [{ "role": "disclosing_party", "name": "" }, { "role": "receiving_party", "name": "" }],
  "effective_date": "2026-01-01",
  "confidentiality_period_months": 24,
  "is_mutual": true,
  "termination_notice_days": 30,
  "governing_law": "US-DE"
}
```

### PSA
```json
{
  "parties": [{ "role": "client", "name": "" }, { "role": "provider", "name": "" }],
  "effective_date": "2026-01-01",
  "payment_terms_days": 30,
  "ip_ownership": "client",
  "liability_cap": { "amount": 0, "currency": "USD" },
  "termination_notice_days": 30,
  "governing_law": "US-DE"
}
```

(Each field object also carries `source_excerpt` and `confidence`, omitted above for brevity.)

---

## 7. Document Entity & Metadata

```json
{
  "id": "doc_123",
  "company_id": "comp_456",
  "uploaded_by": "usr_123",
  "original_filename": "vendor_agreement.pdf",
  "file_hash": "",
  "uploaded_at": "2026-01-01T12:00:00Z",
  "contract_type": "saas",
  "status": "PENDING",
  "extracted_data": {},
  "compliance": {}
}
```

---

## 8. Status Enum

```
PENDING       — uploaded, not yet processed
PROCESSING    — workflow actively running
APPROVED      — passed validation + compliance, no high-risk issues
REVIEW_REQUIRED — paused for human review
REJECTED      — reviewer rejected the extraction/document
EXTRACTION_FAILED — failed validation after 3 attempts, unresolved
```

`review_required` is never stored as a separate boolean — always derived from `status`.

---

## 9. Company Policies

Stored as data, not hardcoded.

```json
{
  "contract_type": "saas",
  "rules": [
    { "field": "liability_cap.amount", "operator": ">=", "value": 500000, "severity": "high" },
    { "field": "governing_law", "operator": "in", "value": ["US-DE", "US-NY"], "severity": "medium" }
  ]
}
```

**Operators:** `==`, `!=`, `>=`, `<=`, `>`, `<`, `exists`, `in`

---

## 10. Compliance Engine

- Runs after successful extraction validation.
- Fully deterministic — no LLM involvement in pass/warning/violation decisions.
- Each rule evaluates to `PASS`, `WARNING`, or `VIOLATION` with severity `low` / `medium` / `high`.
- Any `high` severity violation → `REVIEW_REQUIRED`.

---

## 11. Workflow (LangGraph)

```
Upload → status: PENDING
  ↓
Dedupe check (file hash + company_id)
  ↓
Trigger process → status: PROCESSING
  ↓
Classify contract type
  │
  ├─ confidence below threshold → status: REVIEW_REQUIRED (flagged: ambiguous classification)
  └─ confident ↓
Extract (typed schema)
  ↓
Pydantic Validate
  │
  ├─ transport/API error (timeout, rate limit, malformed response)
  │     → retry with backoff (separate counter, max 3)
  │
  └─ invalid extraction
        → Correct (validation error explicitly fed back into prompt)
        → Validate again (max 3 attempts total)
  ↓
valid?
  ├─ no (after 3 attempts) → status: EXTRACTION_FAILED → Human Review
  └─ yes ↓
Compliance Check
  ↓
high-risk violation?
  ├─ no  → status: APPROVED → Store
  └─ yes → status: REVIEW_REQUIRED (paused, checkpointed) → Human Review → resume → Store
```

Transport failures (API down, rate-limited, bad JSON) are retried independently from extraction-accuracy failures (wrong field values), with separate counters.

---

## 12. Human-in-the-Loop

Triggered when:
- A high-severity compliance violation exists.
- Extraction fails validation after 3 attempts.
- Classification confidence is below threshold.

Workflow pauses via LangGraph checkpointing (durable, resumable without reprocessing).

**Resume request body:**
```json
{
  "decision": "approve | reject | edit",
  "edited_data": {},
  "reviewer_id": "usr_123",
  "notes": ""
}
```

- `approve` → status becomes `APPROVED`, stored as-is.
- `reject` → status becomes `REJECTED`, document retained with reviewer notes.
- `edit` → `edited_data` merged into `extracted_data`, re-run through compliance check, then stored.

---

## 13. Persistence

PostgreSQL stores:
- Companies, users (with role, company_id)
- Policies
- Documents (with file hash, uploader, filename, timestamps)
- Processing runs (retry counts by failure type)
- Extracted data (with source excerpts and confidence scores)
- Compliance results
- Human review decisions and audit trail (who, what, when, previous vs. new state)

LangGraph checkpointer stores workflow state for pause/resume.

---

## 14. API

```
POST   /auth/register              → creates company + first admin
POST   /auth/login                 → returns JWT
POST   /companies/{id}/users       → (admin) add user to company
POST   /companies/{id}/policies    → create/update compliance policy
POST   /documents                  → upload contract (dedup checked)
POST   /documents/{id}/process     → trigger workflow
GET    /documents                  → list company's documents (paginated, filterable by status)
GET    /documents/{id}             → get one document + current state
GET    /runs/{id}                  → get processing run detail
POST   /runs/{id}/resume           → submit review decision (see body above)
GET    /runs/{id}/audit-log        → full history of the run
```

All endpoints except `/auth/register` and `/auth/login` require a valid JWT; every query is scoped to the token's `company_id`.

---

## 15. Deployment

- Dockerized (API + Postgres via docker-compose) — one-command local deployment.
- Environment-based config for LLM API keys, DB connection, JWT secret.

---

## 16. Testing & Evaluation

- **Unit tests** on the compliance rule engine (pure deterministic logic — target 90%+ coverage).
- **Unit tests** on Pydantic schema validation edge cases.
- **Hand-labeled evaluation set**: 10+ contracts per type (30+ total), with ground-truth field values.
- Extraction accuracy measured and reported per field and overall.
- Integration tests covering: full happy path (upload → extract → validate → compliance → store), review-pause/resume path, and multi-tenant isolation (verify company A cannot access company B's data).

---

## 17. Technology

```
Python, FastAPI, Pydantic
LangChain, LangGraph
Gemini
PostgreSQL
Docker
Pytest
JWT (e.g., PyJWT)
```

---

## 18. Success Criteria

- 3 contract types processed end-to-end with typed, rule-evaluable schemas.
- Compliance engine fully deterministic, with measured test coverage.
- Extraction retries correctly differentiate transport errors from validation errors.
- Full status lifecycle (`PENDING` → `PROCESSING` → terminal state) correctly represented at every stage.
- High-risk and low-confidence-classification cases pause and resume correctly via checkpointing.
- Multi-tenant isolation verified under test — no cross-company data leakage.
- No duplicate processing on resubmitted files.
- Real extraction accuracy number reported from a hand-labeled evaluation set.
- Entire system runs via a single Docker Compose command.

---

## 19. Explicitly Out of Scope

- OCR / scanned PDF support
- Cloud object storage
- Background job queue (Redis)
- Observability/tracing dashboards
- Advanced/visual policy rule builder
- Additional contract types beyond the three listed
- Frontend UI
