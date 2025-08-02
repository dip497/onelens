from sqlalchemy import Column, String, Enum, ForeignKey, Date, Integer, Text, DECIMAL
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin
from .enums import CustomerSegment, CustomerVertical, UrgencyLevel, RequestSource, ImpactLevel, TShirtSize

class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    company = Column(String(255))
    phone = Column(String(50))
    t_shirt_size = Column(Enum(TShirtSize))
    segment = Column(Enum(CustomerSegment))
    vertical = Column(Enum(CustomerVertical))
    arr = Column(DECIMAL(12, 2))  # Annual Recurring Revenue
    employee_count = Column(Integer)
    geographic_region = Column(String(100))
    contract_end_date = Column(Date)
    strategic_importance = Column(Enum(ImpactLevel))

    # Relationships
    feature_requests = relationship("FeatureRequest", back_populates="customer")
    rfp_documents = relationship("RFPDocument", back_populates="customer")

class FeatureRequest(Base, TimestampMixin):
    __tablename__ = "feature_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    urgency = Column(Enum(UrgencyLevel))
    business_justification = Column(Text)
    estimated_deal_impact = Column(DECIMAL(12, 2))
    source = Column(Enum(RequestSource))
    request_details = Column(Text)

    # Relationships
    feature = relationship("Feature", back_populates="feature_requests")
    customer = relationship("Customer", back_populates="feature_requests")