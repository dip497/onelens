"""
Module Features - Separate from Epic Features
These are features specifically for Product Modules (sales/marketing view)
"""
from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin
from .enums import AvailabilityStatus, ComplexityLevel

class ModuleFeature(Base, TimestampMixin):
    """
    Features that belong to Product Modules (for sales/marketing)
    Separate from epic features (for development)
    """
    __tablename__ = "module_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("product_modules.id", ondelete="CASCADE"), nullable=False)
    
    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text)
    value_proposition = Column(Text)  # How this feature provides value to customers
    
    # Sales/Marketing specific fields
    is_key_differentiator = Column(Boolean, default=False)
    competitor_comparison = Column(Text)  # How we compare to competitors on this feature
    target_segment = Column(String(100))  # Which customer segment benefits most
    
    # Status and availability
    status = Column(Enum(AvailabilityStatus), default=AvailabilityStatus.AVAILABLE)
    availability_date = Column(String(50))  # When it will be/was available
    
    # Complexity for implementation (if customer asks)
    implementation_complexity = Column(Enum(ComplexityLevel), default=ComplexityLevel.MEDIUM)
    
    # Metrics and proof points
    adoption_rate = Column(Integer)  # Percentage of customers using this
    success_metrics = Column(Text)  # JSON string of success metrics
    customer_quotes = Column(Text)  # JSON array of customer testimonials
    
    # Linked epic feature (optional - if this module feature comes from development)
    epic_feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="SET NULL"), nullable=True)
    
    # Display order
    order_index = Column(Integer, default=0)
    
    # Relationships
    module = relationship("ProductModule", back_populates="module_features")
    epic_feature = relationship("Feature", backref="module_feature_instances")
    
    def __repr__(self):
        return f"<ModuleFeature(name='{self.name}', module='{self.module_id}')>"