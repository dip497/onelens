"""RFP-related Pydantic schemas."""

from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import Field, validator

from ..models.enums import ProcessedStatus
from .base import BaseCreateSchema, BaseUpdateSchema, BaseResponseSchema, PaginatedResponse


class RFPDocumentBase(BaseCreateSchema):
    """Base RFPDocument schema with common fields."""
    
    filename: Optional[str] = Field(None, max_length=255, description="Original filename of the RFP document")
    business_context: Optional[Dict[str, Any]] = Field(None, description="Business context extracted from RFP")


class RFPDocumentCreate(RFPDocumentBase):
    """Schema for creating a new RFPDocument."""
    
    customer_id: Optional[UUID] = Field(None, description="ID of the customer who submitted the RFP")
    
    @validator('filename')
    def validate_filename(cls, v):
        if v:
            # Basic filename validation
            if not v.strip():
                raise ValueError('Filename cannot be empty')
            # Check for common file extensions
            allowed_extensions = {'.pdf', '.doc', '.docx', '.txt', '.rtf'}
            if not any(v.lower().endswith(ext) for ext in allowed_extensions):
                raise ValueError('File must have a valid extension (.pdf, .doc, .docx, .txt, .rtf)')
        return v


class RFPDocumentUpdate(BaseUpdateSchema):
    """Schema for updating an existing RFPDocument."""
    
    filename: Optional[str] = Field(None, max_length=255, description="Original filename of the RFP document")
    customer_id: Optional[UUID] = Field(None, description="ID of the customer who submitted the RFP")
    processed_status: Optional[ProcessedStatus] = Field(None, description="Processing status")
    total_questions: Optional[int] = Field(None, ge=0, description="Total number of questions in RFP")
    processed_questions: Optional[int] = Field(None, ge=0, description="Number of processed questions")
    business_context: Optional[Dict[str, Any]] = Field(None, description="Business context extracted from RFP")
    
    @validator('filename')
    def validate_filename(cls, v):
        if v and not v.strip():
            raise ValueError('Filename cannot be empty')
        return v
    
    @validator('processed_questions')
    def validate_processed_questions(cls, v, values):
        total = values.get('total_questions')
        if v is not None and total is not None and v > total:
            raise ValueError('Processed questions cannot exceed total questions')
        return v


class RFPDocumentResponse(BaseResponseSchema):
    """Schema for RFPDocument responses."""
    
    filename: Optional[str]
    customer_id: Optional[UUID]
    processed_status: ProcessedStatus
    total_questions: Optional[int]
    processed_questions: Optional[int]
    business_context: Optional[Dict[str, Any]]
    
    # Nested relationships
    customer: Optional[dict] = Field(None, description="Associated customer information")
    qa_pairs: List[dict] = Field(default_factory=list, description="Q&A pairs from the RFP")
    
    # Computed fields
    processing_progress_percentage: Optional[float] = Field(None, description="Processing progress percentage")
    questions_remaining: Optional[int] = Field(None, description="Number of questions remaining to process")
    
    @validator('qa_pairs', pre=True, always=True)
    def validate_qa_pairs(cls, v):
        if v is None:
            return []
        return v


class RFPDocumentListResponse(PaginatedResponse):
    """Paginated RFPDocument list response."""
    
    items: List[RFPDocumentResponse]


class RFPDocumentSummary(BaseResponseSchema):
    """Minimal RFPDocument schema for summary views."""
    
    filename: Optional[str]
    customer_id: Optional[UUID]
    processed_status: ProcessedStatus
    total_questions: Optional[int]
    processed_questions: Optional[int]
    processing_progress_percentage: Optional[float] = None


# RFP Q&A Pair schemas
class RFPQAPairBase(BaseCreateSchema):
    """Base RFPQAPair schema with common fields."""
    
    question: str = Field(..., description="Question from the RFP")
    answer: str = Field(..., description="Answer to the question")
    customer_context: Optional[Dict[str, Any]] = Field(None, description="Customer-specific context")
    business_impact_estimate: Optional[Decimal] = Field(None, ge=0, description="Estimated business impact")


