from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Document


# Creates and persists a new document record in the database
def create_document(
    session: Session,
    filename: str,
    raw_text: str,
    status: str = "PROCESSING",
) -> Document:
    document = Document(filename=filename, raw_text=raw_text, status=status)
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


# Retrieves a document by its primary key UUID
def get_document_by_id(session: Session, document_id: str) -> Optional[Document]:
    return session.get(Document, document_id)


# Updates specific fields on an existing document record
def update_document(
    session: Session,
    document_id: str,
    **kwargs: Any,
) -> Optional[Document]:
    document = session.get(Document, document_id)
    if not document:
        return None

    # Dynamically apply updated attributes to the model instance
    for key, value in kwargs.items():
        setattr(document, key, value)

    session.commit()
    session.refresh(document)
    return document


# Lists documents optionally filtered by their processing status
def list_documents(
    session: Session,
    status: Optional[str] = None,
) -> list[Document]:
    query = select(Document).order_by(Document.created_at.desc())
    if status:
        query = query.where(Document.status == status)

    return list(session.scalars(query).all())
