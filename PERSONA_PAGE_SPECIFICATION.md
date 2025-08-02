# Persona Page Technical Specification

## Executive Summary

This document outlines the technical specification for implementing a comprehensive Persona Page feature that includes product management, competitor analysis, and battle card generation. The system will enable users to create product personas, track competitors, analyze their features, and generate battle cards automatically using web scraping agents.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │     │   Backend API   │     │   Database      │
│   (React/TS)    │────▶│   (FastAPI)     │────▶│  (PostgreSQL)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │ Scraping Agents │
                        │   (Celery)      │
                        └─────────────────┘
```

## Database Schema Design

### New Tables

#### 1. Products Table
```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    tagline VARCHAR(500),
    logo_url VARCHAR(500),
    website VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. Product Segments Table
```sql
CREATE TABLE product_segments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    target_market TEXT,
    customer_size ENUM('SMB', 'MID_MARKET', 'ENTERPRISE', 'ALL'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 3. Product Modules Table
```sql
CREATE TABLE product_modules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    icon VARCHAR(100),
    order_index INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 4. Module Features Table (Extends existing features table)
```sql
ALTER TABLE features ADD COLUMN module_id UUID REFERENCES product_modules(id) ON DELETE SET NULL;
ALTER TABLE features ADD COLUMN is_key_differentiator BOOLEAN DEFAULT FALSE;
```

#### 5. Battle Cards Table
```sql
CREATE TABLE battle_cards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    version INTEGER DEFAULT 1,
    status ENUM('DRAFT', 'PUBLISHED', 'ARCHIVED') DEFAULT 'DRAFT',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE,
    created_by UUID REFERENCES users(id),
    UNIQUE(product_id, competitor_id, version)
);
```

#### 6. Battle Card Sections Table
```sql
CREATE TABLE battle_card_sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    battle_card_id UUID NOT NULL REFERENCES battle_cards(id) ON DELETE CASCADE,
    section_type ENUM('WHY_WE_WIN', 'COMPETITOR_STRENGTHS', 'OBJECTION_HANDLING', 
                      'FEATURE_COMPARISON', 'PRICING_COMPARISON', 'KEY_DIFFERENTIATORS') NOT NULL,
    content JSONB NOT NULL,
    order_index INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 7. Competitor Scraping Jobs Table
```sql
CREATE TABLE competitor_scraping_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    job_type ENUM('FEATURES', 'PRICING', 'NEWS', 'REVIEWS', 'FULL_SCAN') NOT NULL,
    status ENUM('PENDING', 'RUNNING', 'COMPLETED', 'FAILED') DEFAULT 'PENDING',
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    results JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Updated Enums (add to enums.py)
```python
class CustomerSize(str, enum.Enum):
    SMB = "SMB"
    MID_MARKET = "Mid Market"
    ENTERPRISE = "Enterprise"
    ALL = "All"

class BattleCardStatus(str, enum.Enum):
    DRAFT = "Draft"
    PUBLISHED = "Published"
    ARCHIVED = "Archived"

class BattleCardSectionType(str, enum.Enum):
    WHY_WE_WIN = "Why We Win"
    COMPETITOR_STRENGTHS = "Competitor Strengths"
    OBJECTION_HANDLING = "Objection Handling"
    FEATURE_COMPARISON = "Feature Comparison"
    PRICING_COMPARISON = "Pricing Comparison"
    KEY_DIFFERENTIATORS = "Key Differentiators"

class ScrapingJobType(str, enum.Enum):
    FEATURES = "Features"
    PRICING = "Pricing"
    NEWS = "News"
    REVIEWS = "Reviews"
    FULL_SCAN = "Full Scan"

class ScrapingJobStatus(str, enum.Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
```

## Backend API Endpoints

### Product Management Endpoints

#### 1. Product CRUD Operations
```python
# GET /api/v1/products - List all products
# POST /api/v1/products - Create new product
# GET /api/v1/products/{product_id} - Get product details
# PUT /api/v1/products/{product_id} - Update product
# DELETE /api/v1/products/{product_id} - Delete product

# Product Segments
# GET /api/v1/products/{product_id}/segments - List product segments
# POST /api/v1/products/{product_id}/segments - Create segment
# PUT /api/v1/segments/{segment_id} - Update segment
# DELETE /api/v1/segments/{segment_id} - Delete segment

# Product Modules
# GET /api/v1/products/{product_id}/modules - List product modules
# POST /api/v1/products/{product_id}/modules - Create module
# PUT /api/v1/modules/{module_id} - Update module
# DELETE /api/v1/modules/{module_id} - Delete module
# PUT /api/v1/products/{product_id}/modules/reorder - Reorder modules

# Module Features
# GET /api/v1/modules/{module_id}/features - List module features
# POST /api/v1/modules/{module_id}/features - Add feature to module
# DELETE /api/v1/modules/{module_id}/features/{feature_id} - Remove feature from module
```

