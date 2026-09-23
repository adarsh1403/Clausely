import json
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models import Base
from app.repository import create_document, get_document_by_id
from app.workflow.graph import build_contract_graph


# Provides an isolated in-memory database session and patches nodes.SessionLocal
@pytest.fixture
def workflow_db(monkeypatch):
    # Use StaticPool so multiple sessions share the same in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Patch SessionLocal inside workflow nodes to use isolated test database
    monkeypatch.setattr("app.workflow.nodes.SessionLocal", TestingSessionLocal)

    session = TestingSessionLocal()
    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


# Helper returning a valid, compliant contract JSON string
def get_valid_compliant_json() -> str:
    return json.dumps({
        "vendor_name": "CloudServices Inc",
        "customer_name": "Acme Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 200000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
        "renewal_notice_days": 30,
        "termination_notice_days": 30,
    })


# Tests that a valid, compliant contract flows to APPROVED and saves to DB
def test_workflow_happy_path_compliant(workflow_db, monkeypatch):
    doc = create_document(workflow_db, "compliant.txt", "Standard compliant agreement")
    mock_extract = MagicMock(return_value=get_valid_compliant_json())
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    graph = build_contract_graph()
    config = {"configurable": {"thread_id": doc.id}}
    final_state = graph.invoke(
        {
            "document_id": doc.id,
            "raw_text": doc.raw_text,
            "retry_count": 0,
        },
        config=config,
    )

    assert final_state["status"] == "APPROVED"
    assert final_state["requires_human_review"] is False
    assert final_state["retry_count"] == 0

    workflow_db.expire_all()
    saved_doc = get_document_by_id(workflow_db, doc.id)
    assert saved_doc is not None
    assert saved_doc.status == "APPROVED"
    assert saved_doc.extracted_data["vendor_name"] == "CloudServices Inc"


# Tests that an initial validation failure triggers the retry loop and recovers
def test_workflow_self_healing_retry(workflow_db, monkeypatch):
    doc = create_document(workflow_db, "healing.txt", "Contract needing self-correction")
    invalid_json = json.dumps({"vendor_name": "Broken", "annual_value": -100.0})

    mock_extract = MagicMock(side_effect=[invalid_json, get_valid_compliant_json()])
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    graph = build_contract_graph()
    config = {"configurable": {"thread_id": doc.id}}
    final_state = graph.invoke(
        {
            "document_id": doc.id,
            "raw_text": doc.raw_text,
            "retry_count": 0,
        },
        config=config,
    )

    assert final_state["status"] == "APPROVED"
    assert final_state["retry_count"] == 1
    assert mock_extract.call_count == 2

    workflow_db.expire_all()
    saved_doc = get_document_by_id(workflow_db, doc.id)
    assert saved_doc.status == "APPROVED"
    assert saved_doc.retry_count == 1


# Tests that persistent extraction failures stop at MAX_EXTRACTION_RETRIES and flag FAILED
def test_workflow_max_retries_exceeded(workflow_db, monkeypatch):
    doc = create_document(workflow_db, "broken.txt", "Unparseable contract")
    invalid_json = json.dumps({"vendor_name": "Still Broken"})

    mock_extract = MagicMock(return_value=invalid_json)
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    graph = build_contract_graph()
    config = {"configurable": {"thread_id": doc.id}}
    final_state = graph.invoke(
        {
            "document_id": doc.id,
            "raw_text": doc.raw_text,
            "retry_count": 0,
        },
        config=config,
    )

    assert final_state["status"] == "FAILED"
    assert final_state["requires_human_review"] is True
    assert final_state["retry_count"] == 3

    workflow_db.expire_all()
    saved_doc = get_document_by_id(workflow_db, doc.id)
    assert saved_doc.status == "FAILED"
    assert saved_doc.requires_human_review is True


# Tests that a high-risk contract is flagged as REVIEW_REQUIRED by the compliance node
def test_workflow_high_risk_compliance_flagged(workflow_db, monkeypatch):
    doc = create_document(workflow_db, "high_risk.txt", "Contract with excessive liability")
    high_risk_json = json.dumps({
        "vendor_name": "RiskyVendor LLC",
        "customer_name": "Acme Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 900000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    })

    mock_extract = MagicMock(return_value=high_risk_json)
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    graph = build_contract_graph()
    config = {"configurable": {"thread_id": doc.id}}
    final_state = graph.invoke(
        {
            "document_id": doc.id,
            "raw_text": doc.raw_text,
            "retry_count": 0,
        },
        config=config,
    )

    assert final_state["status"] == "REVIEW_REQUIRED"
    assert final_state["requires_human_review"] is True

    workflow_db.expire_all()
    saved_doc = get_document_by_id(workflow_db, doc.id)
    assert saved_doc.status == "REVIEW_REQUIRED"
    assert saved_doc.requires_human_review is True
