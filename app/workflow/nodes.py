from typing import Any
from app.compliance import audit_contract_compliance
from app.config import get_settings
from app.database import SessionLocal
from app.llm import extract_contract
from app.repository import update_document
from app.validation import validate_raw_extraction
from app.workflow.state import ContractState


# Node 1: Calls Gemini LLM to extract contract fields as a raw JSON string
def extract_contract_node(state: ContractState) -> dict[str, Any]:
    raw_text = state["raw_text"]
    retry_count = state.get("retry_count", 0)

    # Pass previous validation errors only on retry attempts
    errors = state.get("validation_errors") if retry_count > 0 else None
    raw_json = extract_contract(raw_text, validation_errors=errors)

    return {
        "raw_llm_output": raw_json,
        "status": "PROCESSING",
    }


# Node 2: Validates extracted JSON against VendorContract schema and tracks retries
def validate_extraction_node(state: ContractState) -> dict[str, Any]:
    raw_json = state.get("raw_llm_output") or ""
    extracted_data, errors = validate_raw_extraction(raw_json)

    # Clear errors and store structured dictionary when validation succeeds
    if extracted_data is not None:
        return {
            "extracted_data": extracted_data,
            "validation_errors": [],
        }

    # Increment retry count when validation fails
    new_retry_count = state.get("retry_count", 0) + 1
    max_retries = get_settings().MAX_EXTRACTION_RETRIES

    # Flag as failed for human review once retry threshold is reached
    if new_retry_count >= max_retries:
        return {
            "extracted_data": None,
            "validation_errors": errors,
            "retry_count": new_retry_count,
            "status": "FAILED",
            "requires_human_review": True,
        }

    return {
        "extracted_data": None,
        "validation_errors": errors,
        "retry_count": new_retry_count,
    }


# Node 3: Audits extracted contract fields against corporate compliance rules
def audit_compliance_node(state: ContractState) -> dict[str, Any]:
    extracted_data = state.get("extracted_data") or {}
    audit_result = audit_contract_compliance(extracted_data)

    return {
        "compliance_findings": audit_result["compliance_findings"],
        "requires_human_review": audit_result["requires_human_review"],
        "status": audit_result["status"],
    }


# Node 5: Persists final state and audit findings to the SQLite documents table
def save_document_node(state: ContractState) -> dict[str, Any]:
    db = SessionLocal()
    try:
        update_document(
            db,
            state["document_id"],
            status=state.get("status", "PROCESSING"),
            extracted_data=state.get("extracted_data"),
            compliance_findings=state.get("compliance_findings"),
            retry_count=state.get("retry_count", 0),
            requires_human_review=state.get("requires_human_review", False),
            reviewer_decision=state.get("human_decision"),
            reviewer_notes=state.get("reviewer_notes"),
        )
    finally:
        db.close()

    return {
        "status": state.get("status", "PROCESSING"),
    }
