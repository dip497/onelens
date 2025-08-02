from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from .base import Base, TimestampMixin

class Feature(Base, TimestampMixin):
    __tablename__ = "features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    epic_id = Column(UUID(as_uuid=True), ForeignKey("epics.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(UUID(as_uuid=True), ForeignKey("product_modules.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    normalized_text = Column(Text)
    # embedding = Column(Vector(384))  # TODO: Enable after creating pgvector extension
    customer_request_count = Column(Integer, default=0)
    is_key_differentiator = Column(Boolean, default=False)

    # Relationships
    epic = relationship("Epic", back_populates="features")
    module = relationship("ProductModule", back_populates="features")
    feature_requests = relationship("FeatureRequest", back_populates="feature", cascade="all, delete-orphan")
    trend_analyses = relationship("TrendAnalysis", back_populates="feature", cascade="all, delete-orphan")
    business_impact_analyses = relationship("BusinessImpactAnalysis", back_populates="feature", cascade="all, delete-orphan")
    market_opportunity_analyses = relationship("MarketOpportunityAnalysis", back_populates="feature", cascade="all, delete-orphan")
    geographic_analyses = relationship("GeographicAnalysis", back_populates="feature", cascade="all, delete-orphan")
    priority_scores = relationship("PriorityScore", back_populates="feature", cascade="all, delete-orphan")
    analysis_reports = relationship("FeatureAnalysisReport", back_populates="feature", cascade="all, delete-orphan")
    rfp_qa_pairs = relationship("RFPQAPair", back_populates="feature")