### Competitor Management Endpoints

#### 2. Enhanced Competitor Operations
```python
# GET /api/v1/competitors - List all competitors (existing)
# POST /api/v1/competitors - Create new competitor (existing)
# GET /api/v1/competitors/{competitor_id} - Get competitor details (existing)
# PUT /api/v1/competitors/{competitor_id} - Update competitor (existing)
# DELETE /api/v1/competitors/{competitor_id} - Delete competitor (existing)

# New endpoints
# POST /api/v1/competitors/{competitor_id}/scrape - Trigger web scraping
# GET /api/v1/competitors/{competitor_id}/scraping-jobs - Get scraping job history
# GET /api/v1/competitors/{competitor_id}/analysis - Get competitive analysis
```

### Battle Card Endpoints

#### 3. Battle Card Operations
```python
# GET /api/v1/battle-cards - List all battle cards
# POST /api/v1/battle-cards - Create new battle card
# GET /api/v1/battle-cards/{battle_card_id} - Get battle card details
# PUT /api/v1/battle-cards/{battle_card_id} - Update battle card
# DELETE /api/v1/battle-cards/{battle_card_id} - Delete battle card
# POST /api/v1/battle-cards/{battle_card_id}/publish - Publish battle card
# POST /api/v1/battle-cards/{battle_card_id}/archive - Archive battle card
# GET /api/v1/battle-cards/{battle_card_id}/export - Export battle card (PDF/PPT)

# Battle Card Generation
# POST /api/v1/products/{product_id}/generate-battle-card - Auto-generate battle card
```

### Request/Response Schemas

#### Product Schema
```python
class ProductCreate(BaseModel):
    name: str
    description: Optional[str]
    tagline: Optional[str]
    logo_url: Optional[str]
    website: Optional[str]

class ProductResponse(ProductCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime
    segments: List[SegmentResponse] = []
    modules: List[ModuleResponse] = []

class SegmentCreate(BaseModel):
    name: str
    description: Optional[str]
    target_market: Optional[str]
    customer_size: CustomerSize

class ModuleCreate(BaseModel):
    name: str
    description: Optional[str]
    icon: Optional[str]
    order_index: int = 0

class BattleCardCreate(BaseModel):
    product_id: UUID
    competitor_id: UUID
    sections: List[BattleCardSectionCreate]

class BattleCardSectionCreate(BaseModel):
    section_type: BattleCardSectionType
    content: Dict[str, Any]
    order_index: int = 0

class CompetitorScrapingRequest(BaseModel):
    job_type: ScrapingJobType
    target_urls: Optional[List[str]] = []
```

## Frontend Implementation

### Component Structure

```
src/components/personas/
├── PersonaDashboard.tsx         # Main dashboard
├── ProductList.tsx              # List of products
├── ProductDetail.tsx            # Product detail view
├── ProductForm.tsx              # Create/Edit product form
├── SegmentManager.tsx           # Manage segments
├── ModuleManager.tsx            # Manage modules
├── FeatureAssignment.tsx        # Assign features to modules
├── CompetitorComparison.tsx     # Compare with competitors
├── BattleCardGenerator.tsx      # Generate battle cards
├── BattleCardViewer.tsx         # View/Edit battle cards
└── ScrapingJobMonitor.tsx       # Monitor scraping jobs
```

### Key UI Features

1. **Product Dashboard**
   - Grid/List view of all products
   - Quick stats (segments, modules, features)
   - Search and filter capabilities

2. **Product Detail Page**
   - Overview tab with basic info
   - Segments tab with target market info
   - Modules tab with drag-and-drop reordering
   - Features tab with module assignment
   - Competitors tab with comparison matrix
   - Battle Cards tab with generation/viewing

3. **Battle Card Builder**
   - Template selection
   - AI-powered content suggestions
   - Real-time preview
   - Export options (PDF, PPT, Web)
   - Version control

4. **Competitor Analysis**
   - Side-by-side feature comparison
   - Strength/Weakness analysis
   - Win/Loss insights
   - Automated scraping triggers

### State Management

```typescript
// Redux Slices
interface PersonaState {
  products: Product[];
  currentProduct: Product | null;
  competitors: Competitor[];
  battleCards: BattleCard[];
  scrapingJobs: ScrapingJob[];
  loading: boolean;
  error: string | null;
}

// Key Actions
- fetchProducts()
- createProduct()
- updateProduct()
- deleteProduct()
- generateBattleCard()
- triggerCompetitorScraping()
- exportBattleCard()
```

## Web Scraping Agent Architecture

### Celery Tasks

