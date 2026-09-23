import json
import sqlite3
from unittest.mock import MagicMock
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models import Base
from app.repository import create_document, get_document_by_id
from app.workflow.graph import (
    build_contract_graph,
    resume_contract_workflow,
    run_contract_workflow,
)


# Provides an isolated in-memory database and SqliteSaver checkpointer for HITL tests
@pytest.fixture
def hitl_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Patch SessionLocal inside workflow nodes to use isolated test database
    monkeypatch.setattr("app.workflow.nodes.SessionLocal", TestingSessionLocal)

    # Initialize an isolated in-memory SqliteSaver for LangGraph checkpoints
    checkpoint_conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(checkpoint_conn)
    graph = build_contract_graph(checkpointer=checkpointer)

    session = TestingSessionLocal()
    yield session, graph

    session.close()
    checkpoint_conn.close()
    Base.metadata.drop_all(bind=engine)


# Helper returning a high-risk contract JSON string with excessive liability cap
def get_high_risk_json() -> str:
    return json.dumps({
        "vendor_name": "HighRisk Cloud Inc",
        "customer_name": "Acme Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 850000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    })


# Tests pausing on a high-risk contract and resuming with an approve decision
def test_hitl_pauses_on_high_risk_and_resumes_approve(hitl_env, monkeypatch):
    db_session, graph = hitl_env
    doc = create_document(db_session, "approve_flow.txt", "High liability contract")

    mock_extract = MagicMock(return_value=get_high_risk_json())
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    # Start workflow; execution should pause at human_review_interrupt
    paused_state = run_contract_workflow(doc.id, doc.raw_text, graph=graph)
    assert paused_state["status"] == "REVIEW_REQUIRED"
    assert paused_state["requires_human_review"] is True

    # Verify database reflects waiting status while workflow is paused
    db_session.expire_all()
    waiting_doc = get_document_by_id(db_session, doc.id)
    assert waiting_doc.status == "REVIEW_REQUIRED"
    assert waiting_doc.requires_human_review is True

    # Resume workflow with human approval
    final_state = resume_contract_workflow(
        doc.id,
        decision="approve",
        notes="Approved by General Counsel",
        graph=graph,
    )
    assert final_state["status"] == "APPROVED"
    assert final_state["human_decision"] == "approve"

    db_session.expire_all()
    final_doc = get_document_by_id(db_session, doc.id)
    assert final_doc.status == "APPROVED"
    assert final_doc.reviewer_decision == "approve"
    assert final_doc.reviewer_notes == "Approved by General Counsel"


# Tests pausing on a high-risk contract and resuming with a reject decision
def test_hitl_pauses_on_high_risk_and_resumes_reject(hitl_env, monkeypatch):
    db_session, graph = hitl_env
    doc = create_document(db_session, "reject_flow.txt", "High liability contract")

    mock_extract = MagicMock(return_value=get_high_risk_json())
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    run_contract_workflow(doc.id, doc.raw_text, graph=graph)

    # Resume workflow with rejection
    final_state = resume_contract_workflow(
        doc.id,
        decision="reject",
        notes="Liability cap is unacceptable",
        graph=graph,
    )
    assert final_state["status"] == "REJECTED"

    db_session.expire_all()
    final_doc = get_document_by_id(db_session, doc.id)
    assert final_doc.status == "REJECTED"
    assert final_doc.reviewer_decision == "reject"
    assert final_doc.reviewer_notes == "Liability cap is unacceptable"


# Tests resuming with an edit decision that modifies fields and re-audits compliance
def test_hitl_pauses_and_resumes_with_edit_and_reaudits(hitl_env, monkeypatch):
    db_session, graph = hitl_env
    doc = create_document(db_session, "edit_flow.txt", "Offshore jurisdiction contract")

    offshore_json = json.dumps({
        "vendor_name": "Offshore Vendor",
        "customer_name": "Acme Corp",
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

    paused_state = run_contract_workflow(doc.id, doc.raw_text, graph=graph)
    assert paused_state["status"] == "REVIEW_REQUIRED"

    # Resume with edited governing law and verify re-auditing passes
    final_state = resume_contract_workflow(
        doc.id,
        decision="edit",
        edited_data={"governing_law": "US-DE"},
        notes="Amended governing law to Delaware",
        graph=graph,
    )
    assert final_state["status"] == "APPROVED"
    assert final_state["extracted_data"]["governing_law"] == "US-DE"

    law_finding = next(f for f in final_state["compliance_findings"] if f["rule"] == "GOVERNING_LAW")
    assert law_finding["passed"] is True

    db_session.expire_all()
    final_doc = get_document_by_id(db_session, doc.id)
    assert final_doc.status == "APPROVED"
    assert final_doc.extracted_data["governing_law"] == "US-DE"
    assert final_doc.reviewer_decision == "edit"


# Tests pausing when extraction exhausts retries and resuming with rejection
def test_hitl_pauses_on_failed_extraction_and_resumes(hitl_env, monkeypatch):
    db_session, graph = hitl_env
    doc = create_document(db_session, "failed_flow.txt", "Corrupted contract")

    mock_extract = MagicMock(return_value="invalid json {")
    monkeypatch.setattr("app.workflow.nodes.extract_contract", mock_extract)

    paused_state = run_contract_workflow(doc.id, doc.raw_text, graph=graph)
    assert paused_state["status"] == "FAILED"
    assert paused_state["requires_human_review"] is True

    db_session.expire_all()
    waiting_doc = get_document_by_id(db_session, doc.id)
    assert waiting_doc.status == "FAILED"

    final_state = resume_contract_workflow(
        doc.id,
        decision="reject",
        notes="Unreadable document",
        graph=graph,
    )
    assert final_state["status"] == "REJECTED"

    db_session.expire_all()
    final_doc = get_document_by_id(db_session, doc.id)
    assert final_doc.status == "REJECTED"
