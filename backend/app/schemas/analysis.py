"""Analysis-related Pydantic schemas."""

from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import Field, validator

from ..models.enums import ImpactLevel, ComplexityLevel, OpportunityRating
from .base import BaseCreateSchema, BaseUpdateSchema, BaseResponseSchema, PaginatedResponse


# Trend Analysis schemas
class TrendAnalysisBase(BaseCreateSchema):
    """Base TrendAnalysis schema with common fields."""
    
    is_aligned_with_trends: Optional[bool] = Field(None, description="Whether feature aligns with market trends")
    trend_score: Optional[Decimal] = Field(None, ge=0, le=10, description="Trend alignment score (0-10)")
    trend_keywords: Optional[List[str]] = Field(None, description="Keywords representing relevant trends")
    trend_sources: Optional[List[str]] = Field(None, description="Sources for trend information")
    confidence_score: Optional[Decimal] = Field(None, ge=0, le=1, description="Confidence in analysis (0-1)")


class TrendAnalysisCreate(TrendAnalysisBase):
    """Schema for creating a new TrendAnalysis."""
    
    feature_id: UUID = Field(..., description="ID of the feature being analyzed")
    
    @validator('trend_score')
    def validate_trend_score(cls, v):
        if v is not None and (v < 0 or v > 10):
            raise ValueError('Trend score must be between 0 and 10')
        return v
    
    @validator('confidence_score')
    def validate_confidence_score(cls, v):
        if v is not None and (v < 0 or v > 1):
            raise ValueError('Confidence score must be between 0 and 1')
        return v


class TrendAnalysisUpdate(BaseUpdateSchema):
    """Schema for updating an existing TrendAnalysis."""
    
    is_aligned_with_trends: Optional[bool] = Field(None, description="Whether feature aligns with market trends")
    trend_score: Optional[Decimal] = Field(None, ge=0, le=10, description="Trend alignment score (0-10)")
    trend_keywords: Optional[List[str]] = Field(None, description="Keywords representing relevant trends")
    trend_sources: Optional[List[str]] = Field(None, description="Sources for trend information")
    confidence_score: Optional[Decimal] = Field(None, ge=0, le=1, description="Confidence in analysis (0-1)")
    
    @validator('trend_score')
    def validate_trend_score(cls, v):
        if v is not None and (v < 0 or v > 10):
            raise ValueError('Trend score must be between 0 and 10')
        return v
    
    @validator('confidence_score')
    def validate_confidence_score(cls, v):
        if v is not None and (v < 0 or v > 1):
            raise ValueError('Confidence score must be between 0 and 1')
        return v


class TrendAnalysisResponse(BaseResponseSchema):
    """Schema for TrendAnalysis responses."""
    
    feature_id: UUID
    is_aligned_with_trends: Optional[bool]
    trend_score: Optional[Decimal]
    trend_keywords: Optional[List[str]]
    trend_sources: Optional[List[str]]
    confidence_score: Optional[Decimal]
    
    # Nested relationships
    feature: Optional[dict] = Field(None, description="Associated feature information")


# Business Impact Analysis schemas
class BusinessImpactAnalysisBase(BaseCreateSchema):
    """Base BusinessImpactAnalysis schema with common fields."""
    
    impact_score: Optional[int] = Field(None, ge=0, le=100, description="Overall business impact score (0-100)")
    revenue_impact: Optional[ImpactLevel] = Field(None, description="Revenue impact level")
    user_adoption_potential: Optional[ImpactLevel] = Field(None, description="User adoption potential")
    strategic_alignment: Optional[ImpactLevel] = Field(None, description="Strategic alignment level")
    implementation_complexity: Optional[ComplexityLevel] = Field(None, description="Implementation complexity")
    justification: Optional[str] = Field(None, description="Justification for the impact assessment")


