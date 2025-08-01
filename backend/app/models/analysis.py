from sqlalchemy import Column, String, Boolean, Enum, ForeignKey, Text, DECIMAL, Integer, CheckConstraint, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin
from .enums import ImpactLevel, ComplexityLevel, OpportunityRating

class TrendAnalysis(Base, TimestampMixin):
    __tablename__ = "trend_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    is_aligned_with_trends = Column(Boolean)
    trend_score = Column(DECIMAL(3, 1))
    trend_keywords = Column(JSONB)  # ["AI", "automation", "cloud-native"]
    trend_sources = Column(JSONB)  # URLs and references
    confidence_score = Column(DECIMAL(3, 2))

    # Constraints
    __table_args__ = (
        CheckConstraint('trend_score >= 0 AND trend_score <= 10', name='check_trend_score_range'),
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='check_confidence_score_range'),
    )

    # Relationships
    feature = relationship("Feature", back_populates="trend_analyses")

class BusinessImpactAnalysis(Base, TimestampMixin):
    __tablename__ = "business_impact_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    impact_score = Column(Integer)
    revenue_impact = Column(Enum(ImpactLevel))
    user_adoption_potential = Column(Enum(ImpactLevel))
    strategic_alignment = Column(Enum(ImpactLevel))
    implementation_complexity = Column(Enum(ComplexityLevel))
    justification = Column(Text)

    # Constraints
    __table_args__ = (
        CheckConstraint('impact_score >= 0 AND impact_score <= 100', name='check_impact_score_range'),
    )

    # Relationships
    feature = relationship("Feature", back_populates="business_impact_analyses")

class MarketOpportunityAnalysis(Base, TimestampMixin):
    __tablename__ = "market_opportunity_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    total_competitors_analyzed = Column(Integer)
    competitors_providing_feature = Column(Integer)
    competitors_not_providing = Column(Integer)
    opportunity_score = Column(DECIMAL(3, 1))
    market_gap_percentage = Column(DECIMAL(5, 2))

    # Relationships
    feature = relationship("Feature", back_populates="market_opportunity_analyses")

class GeographicAnalysis(Base, TimestampMixin):
    __tablename__ = "geographic_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    country = Column(String(100))
    market_size_usd = Column(BigInteger)
    competitor_presence_count = Column(Integer)
    market_penetration_percentage = Column(DECIMAL(5, 2))
    regulatory_factors = Column(JSONB)
    cultural_adoption_factors = Column(Text)
    opportunity_rating = Column(Enum(OpportunityRating))

    # Relationships
    feature = relationship("Feature", back_populates="geographic_analyses")

class PriorityScore(Base, TimestampMixin):
    __tablename__ = "priority_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    final_score = Column(DECIMAL(4, 1))
    customer_impact_score = Column(DECIMAL(4, 1))
    trend_alignment_score = Column(DECIMAL(4, 1))
    business_impact_score = Column(DECIMAL(4, 1))
    market_opportunity_score = Column(DECIMAL(4, 1))
    segment_diversity_score = Column(DECIMAL(4, 1))
    calculation_metadata = Column(JSONB)
    algorithm_version = Column(String(10), default='1.0')

    # Constraints
    __table_args__ = (
        CheckConstraint('final_score >= 0 AND final_score <= 100', name='check_final_score_range'),
    )

    # Relationships
    feature = relationship("Feature", back_populates="priority_scores")

class FeatureAnalysisReport(Base, TimestampMixin):
    __tablename__ = "feature_analysis_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_id = Column(UUID(as_uuid=True), ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    
    # Trend Alignment
    trend_alignment_status = Column(Boolean)
    trend_keywords = Column(JSONB)
    trend_justification = Column(Text)
    
    # Business Impact
    business_impact_score = Column(Integer)
    revenue_potential = Column(Enum(ImpactLevel))
    user_adoption_forecast = Column(Enum(ImpactLevel))
    
    # Market Opportunity
    total_competitors_analyzed = Column(Integer)
    competitors_providing_count = Column(Integer)
    market_opportunity_score = Column(DECIMAL(3, 1))
    
    # Geographic Analysis
    geographic_insights = Column(JSONB)
    
    # Competitive Insights
    competitor_pros_cons = Column(JSONB)
    competitive_positioning = Column(Text)
    
    # Final Priority
    priority_score = Column(DECIMAL(4, 1))
    priority_ranking = Column(Integer)
    
    generated_by_workflow = Column(String(255))

    # Relationships
    feature = relationship("Feature", back_populates="analysis_reports")