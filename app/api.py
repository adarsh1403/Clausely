from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Optional
from pathlib import Path
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db, init_db
from app.extractor import extract_text_from_bytes
from app.repository import create_document, get_document_by_id, list_documents
from app.schemas import ReviewRequest
from app.workflow.graph import (
    build_contract_graph,
    resume_contract_workflow,
    run_contract_workflow,
)


# Initializes the database schema when the FastAPI application starts
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# Create the FastAPI application instance
app = FastAPI(
    title="Clausely API",
    description="Autonomous contract extraction and compliance auditing system with human-in-the-loop review.",
    version="1.0.0",
    lifespan=lifespan,
)


# Returns a shared compiled LangGraph workflow instance across API requests
@lru_cache
def get_workflow_graph() -> Any:
    return build_contract_graph()


# Path to the static interface HTML file
INDEX_FILE_PATH = Path(__file__).parent / "static" / "index.html"


# Serves the minimal web interface
@app.get("/", response_class=FileResponse)
def serve_index() -> FileResponse:
    return FileResponse(INDEX_FILE_PATH)


# Uploads a contract file or raw text, creates a DB record, and starts workflow processing
@app.post("/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(default=None),
    raw_text: Optional[str] = Form(default=None),
    filename: Optional[str] = Form(default="contract.txt"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    # Extract raw bytes and filename from either file upload or text form input
    if file is not None:
        content = await file.read()
        doc_filename = file.filename or "contract.txt"
    elif raw_text is not None:
        content = raw_text.encode("utf-8")
        doc_filename = filename or "contract.txt"
    else:
        raise HTTPException(
            status_code=400,
            detail="Either a file upload or raw_text must be provided.",
        )

    # Parse clean text from uploaded bytes
    try:
        extracted_text = extract_text_from_bytes(content, doc_filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Persist initial PROCESSING document record
    document = create_document(
        db,
        filename=doc_filename,
        raw_text=extracted_text,
        status="PROCESSING",
    )

    # Schedule LangGraph execution in the background
    background_tasks.add_task(
        run_contract_workflow,
        document.id,
        extracted_text,
        get_workflow_graph(),
    )

    return {
        "document_id": document.id,
        "status": "PROCESSING",
    }


# Retrieves full document status, extracted data, compliance findings, and review notes
@app.get("/documents/{document_id}")
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document.to_dict()


# Submits a human review decision (approve, reject, edit) to resume a paused workflow
@app.post("/documents/{document_id}/review")
def review_document(
    document_id: str,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    if document.status not in ("REVIEW_REQUIRED", "FAILED"):
        raise HTTPException(
            status_code=400,
            detail=f"Document does not require review (current status: {document.status}).",
        )

    # Resume the paused LangGraph thread with the reviewer decision
    resume_contract_workflow(
        document_id=document_id,
        decision=payload.decision,
        edited_data=payload.edited_data,
        notes=payload.notes,
        graph=get_workflow_graph(),
    )

    # Refresh session to read the final persisted state
    db.expire_all()
    updated_doc = get_document_by_id(db, document_id)
    return updated_doc.to_dict()


# Lists all processed documents with optional status filtering
@app.get("/documents")
def get_documents_list(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    documents = list_documents(db, status=status)
    return [doc.to_dict() for doc in documents]
