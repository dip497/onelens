from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
import logging
from pydantic import BaseModel, Field, ConfigDict

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.workflow.v2 import Workflow, Step, Parallel, Condition
from agno.workflow.v2.types import StepInput
from agno.storage.sqlite import SqliteStorage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models import (
    Feature, Epic, TrendAnalysis, BusinessImpactAnalysis,
    MarketOpportunityAnalysis, GeographicAnalysis, PriorityScore,
    FeatureAnalysisReport
)

logger = logging.getLogger(__name__)


class AnalysisResult(BaseModel):
    """Base model for analysis results"""
    feature_id: int
    analysis_type: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    findings: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)


class TrendAnalysisResult(AnalysisResult):
    """Trend analysis specific result"""
    trend_keywords: List[str] = Field(default_factory=list)
    alignment_score: float
    emerging_trends: List[str] = Field(default_factory=list)


class CompetitiveAnalysisResult(AnalysisResult):
    """Competitive analysis specific result"""
    competitors: List[Dict[str, Any]] = Field(default_factory=list)
    market_gaps: List[str] = Field(default_factory=list)
    competitive_advantage: List[str] = Field(default_factory=list)


class BusinessImpactAnalysisResult(AnalysisResult):
    """Business impact analysis specific result"""
    impact_score: float = Field(..., ge=0.0, le=100.0)
    revenue_impact: str
    customer_segments: List[str] = Field(default_factory=list)


class GeographicAnalysisResult(AnalysisResult):
    """Geographic analysis specific result"""
    regions: List[Dict[str, Any]] = Field(default_factory=list)
    market_opportunities: List[str] = Field(default_factory=list)
    regulatory_factors: List[str] = Field(default_factory=list)


class PriorityScoreResult(AnalysisResult):
    """Priority scoring specific result"""
    priority_score: float = Field(..., ge=0.0, le=100.0)
    score_breakdown: Dict[str, float]
    ranking_factors: List[str]


