from typing import Any, Optional, TypedDict


# Shared state structure passed between nodes in the LangGraph workflow
class ContractState(TypedDict, total=False):
    document_id: str
    raw_text: str
    raw_llm_output: Optional[str]
    extracted_data: Optional[dict[str, Any]]
    validation_errors: list[str]
    retry_count: int
    compliance_findings: list[dict[str, Any]]
    requires_human_review: bool
    human_decision: Optional[str]
    reviewer_notes: Optional[str]
    status: str