class RFPQAPairCreate(RFPQAPairBase):
    """Schema for creating a new RFPQAPair."""
    
    document_id: UUID = Field(..., description="ID of the RFP document this Q&A belongs to")
    feature_id: Optional[UUID] = Field(None, description="ID of the feature this Q&A relates to")
    
    @validator('question')
    def validate_question(cls, v):
        if not v or not v.strip():
            raise ValueError('Question cannot be empty')
        return v.strip()
    
    @validator('answer')
    def validate_answer(cls, v):
        if not v or not v.strip():
            raise ValueError('Answer cannot be empty')
        return v.strip()


class RFPQAPairUpdate(BaseUpdateSchema):
    """Schema for updating an existing RFPQAPair."""
    
    question: Optional[str] = Field(None, description="Question from the RFP")
    answer: Optional[str] = Field(None, description="Answer to the question")
    feature_id: Optional[UUID] = Field(None, description="ID of the feature this Q&A relates to")
    customer_context: Optional[Dict[str, Any]] = Field(None, description="Customer-specific context")
    business_impact_estimate: Optional[Decimal] = Field(None, ge=0, description="Estimated business impact")
    
    @validator('question')
    def validate_question(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Question cannot be empty')
        return v.strip() if v else v
    
    @validator('answer')
    def validate_answer(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Answer cannot be empty')
        return v.strip() if v else v


class RFPQAPairResponse(BaseResponseSchema):
    """Schema for RFPQAPair responses."""
    
    document_id: UUID
    feature_id: Optional[UUID]
    question: str
    answer: str
    customer_context: Optional[Dict[str, Any]]
    business_impact_estimate: Optional[Decimal]
    
    # Nested relationships
    document: Optional[dict] = Field(None, description="Associated RFP document information")
    feature: Optional[dict] = Field(None, description="Associated feature information")
    
    # Computed fields
    similarity_score: Optional[float] = Field(None, description="Similarity score to existing features")


# RFP Processing schemas
class RFPProcessingRequest(BaseCreateSchema):
    """Schema for requesting RFP processing."""
    
    document_id: UUID = Field(..., description="ID of the RFP document to process")
    auto_link_features: bool = Field(True, description="Automatically link Q&A pairs to existing features")
    extract_business_context: bool = Field(True, description="Extract business context from the document")
    generate_feature_suggestions: bool = Field(False, description="Generate suggestions for new features")


class RFPProcessingResponse(BaseCreateSchema):
    """Schema for RFP processing results."""
    
    document_id: UUID
    processing_id: UUID = Field(..., description="ID of the processing job")
    status: ProcessedStatus
    
    # Processing results
    total_questions_extracted: int = Field(0, description="Total questions extracted")
    qa_pairs_created: int = Field(0, description="Q&A pairs created")
    features_linked: int = Field(0, description="Features automatically linked")
    business_context_extracted: bool = Field(False, description="Whether business context was extracted")
    feature_suggestions: List[dict] = Field(default_factory=list, description="Suggested new features")
    
    # Processing metadata
    processing_duration_seconds: Optional[float] = Field(None, description="Processing duration")
    error_messages: List[str] = Field(default_factory=list, description="Any error messages")


class RFPAnalysisRequest(BaseCreateSchema):
    """Schema for requesting RFP analysis across multiple documents."""
    
    document_ids: Optional[List[UUID]] = Field(None, description="Specific document IDs to analyze")
    customer_id: Optional[UUID] = Field(None, description="Analyze RFPs for specific customer")
    date_range_start: Optional[str] = Field(None, description="Start date for analysis (YYYY-MM-DD)")
    date_range_end: Optional[str] = Field(None, description="End date for analysis (YYYY-MM-DD)")
    include_feature_gaps: bool = Field(True, description="Include analysis of feature gaps")
    include_trend_analysis: bool = Field(True, description="Include trend analysis from RFPs")


class RFPAnalysisResponse(BaseCreateSchema):
    """Schema for RFP analysis results."""
    
    analysis_id: UUID = Field(..., description="ID of the analysis")
    documents_analyzed: int = Field(0, description="Number of documents analyzed")
    total_qa_pairs: int = Field(0, description="Total Q&A pairs analyzed")
    
    # Feature analysis
    features_mentioned: int = Field(0, description="Number of unique features mentioned")
    most_requested_features: List[dict] = Field(default_factory=list, description="Most frequently requested features")
    feature_gaps: List[dict] = Field(default_factory=list, description="Identified feature gaps")
    
    # Customer insights
    customer_segments_represented: List[str] = Field(default_factory=list, description="Customer segments in analysis")
    geographic_distribution: Dict[str, int] = Field(default_factory=dict, description="Geographic distribution of RFPs")
    
    # Business impact
    total_estimated_impact: Optional[Decimal] = Field(None, description="Total estimated business impact")
    high_impact_opportunities: List[dict] = Field(default_factory=list, description="High impact opportunities")
    
    # Trends
    emerging_trends: List[str] = Field(default_factory=list, description="Emerging trends from RFPs")
    technology_keywords: List[str] = Field(default_factory=list, description="Most mentioned technology keywords")


class RFPSearchRequest(BaseCreateSchema):
    """Schema for searching RFP content."""
    
    query: str = Field(..., min_length=1, description="Search query")
    document_ids: Optional[List[UUID]] = Field(None, description="Limit search to specific documents")
    customer_id: Optional[UUID] = Field(None, description="Limit search to specific customer")
    search_questions: bool = Field(True, description="Search in questions")
    search_answers: bool = Field(True, description="Search in answers")
    similarity_threshold: float = Field(0.7, ge=0, le=1, description="Similarity threshold for semantic search")
    max_results: int = Field(50, ge=1, le=200, description="Maximum number of results")


class RFPSearchResponse(BaseCreateSchema):
    """Schema for RFP search results."""
    
    query: str
    total_results: int
    results: List[dict] = Field(default_factory=list, description="Search results with relevance scores")
    related_features: List[dict] = Field(default_factory=list, description="Related features found")
    suggested_queries: List[str] = Field(default_factory=list, description="Suggested related queries")


class RFPMetrics(BaseCreateSchema):
    """Schema for RFP metrics and statistics."""
    
    total_documents: int = Field(0, description="Total RFP documents")
    documents_by_status: Dict[str, int] = Field(default_factory=dict, description="Documents by processing status")
    total_qa_pairs: int = Field(0, description="Total Q&A pairs")
    average_questions_per_document: float = Field(0, description="Average questions per document")
    documents_with_customer: int = Field(0, description="Documents associated with customers")
    processing_completion_rate: float = Field(0, description="Processing completion rate percentage")
    
    # Feature linkage
    qa_pairs_linked_to_features: int = Field(0, description="Q&A pairs linked to features")
    feature_linkage_rate: float = Field(0, description="Feature linkage rate percentage")
    most_linked_features: List[dict] = Field(default_factory=list, description="Features most linked to RFPs")
    
    # Business impact
    total_estimated_impact: Optional[Decimal] = Field(None, description="Total estimated business impact")
    documents_with_impact_estimates: int = Field(0, description="Documents with business impact estimates")


class RFPBulkOperation(BaseCreateSchema):
    """Schema for bulk operations on RFP documents."""
    
    document_ids: List[UUID] = Field(..., min_items=1, description="List of document IDs")
    operation: str = Field(..., description="Operation to perform (reprocess, delete, link_customer)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Operation-specific parameters")
    
    @validator('document_ids')
    def validate_document_ids(cls, v):
        if not v:
            raise ValueError('At least one document ID is required')
        return list(set(v))  # Remove duplicates