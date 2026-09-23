import sqlite3
from typing import Any, Optional
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from app.config import get_settings
from app.workflow.nodes import (
    audit_compliance_node,
    extract_contract_node,
    human_review_interrupt_node,
    save_document_node,
    validate_extraction_node,
)
from app.workflow.state import ContractState


# Creates a durable SQLite checkpointer from the configured database URL
def get_sqlite_checkpointer(database_url: Optional[str] = None) -> SqliteSaver:
    db_url = database_url or get_settings().DATABASE_URL
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "", 1)
    else:
        db_path = ":memory:"

    connection = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(connection)


# Determines next node after validation based on success or remaining retry count
def route_after_validation(state: ContractState) -> str:
    # Proceed to compliance auditing if extraction succeeded
    if state.get("extracted_data") is not None:
        return "audit_compliance"

    # Retry extraction if retry count has not reached the configured limit
    max_retries = get_settings().MAX_EXTRACTION_RETRIES
    if state.get("retry_count", 0) < max_retries:
        return "extract_contract"

    # Pause for human review when retries are exhausted
    return "human_review_interrupt"


# Determines next node after compliance audit based on high-risk findings
def route_after_compliance(state: ContractState) -> str:
    if state.get("requires_human_review"):
        return "human_review_interrupt"
    return "save_document"


# Assembles and compiles the LangGraph state machine for contract processing
def build_contract_graph(checkpointer: Any = None) -> Any:
    workflow = StateGraph(ContractState)
    active_checkpointer = checkpointer if checkpointer is not None else get_sqlite_checkpointer()

    # Register processing nodes
    workflow.add_node("extract_contract", extract_contract_node)
    workflow.add_node("validate_extraction", validate_extraction_node)
    workflow.add_node("audit_compliance", audit_compliance_node)
    workflow.add_node("human_review_interrupt", human_review_interrupt_node)
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
            "human_review_interrupt": "human_review_interrupt",
        },
    )
    workflow.add_conditional_edges(
        "audit_compliance",
        route_after_compliance,
        {
            "human_review_interrupt": "human_review_interrupt",
            "save_document": "save_document",
        },
    )
    workflow.add_edge("human_review_interrupt", "save_document")
    workflow.add_edge("save_document", END)

    return workflow.compile(checkpointer=active_checkpointer)


# Starts a contract workflow thread using document_id as the checkpoint thread key
def run_contract_workflow(
    document_id: str,
    raw_text: str,
    graph: Any = None,
) -> dict[str, Any]:
    active_graph = graph or build_contract_graph()
    config = {"configurable": {"thread_id": document_id}}
    return active_graph.invoke(
        {
            "document_id": document_id,
            "raw_text": raw_text,
            "retry_count": 0,
        },
        config=config,
    )


# Resumes a paused workflow thread with the human reviewer decision
def resume_contract_workflow(
    document_id: str,
    decision: str,
    edited_data: Optional[dict[str, Any]] = None,
    notes: Optional[str] = None,
    graph: Any = None,
) -> dict[str, Any]:
    active_graph = graph or build_contract_graph()
    config = {"configurable": {"thread_id": document_id}}
    resume_payload = {
        "decision": decision,
        "edited_data": edited_data,
        "notes": notes,
    }
    return active_graph.invoke(Command(resume=resume_payload), config=config)
