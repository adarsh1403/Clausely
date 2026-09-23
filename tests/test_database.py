import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Document
from app.repository import (
    create_document,
    get_document_by_id,
    list_documents,
    update_document,
)


# Provides an isolated in-memory SQLite database session for testing
@pytest.fixture
def db_session():
    # Use in-memory SQLite database for isolated unit test execution
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


# Tests creating a document and retrieving it by primary key UUID
def test_create_and_get_document(db_session):
    doc = create_document(db_session, "vendor_contract.txt", "Contract text between Vendor and Customer")
    assert doc.id is not None
    assert doc.filename == "vendor_contract.txt"
    assert doc.status == "PROCESSING"
    assert doc.retry_count == 0
    assert doc.requires_human_review is False

    retrieved = get_document_by_id(db_session, doc.id)
    assert retrieved is not None
    assert retrieved.id == doc.id
    assert retrieved.raw_text == "Contract text between Vendor and Customer"


# Tests updating document records with structured JSON data and compliance findings
def test_update_document_with_json(db_session):
    doc = create_document(db_session, "service_agreement.pdf", "Raw PDF content")

    extracted_payload = {
        "vendor_name": "CloudVendor",
        "customer_name": "Acme Corp",
        "annual_value": 75000.0,
    }
    findings = [
        {"rule": "LIABILITY_CAP", "severity": "HIGH", "passed": False, "message": "Exceeds annual multiple"},
    ]

    updated = update_document(
        db_session,
        doc.id,
        extracted_data=extracted_payload,
        compliance_findings=findings,
        status="REVIEW_REQUIRED",
        requires_human_review=True,
        retry_count=1,
    )

    assert updated is not None
    assert updated.status == "REVIEW_REQUIRED"
    assert updated.requires_human_review is True
    assert updated.retry_count == 1
    assert updated.extracted_data["vendor_name"] == "CloudVendor"
    assert len(updated.compliance_findings) == 1
    assert updated.compliance_findings[0]["severity"] == "HIGH"


# Tests querying documents with and without status filtering
def test_list_documents_filtering(db_session):
    create_document(db_session, "doc1.txt", "text 1", status="PROCESSING")
    create_document(db_session, "doc2.txt", "text 2", status="APPROVED")
    create_document(db_session, "doc3.txt", "text 3", status="APPROVED")
    create_document(db_session, "doc4.txt", "text 4", status="REJECTED")

    all_docs = list_documents(db_session)
    assert len(all_docs) == 4

    approved_docs = list_documents(db_session, status="APPROVED")
    assert len(approved_docs) == 2

    failed_docs = list_documents(db_session, status="FAILED")
    assert len(failed_docs) == 0


# Tests returning None when querying or updating non-existent records
def test_get_nonexistent_document(db_session):
    missing_doc = get_document_by_id(db_session, "nonexistent-uuid")
    assert missing_doc is None

    updated_result = update_document(db_session, "nonexistent-uuid", status="APPROVED")
    assert updated_result is None


# Tests serialization of Document instances to plain dictionary
def test_document_to_dict(db_session):
    doc = create_document(db_session, "dict_test.txt", "Raw contract text")
    data_dict = doc.to_dict()

    assert data_dict["id"] == doc.id
    assert data_dict["filename"] == "dict_test.txt"
    assert data_dict["status"] == "PROCESSING"
    assert data_dict["created_at"] is not None
    assert "updated_at" in data_dict
