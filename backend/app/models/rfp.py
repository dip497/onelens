from sqlalchemy import Column, String, Enum, ForeignKey, Text, DECIMAL, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from .base import Base, TimestampMixin
from .enums import ProcessedStatus

class RFPDocument(Base, TimestampMixin):
    __tablename__ = "rfp_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255))
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    processed_status = Column(Enum(ProcessedStatus), default=ProcessedStatus.PENDING)
    total_questions = Column(Integer)
    processed_questions = Column(Integer)
    business_context = Column(JSONB)

    # Relationships
    customer = relationship("Customer", back_populates="rfp_documents")
    qa_pairs = relationship("RFPQAPair", back_populates="document", cascade="all, delete-orphan")

class RFPQAPair(Base, TimestampMixin):
    __tablename__ = "rfp_qa_pairs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("rfp_documents.id", ondelete="CASCADE"), nullable=False)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    customer_context = Column(JSONB)
    business_impact_estimate = Column(DECIMAL(12, 2))
    # embedding = Column(Vector(384))  # TODO: Enable after creating pgvector extension

    # Relationships
    document = relationship("RFPDocument", back_populates="qa_pairs")
    feature = relationship("Feature", back_populates="rfp_qa_pairs")