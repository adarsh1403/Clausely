import json
import sqlite3
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api import app
from app.database import get_db
from app.models import Base
from app.workflow.graph import build_contract_graph


# Provides a FastAPI TestClient wired to an isolated in-memory DB and checkpointer
@pytest.fixture
def api_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Override FastAPI get_db dependency and workflow node SessionLocal
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.workflow.nodes.SessionLocal", TestingSessionLocal)

    # Create an isolated SqliteSaver checkpointer for the test client
    checkpoint_conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(checkpoint_conn)
    test_graph = build_contract_graph(checkpointer=checkpointer)
    monkeypatch.setattr("app.api.get_workflow_graph", lambda: test_graph)

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
    checkpoint_conn.close()
    Base.metadata.drop_all(bind=engine)


# Helper returning compliant JSON extraction output
def get_compliant_json() -> str:
    return json.dumps({
        "vendor_name": "Acme Cloud Ltd",
        "customer_name": "Global Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 200000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
        "renewal_notice_days": 30,
        "termination_notice_days": 30,
    })


# Tests uploading a compliant file and polling its auto-approved status
def test_api_upload_and_auto_approve(api_client, monkeypatch):
    mock_extract = MagicMock(return_value=get_compliant_json())
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    upload_res = api_client.post(
        "/documents/upload",
        files={"file": ("contract.txt", b"Standard compliant agreement", "text/plain")},
    )
    assert upload_res.status_code == 200
    payload = upload_res.json()
    assert payload["status"] == "PROCESSING"
    doc_id = payload["document_id"]

    # Check document status after background task finishes
    status_res = api_client.get(f"/documents/{doc_id}")
    assert status_res.status_code == 200
    doc_data = status_res.json()
    assert doc_data["status"] == "APPROVED"
    assert doc_data["extracted_data"]["vendor_name"] == "Acme Cloud Ltd"


# Tests uploading a high-risk contract, verifying REVIEW_REQUIRED, and approving via API
def test_api_upload_high_risk_and_review_approve(api_client, monkeypatch):
    high_risk_json = json.dumps({
        "vendor_name": "RiskyVendor Inc",
        "customer_name": "Global Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 800000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    })
    mock_extract = MagicMock(return_value=high_risk_json)
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    upload_res = api_client.post(
        "/documents/upload",
        data={"raw_text": "High risk contract text", "filename": "high_risk.txt"},
    )
    doc_id = upload_res.json()["document_id"]

    # Verify workflow paused at REVIEW_REQUIRED
    paused_res = api_client.get(f"/documents/{doc_id}")
    assert paused_res.json()["status"] == "REVIEW_REQUIRED"
    assert paused_res.json()["requires_human_review"] is True

    # Submit human review approval
    review_res = api_client.post(
        f"/documents/{doc_id}/review",
        json={"decision": "approve", "notes": "Approved after executive review"},
    )
    assert review_res.status_code == 200
    reviewed_doc = review_res.json()
    assert reviewed_doc["status"] == "APPROVED"
    assert reviewed_doc["reviewer_decision"] == "approve"
    assert reviewed_doc["reviewer_notes"] == "Approved after executive review"


# Tests resuming a paused document with an edit decision that re-audits compliance
def test_api_upload_and_review_edit(api_client, monkeypatch):
    offshore_json = json.dumps({
        "vendor_name": "Offshore SaaS",
        "customer_name": "Global Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 150000.0,
        "governing_law": "KY-CAYMAN",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    })
    mock_extract = MagicMock(return_value=offshore_json)
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    upload_res = api_client.post(
        "/documents/upload",
        data={"raw_text": "Offshore contract", "filename": "offshore.txt"},
    )
    doc_id = upload_res.json()["document_id"]

    # Submit edit updating governing law to US-DE
    review_res = api_client.post(
        f"/documents/{doc_id}/review",
        json={
            "decision": "edit",
            "edited_data": {"governing_law": "US-DE"},
            "notes": "Amended jurisdiction to Delaware",
        },
    )
    assert review_res.status_code == 200
    reviewed_doc = review_res.json()
    assert reviewed_doc["status"] == "APPROVED"
    assert reviewed_doc["extracted_data"]["governing_law"] == "US-DE"

    law_finding = next(f for f in reviewed_doc["compliance_findings"] if f["rule"] == "GOVERNING_LAW")
    assert law_finding["passed"] is True


# Tests listing documents with and without status query filters
def test_api_list_documents_with_status_filter(api_client, monkeypatch):
    high_risk_json = json.dumps({
        "vendor_name": "RiskyVendor Inc",
        "customer_name": "Global Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 900000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    })
    mock_extract = MagicMock(side_effect=[get_compliant_json(), high_risk_json])
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    api_client.post("/documents/upload", data={"raw_text": "Doc 1", "filename": "doc1.txt"})
    api_client.post("/documents/upload", data={"raw_text": "Doc 2", "filename": "doc2.txt"})

    all_res = api_client.get("/documents")
    assert all_res.status_code == 200
    assert len(all_res.json()) == 2

    approved_res = api_client.get("/documents?status=APPROVED")
    assert len(approved_res.json()) == 1

    review_res = api_client.get("/documents?status=REVIEW_REQUIRED")
    assert len(review_res.json()) == 1


# Tests that requesting or reviewing a missing document returns 404
def test_api_missing_document_returns_404(api_client):
    get_res = api_client.get("/documents/nonexistent-id")
    assert get_res.status_code == 404

    review_res = api_client.post(
        "/documents/nonexistent-id/review",
        json={"decision": "approve"},
    )
    assert review_res.status_code == 404


# Tests serving the root minimal interface HTML page
def test_serve_index_page(api_client):
    response = api_client.get("/")
    assert response.status_code == 200
    assert "Clausely" in response.text


# Tests service health check and database connectivity
def test_api_health_check(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["version"] == "1.0.0"


# Tests generating compliance audit report for an existing document
def test_api_get_document_report(api_client, monkeypatch):
    mock_extract = MagicMock(return_value=get_compliant_json())
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    upload_res = api_client.post(
        "/documents/upload",
        data={"raw_text": "Sample text", "filename": "report_test.txt"},
    )
    doc_id = upload_res.json()["document_id"]

    report_res = api_client.get(f"/documents/{doc_id}/report")
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["document_id"] == doc_id
    assert report_data["filename"] == "report_test.txt"
    assert "Clausely Compliance Audit Report" in report_data["report_markdown"]
    assert "Acme Cloud Ltd" in report_data["report_markdown"]


# Tests that requesting a report for a nonexistent document returns 404
def test_api_get_document_report_not_found(api_client):
    report_res = api_client.get("/documents/nonexistent-id/report")
    assert report_res.status_code == 404

