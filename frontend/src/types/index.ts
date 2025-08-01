// Epic types
export enum EpicStatus {
  DRAFT = 'Draft',
  ANALYSIS_PENDING = 'Analysis Pending',
  ANALYZED = 'Analyzed',
  APPROVED = 'Approved',
  IN_PROGRESS = 'In Progress',
  DELIVERED = 'Delivered'
}

export interface Epic {
  id: string;
  title: string;
  description?: string;
  business_justification?: string;
  status: EpicStatus;
  created_at: string;
  updated_at: string;
  created_by?: string;
  assigned_to?: string;
  features_count?: number;
}

// Feature types
export interface Feature {
  id: string;
  epic_id: string;
  title: string;
  description?: string;
  customer_request_count: number;
  created_at: string;
  priority_score?: PriorityScore;
}

// Customer types
export enum CustomerSegment {
  SMALL = 'Small',
  MEDIUM = 'Medium',
  LARGE = 'Large',
  ENTERPRISE = 'Enterprise'
}

export enum UrgencyLevel {
  CRITICAL = 'Critical',
  HIGH = 'High',
  MEDIUM = 'Medium',
  LOW = 'Low'
}

export interface Customer {
  id: string;
  name: string;
  segment: CustomerSegment;
  vertical?: string;
  arr?: number;
  employee_count?: number;
  geographic_region?: string;
}

export interface FeatureRequest {
  id: string;
  feature_id: string;
  customer_id: string;
  urgency: UrgencyLevel;
  business_justification?: string;
  estimated_deal_impact?: number;
  created_at: string;
}

// Analysis types
export interface PriorityScore {
  id: string;
  feature_id: string;
  final_score: number;
  customer_impact_score: number;
  trend_alignment_score: number;
  business_impact_score: number;
  market_opportunity_score: number;
  segment_diversity_score: number;
  calculated_at: string;
}

export interface TrendAnalysis {
  id: string;
  feature_id: string;
  is_aligned_with_trends: boolean;
  trend_score: number;
  trend_keywords: string[];
  confidence_score: number;
  created_at: string;
}

export interface FeatureAnalysisReport {
  id: string;
  feature_id: string;
  trend_alignment_status: boolean;
  business_impact_score: number;
  total_competitors_analyzed: number;
  competitors_providing_count: number;
  market_opportunity_score: number;
  priority_score: number;
  priority_ranking: number;
  generated_at: string;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// API Response types
export interface ApiError {
  detail: string;
  status?: number;
}

// Form types
export interface EpicCreateInput {
  title: string;
  description?: string;
  business_justification?: string;
  assigned_to?: string;
}

export interface FeatureCreateInput {
  epic_id: string;
  title: string;
  description?: string;
}

export interface FeatureRequestCreateInput {
  customer_id: string;
  urgency: UrgencyLevel;
  business_justification?: string;
  estimated_deal_impact?: number;
  source?: string;
}

// Analysis request types
export interface AnalysisRequest {
  analysis_types?: string[];
}

// Dashboard types
export interface EpicSummary {
  status: EpicStatus;
  count: number;
}

export interface FeatureRanking {
  rank: number;
  feature_id: string;
  feature_title: string;
  epic_id: string;
  priority_score: number;
  calculated_at: string;
}