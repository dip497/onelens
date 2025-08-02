# Single Product Persona Design

## System Architecture Changes

### Core Concept
- **ONE Product Persona**: Represents YOUR company's product
- **Multiple Competitors**: Track and analyze many competitors
- **Battle Cards**: Generate "Our Product vs Competitor X" comparisons

### Data Structure
```
Your Company (Single Product/Persona)
├── Product Info (name, description, website)
├── Modules (organize features)
│   ├── Core Features
│   ├── Analytics & Insights
│   ├── Integration & API
│   ├── User Experience
│   └── Security & Compliance
├── Features (assigned to modules)
│   ├── Feature 1 → Module A
│   ├── Feature 2 → Module B
│   └── Feature 3 (key differentiator) → Module A
└── Customer Segments
    ├── Enterprise
    ├── Mid-Market
    └── SMB

Competitors (Multiple)
├── Competitor A
│   ├── Basic Info
│   ├── Features (discovered via AI/scraping)
│   └── Market Position
├── Competitor B
└── Competitor C

Battle Cards
├── Your Product vs Competitor A
├── Your Product vs Competitor B
└── Your Product vs Competitor C
```

## Implementation Details

### 1. Database Changes
- Product table remains but system enforces single record
- Features link to modules via `module_id`
- Modules belong to the single product
- Battle cards compare THE product against competitors

### 2. API Changes

#### New Persona API (`/api/v1/persona`)
- `GET /persona/` - Get your company's product persona
- `PUT /persona/` - Update your product info
- `GET /persona/stats` - Get statistics

#### Existing APIs
- Products API still exists but PersonaDashboard redirects to single product
- Competitors API allows creating multiple competitors
- Battle Cards API generates comparisons

### 3. Frontend Changes
- PersonaDashboard checks if persona exists
- If not initialized: Shows setup instructions
- If initialized: Redirects to product detail page
- Navigation says "Product Personas" but manages single persona

### 4. Competitor Intelligence

#### Using Agno Agents
We have access to these pre-built agents:
- **competitive_analysis_agent**: Research competitor features and positioning
- **trend_analysis_agent**: Analyze market trends
- **market_opportunity_agent**: Geographic market analysis

#### Competitor Data Collection Service
```python
# app/services/competitor_intelligence.py
CompetitorIntelligenceService:
  - analyze_competitor() - Use AI to research competitor
  - compare_with_our_product() - Generate comparison
  - generate_battle_card_content() - Create battle card sections
```

## How It Works

1. **Initial Setup**
   ```bash
   python ensure_single_persona.py
   ```
   Creates your company persona with default modules

2. **Feature Assignment**
   - Create features in Epic/Feature system
   - Assign features to product modules
   - Mark key differentiators

3. **Competitor Analysis**
   - Add competitors manually
   - Use AI agents to discover their features
   - System stores competitor features

4. **Battle Card Generation**
   - Select a competitor
   - AI compares your features vs theirs
   - Generates structured battle card content
   - Sections: Why We Win, Their Strengths, Objection Handling

## Testing

Run the test script to verify everything works:
```bash
python test_persona_api.py
```

This will check:
- Persona API endpoints
- Product-Module-Feature relationships
- Competitor data
- API connectivity

## Benefits of This Design

1. **Clarity**: One product to manage, not multiple
2. **Focus**: Your product vs competitors
3. **Intelligence**: AI-powered competitor analysis
4. **Structure**: Clear hierarchy (Product → Modules → Features)
5. **Sales Enablement**: Battle cards for each competitor