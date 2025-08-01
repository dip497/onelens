-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create ENUM types
CREATE TYPE epic_status AS ENUM ('Draft', 'Analysis Pending', 'Analyzed', 'Approved', 'In Progress', 'Delivered');
CREATE TYPE market_position AS ENUM ('Leader', 'Challenger', 'Visionary', 'Niche');
CREATE TYPE company_size AS ENUM ('Startup', 'SMB', 'Enterprise', 'Large Enterprise');
CREATE TYPE customer_segment AS ENUM ('Small', 'Medium', 'Large', 'Enterprise');
CREATE TYPE customer_vertical AS ENUM ('Healthcare', 'Finance', 'Technology', 'Manufacturing', 'Retail', 'Other');
CREATE TYPE urgency_level AS ENUM ('Critical', 'High', 'Medium', 'Low');
CREATE TYPE request_source AS ENUM ('Sales Call', 'Support Ticket', 'User Interview', 'RFP');
CREATE TYPE impact_level AS ENUM ('High', 'Medium', 'Low');
CREATE TYPE complexity_level AS ENUM ('Low', 'Medium', 'High');
CREATE TYPE availability_status AS ENUM ('Available', 'Beta', 'Planned', 'Discontinued');
CREATE TYPE pricing_tier AS ENUM ('Free', 'Basic', 'Pro', 'Enterprise');
CREATE TYPE local_presence AS ENUM ('Strong', 'Medium', 'Weak', 'None');
CREATE TYPE opportunity_rating AS ENUM ('High', 'Medium', 'Low');
CREATE TYPE processed_status AS ENUM ('Pending', 'Processing', 'Complete', 'Failed');

-- Users table (simplified for now)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Epics table
CREATE TABLE epics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    business_justification TEXT,
    status epic_status DEFAULT 'Draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(id),
    assigned_to UUID REFERENCES users(id)
);

-- Features table
CREATE TABLE features (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    epic_id UUID REFERENCES epics(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    normalized_text TEXT,
    embedding vector(384),
    customer_request_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT features_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES epics(id)
);

-- Create index for vector similarity search
CREATE INDEX features_embedding_idx ON features USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Customers table
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    segment customer_segment,
    vertical customer_vertical,
    arr DECIMAL(12,2),
    employee_count INTEGER,
    geographic_region VARCHAR(100),
    contract_end_date DATE,
    strategic_importance impact_level,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Feature requests table
CREATE TABLE feature_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id),
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    urgency urgency_level,
    business_justification TEXT,
    estimated_deal_impact DECIMAL(12,2),
    source request_source,
    request_details TEXT
);

-- Competitors table
CREATE TABLE competitors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    website VARCHAR(500),
    market_position market_position,
    primary_markets JSONB,
    company_size company_size,
    funding_stage VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Competitor features table
CREATE TABLE competitor_features (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    competitor_id UUID REFERENCES competitors(id) ON DELETE CASCADE,
    feature_name VARCHAR(255),
    feature_description TEXT,
    availability availability_status,
    pricing_tier pricing_tier,
    strengths TEXT,
    weaknesses TEXT,
    last_verified TIMESTAMP,
    source_url VARCHAR(500)
);

-- Trend analysis table
CREATE TABLE trend_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    is_aligned_with_trends BOOLEAN,
    trend_score DECIMAL(3,1) CHECK (trend_score >= 0 AND trend_score <= 10),
    trend_keywords JSONB,
    trend_sources JSONB,
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confidence_score DECIMAL(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

-- Business impact analysis table
CREATE TABLE business_impact_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    impact_score INTEGER CHECK (impact_score >= 0 AND impact_score <= 100),
    revenue_impact impact_level,
    user_adoption_potential impact_level,
    strategic_alignment impact_level,
    implementation_complexity complexity_level,
    justification TEXT,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market opportunity analysis table
CREATE TABLE market_opportunity_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    total_competitors_analyzed INTEGER,
    competitors_providing_feature INTEGER,
    competitors_not_providing INTEGER,
    opportunity_score DECIMAL(3,1),
    market_gap_percentage DECIMAL(5,2),
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Geographic analysis table
CREATE TABLE geographic_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    country VARCHAR(100),
    market_size_usd BIGINT,
    competitor_presence_count INTEGER,
    market_penetration_percentage DECIMAL(5,2),
    regulatory_factors JSONB,
    cultural_adoption_factors TEXT,
    opportunity_rating opportunity_rating,
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Competitor geographic presence table
CREATE TABLE competitor_geographic_presence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    competitor_id UUID REFERENCES competitors(id) ON DELETE CASCADE,
    country VARCHAR(100),
    market_share_percentage DECIMAL(5,2),
    local_presence local_presence,
    key_customers JSONB
);

-- Priority scores table
CREATE TABLE priority_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    final_score DECIMAL(4,1) CHECK (final_score >= 0 AND final_score <= 100),
    customer_impact_score DECIMAL(4,1),
    trend_alignment_score DECIMAL(4,1),
    business_impact_score DECIMAL(4,1),
    market_opportunity_score DECIMAL(4,1),
    segment_diversity_score DECIMAL(4,1),
    calculation_metadata JSONB,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    algorithm_version VARCHAR(10) DEFAULT '1.0'
);

-- RFP documents table
CREATE TABLE rfp_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255),
    customer_id UUID REFERENCES customers(id),
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_status processed_status DEFAULT 'Pending',
    total_questions INTEGER,
    processed_questions INTEGER,
    business_context JSONB
);

-- RFP Q&A pairs table
CREATE TABLE rfp_qa_pairs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES rfp_documents(id) ON DELETE CASCADE,
    feature_id UUID REFERENCES features(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    customer_context JSONB,
    business_impact_estimate DECIMAL(12,2),
    embedding vector(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for RFP Q&A embedding search
CREATE INDEX rfp_qa_embedding_idx ON rfp_qa_pairs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Feature analysis reports table
CREATE TABLE feature_analysis_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    trend_alignment_status BOOLEAN,
    trend_keywords JSONB,
    trend_justification TEXT,
    business_impact_score INTEGER,
    revenue_potential impact_level,
    user_adoption_forecast impact_level,
    total_competitors_analyzed INTEGER,
    competitors_providing_count INTEGER,
    market_opportunity_score DECIMAL(3,1),
    geographic_insights JSONB,
    competitor_pros_cons JSONB,
    competitive_positioning TEXT,
    priority_score DECIMAL(4,1),
    priority_ranking INTEGER,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    generated_by_workflow VARCHAR(255)
);

-- Create indexes for performance
CREATE INDEX idx_features_epic_id ON features(epic_id);
CREATE INDEX idx_feature_requests_feature_id ON feature_requests(feature_id);
CREATE INDEX idx_feature_requests_customer_id ON feature_requests(customer_id);
CREATE INDEX idx_competitor_features_competitor_id ON competitor_features(competitor_id);
CREATE INDEX idx_priority_scores_feature_id ON priority_scores(feature_id);
CREATE INDEX idx_analysis_reports_feature_id ON feature_analysis_reports(feature_id);

-- Create update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for epics table
CREATE TRIGGER update_epics_updated_at BEFORE UPDATE ON epics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();