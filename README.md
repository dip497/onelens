# Epic Analysis System

An AI-powered system for analyzing product features, tracking market trends, and prioritizing development efforts based on competitive intelligence and customer demand.

## 🚀 Features

- **Epic & Feature Management**: Create and manage product epics with detailed feature tracking
- **AI-Powered Analysis**: Automated trend analysis, competitive research, and market opportunity assessment
- **Smart Prioritization**: Multi-factor priority scoring algorithm considering customer impact, market trends, and competitive landscape
- **RFP Processing**: Automated extraction and matching of requirements from RFP documents
- **Geographic Market Analysis**: Insights for top 5 business markets (US, UK, Germany, Japan, Australia)
- **Competitive Intelligence**: Track competitor features and identify market gaps

## 🏗️ Architecture

### Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL with pgvector
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Shadcn/UI
- **AI Framework**: Agno framework for agent orchestration
- **Infrastructure**: Docker, Redis, pgvector for embeddings

### Key Components

1. **Database Models**
   - Epics, Features, Customers, Competitors
   - Analysis results (Trend, Business Impact, Market Opportunity, Geographic)
   - RFP documents and Q&A pairs

2. **API Endpoints**
   - Epic CRUD operations with analysis triggers
   - Feature management with similarity search
   - Customer request tracking
   - Competitive analysis data

3. **AI Agents**
   - Trend Analysis Agent
   - Competitive Analysis Agent
   - Market Opportunity Agent
   - Priority Scoring Agent

## 🛠️ Setup Instructions

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ and npm
- Python 3.11+
- Git

### Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd onelens
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start the services with Docker**
   ```bash
   docker-compose up -d
   ```

   This will start:
   - PostgreSQL with pgvector extension
   - Redis cache
   - Backend API (FastAPI)
   - Frontend (React)
   - Agno AI framework

4. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/api/v1/docs

### Manual Setup (Development)

#### Backend Setup

1. **Create Python virtual environment**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -e .
   ```

3. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

4. **Start the backend server**
   ```bash
   uvicorn main:app --reload
   ```

#### Frontend Setup

1. **Install dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Start the development server**
   ```bash
   npm run dev
   ```

## 📊 Priority Scoring Algorithm

The system uses a multi-factor algorithm to calculate feature priority:

- **Customer Impact (30%)**: Weighted by segment (Enterprise=10x, Large=5x, Medium=2.5x, Small=1x)
- **Trend Alignment (20%)**: AI-analyzed technology trend matching
- **Business Impact (25%)**: Revenue potential and strategic value
- **Market Opportunity (20%)**: Competitive gap analysis
- **Segment Diversity (5%)**: Cross-segment appeal

## 🔄 Workflows

### Epic Analysis Workflow

1. Create an epic with features
2. System triggers automated analysis
3. AI agents perform:
   - Trend alignment check
   - Competitive landscape research
   - Market opportunity assessment
   - Geographic market analysis
4. Priority scores are calculated
5. Comprehensive reports are generated

### RFP Processing

1. Upload RFP document (Excel, CSV, PDF)
2. System extracts Q&A pairs
3. Similarity matching with existing features (>85% threshold)
4. Automatic feature request creation or update
5. Priority score recalculation

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## 📝 API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.