class BusinessImpactAnalysisCreate(BusinessImpactAnalysisBase):
    """Schema for creating a new BusinessImpactAnalysis."""
    
    feature_id: UUID = Field(..., description="ID of the feature being analyzed")
    
    @validator('impact_score')
    def validate_impact_score(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('Impact score must be between 0 and 100')
        return v


class BusinessImpactAnalysisUpdate(BaseUpdateSchema):
    """Schema for updating an existing BusinessImpactAnalysis."""
    
    impact_score: Optional[int] = Field(None, ge=0, le=100, description="Overall business impact score (0-100)")
    revenue_impact: Optional[ImpactLevel] = Field(None, description="Revenue impact level")
    user_adoption_potential: Optional[ImpactLevel] = Field(None, description="User adoption potential")
    strategic_alignment: Optional[ImpactLevel] = Field(None, description="Strategic alignment level")
    implementation_complexity: Optional[ComplexityLevel] = Field(None, description="Implementation complexity")
    justification: Optional[str] = Field(None, description="Justification for the impact assessment")
    
    @validator('impact_score')
    def validate_impact_score(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('Impact score must be between 0 and 100')
        return v


class BusinessImpactAnalysisResponse(BaseResponseSchema):
    """Schema for BusinessImpactAnalysis responses."""
    
    feature_id: UUID
    impact_score: Optional[int]
    revenue_impact: Optional[ImpactLevel]
    user_adoption_potential: Optional[ImpactLevel]
    strategic_alignment: Optional[ImpactLevel]
    implementation_complexity: Optional[ComplexityLevel]
    justification: Optional[str]
    
    # Nested relationships
    feature: Optional[dict] = Field(None, description="Associated feature information")


# Market Opportunity Analysis schemas
class MarketOpportunityAnalysisBase(BaseCreateSchema):
    """Base MarketOpportunityAnalysis schema with common fields."""
    
    total_competitors_analyzed: Optional[int] = Field(None, ge=0, description="Total competitors analyzed")
    competitors_providing_feature: Optional[int] = Field(None, ge=0, description="Competitors providing this feature")
    competitors_not_providing: Optional[int] = Field(None, ge=0, description="Competitors not providing this feature")
    opportunity_score: Optional[Decimal] = Field(None, ge=0, le=10, description="Market opportunity score (0-10)")
    market_gap_percentage: Optional[Decimal] = Field(None, ge=0, le=100, description="Market gap percentage")


class MarketOpportunityAnalysisCreate(MarketOpportunityAnalysisBase):
    """Schema for creating a new MarketOpportunityAnalysis."""
    
    feature_id: UUID = Field(..., description="ID of the feature being analyzed")
    
    @validator('competitors_not_providing')
    def validate_competitor_counts(cls, v, values):
        total = values.get('total_competitors_analyzed')
        providing = values.get('competitors_providing_feature')
        
        if total is not None and providing is not None and v is not None:
            if providing + v != total:
                raise ValueError('competitors_providing_feature + competitors_not_providing must equal total_competitors_analyzed')
        return v


class MarketOpportunityAnalysisUpdate(BaseUpdateSchema):
    """Schema for updating an existing MarketOpportunityAnalysis."""
    
    total_competitors_analyzed: Optional[int] = Field(None, ge=0, description="Total competitors analyzed")
    competitors_providing_feature: Optional[int] = Field(None, ge=0, description="Competitors providing this feature")
    competitors_not_providing: Optional[int] = Field(None, ge=0, description="Competitors not providing this feature")
    opportunity_score: Optional[Decimal] = Field(None, ge=0, le=10, description="Market opportunity score (0-10)")
    market_gap_percentage: Optional[Decimal] = Field(None, ge=0, le=100, description="Market gap percentage")


class MarketOpportunityAnalysisResponse(BaseResponseSchema):
    """Schema for MarketOpportunityAnalysis responses."""
    
    feature_id: UUID
    total_competitors_analyzed: Optional[int]
    competitors_providing_feature: Optional[int]
    competitors_not_providing: Optional[int]
    opportunity_score: Optional[Decimal]
    market_gap_percentage: Optional[Decimal]
    
    # Nested relationships
    feature: Optional[dict] = Field(None, description="Associated feature information")


# Geographic Analysis schemas
class GeographicAnalysisBase(BaseCreateSchema):
    """Base GeographicAnalysis schema with common fields."""
    
    country: Optional[str] = Field(None, max_length=100, description="Country name")
    market_size_usd: Optional[int] = Field(None, ge=0, description="Market size in USD")
    competitor_presence_count: Optional[int] = Field(None, ge=0, description="Number of competitors present")
    market_penetration_percentage: Optional[Decimal] = Field(None, ge=0, le=100, description="Market penetration percentage")
    regulatory_factors: Optional[Dict[str, Any]] = Field(None, description="Regulatory factors affecting the market")
    cultural_adoption_factors: Optional[str] = Field(None, description="Cultural factors affecting adoption")
    opportunity_rating: Optional[OpportunityRating] = Field(None, description="Opportunity rating for this market")


class GeographicAnalysisCreate(GeographicAnalysisBase):
    """Schema for creating a new GeographicAnalysis."""
    
    feature_id: UUID = Field(..., description="ID of the feature being analyzed")


class GeographicAnalysisUpdate(BaseUpdateSchema):
    """Schema for updating an existing GeographicAnalysis."""
    
    country: Optional[str] = Field(None, max_length=100, description="Country name")
    market_size_usd: Optional[int] = Field(None, ge=0, description="Market size in USD")
    competitor_presence_count: Optional[int] = Field(None, ge=0, description="Number of competitors present")
    market_penetration_percentage: Optional[Decimal] = Field(None, ge=0, le=100, description="Market penetration percentage")
    regulatory_factors: Optional[Dict[str, Any]] = Field(None, description="Regulatory factors affecting the market")
    cultural_adoption_factors: Optional[str] = Field(None, description="Cultural factors affecting adoption")
    opportunity_rating: Optional[OpportunityRating] = Field(None, description="Opportunity rating for this market")


class GeographicAnalysisResponse(BaseResponseSchema):
    """Schema for GeographicAnalysis responses."""
    
    feature_id: UUID
    country: Optional[str]
    market_size_usd: Optional[int]
    competitor_presence_count: Optional[int]
    market_penetration_percentage: Optional[Decimal]
    regulatory_factors: Optional[Dict[str, Any]]
    cultural_adoption_factors: Optional[str]
    opportunity_rating: Optional[OpportunityRating]
    
    # Nested relationships
    feature: Optional[dict] = Field(None, description="Associated feature information")


# Priority Score schemas
class PriorityScoreBase(BaseCreateSchema):
    """Base PriorityScore schema with common fields."""
    
    final_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Final priority score (0-100)")
    customer_impact_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Customer impact score")
    trend_alignment_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Trend alignment score")
    business_impact_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Business impact score")
    market_opportunity_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Market opportunity score")
    segment_diversity_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Segment diversity score")
    calculation_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata about score calculation")
    algorithm_version: str = Field(default='1.0', description="Algorithm version used for calculation")


class PriorityScoreCreate(PriorityScoreBase):
    """Schema for creating a new PriorityScore."""
    
    feature_id: UUID = Field(..., description="ID of the feature being scored")


class PriorityScoreUpdate(BaseUpdateSchema):
    """Schema for updating an existing PriorityScore."""
    
    final_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Final priority score (0-100)")
    customer_impact_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Customer impact score")
    trend_alignment_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Trend alignment score")
    business_impact_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Business impact score")
    market_opportunity_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Market opportunity score")
    segment_diversity_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Segment diversity score")
    calculation_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata about score calculation")
    algorithm_version: Optional[str] = Field(None, description="Algorithm version used for calculation")


class PriorityScoreResponse(BaseResponseSchema):
    """Schema for PriorityScore responses."""
    
    feature_id: UUID
    final_score: Optional[Decimal]
    customer_impact_score: Optional[Decimal]
    trend_alignment_score: Optional[Decimal]
    business_impact_score: Optional[Decimal]
    market_opportunity_score: Optional[Decimal]
    segment_diversity_score: Optional[Decimal]
    calculation_metadata: Optional[Dict[str, Any]]
    algorithm_version: str
    
    # Nested relationships
    feature: Optional[dict] = Field(None, description="Associated feature information")


# Feature Analysis Report schemas
class FeatureAnalysisReportBase(BaseCreateSchema):
    """Base FeatureAnalysisReport schema with common fields."""
    
    # Trend Alignment
    trend_alignment_status: Optional[bool] = Field(None, description="Trend alignment status")
    trend_keywords: Optional[List[str]] = Field(None, description="Relevant trend keywords")
    trend_justification: Optional[str] = Field(None, description="Trend alignment justification")
    
    # Business Impact
    business_impact_score: Optional[int] = Field(None, ge=0, le=100, description="Business impact score")
    revenue_potential: Optional[ImpactLevel] = Field(None, description="Revenue potential level")
    user_adoption_forecast: Optional[ImpactLevel] = Field(None, description="User adoption forecast")
    
    # Market Opportunity
    total_competitors_analyzed: Optional[int] = Field(None, ge=0, description="Total competitors analyzed")
    competitors_providing_count: Optional[int] = Field(None, ge=0, description="Competitors providing feature")
    market_opportunity_score: Optional[Decimal] = Field(None, ge=0, le=10, description="Market opportunity score")
    
    # Geographic Analysis
    geographic_insights: Optional[Dict[str, Any]] = Field(None, description="Geographic analysis insights")
    
    # Competitive Insights
    competitor_pros_cons: Optional[Dict[str, Any]] = Field(None, description="Competitor pros and cons")
    competitive_positioning: Optional[str] = Field(None, description="Competitive positioning analysis")
    
    # Final Priority
    priority_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Final priority score")
    priority_ranking: Optional[int] = Field(None, ge=1, description="Priority ranking")
    
    generated_by_workflow: Optional[str] = Field(None, description="Workflow that generated this report")


class FeatureAnalysisReportCreate(FeatureAnalysisReportBase):
    """Schema for creating a new FeatureAnalysisReport."""
    
    feature_id: UUID = Field(..., description="ID of the feature being analyzed")


class FeatureAnalysisReportUpdate(BaseUpdateSchema):
    """Schema for updating an existing FeatureAnalysisReport."""
    
    # Trend Alignment
    trend_alignment_status: Optional[bool] = Field(None, description="Trend alignment status")
    trend_keywords: Optional[List[str]] = Field(None, description="Relevant trend keywords")
    trend_justification: Optional[str] = Field(None, description="Trend alignment justification")
    
    # Business Impact
    business_impact_score: Optional[int] = Field(None, ge=0, le=100, description="Business impact score")
    revenue_potential: Optional[ImpactLevel] = Field(None, description="Revenue potential level")
    user_adoption_forecast: Optional[ImpactLevel] = Field(None, description="User adoption forecast")
    
    # Market Opportunity
    total_competitors_analyzed: Optional[int] = Field(None, ge=0, description="Total competitors analyzed")
    competitors_providing_count: Optional[int] = Field(None, ge=0, description="Competitors providing feature")
    market_opportunity_score: Optional[Decimal] = Field(None, ge=0, le=10, description="Market opportunity score")
    
    # Geographic Analysis
    geographic_insights: Optional[Dict[str, Any]] = Field(None, description="Geographic analysis insights")
    
    # Competitive Insights
    competitor_pros_cons: Optional[Dict[str, Any]] = Field(None, description="Competitor pros and cons")
    competitive_positioning: Optional[str] = Field(None, description="Competitive positioning analysis")
    
    # Final Priority
    priority_score: Optional[Decimal] = Field(None, ge=0, le=100, description="Final priority score")
    priority_ranking: Optional[int] = Field(None, ge=1, description="Priority ranking")
    
    generated_by_workflow: Optional[str] = Field(None, description="Workflow that generated this report")


class FeatureAnalysisReportResponse(BaseResponseSchema):
    """Schema for FeatureAnalysisReport responses."""
    
    feature_id: UUID
    
    # Trend Alignment
    trend_alignment_status: Optional[bool]
    trend_keywords: Optional[List[str]]
    trend_justification: Optional[str]
    
    # Business Impact
    business_impact_score: Optional[int]
    revenue_potential: Optional[ImpactLevel]
    user_adoption_forecast: Optional[ImpactLevel]
    
    # Market Opportunity
    total_competitors_analyzed: Optional[int]
    competitors_providing_count: Optional[int]
    market_opportunity_score: Optional[Decimal]
    
    # Geographic Analysis
    geographic_insights: Optional[Dict[str, Any]]
    
    # Competitive Insights
    competitor_pros_cons: Optional[Dict[str, Any]]
    competitive_positioning: Optional[str]
    
    # Final Priority
    priority_score: Optional[Decimal]
    priority_ranking: Optional[int]
    
    generated_by_workflow: Optional[str]
    
    # Nested relationships
    feature: Optional[dict] = Field(None, description="Associated feature information")


# Comprehensive Analysis schemas
class ComprehensiveAnalysisRequest(BaseCreateSchema):
    """Schema for requesting comprehensive analysis of a feature."""
    
    feature_id: UUID = Field(..., description="ID of the feature to analyze")
    include_trend_analysis: bool = Field(True, description="Include trend analysis")
    include_business_impact: bool = Field(True, description="Include business impact analysis")
    include_market_opportunity: bool = Field(True, description="Include market opportunity analysis")
    include_geographic_analysis: bool = Field(True, description="Include geographic analysis")
    generate_priority_score: bool = Field(True, description="Generate priority score")
    generate_report: bool = Field(True, description="Generate comprehensive report")


class ComprehensiveAnalysisResponse(BaseCreateSchema):
    """Schema for comprehensive analysis results."""
    
    feature_id: UUID
    analysis_id: UUID = Field(..., description="ID of the analysis run")
    
    # Analysis results
    trend_analysis: Optional[TrendAnalysisResponse] = None
    business_impact_analysis: Optional[BusinessImpactAnalysisResponse] = None
    market_opportunity_analysis: Optional[MarketOpportunityAnalysisResponse] = None
    geographic_analyses: List[GeographicAnalysisResponse] = Field(default_factory=list)
    priority_score: Optional[PriorityScoreResponse] = None
    analysis_report: Optional[FeatureAnalysisReportResponse] = None
    
    # Analysis metadata
    analysis_status: str = Field("completed", description="Status of the analysis")
    analysis_duration_seconds: Optional[float] = Field(None, description="Duration of analysis")
    error_messages: List[str] = Field(default_factory=list, description="Any error messages during analysis")


class AnalysisMetrics(BaseCreateSchema):
    """Schema for analysis metrics and statistics."""
    
    total_features_analyzed: int = Field(0, description="Total features analyzed")
    features_with_trend_analysis: int = Field(0, description="Features with trend analysis")
    features_with_business_impact: int = Field(0, description="Features with business impact analysis")
    features_with_market_opportunity: int = Field(0, description="Features with market opportunity analysis")
    features_with_geographic_analysis: int = Field(0, description="Features with geographic analysis")
    features_with_priority_scores: int = Field(0, description="Features with priority scores")
    average_priority_score: Optional[Decimal] = Field(None, description="Average priority score")
    top_priority_features: List[dict] = Field(default_factory=list, description="Top priority features")
    analysis_completion_rate: Optional[Decimal] = Field(None, description="Analysis completion rate percentage")