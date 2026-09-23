from datetime import datetime, timezone
from typing import Any, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Base class for SQLAlchemy declarative models
class Base(DeclarativeBase):
    pass


# Database model storing contract documents and processing results
class Document(Base):
    __tablename__ = "documents"

    # Unique identifier for the document
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Original filename and uploaded content
    filename: Mapped[str] = mapped_column(String, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Current processing status (PENDING, PROCESSING, APPROVED, REVIEW_REQUIRED, REJECTED, FAILED)
    status: Mapped[str] = mapped_column(String, default="PROCESSING", nullable=False)

    # Structured extraction results stored as JSON
    extracted_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Compliance audit findings stored as JSON array
    compliance_findings: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)

    # Extraction retry tracking and review requirement flag
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Human reviewer inputs
    reviewer_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Record timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Converts model fields to a serializable dictionary
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "raw_text": self.raw_text,
            "status": self.status,
            "extracted_data": self.extracted_data,
            "compliance_findings": self.compliance_findings,
            "retry_count": self.retry_count,
            "requires_human_review": self.requires_human_review,
            "reviewer_decision": self.reviewer_decision,
            "reviewer_notes": self.reviewer_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