```python
# tasks/competitor_scraping.py

@celery_app.task
def scrape_competitor_website(competitor_id: str, job_type: str):
    """
    Main scraping task that delegates to specific scrapers
    """
    pass

@celery_app.task
def scrape_features(competitor_id: str, urls: List[str]):
    """
    Scrape product features from competitor websites
    """
    pass

@celery_app.task
def scrape_pricing(competitor_id: str, urls: List[str]):
    """
    Scrape pricing information
    """
    pass

@celery_app.task
def analyze_competitor_content(competitor_id: str, content: dict):
    """
    Use AI to analyze scraped content and extract insights
    """
    pass

@celery_app.task
def generate_battle_card_content(product_id: str, competitor_id: str):
    """
    Generate battle card content using AI based on collected data
    """
    pass
```

### Scraping Strategy

1. **Feature Detection**
   - Identify feature pages/sections
   - Extract feature names and descriptions
   - Categorize by module/area
   - Identify pricing tiers

2. **Content Analysis**
   - Use LLM to understand features
   - Extract key differentiators
   - Identify strengths/weaknesses
   - Generate objection responses

3. **Data Validation**
   - Cross-reference multiple sources
   - Version tracking
   - Confidence scoring
   - Manual review flags

## Integration Points

### Existing System Integration

1. **Feature Management**
   - Link features to product modules
   - Maintain feature-customer relationships
   - Preserve RFP connections

2. **Customer Data**
   - Associate battle cards with customer segments
   - Track usage in sales processes
   - Win/loss analysis integration

3. **Epic System**
   - Link product roadmap to competitive gaps
   - Prioritize features based on competitive analysis

### External Integrations

1. **Web Scraping Tools**
   - Selenium for dynamic content
   - BeautifulSoup for HTML parsing
   - Scrapy for large-scale scraping

2. **AI/LLM Integration**
   - OpenAI/Anthropic for content analysis
   - Embedding generation for similarity matching
   - Competitive insight generation

## Security Considerations

1. **Data Protection**
   - Encrypt sensitive competitive data
   - Role-based access control for battle cards
   - Audit logs for all modifications

2. **Scraping Ethics**
   - Respect robots.txt
   - Rate limiting
   - User-agent identification
   - Terms of service compliance

3. **API Security**
   - JWT authentication
   - Rate limiting per endpoint
   - Input validation
   - SQL injection prevention

## Performance Optimization

1. **Database**
   - Index on frequently queried fields
   - Materialized views for complex comparisons
   - Partition large tables by date

2. **Caching**
   - Redis for battle card templates
   - CDN for static assets
   - API response caching

3. **Async Processing**
   - Background jobs for scraping
   - Batch processing for analysis
   - WebSocket for real-time updates

## Deployment Considerations

1. **Infrastructure**
   - Separate worker nodes for scraping
   - Redis for Celery broker
   - S3 for document storage

2. **Monitoring**
   - Scraping job success rates
   - API performance metrics
   - Error tracking and alerting

3. **Scaling**
   - Horizontal scaling for API
   - Auto-scaling for worker nodes
   - Database read replicas

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- Create database schema
- Implement basic CRUD APIs
- Build product management UI

### Phase 2: Competitor Integration (Week 3-4)
- Enhance competitor models
- Build comparison features
- Create manual battle card builder

### Phase 3: Automation (Week 5-6)
- Implement web scraping agents
- Add AI-powered analysis
- Auto-generate battle cards

### Phase 4: Polish & Launch (Week 7-8)
- Export functionality
- Performance optimization
- Security hardening
- User training

## Success Metrics

1. **Usage Metrics**
   - Number of products created
   - Battle cards generated
   - Export frequency

2. **Quality Metrics**
   - Scraping accuracy
   - AI content quality scores
   - User satisfaction ratings

3. **Business Impact**
   - Sales win rate improvement
   - Time saved in competitive analysis
   - Deal velocity increase

## Appendix: Sample Data Structures

### Battle Card Content Structure
```json
{
  "why_we_win": [
    {
      "point": "Superior AI-powered analytics",
      "evidence": "Customer case study: 50% faster insights",
      "talk_track": "Our AI engine analyzes data 50% faster..."
    }
  ],
  "competitor_strengths": [
    {
      "strength": "Established market presence",
      "counter": "Focus on innovation and agility",
      "response": "While they have market presence, we offer..."
    }
  ],
  "objection_handling": [
    {
      "objection": "Your product lacks feature X",
      "response": "We've taken a different approach that...",
      "proof_points": ["Customer testimonial", "ROI data"]
    }
  ],
  "feature_comparison": {
    "our_product": {
      "features": ["Feature A", "Feature B"],
      "unique_features": ["Feature C"]
    },
    "competitor": {
      "features": ["Feature A", "Feature D"],
      "missing_features": ["Feature B", "Feature C"]
    }
  }
}
```

This specification provides a comprehensive blueprint for implementing the Persona Page feature with integrated competitor analysis and battle card generation capabilities.