class AgnoWorkflowService:
    """Service for managing Agno workflows using the Python library directly"""
    
    def __init__(self):
        self.storage = SqliteStorage(
            table_name="agno_workflows",
            db_file="tmp/agno_workflows.db",
            mode="workflow_v2"
        )
        self._initialize_agents()
        self._initialize_workflows()
    
    def _initialize_agents(self):
        """Initialize Agno agents for different analysis types"""
        
        # Trend Analysis Agent
        self.trend_agent = Agent(
            name="Trend Analyst",
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=[DuckDuckGoTools()],
            instructions=[
                "You are a market trend analyst for the Epic Analysis System.",
                "Your role is to analyze if product features align with current technology and business trends.",
                "For each feature, you should:",
                "1. Research current market trends relevant to the feature",
                "2. Identify key trend keywords and technologies",
                "3. Assess alignment with future market direction",
                "4. Provide confidence score (0.0-1.0) for your assessment",
                "Focus on trends from the last 12 months and emerging technologies.",
                "Always provide all required fields in your response."
            ],
            response_model=TrendAnalysisResult
        )
        
        # Business Impact Agent
        self.business_impact_agent = Agent(
            name="Business Impact Analyst",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=[
                "You are a business impact analyst for the Epic Analysis System.",
                "Calculate the business impact based on customer requests and ARR.",
                "Consider:",
                "1. Number of customer requests",
                "2. Customer segment weights (Enterprise=10x, Large=5x, Medium=2.5x, Small=1x)",
                "3. Total ARR impact",
                "4. Deal urgency factors",
                "Provide detailed financial impact analysis.",
                "Always provide all required fields in your response."
            ],
            response_model=BusinessImpactAnalysisResult
        )
        
        # Competitive Analysis Agent
        self.competitive_agent = Agent(
            name="Competitive Intelligence Analyst",
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=[DuckDuckGoTools()],
            instructions=[
                "You are a competitive intelligence analyst for the Epic Analysis System.",
                "Your role is to research competitor feature offerings and market positioning.",
                "For each feature, you should:",
                "1. Identify which competitors offer similar features",
                "2. Analyze strengths and weaknesses of competitor implementations",
                "3. Assess market gaps and opportunities",
                "4. Provide detailed pros/cons analysis",
                "Focus on direct competitors and market leaders in the space.",
                "Return your analysis in JSON format with these exact fields:",
                "- feature_id: integer",
                "- analysis_type: 'competitive'",
                "- confidence_score: float (0.0-1.0)",
                "- findings: object with key insights",
                "- recommendations: array of strings",
                "- competitors: array of competitor objects",
                "- market_gaps: array of strings",
                "- competitive_advantage: array of strings"
            ]
        )
        
        # Geographic Analysis Agent
        self.geographic_agent = Agent(
            name="Geographic Market Analyst",
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=[DuckDuckGoTools()],
            instructions=[
                "You are a market opportunity analyst focusing on geographic markets.",
                "Analyze market opportunities in these top 5 business countries:",
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
                "Always provide all required fields in your response."
            ],
            response_model=GeographicAnalysisResult
        )

        # Priority Scoring Agent
        self.priority_agent = Agent(
            name="Priority Calculator",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=[
                "You are a priority scoring engine for the Epic Analysis System.",
                "Calculate feature priority based on multiple weighted factors:",
                "- Customer Impact (30%): Weighted by segment",
                "- Trend Alignment (20%): Based on trend analysis score",
                "- Business Impact (25%): Revenue potential and strategic value",
                "- Market Opportunity (20%): Competitive gap analysis",
                "- Segment Diversity (5%): Cross-segment appeal",
                "Provide detailed score breakdown and justification.",
                "Return your analysis in JSON format with these exact fields:",
                "- feature_id: integer",
                "- analysis_type: 'priority'",
                "- confidence_score: float (0.0-1.0)",
                "- findings: object with key insights",
                "- recommendations: array of strings",
                "- priority_score: float (0.0-100.0)",
                "- score_breakdown: object with component scores",
                "- ranking_factors: array of strings"
            ]
        )
    
    def _initialize_workflows(self):
        """Initialize workflow definitions"""
        
        # Define workflow steps
        self.trend_step = Step(
            name="trend_analysis",
            description="Analyze market trends",
            agent=self.trend_agent
        )
        
        self.business_step = Step(
            name="business_impact",
            description="Calculate business impact",
            agent=self.business_impact_agent
        )
        
        self.competitive_step = Step(
            name="competitive_analysis",
            description="Analyze competitive landscape",
            agent=self.competitive_agent
        )
        
        self.geographic_step = Step(
            name="geographic_analysis",
            description="Analyze geographic markets",
            agent=self.geographic_agent
        )
        
        self.priority_step = Step(
            name="priority_scoring",
            description="Calculate priority score",
            agent=self.priority_agent
        )
    
    def create_feature_workflow(self, analysis_types: List[str]) -> Workflow:
        """Create a workflow for feature analysis based on selected types"""
        
        steps = []
        
        # Add parallel analysis steps based on requested types
        parallel_steps = []
        
        if "trend_analysis" in analysis_types:
            parallel_steps.append(self.trend_step)
        
        if "business_impact" in analysis_types:
            parallel_steps.append(self.business_step)
        
        if "competitive_analysis" in analysis_types:
            parallel_steps.append(self.competitive_step)
        
        if "geographic_analysis" in analysis_types:
            parallel_steps.append(self.geographic_step)
        
        if parallel_steps:
            steps.append(Parallel(
                *parallel_steps,
                name="Parallel Analysis",
                description="Run multiple analyses in parallel"
            ))
        
        # Add priority scoring if requested
        if "priority_scoring" in analysis_types:
            steps.append(self.priority_step)
        
        return Workflow(
            name="Feature Analysis Workflow",
            description="Analyze individual features",
            steps=steps,
            storage=self.storage
        )
    
    def create_epic_workflow(self) -> Workflow:
        """Create a workflow for complete epic analysis"""
        
        return Workflow(
            name="Epic Complete Analysis",
            description="Analyze all features in an epic",
            steps=[
                Parallel(
                    self.trend_step,
                    self.business_step,
                    self.competitive_step,
                    self.geographic_step,
                    name="Comprehensive Analysis",
                    description="Run all analyses in parallel"
                ),
                self.priority_step
            ],
            storage=self.storage
        )
    
    async def analyze_feature(
        self,
        feature_id: str,
        feature_data: Dict[str, Any],
        analysis_types: List[str],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """Run feature analysis workflow"""
        
        try:
            # Create workflow for requested analysis types
            workflow = self.create_feature_workflow(analysis_types)
            
            # Prepare context data
            context = {
                "feature_id": feature_id,
                "title": feature_data.get("title", ""),
                "description": feature_data.get("description", ""),
                "customer_requests": feature_data.get("customer_requests", []),
                "epic_context": feature_data.get("epic_context", {})
            }
            
            # Run workflow
            logger.info(f"Starting feature analysis for feature {feature_id}")
            
            # Run the workflow (Agno handles the execution)
            response = workflow.run(
                message=f"Analyze feature: {context['title']}. Description: {context['description']}",
                stream=False
            )
            
            # Process and store results
            results = await self._process_workflow_results(
                response, feature_id, analysis_types, db_session
            )
            
            return {
                "status": "completed",
                "feature_id": feature_id,
                "analyses_completed": analysis_types,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error in feature analysis workflow: {str(e)}")
            return {
                "status": "failed",
                "feature_id": feature_id,
                "error": str(e)
            }
    
    async def analyze_epic(
        self,
        epic_id: str,
        epic_data: Dict[str, Any],
        features_data: List[Dict[str, Any]],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """Run epic analysis workflow"""
        
        try:
            # Create epic workflow
            workflow = self.create_epic_workflow()
            
            # Prepare context
            context = {
                "epic_id": epic_id,
                "title": epic_data.get("title", ""),
                "description": epic_data.get("description", ""),
                "features": features_data
            }
            
            logger.info(f"Starting epic analysis for epic {epic_id} with {len(features_data)} features")
            
            # Run workflow for each feature
            all_results = []
            for feature in features_data:
                response = workflow.run(
                    message=f"Analyze feature '{feature['title']}' in epic '{context['title']}'. "
                           f"Feature description: {feature.get('description', '')}",
                    stream=False
                )
                
                results = await self._process_workflow_results(
                    response, feature["id"], 
                    ["trend_analysis", "business_impact", "competitive_analysis", 
                     "geographic_analysis", "priority_scoring"],
                    db_session
                )
                all_results.append(results)
            
            return {
                "status": "completed",
                "epic_id": epic_id,
                "features_analyzed": len(features_data),
                "results": all_results
            }
            
        except Exception as e:
            logger.error(f"Error in epic analysis workflow: {str(e)}")
            return {
                "status": "failed",
                "epic_id": epic_id,
                "error": str(e)
            }
    
    async def _process_workflow_results(
        self,
        response: Any,
        feature_id: str,
        analysis_types: List[str],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """Process workflow results and store in database"""

        results = {}
        stored_analyses = []

        logger.info(f"Processing results for feature {feature_id}")
        logger.info(f"Workflow response type: {type(response)}")

        # Extract content from WorkflowRunResponse
        content = ""
        if hasattr(response, 'content'):
            content = response.content
        elif isinstance(response, str):
            content = response
        else:
            content = str(response)

        logger.info(f"Extracted content: {content[:200]}...")

        # Parse JSON from content if it contains JSON
        import json
        import re

        # Look for JSON blocks in the content
        json_pattern = r'```json
\s*(\{.*?\})\s*
```'
        json_matches = re.findall(json_pattern, content, re.DOTALL)

        if json_matches:
            try:
                # Parse the first JSON block found
                analysis_data = json.loads(json_matches[0])
                logger.info(f"Parsed analysis data: {analysis_data}")

                # Store basic analysis result
                from app.models import FeatureAnalysisReport

                analysis_report = FeatureAnalysisReport(
                    feature_id=feature_id,
                    trend_alignment_status=analysis_data.get('analysis_type') == 'trend',
                    trend_keywords=analysis_data.get('trend_keywords', []),
                    trend_justification=str(analysis_data.get('findings', {})),
                    business_impact_score=int(analysis_data.get('impact_score', 0)) if analysis_data.get('impact_score') else None,
                    priority_score=float(analysis_data.get('priority_score', 0)) if analysis_data.get('priority_score') else None,
                    generated_by_workflow="agno_analysis_v1"
                )

                db_session.add(analysis_report)
                await db_session.commit()

                stored_analyses.append("feature_analysis_report")
                logger.info(f"Stored analysis report for feature {feature_id}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from analysis result: {e}")
            except Exception as e:
                logger.error(f"Failed to store analysis result: {e}")

        return {
            "feature_id": feature_id,
            "analyses_completed": analysis_types,
            "stored_analyses": stored_analyses,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workflow_response": content[:500] if content else None  # Truncate for logging
        }


# Singleton instance
agno_service = AgnoWorkflowService()

# Singleton instance
agno_service = AgnoWorkflowService()

# Singleton instance
agno_service = AgnoWorkflowService()

# Singleton instance
agno_service = AgnoWorkflowService()
                stored_analyses.append("feature_analysis_report")
                logger.info(f"Stored analysis report for feature {feature_id}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from analysis result: {e}")
            except Exception as e:
                logger.error(f"Failed to store analysis result: {e}")

        return {
            "feature_id": feature_id,
            "analyses_completed": analysis_types,
            "stored_analyses": stored_analyses,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workflow_response": content[:500] if content else None  # Truncate for logging
        }


# Singleton instance
agno_service = AgnoWorkflowService()        "feature_id": feature_id,
            "analyses_completed": analysis_types,
            "stored_analyses": stored_analyses,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workflow_response": content[:500] if content else None  # Truncate for logging
        }


# Singleton instance
agno_service = AgnoWorkflowService()