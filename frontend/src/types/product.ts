export interface Product {
  id: string;
  name: string;
  description?: string;
  tagline?: string;
  logo_url?: string;
  website?: string;
  created_at: string;
  updated_at: string;
  segments: ProductSegment[];
  modules: ProductModule[];
}

export interface ProductCreate {
  name: string;
  description?: string;
  tagline?: string;
  logo_url?: string;
  website?: string;
}

export interface ProductUpdate {
  name?: string;
  description?: string;
  tagline?: string;
  logo_url?: string;
  website?: string;
}

export interface ProductSegment {
  id: string;
  product_id: string;
  name: string;
  description?: string;
  target_market?: string;
  customer_size?: CustomerSize;
  created_at: string;
  updated_at: string;
}

export interface ProductModule {
  id: string;
  product_id: string;
  name: string;
  description?: string;
  icon?: string;
  order_index: number;
  created_at: string;
  updated_at: string;
  feature_count?: number;
}

export enum CustomerSize {
  SMB = 'SMB',
  MID_MARKET = 'Mid Market',
  ENTERPRISE = 'Enterprise',
  ALL = 'All',
}

export interface BattleCard {
  id: string;
  product_id: string;
  competitor_id: string;
  version: number;
  status: BattleCardStatus;
  published_at?: string;
  created_by?: string;
  created_at: string;
  updated_at: string;
  sections: BattleCardSection[];
  product_name?: string;
  competitor_name?: string;
}

export interface BattleCardSection {
  id: string;
  battle_card_id: string;
  section_type: BattleCardSectionType;
  content: any;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export enum BattleCardStatus {
  DRAFT = 'Draft',
  PUBLISHED = 'Published',
  ARCHIVED = 'Archived',
}

export enum BattleCardSectionType {
  WHY_WE_WIN = 'Why We Win',
  COMPETITOR_STRENGTHS = 'Competitor Strengths',
  OBJECTION_HANDLING = 'Objection Handling',
  FEATURE_COMPARISON = 'Feature Comparison',
  PRICING_COMPARISON = 'Pricing Comparison',
  KEY_DIFFERENTIATORS = 'Key Differentiators',
}

export interface ScrapingJob {
  id: string;
  competitor_id: string;
  job_type: ScrapingJobType;
  status: ScrapingJobStatus;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  results?: any;
  created_at: string;
  updated_at: string;
}

export enum ScrapingJobType {
  FEATURES = 'Features',
  PRICING = 'Pricing',
  NEWS = 'News',
  REVIEWS = 'Reviews',
  FULL_SCAN = 'Full Scan',
}

export enum ScrapingJobStatus {
  PENDING = 'Pending',
  RUNNING = 'Running',
  COMPLETED = 'Completed',
  FAILED = 'Failed',
}