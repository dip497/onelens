# OneLens Knowledge Base Integration

This document explains how the OneLens platform integrates ChromaDB with Agno framework to provide intelligent, knowledge-based AI assistance.

## Overview

The knowledge base integration allows the OneLens AI Assistant to:
- Access and search through all OneLens data (epics, features, customers, competitors, etc.)
- Provide contextual responses based on your actual data
- Use Agentic RAG (Retrieval-Augmented Generation) for accurate information retrieval
- Maintain up-to-date knowledge as your data changes

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   OneLens DB    │───▶│   Knowledge      │───▶│   ChromaDB      │
│   (PostgreSQL)  │    │   Loader         │    │   (Vector DB)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Query    │───▶│   Agno Agent     │◄───│   ChromaDB      │
│                 │    │   (with KB)      │    │   Knowledge     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Components

### 1. ChromaDBService (`app/services/chromadb_service.py`)
- Manages ChromaDB client and collection operations
- Handles document storage, querying, and management
- Provides low-level ChromaDB interface

### 2. ChromaDBKnowledge (`app/services/agno_chromadb_knowledge.py`)
- Agno-compatible knowledge base implementation
- Bridges ChromaDB with Agno's knowledge system
- Implements search and document management for Agno agents

### 3. KnowledgeLoader (`app/services/knowledge_loader.py`)
- Loads OneLens data into the knowledge base
- Converts database records to searchable documents
- Handles data synchronization and updates

### 4. Knowledge API (`app/api/v1/knowledge.py`)
- REST endpoints for knowledge base management
- Allows loading, searching, and maintaining the knowledge base
- Provides health checks and information endpoints

## Setup and Usage

### 1. Initialize the Knowledge Base

Run the initialization script to load your existing data:

```bash
cd backend
python scripts/init_knowledge_base.py
```

This will:
- Create a ChromaDB collection
- Load all OneLens data (epics, features, customers, etc.)
- Test the knowledge base functionality

### 2. API Endpoints

The knowledge base provides several API endpoints:

#### Get Knowledge Base Info
```http
GET /api/v1/knowledge/info
```

#### Load Data into Knowledge Base
```http
POST /api/v1/knowledge/load?recreate=false
```

#### Search Knowledge Base
```http
POST /api/v1/knowledge/search?query=customer%20requests&limit=10
```

#### Clear Knowledge Base
```http
POST /api/v1/knowledge/clear
```

#### Add Text to Knowledge Base
```http
POST /api/v1/knowledge/add-text?text=Your%20custom%20text
```

### 3. Using with the AI Assistant

The AI Assistant automatically uses the knowledge base when `search_knowledge=True` is enabled (which it is by default). Users can ask questions like:

- "What features do our enterprise customers want most?"
- "Show me competitors in the CRM space"
- "What are the highest priority epics?"
- "Which customers have requested authentication features?"

The agent will automatically search the knowledge base and provide responses based on your actual data.

## Configuration

### Environment Variables

Add these to your `.env` file:

```env
# ChromaDB Configuration
CHROMA_DB_PATH=./chroma_db
CHROMA_COLLECTION_NAME=onelens_knowledge
```

### Settings

The knowledge base configuration is in `app/core/config.py`:

```python
# ChromaDB Configuration
CHROMA_DB_PATH: str = "./chroma_db"
CHROMA_COLLECTION_NAME: str = "onelens_knowledge"
```

## Data Types Loaded

The knowledge base includes the following OneLens data:

1. **Epics**: Title, description, business justification, status, priority
2. **Features**: Title, description, epic association, customer request counts
3. **Customers**: Name, segment, vertical, region, ARR, strategic importance
4. **Feature Requests**: Customer requests with business justification and urgency
5. **Competitors**: Name, description, market position, website
6. **Competitor Features**: Feature comparisons and pricing information

## Maintenance

### Updating the Knowledge Base

When your OneLens data changes, you can update the knowledge base:

1. **Full Reload**: Use the API or script with `recreate=true`
2. **Incremental Updates**: Add new documents via the API
3. **Automated Sync**: Set up periodic updates (recommended for production)

### Monitoring

Check knowledge base health:

```http
GET /api/v1/knowledge/health
```

This returns information about:
- Whether the knowledge base exists
- Number of documents
- Collection metadata
- Health status

## Advanced Usage

### Custom Metadata Filters

When searching, you can filter by metadata:

```python
# Search only for customer-related documents
results = kb.search(
    query="enterprise customers",
    filters={"type": "customer"}
)

# Search for high-priority items
results = kb.search(
    query="urgent features",
    filters={"urgency": "HIGH"}
)
```

### Adding Custom Documents

You can add custom documents to enhance the knowledge base:

```python
from app.services.agno_chromadb_knowledge import ChromaDBKnowledge

kb = ChromaDBKnowledge()
kb.load_text(
    text="Our Q4 strategy focuses on enterprise customers...",
    metadata={"type": "strategy", "quarter": "Q4"}
)
```

## Troubleshooting

### Common Issues

1. **ChromaDB not found**: Ensure ChromaDB is installed (`pip install chromadb`)
2. **Empty knowledge base**: Run the initialization script
3. **Search returns no results**: Check if data was loaded correctly
4. **Permission errors**: Ensure the ChromaDB directory is writable

### Debugging

Enable debug logging to see knowledge base operations:

```python
import logging
logging.getLogger("app.services.chromadb_service").setLevel(logging.DEBUG)
logging.getLogger("app.services.agno_chromadb_knowledge").setLevel(logging.DEBUG)
```

## Performance Considerations

- **Initial Load**: First-time loading may take a few minutes depending on data size
- **Search Speed**: ChromaDB provides fast similarity search for most queries
- **Memory Usage**: ChromaDB keeps embeddings in memory for better performance
- **Disk Space**: Vector embeddings require additional storage space

## Security

- ChromaDB data is stored locally by default
- No external API calls for basic operations
- Embeddings are generated using local sentence-transformers model
- Consider encryption for sensitive production data

## Next Steps

1. **Monitor Usage**: Track which queries are most common
2. **Optimize Content**: Refine document content for better search results
3. **Add More Data**: Include additional data sources (documents, wikis, etc.)
4. **Automate Updates**: Set up automated knowledge base synchronization
5. **Custom Embeddings**: Consider using domain-specific embedding models
