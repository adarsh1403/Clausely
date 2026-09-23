import json
from pathlib import Path
import sqlite3
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api import app
from app.config import get_settings
from app.database import get_db
from app.models import Base
from app.workflow.graph import build_contract_graph

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# Provides an isolated end-to-end FastAPI client, SQLite DB, and checkpointer
@pytest.fixture
def e2e_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.workflow.nodes.SessionLocal", TestingSessionLocal)

    checkpoint_conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(checkpoint_conn)
    test_graph = build_contract_graph(checkpointer=checkpointer)
    monkeypatch.setattr("app.api.get_workflow_graph", lambda: test_graph)

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    checkpoint_conn.close()
    Base.metadata.drop_all(bind=engine)


# Tests end-to-end upload, extraction, compliance audit, and auto-approval of a clean contract
def test_e2e_clean_contract_full_lifecycle(e2e_client, monkeypatch):
    clean_bytes = (FIXTURES_DIR / "clean_saas_contract.txt").read_bytes()
    extracted_json = json.dumps({
        "vendor_name": "CloudScale Technologies Inc.",
        "customer_name": "Acme Global Corp.",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 200000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
        "renewal_notice_days": 30,
        "termination_notice_days": 30,
    })
    monkeypatch.setattr("app.workflow.nodes.extract_contract", MagicMock(return_value=extracted_json))

    upload_res = e2e_client.post(
        "/documents/upload",
        files={"file": ("clean_saas_contract.txt", clean_bytes, "text/plain")},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["document_id"]

    doc_res = e2e_client.get(f"/documents/{doc_id}")
    doc_data = doc_res.json()
    assert doc_data["status"] == "APPROVED"
    assert doc_data["requires_human_review"] is False
    assert doc_data["retry_count"] == 0
    assert doc_data["extracted_data"]["vendor_name"] == "CloudScale Technologies Inc."


# Tests end-to-end self-healing reflection loop when initial date format fails schema validation
def test_e2e_self_healing_reflection_lifecycle(e2e_client, monkeypatch):
    malformed_bytes = (FIXTURES_DIR / "malformed_dates_contract.txt").read_bytes()

    initial_bad_json = json.dumps({
        "vendor_name": "Precision Analytics Inc.",
        "customer_name": "Acme Global Corp.",
        "effective_date": "April-First-2025",
        "expiration_date": "2026-04-01",
        "annual_value": 60000.0,
        "liability_cap_amount": 100000.0,
        "governing_law": "US-NY",
        "auto_renewal": True,
        "renewal_notice_days": 30,
        "termination_notice_days": 30,
    })
    corrected_good_json = json.dumps({
        "vendor_name": "Precision Analytics Inc.",
        "customer_name": "Acme Global Corp.",
        "effective_date": "2025-04-01",
        "expiration_date": "2026-04-01",
        "annual_value": 60000.0,
        "liability_cap_amount": 100000.0,
        "governing_law": "US-NY",
        "auto_renewal": True,
        "renewal_notice_days": 30,
        "termination_notice_days": 30,
    })

    mock_extract = MagicMock(side_effect=[initial_bad_json, corrected_good_json])
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    upload_res = e2e_client.post(
        "/documents/upload",
        files={"file": ("malformed_dates_contract.txt", malformed_bytes, "text/plain")},
    )
    doc_id = upload_res.json()["document_id"]

    # Verify second call received the Pydantic validation error feedback
    assert mock_extract.call_count == 2
    retry_call_kwargs = mock_extract.call_args_list[1].kwargs
    assert any("effective_date" in err for err in retry_call_kwargs["validation_errors"])

    doc_res = e2e_client.get(f"/documents/{doc_id}")
    doc_data = doc_res.json()
    assert doc_data["status"] == "APPROVED"
    assert doc_data["retry_count"] == 1


# Tests end-to-end high-risk liability pause at interrupt() and human reviewer rejection
def test_e2e_high_risk_pause_and_human_rejection(e2e_client, monkeypatch):
    high_risk_bytes = (FIXTURES_DIR / "high_risk_liability_contract.txt").read_bytes()
    high_risk_json = json.dumps({
        "vendor_name": "MegaData Systems LLC",
        "customer_name": "Acme Global Corp.",
        "effective_date": "2025-02-01",
        "expiration_date": "2026-02-01",
        "annual_value": 150000.0,
        "liability_cap_amount": 900000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    })
    monkeypatch.setattr("app.workflow.nodes.extract_contract", MagicMock(return_value=high_risk_json))

    upload_res = e2e_client.post(
        "/documents/upload",
        files={"file": ("high_risk_liability_contract.txt", high_risk_bytes, "text/plain")},
    )
    doc_id = upload_res.json()["document_id"]

    paused_doc = e2e_client.get(f"/documents/{doc_id}").json()
    assert paused_doc["status"] == "REVIEW_REQUIRED"
    assert paused_doc["requires_human_review"] is True

    review_res = e2e_client.post(
        f"/documents/{doc_id}/review",
        json={"decision": "reject", "notes": "Liability cap of $900k exceeds corporate limit."},
    )
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "REJECTED"


# Tests end-to-end disapproved jurisdiction pause, human edit, and compliance re-auditing
def test_e2e_jurisdiction_pause_and_human_edit_amendment(e2e_client, monkeypatch):
    jurisdiction_bytes = (FIXTURES_DIR / "disapproved_jurisdiction_contract.txt").read_bytes()
    jurisdiction_json = json.dumps({
        "vendor_name": "IslandSoft Ltd.",
        "customer_name": "Acme Global Corp.",
        "effective_date": "2025-03-01",
        "expiration_date": "2026-03-01",
        "annual_value": 80000.0,
        "liability_cap_amount": 120000.0,
        "governing_law": "KY-CAYMAN",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 45,
    })
    monkeypatch.setattr("app.workflow.nodes.extract_contract", MagicMock(return_value=jurisdiction_json))

    upload_res = e2e_client.post(
        "/documents/upload",
        files={"file": ("disapproved_jurisdiction_contract.txt", jurisdiction_bytes, "text/plain")},
    )
    doc_id = upload_res.json()["document_id"]

    paused_doc = e2e_client.get(f"/documents/{doc_id}").json()
    assert paused_doc["status"] == "REVIEW_REQUIRED"

    review_res = e2e_client.post(
        f"/documents/{doc_id}/review",
        json={
            "decision": "edit",
            "edited_data": {"governing_law": "US-NY"},
            "notes": "Vendor agreed to New York governing law addendum.",
        },
    )
    assert review_res.status_code == 200
    final_doc = review_res.json()
    assert final_doc["status"] == "APPROVED"
    assert final_doc["extracted_data"]["governing_law"] == "US-NY"

    law_finding = next(f for f in final_doc["compliance_findings"] if f["rule"] == "GOVERNING_LAW")
    assert law_finding["passed"] is True


# Tests that modifying .env policy variables dynamically alters compliance outcomes without code changes
def test_e2e_zero_hardcoding_dynamic_policy_override(e2e_client, monkeypatch):
    # Raise policy thresholds via environment variables so $900k cap becomes compliant
    monkeypatch.setenv("POLICY_MAX_LIABILITY_CAP_USD", "1000000.0")
    monkeypatch.setenv("POLICY_LIABILITY_ANNUAL_MULTIPLE", "10.0")
    get_settings.cache_clear()

    high_risk_bytes = (FIXTURES_DIR / "high_risk_liability_contract.txt").read_bytes()
    high_risk_json = json.dumps({
        "vendor_name": "MegaData Systems LLC",
        "customer_name": "Acme Global Corp.",
        "effective_date": "2025-02-01",
        "expiration_date": "2026-02-01",
        "annual_value": 150000.0,
        "liability_cap_amount": 900000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    })
    monkeypatch.setattr("app.workflow.nodes.extract_contract", MagicMock(return_value=high_risk_json))

    upload_res = e2e_client.post(
        "/documents/upload",
        files={"file": ("high_risk_liability_contract.txt", high_risk_bytes, "text/plain")},
    )
    doc_id = upload_res.json()["document_id"]

    # Contract now auto-approves under the updated environment policy
    doc_data = e2e_client.get(f"/documents/{doc_id}").json()
    assert doc_data["status"] == "APPROVED"
    assert doc_data["requires_human_review"] is False
