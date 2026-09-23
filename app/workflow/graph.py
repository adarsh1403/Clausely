from typing import Any
from langgraph.graph import END, START, StateGraph
from app.config import get_settings
from app.workflow.nodes import (
    audit_compliance_node,
    extract_contract_node,
    save_document_node,
    validate_extraction_node,
)
from app.workflow.state import ContractState


# Determines next node after validation based on success or remaining retry count
def route_after_validation(state: ContractState) -> str:
    # Proceed to compliance auditing if extraction succeeded
    if state.get("extracted_data") is not None:
        return "audit_compliance"

    # Retry extraction if retry count has not reached the configured limit
    max_retries = get_settings().MAX_EXTRACTION_RETRIES
    if state.get("retry_count", 0) < max_retries:
        return "extract_contract"

    # Save failed state when retries are exhausted
    return "save_document"


# Assembles and compiles the LangGraph state machine for contract processing
def build_contract_graph(checkpointer: Any = None) -> Any:
    workflow = StateGraph(ContractState)

    # Register processing nodes
    workflow.add_node("extract_contract", extract_contract_node)
    workflow.add_node("validate_extraction", validate_extraction_node)
    workflow.add_node("audit_compliance", audit_compliance_node)
    workflow.add_node("save_document", save_document_node)

    # Wire standard and conditional transitions
    workflow.add_edge(START, "extract_contract")
    workflow.add_edge("extract_contract", "validate_extraction")
    workflow.add_conditional_edges(
        "validate_extraction",
        route_after_validation,
        {
            "audit_compliance": "audit_compliance",
            "extract_contract": "extract_contract",
            "save_document": "save_document",
        },
    )
    workflow.add_edge("audit_compliance", "save_document")
    workflow.add_edge("save_document", END)

    return workflow.compile(checkpointer=checkpointer)
