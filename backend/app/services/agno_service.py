from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
import logging
from pydantic import BaseModel, Field

from agno.workflow.v2 import Workflow, Step, Parallel
from agno.storage.sqlite import SqliteStorage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.agents import get_analysis_agents, get_agent
from app.models import (
    Feature, Epic, TrendAnalysis, BusinessImpactAnalysis,
    MarketOpportunityAnalysis, GeographicAnalysis, PriorityScore,
    FeatureAnalysisReport
)

logger = logging.getLogger(__name__)


class TrendAnalysisResult(BaseModel):
    """Trend analysis result with all required fields"""
    feature_id: str = Field(description="The feature ID being analyzed")
    analysis_type: str = Field(default="trend", description="Type of analysis")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the analysis")
    trend_keywords: List[str] = Field(description="Key trend keywords identified")
    alignment_score: float = Field(ge=0.0, le=1.0, description="How well aligned with trends (0-1)")
    emerging_trends: List[str] = Field(description="Emerging trends related to this feature")
    findings: Dict[str, Any] = Field(description="Detailed findings from the analysis")
    recommendations: List[str] = Field(description="Recommendations based on trends")


class BusinessImpactAnalysisResult(BaseModel):
    """Business impact analysis result"""
    feature_id: str = Field(description="The feature ID being analyzed")
    analysis_type: str = Field(default="business_impact", description="Type of analysis")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the analysis")
    impact_score: float = Field(ge=0.0, le=100.0, description="Business impact score (0-100)")
    revenue_impact: str = Field(description="Expected revenue impact (High/Medium/Low)")
    user_adoption_score: float = Field(ge=0.0, le=100.0, description="Expected user adoption score")
    customer_segments: List[str] = Field(description="Customer segments that will benefit")
    findings: Dict[str, Any] = Field(description="Detailed business impact findings")
    recommendations: List[str] = Field(description="Business recommendations")


class CompetitiveAnalysisResult(BaseModel):
    """Competitive analysis result"""
    feature_id: str = Field(description="The feature ID being analyzed")
    analysis_type: str = Field(default="competitive", description="Type of analysis")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the analysis")
    competitors: List[Dict[str, Any]] = Field(description="List of competitors analyzed")
    market_gaps: List[str] = Field(description="Identified market gaps")
    competitive_advantage: List[str] = Field(description="Our competitive advantages")
    opportunity_score: float = Field(ge=0.0, le=10.0, description="Market opportunity score")
    findings: Dict[str, Any] = Field(description="Detailed competitive findings")
    recommendations: List[str] = Field(description="Competitive strategy recommendations")


class GeographicAnalysisResult(BaseModel):
    """Geographic analysis result"""
    feature_id: str = Field(description="The feature ID being analyzed")
    analysis_type: str = Field(default="geographic", description="Type of analysis")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the analysis")
    regions: List[Dict[str, Any]] = Field(description="Analysis by geographic region")
    market_opportunities: List[str] = Field(description="Geographic market opportunities")
    regulatory_factors: List[str] = Field(description="Regulatory considerations by region")
    findings: Dict[str, Any] = Field(description="Detailed geographic findings")
    recommendations: List[str] = Field(description="Geographic expansion recommendations")


class PriorityScoreResult(BaseModel):
    """Priority scoring result"""
    feature_id: str = Field(description="The feature ID being analyzed")
    analysis_type: str = Field(default="priority", description="Type of analysis")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the scoring")
    priority_score: float = Field(ge=0.0, le=100.0, description="Overall priority score (0-100)")
    score_breakdown: Dict[str, float] = Field(description="Breakdown of score components")
    ranking_factors: List[str] = Field(description="Key factors affecting the ranking")
    findings: Dict[str, Any] = Field(description="Detailed priority findings")
    recommendations: List[str] = Field(description="Priority-based recommendations")


