from sqlalchemy import Column, String, Enum, ForeignKey, Text, DECIMAL, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin
from .enums import MarketPosition, CompanySize, AvailabilityStatus, PricingTier, LocalPresence

class Competitor(Base, TimestampMixin):
    __tablename__ = "competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    website = Column(String(500))
    market_position = Column(Enum(MarketPosition))
    primary_markets = Column(JSONB)  # ["US", "EU", "APAC"]
    company_size = Column(Enum(CompanySize))
    funding_stage = Column(String(100))

    # Relationships
    features = relationship("CompetitorFeature", back_populates="competitor", cascade="all, delete-orphan")
    geographic_presence = relationship("CompetitorGeographicPresence", back_populates="competitor", cascade="all, delete-orphan")

class CompetitorFeature(Base, TimestampMixin):
    __tablename__ = "competitor_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    feature_name = Column(String(255))
    feature_description = Column(Text)
    availability = Column(Enum(AvailabilityStatus))
    pricing_tier = Column(Enum(PricingTier))
    strengths = Column(Text)
    weaknesses = Column(Text)
    last_verified = Column(DateTime(timezone=True))
    source_url = Column(String(500))

    # Relationships
    competitor = relationship("Competitor", back_populates="features")

class CompetitorGeographicPresence(Base, TimestampMixin):
    __tablename__ = "competitor_geographic_presence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    country = Column(String(100))
    market_share_percentage = Column(DECIMAL(5, 2))
    local_presence = Column(Enum(LocalPresence))
    key_customers = Column(JSONB)

    # Relationships
    competitor = relationship("Competitor", back_populates="geographic_presence")