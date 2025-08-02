# OneLens Centralized Agents

This module provides centralized agent definitions for the OneLens platform. All agents are defined in a single location to ensure consistency and easy maintenance across the application.

## Usage

### Basic Usage

```python
from app.agents import get_agent, get_onelens_assistant

# Get the main assistant
assistant = get_onelens_assistant()

# Get a specific agent
trend_agent = get_agent("trend_analyst")
```

### Analysis Agents

```python
from app.agents import get_analysis_agents

# Get all analysis agents
analysis_agents = get_analysis_agents()

trend_agent = analysis_agents.get("trend_analyst")
business_agent = analysis_agents.get("business_impact_analyst")
competitive_agent = analysis_agents.get("competitive_analyst")
```

### Document Processing Agents

```python
from app.agents import get_document_processing_agents

doc_agents = get_document_processing_agents()
rfp_processor = doc_agents.get("rfp_processor")
```

### Workflow Integration

```python
from agno.workflow.v2 import Workflow, Step, Parallel
from app.agents import get_analysis_agents

analysis_agents = get_analysis_agents()

workflow = Workflow(
    name="Feature Analysis",
    steps=[
        Parallel(
            Step(name="trend", agent=analysis_agents["trend_analyst"]),
            Step(name="business", agent=analysis_agents["business_impact_analyst"]),
            Step(name="competitive", agent=analysis_agents["competitive_analyst"])
        )
    ]
)
```

## Available Agents

### Core Platform Agents
- `onelens_assistant` - Main OneLens AI Assistant

### Analysis Agents
- `trend_analyst` - Market trend analysis
- `business_impact_analyst` - Business impact analysis
- `competitive_analyst` - Competitive intelligence
- `market_opportunity_analyst` - Market opportunity analysis
- `geographic_analyst` - Geographic market analysis
- `priority_calculator` - Priority scoring calculation

### Document Processing Agents
- `document_parser` - General document parsing
- `rfp_processor` - RFP document processing
- `embedding_generator` - Embedding generation

### Utility Agents
- `similarity_matcher` - Content similarity matching
- `database_updater` - Database update operations

## API Functions

- `get_agent(name: str)` - Get a specific agent by name
- `get_onelens_assistant()` - Get the main assistant agent
- `get_analysis_agents()` - Get all analysis agents
- `get_document_processing_agents()` - Get all document processing agents
- `list_all_agents()` - List all available agent names

## Migration from Scattered Agents

Replace individual agent definitions with imports from this module:

```python
# Before
from agno.agent import Agent
from agno.models.openai import OpenAIChat

trend_agent = Agent(
    name="Trend Analyst",
    model=OpenAIChat(id="gpt-4o-mini"),
    instructions=[...]
)

# After
from app.agents import get_agent

trend_agent = get_agent("trend_analyst")
```
