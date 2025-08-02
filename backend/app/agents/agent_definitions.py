"""
Centralized Agent Definitions for OneLens Platform

This file contains all agent configurations and definitions used across the OneLens platform.
Import agents from this file to ensure consistency across the application.
"""

from typing import Dict, Any, List, Optional
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from app.tools import search_knowledge_base
from app.core.config import settings


class AgentRegistry:
    """Central registry for all OneLens agents"""
    
    def __init__(self):
        self._agents: Dict[str, Agent] = {}
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize all agents"""
        self._agents.update({
            # Core Platform Agents
            "onelens_assistant": self._create_onelens_assistant(),
            
            # Analysis Agents
            "trend_analyst": self._create_trend_analyst(),
            "business_impact_analyst": self._create_business_impact_analyst(),
            "competitive_analyst": self._create_competitive_analyst(),
            "market_opportunity_analyst": self._create_market_opportunity_analyst(),
            "geographic_analyst": self._create_geographic_analyst(),
            "priority_calculator": self._create_priority_calculator(),
            
            # Document Processing Agents
            "document_parser": self._create_document_parser(),
            "rfp_processor": self._create_rfp_processor(),
            "embedding_generator": self._create_embedding_generator(),
            
            # Utility Agents
            "similarity_matcher": self._create_similarity_matcher(),
            "database_updater": self._create_database_updater(),
        })
    
    def get_agent(self, name: str) -> Optional[Agent]:
        """Get an agent by name"""
        return self._agents.get(name)
    
    def list_agents(self) -> List[str]:
        """List all available agent names"""
        return list(self._agents.keys())
    
    def get_all_agents(self) -> Dict[str, Agent]:
        """Get all agents"""
        return self._agents.copy()
    
    # Core Platform Agents
    def _create_onelens_assistant(self) -> Agent:
        """OneLens AI Assistant for general platform help"""
        return Agent(
            name="OneLens Assistant",
            tools=[search_knowledge_base],
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=[
                "You are OneLens AI Assistant, a helpful AI assistant for the OneLens platform.",
                "OneLens is a comprehensive product management and analysis platform.",
                "You can help users with:",
                "- Epic and feature management",
                "- Product analysis and insights", 
                "- Competitor analysis",
                "- Customer insights",
                "- General product management questions",
                "Be friendly, helpful, and provide actionable insights.",
                "When discussing features or epics, consider their business impact and user value.",
                "Keep responses concise but informative.",
            ],
            add_datetime_to_instructions=True,
            markdown=True,
        )
    
    # Analysis Agents
    def _create_trend_analyst(self) -> Agent:
        """Market trend analysis agent"""
        return Agent(
            name="Trend Analyst",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            tools=[DuckDuckGoTools()],
            instructions=[
                "You are a market trend analyst for the OneLens platform.",
                "Your role is to analyze if product features align with current technology and business trends.",
                "For each feature, you should:",
                "1. Research current market trends relevant to the feature",
                "2. Identify key trend keywords and technologies", 
                "3. Assess alignment with future market direction",
                "4. Provide confidence score for your assessment",
                "Focus on trends from the last 12 months and emerging technologies.",
                "Provide structured analysis with trend_score (1-10), alignment_keywords, and market_direction.",
                "Consider technology adoption curves and business transformation trends.",
            ]
        )
    
    def _create_business_impact_analyst(self) -> Agent:
        """Business impact analysis agent"""
        return Agent(
            name="Business Impact Analyst",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            instructions=[
                "You are a business impact analyst for the OneLens platform.",
                "Analyze the business value and impact of product features.",
                "Focus on:",
                "1. Revenue potential and impact",
                "2. Customer adoption likelihood",
                "3. Implementation complexity vs. value",
                "4. Strategic business alignment",
                "5. Risk assessment",
                "Provide impact_score (1-10), revenue_impact assessment, and customer_segments analysis.",
                "Consider: Enterprise=10x weight, Large=5x, Medium=2.5x, Small=1x.",
                "Include detailed business recommendations and ROI considerations.",
            ]
        )
    
    def _create_competitive_analyst(self) -> Agent:
        """Competitive intelligence analyst"""
        return Agent(
            name="Competitive Intelligence Analyst", 
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            tools=[DuckDuckGoTools()],
            instructions=[
                "You are a competitive intelligence analyst for the OneLens platform.",
                "Research competitor feature offerings and market positioning.",
                "For each feature, analyze:",
                "1. Which competitors offer similar features",
                "2. Strengths and weaknesses of competitor implementations",
                "3. Market gaps and opportunities", 
                "4. Competitive advantages we can leverage",
                "Focus on direct competitors and market leaders.",
                "Provide competitive_score (1-10), market_gaps list, and strategic recommendations.",
                "Include detailed competitor analysis and differentiation opportunities.",
            ]
        )
    
    def _create_market_opportunity_analyst(self) -> Agent:
        """Market opportunity analysis agent"""
        return Agent(
            name="Market Opportunity Analyst",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            tools=[DuckDuckGoTools()],
            instructions=[
                "You are a market opportunity analyst for the OneLens platform.",
                "Assess market size and competitive landscape by geography.",
                "Focus on these top 5 business countries:",
                "- United States",
                "- United Kingdom", 
                "- Germany",
                "- Japan",
                "- Australia",
                "For each country, analyze:",
                "1. Market size and growth potential",
                "2. Competitor presence and market share",
                "3. Regulatory factors",
                "4. Cultural adoption factors", 
                "5. Overall opportunity rating",
                "Provide opportunity_score (1-10) and geographic_insights.",
            ]
        )
    
    def _create_geographic_analyst(self) -> Agent:
        """Geographic market analysis agent"""
        return Agent(
            name="Geographic Market Analyst",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            tools=[DuckDuckGoTools()],
            instructions=[
                "You are a geographic market analyst for the OneLens platform.",
                "Analyze market opportunities across different geographic regions.",
                "Focus on market penetration, regulatory environment, and cultural factors.",
                "Provide detailed geographic analysis with market_size, growth_rate, and opportunity_rating.",
                "Consider local competition, regulatory requirements, and market maturity.",
                "Include recommendations for market entry strategies.",
            ]
        )
    
    def _create_priority_calculator(self) -> Agent:
        """Priority scoring calculation agent"""
        return Agent(
            name="Priority Calculator",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            instructions=[
                "You are a priority scoring engine for the OneLens platform.",
                "Calculate feature priority based on multiple weighted factors:",
                "- Customer Impact (30%): Weighted by segment (Enterprise=10x, Large=5x, Medium=2.5x, Small=1x)",
                "- Trend Alignment (20%): Based on trend analysis score",
                "- Business Impact (25%): Revenue potential and strategic value",
                "- Market Opportunity (20%): Competitive gap analysis",
                "- Segment Diversity (5%): Cross-segment appeal",
                "Provide detailed score breakdown and justification.",
                "Calculate final priority_score (1-100) with component scores.",
                "Include actionable recommendations based on priority analysis.",
            ]
        )

    # Document Processing Agents
    def _create_document_parser(self) -> Agent:
        """Document parsing agent for various file formats"""
        return Agent(
            name="Document Parser",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            instructions=[
                "You are a document parsing specialist for the Motadata platform.",
                "Extract structured information from various document formats (PDF, DOCX, TXT).",
                "Focus on:",
                "1. Identifying document structure and sections",
                "2. Extracting key information and metadata",
                "3. Converting unstructured text to structured data",
                "4. Maintaining document context and relationships",
                "Provide clean, structured output suitable for further processing.",
                "Handle various document types: RFPs, requirements docs, specifications.",
            ]
        )

    def _create_rfp_processor(self) -> Agent:
        """RFP document processing agent"""
        return Agent(
            name="RFP Processor",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            tools=[search_knowledge_base],
            instructions=[
                "You are an RFP processing specialist for the OneLens platform.",
                "Process RFP documents and generate responses based on company knowledge.",
                "For each RFP question:",
                "1. Parse and understand the question requirements",
                "2. Search company knowledge base for relevant information",
                "3. Generate appropriate yes/no responses with justification",
                "4. Identify missing capabilities or gaps",
                "5. Provide confidence scores for responses",
                "Focus on accuracy and compliance with RFP requirements.",
                "Use search_document tool to find relevant company capabilities.",
            ]
        )

    def _create_embedding_generator(self) -> Agent:
        """Embedding generation agent for semantic search"""
        return Agent(
            name="Embedding Generator",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            instructions=[
                "You are an embedding generation specialist for the OneLens platform.",
                "Generate high-quality embeddings for semantic search and similarity matching.",
                "Process text content to create meaningful vector representations.",
                "Focus on:",
                "1. Text preprocessing and normalization",
                "2. Semantic meaning preservation",
                "3. Optimal embedding dimensions",
                "4. Batch processing efficiency",
                "Ensure embeddings capture semantic relationships for accurate matching.",
            ]
        )

    # Utility Agents
    def _create_similarity_matcher(self) -> Agent:
        """Similarity matching agent for content comparison"""
        return Agent(
            name="Similarity Matcher",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            instructions=[
                "You are a similarity matching specialist for the OneLens platform.",
                "Compare and match content based on semantic similarity.",
                "Use embedding vectors and similarity algorithms to:",
                "1. Find similar features and requirements",
                "2. Match RFP questions to existing capabilities",
                "3. Identify duplicate or related content",
                "4. Provide similarity scores and confidence levels",
                "Apply configurable similarity thresholds (default: 0.85).",
                "Return ranked matches with detailed similarity analysis.",
            ]
        )

    def _create_database_updater(self) -> Agent:
        """Database update agent for data persistence"""
        return Agent(
            name="Database Updater",
            model=OpenAIChat(id="gpt-4o-mini", max_retries=3, timeout=60.0),
            instructions=[
                "You are a database update specialist for the OneLens platform.",
                "Handle data persistence and database operations safely.",
                "Focus on:",
                "1. Updating feature request counts and metrics",
                "2. Maintaining data consistency and integrity",
                "3. Handling concurrent updates safely",
                "4. Logging all database changes",
                "5. Validating data before persistence",
                "Ensure all updates follow platform data models and constraints.",
                "Provide detailed update summaries and error handling.",
            ]
        )


# Global agent registry instance
agent_registry = AgentRegistry()


# Convenience functions for easy access
def get_agent(name: str) -> Optional[Agent]:
    """Get an agent by name"""
    return agent_registry.get_agent(name)


def get_onelens_assistant() -> Agent:
    """Get the main OneLens assistant agent"""
    return agent_registry.get_agent("onelens_assistant")


def get_analysis_agents() -> Dict[str, Agent]:
    """Get all analysis agents"""
    analysis_agent_names = [
        "trend_analyst", "business_impact_analyst", "competitive_analyst",
        "market_opportunity_analyst", "geographic_analyst", "priority_calculator"
    ]
    return {name: agent_registry.get_agent(name) for name in analysis_agent_names}


def get_document_processing_agents() -> Dict[str, Agent]:
    """Get all document processing agents"""
    doc_agent_names = ["document_parser", "rfp_processor", "embedding_generator"]
    return {name: agent_registry.get_agent(name) for name in doc_agent_names}


def list_all_agents() -> List[str]:
    """List all available agent names"""
    return agent_registry.list_agents()