class AgnoWorkflowServiceV2:
    """Improved Agno workflow service with proper structured outputs"""
    
    def __init__(self):
        self.storage = SqliteStorage(
            table_name="agno_workflows_v2",
            db_file="tmp/agno_workflows_v2.db",
            mode="workflow_v2"
        )
        self._initialize_agents()
        self._initialize_workflows()
    
    def _initialize_agents(self):
        """Initialize Agno agents from centralized definitions"""
        try:
            analysis_agents = get_analysis_agents()

            self.trend_agent = analysis_agents.get("trend_analyst")
            self.business_impact_agent = analysis_agents.get("business_impact_analyst")
            self.competitive_agent = analysis_agents.get("competitive_analyst")
            self.geographic_agent = analysis_agents.get("geographic_analyst")
            self.priority_agent = analysis_agents.get("priority_calculator")

            # Verify all agents were loaded
            missing_agents = []
            for name, agent in [
                ("trend_analyst", self.trend_agent),
                ("business_impact_analyst", self.business_impact_agent),
                ("competitive_analyst", self.competitive_agent),
                ("geographic_analyst", self.geographic_agent),
                ("priority_calculator", self.priority_agent)
            ]:
                if agent is None:
                    missing_agents.append(name)

            if missing_agents:
                logger.error(f"Failed to load agents: {missing_agents}")
                raise ValueError(f"Failed to load agents: {missing_agents}")

            logger.info("All agents successfully initialized from centralized definitions")

        except Exception as e:
            logger.error(f"Error initializing agents: {str(e)}", exc_info=True)
            raise

    def _initialize_workflows(self):
        """Initialize workflow definitions"""
        
        # Define workflow steps
        self.trend_step = Step(
            name="trend_analysis",
            description="Analyze market trends for the feature",
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
            description="Calculate final priority score",
            agent=self.priority_agent
        )
    
    def create_feature_workflow(self, analysis_types: List[str]) -> Workflow:
        """Create a workflow for feature analysis"""
        
        steps = []
        
        # Add parallel analysis steps
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
            description="Comprehensive feature analysis",
            steps=steps,
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

        print(f"=== STARTING ANALYZE_FEATURE for {feature_id} ===")
        print(f"Analysis types: {analysis_types}")
        logger.info(f"=== STARTING ANALYZE_FEATURE for {feature_id} ===")
        logger.info(f"Analysis types: {analysis_types}")

        try:
            # Create workflow
            workflow = self.create_feature_workflow(analysis_types)
            
            # Prepare message with feature context
            message = f"""
Analyze this feature:
- Feature ID: {feature_id}
- Title: {feature_data.get('title', '')}
- Description: {feature_data.get('description', '')}
- Customer Requests: {len(feature_data.get('customer_requests', []))} requests

Customer request details:
{feature_data.get('customer_requests', [])}

IMPORTANT: Always include feature_id="{feature_id}" in your response.
"""
            
            logger.info(f"Starting feature analysis for {feature_id}")
            
            # Run workflow
            print(f"=== RUNNING WORKFLOW ===")
            logger.info(f"=== RUNNING WORKFLOW ===")
            response = workflow.run(message=message, stream=False)
            print(f"=== WORKFLOW COMPLETED ===")
            logger.info(f"=== WORKFLOW COMPLETED ===")
            print(f"Response type: {type(response)}")
            logger.info(f"Response type: {type(response)}")
            print(f"Response attributes: {dir(response)}")
            logger.info(f"Response attributes: {dir(response)}")

            # Process results
            print(f"=== CALLING _process_workflow_results ===")
            logger.info(f"=== CALLING _process_workflow_results ===")
            results = await self._process_workflow_results(
                response, feature_id, analysis_types, db_session
            )
            print(f"=== _process_workflow_results COMPLETED ===")
            logger.info(f"=== _process_workflow_results COMPLETED ===")
            print(f"Results: {results}")
            logger.info(f"Results: {results}")
            
            return {
                "status": "completed",
                "feature_id": feature_id,
                "analyses_completed": analysis_types,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error in feature analysis: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "feature_id": feature_id,
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

        # Initialize data containers
        trend_data = None
        business_data = None
        competitive_data = None
        geographic_data = None
        priority_data = None

        print(f"=== PROCESSING WORKFLOW RESULTS for feature {feature_id} ===")
        logger.info(f"=== PROCESSING WORKFLOW RESULTS for feature {feature_id} ===")
        print(f"Response type: {type(response)}")
        logger.info(f"Response type: {type(response)}")
        print(f"Response repr: {repr(response)[:500]}...")
        logger.info(f"Response repr: {repr(response)[:500]}...")

        # Check step_responses for parallel results
        if hasattr(response, 'step_responses'):
            print(f"Found step_responses: {len(response.step_responses)} responses")
            logger.info(f"Found step_responses: {len(response.step_responses)} responses")
            for i, step_response in enumerate(response.step_responses):
                print(f"Step {i}: {type(step_response)} - {repr(step_response)[:200]}...")
                logger.info(f"Step {i}: {type(step_response)} - {repr(step_response)[:200]}...")

                # Process each step response
                if hasattr(step_response, 'content'):
                    if hasattr(step_response.content, 'model_dump'):
                        # Structured content (like PriorityScoreResult)
                        data = step_response.content.model_dump()
                        print(f"Step {i} structured data: {data}")
                        logger.info(f"Step {i} structured data: {data}")
                        trend_data, business_data, competitive_data, geographic_data, priority_data = self._categorize_data(
                            data, trend_data, business_data, competitive_data,
                            geographic_data, priority_data
                        )
                    elif isinstance(step_response.content, str) and "SUCCESS:" in step_response.content:
                        # Parallel execution results (formatted string)
                        print(f"Step {i} contains parallel results - parsing...")
                        logger.info(f"Step {i} contains parallel results - parsing...")

                        # Parse the parallel results string to extract individual agent data
                        parallel_content = step_response.content
                        print(f"Parallel content preview: {parallel_content[:500]}...")
                        logger.info(f"Parallel content preview: {parallel_content[:500]}...")

                        # Try to extract structured data from the parallel results
                        # The content should contain individual agent results
                        import re

                        # Look for patterns like "SUCCESS: trend_analysis" followed by structured data
                        success_patterns = re.findall(r'SUCCESS: (\w+)\n(.*?)(?=SUCCESS:|$)', parallel_content, re.DOTALL)

                        for analysis_type, result_content in success_patterns:
                            print(f"Found {analysis_type} result: {result_content[:200]}...")
                            logger.info(f"Found {analysis_type} result: {result_content[:200]}...")

                            # Try to parse the Python object representation
                            try:
                                # The content is in Python object representation format
                                # Convert it to a dictionary by parsing the key=value pairs

                                # Extract key=value pairs from the result content
                                import ast

                                # Try to parse as Python literal (for simple cases)
                                try:
                                    # Look for patterns like "key='value'" or "key=value"
                                    data = {}

                                    # Extract feature_id
                                    feature_id_match = re.search(r"feature_id='([^']+)'", result_content)
                                    if feature_id_match:
                                        data['feature_id'] = feature_id_match.group(1)

                                    # Extract analysis_type
                                    analysis_type_match = re.search(r"analysis_type='([^']+)'", result_content)
                                    if analysis_type_match:
                                        data['analysis_type'] = analysis_type_match.group(1)

                                    # Extract confidence_score
                                    confidence_match = re.search(r"confidence_score=([0-9.]+)", result_content)
                                    if confidence_match:
                                        data['confidence_score'] = float(confidence_match.group(1))

                                    # Extract specific fields based on analysis type
                                    if analysis_type == 'trend_analysis':
                                        # Extract trend-specific fields
                                        alignment_match = re.search(r"alignment_score=([0-9.]+)", result_content)
                                        if alignment_match:
                                            data['alignment_score'] = float(alignment_match.group(1))

                                        # Extract trend_keywords (list)
                                        keywords_match = re.search(r"trend_keywords=\[([^\]]+)\]", result_content)
                                        if keywords_match:
                                            keywords_str = keywords_match.group(1)
                                            # Parse the list of quoted strings
                                            keywords = [k.strip().strip("'\"") for k in keywords_str.split(',')]
                                            data['trend_keywords'] = keywords

                                    elif analysis_type == 'business_impact':
                                        # Extract business-specific fields
                                        impact_match = re.search(r"impact_score=([0-9.]+)", result_content)
                                        if impact_match:
                                            data['impact_score'] = float(impact_match.group(1))

                                        revenue_match = re.search(r"revenue_impact='([^']+)'", result_content)
                                        if revenue_match:
                                            data['revenue_impact'] = revenue_match.group(1)

                                        adoption_match = re.search(r"user_adoption_score=([0-9.]+)", result_content)
                                        if adoption_match:
                                            data['user_adoption_score'] = float(adoption_match.group(1))

                                    elif analysis_type == 'competitive_analysis':
                                        # Extract competitive-specific fields
                                        opportunity_match = re.search(r"opportunity_score=([0-9.]+)", result_content)
                                        if opportunity_match:
                                            data['opportunity_score'] = float(opportunity_match.group(1))

                                    elif analysis_type == 'geographic_analysis':
                                        # Extract geographic-specific fields
                                        opportunities_match = re.search(r"market_opportunities=\[([^\]]+)\]", result_content)
                                        if opportunities_match:
                                            data['market_opportunities'] = opportunities_match.group(1).split(',')

                                    if data:
                                        print(f"Parsed {analysis_type} data: {data}")
                                        logger.info(f"Parsed {analysis_type} data: {data}")

                                        # Categorize the parsed data
                                        trend_data, business_data, competitive_data, geographic_data, priority_data = self._categorize_data(
                                            data, trend_data, business_data, competitive_data,
                                            geographic_data, priority_data
                                        )
                                    else:
                                        print(f"No data extracted for {analysis_type}")
                                        logger.warning(f"No data extracted for {analysis_type}")

                                except Exception as parse_error:
                                    print(f"Error parsing {analysis_type} object representation: {parse_error}")
                                    logger.error(f"Error parsing {analysis_type} object representation: {parse_error}")

                            except Exception as e:
                                print(f"Error processing {analysis_type} results: {e}")
                                logger.error(f"Error processing {analysis_type} results: {e}")
        else:
            print("No step_responses found")
            logger.info("No step_responses found")



        # Process the response based on its structure
        if hasattr(response, '__dict__'):
            logger.info(f"Response attributes: {list(response.__dict__.keys())}")

        # Try to extract structured data from the response
        if hasattr(response, 'content'):
            logger.info(f"Found response.content: {type(response.content)}")
            # Single agent response
            content = response.content
            if hasattr(content, 'model_dump'):
                logger.info(f"Content has model_dump method")
                data = content.model_dump()
                logger.info(f"Model dump data: {data}")
                trend_data, business_data, competitive_data, geographic_data, priority_data = self._categorize_data(
                    data, trend_data, business_data, competitive_data,
                    geographic_data, priority_data
                )
            else:
                logger.info(f"Content does not have model_dump method: {type(content)}")
                logger.info(f"Content repr: {repr(content)[:500]}...")
        
        # For workflow responses, check for steps or messages
        if hasattr(response, 'steps'):
            logger.info(f"Found response.steps: {len(response.steps)} steps")
            for step in response.steps:
                logger.info(f"Processing step: {getattr(step, 'name', 'unknown')}")
                if hasattr(step, 'output') and hasattr(step.output, 'content'):
                    content = step.output.content
                    if hasattr(content, 'model_dump'):
                        data = content.model_dump()
                        logger.info(f"Step data: {data}")
                        trend_data, business_data, competitive_data, geographic_data, priority_data = self._categorize_data(
                            data, trend_data, business_data, competitive_data,
                            geographic_data, priority_data
                        )

        # Check for step_responses (parallel execution results)
        elif hasattr(response, 'step_responses'):
            logger.info(f"Found step_responses: {len(response.step_responses)} responses")
            for step_response in response.step_responses:
                step_name = getattr(step_response, 'step_name', 'unknown')
                logger.info(f"Processing step response: {step_name}")
                if hasattr(step_response, 'content') and hasattr(step_response.content, 'model_dump'):
                    data = step_response.content.model_dump()
                    logger.info(f"Step response data: {data}")
                    trend_data, business_data, competitive_data, geographic_data, priority_data = self._categorize_data(
                        data, trend_data, business_data, competitive_data,
                        geographic_data, priority_data
                    )
                elif hasattr(step_response, 'content'):
                    logger.info(f"Step response content (no model_dump): {type(step_response.content)}")
                    logger.info(f"Content: {repr(step_response.content)[:300]}...")

        # Check for step_results (from parallel workflow events)
        elif hasattr(response, 'step_results'):
            logger.info(f"Found step_results: {len(response.step_results)} results")
            for step_result in response.step_results:
                step_name = getattr(step_result, 'step_name', 'unknown')
                logger.info(f"Processing step result: {step_name}")
                if hasattr(step_result, 'content') and hasattr(step_result.content, 'model_dump'):
                    data = step_result.content.model_dump()
                    logger.info(f"Step result data: {data}")
                    trend_data, business_data, competitive_data, geographic_data, priority_data = self._categorize_data(
                        data, trend_data, business_data, competitive_data,
                        geographic_data, priority_data
                    )
                elif hasattr(step_result, 'content'):
                    logger.info(f"Step result content (no model_dump): {type(step_result.content)}")
                    logger.info(f"Content: {repr(step_result.content)[:300]}...")

        else:
            logger.warning(f"No recognizable workflow structure found")
            logger.warning(f"Response type: {type(response)}")
            logger.warning(f"Response attributes: {dir(response)}")
        
        # Store the analysis results
        return await self._store_analysis_results(
            feature_id, trend_data, business_data, competitive_data,
            geographic_data, priority_data, db_session
        )
    
    def _categorize_data(self, data, trend_data, business_data, competitive_data, 
                        geographic_data, priority_data):
        """Categorize data based on analysis type"""
        analysis_type = data.get('analysis_type', '')
        
        if analysis_type == 'trend':
            return data, business_data, competitive_data, geographic_data, priority_data
        elif analysis_type == 'business_impact':
            return trend_data, data, competitive_data, geographic_data, priority_data
        elif analysis_type == 'competitive':
            return trend_data, business_data, data, geographic_data, priority_data
        elif analysis_type == 'geographic':
            return trend_data, business_data, competitive_data, data, priority_data
        elif analysis_type == 'priority':
            return trend_data, business_data, competitive_data, geographic_data, data
        
        return trend_data, business_data, competitive_data, geographic_data, priority_data
    
    async def analyze_epic(
        self,
        epic_id: str,
        epic_data: Dict[str, Any],
        features_data: List[Dict[str, Any]],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """Analyze all features in an epic"""
        
        try:
            results = []
            for feature_data in features_data:
                feature_id = feature_data["id"]
                
                # Run analysis for each feature
                result = await self.analyze_feature(
                    feature_id=feature_id,
                    feature_data=feature_data,
                    analysis_types=[
                        "trend_analysis",
                        "business_impact",
                        "competitive_analysis",
                        "geographic_analysis",
                        "priority_scoring"
                    ],
                    db_session=db_session
                )
                
                results.append(result)
            
            # Count successful analyses
            successful = sum(1 for r in results if r.get("status") == "completed")
            
            return {
                "status": "completed",
                "epic_id": epic_id,
                "features_analyzed": len(features_data),
                "successful_analyses": successful,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error in epic analysis: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "epic_id": epic_id,
                "error": str(e)
            }
    
    async def _store_analysis_results(
        self, feature_id, trend_data, business_data, competitive_data,
        geographic_data, priority_data, db_session
    ) -> Dict[str, Any]:
        """Store analysis results in database"""
        
        from app.models import FeatureAnalysisReport
        from app.models.enums import ImpactLevel
        
        try:
            # Helper function to determine impact level
            def get_impact_level(score):
                if score >= 70:
                    return ImpactLevel.HIGH
                elif score >= 40:
                    return ImpactLevel.MEDIUM
                else:
                    return ImpactLevel.LOW
            
            # Process geographic insights
            geographic_insights = None
            if geographic_data and 'regions' in geographic_data:
                geographic_insights = {
                    "top_markets": geographic_data['regions'][:5],
                    "total_market_size": sum(r.get('market_size', 0) for r in geographic_data['regions']),
                    "regulatory_considerations": geographic_data.get('regulatory_factors', [])
                }
            
            # Process competitor pros/cons
            competitor_pros_cons = None
            if competitive_data and 'competitors' in competitive_data:
                competitor_pros_cons = {
                    "main_competitors": competitive_data['competitors'][:3],
                    "market_gaps": competitive_data.get('market_gaps', []),
                    "competitive_advantages": competitive_data.get('competitive_advantage', [])
                }
            
            # Create analysis report
            from uuid import UUID
            analysis_report = FeatureAnalysisReport(
                feature_id=UUID(feature_id) if isinstance(feature_id, str) else feature_id,
                
                # Trend Analysis
                trend_alignment_status=bool(trend_data and trend_data.get('alignment_score', 0) > 0.5),
                trend_keywords=trend_data.get('trend_keywords', []) if trend_data else [],
                trend_justification=str(trend_data.get('findings', {})) if trend_data else None,
                
                # Business Impact
                business_impact_score=int(business_data.get('impact_score', 0)) if business_data else None,
                revenue_potential=get_impact_level(business_data.get('impact_score', 0)) if business_data else None,
                user_adoption_forecast=get_impact_level(
                    business_data.get('user_adoption_score', 50)
                ) if business_data else None,
                
                # Market Opportunity
                total_competitors_analyzed=len(competitive_data.get('competitors', [])) if competitive_data else 0,
                competitors_providing_count=sum(
                    1 for c in competitive_data.get('competitors', [])
                    if c.get('has_feature', False)
                ) if competitive_data else 0,
                market_opportunity_score=float(
                    competitive_data.get('opportunity_score', 0)
                ) if competitive_data else None,
                
                # Geographic Insights
                geographic_insights=geographic_insights,
                
                # Competitive Analysis
                competitor_pros_cons=competitor_pros_cons,
                competitive_positioning=str(competitive_data.get('findings', {})) if competitive_data else None,
                
                # Priority Score
                priority_score=float(priority_data.get('priority_score', 0)) if priority_data else None,
                
                generated_by_workflow="agno_analysis_v3"
            )
            
            db_session.add(analysis_report)
            await db_session.commit()
            
            logger.info(f"Stored analysis report for feature {feature_id}")
            
            return {
                "feature_id": feature_id,
                "stored": True,
                "has_trend_data": trend_data is not None,
                "has_business_data": business_data is not None,
                "has_competitive_data": competitive_data is not None,
                "has_geographic_data": geographic_data is not None,
                "has_priority_data": priority_data is not None
            }
            
        except Exception as e:
            logger.error(f"Failed to store analysis results: {e}", exc_info=True)
            await db_session.rollback()
            return {
                "feature_id": feature_id,
                "stored": False,
                "error": str(e)
            }


# Singleton instance - lazy initialization to avoid import-time errors
agno_service_v2 = None

def get_agno_service_v2() -> AgnoWorkflowServiceV2:
    """Get the singleton AgnoWorkflowServiceV2 instance"""
    global agno_service_v2
    if agno_service_v2 is None:
        agno_service_v2 = AgnoWorkflowServiceV2()
    return agno_service_v2