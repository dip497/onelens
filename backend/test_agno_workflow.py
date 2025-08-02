#!/usr/bin/env python3
"""
Test script to verify Agno workflow execution
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set OpenAI API key
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.workflow.v2 import Workflow, Step, Parallel
from agno.storage.sqlite import SqliteStorage


def test_simple_workflow():
    """Test a simple Agno workflow"""
    
    print("Testing Agno Workflow Execution...")
    print("=" * 50)
    
    # Create a simple agent
    analyzer = Agent(
        name="Feature Analyzer",
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=[
            "You are analyzing a software feature.",
            "Provide a brief analysis of the feature's potential impact.",
            "Be concise and focus on key points."
        ]
    )
    
    # Create a step
    analysis_step = Step(
        name="analyze",
        description="Analyze the feature",
        agent=analyzer
    )
    
    # Create workflow
    workflow = Workflow(
        name="Test Feature Analysis",
        description="Simple test workflow",
        steps=[analysis_step],
        storage=SqliteStorage(
            table_name="test_workflows",
            db_file="tmp/test_workflows.db",
            mode="workflow_v2"
        )
    )
    
    # Test feature
    test_feature = {
        "title": "Dark Mode Support",
        "description": "Add dark mode theme support to the application UI"
    }
    
    print(f"\nAnalyzing feature: {test_feature['title']}")
    print(f"Description: {test_feature['description']}")
    print("\n" + "-" * 50 + "\n")
    
    try:
        # Run the workflow
        response = workflow.run(
            message=f"Analyze this feature: {test_feature['title']}. {test_feature['description']}",
            stream=False
        )
        
        print("Analysis Result:")
        print(response)
        print("\n✅ Workflow executed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error running workflow: {str(e)}")
        import traceback
        traceback.print_exc()


def test_parallel_workflow():
    """Test a parallel workflow with multiple agents"""
    
    print("\n\nTesting Parallel Workflow Execution...")
    print("=" * 50)
    
    # Create multiple agents
    trend_agent = Agent(
        name="Trend Analyst",
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=["Analyze if this feature aligns with current tech trends."]
    )
    
    impact_agent = Agent(
        name="Impact Analyst", 
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=["Analyze the business impact of this feature."]
    )
    
    # Create steps
    trend_step = Step(name="trend", agent=trend_agent)
    impact_step = Step(name="impact", agent=impact_agent)
    
    # Create workflow with parallel execution
    workflow = Workflow(
        name="Parallel Analysis",
        description="Run multiple analyses in parallel",
        steps=[
            Parallel(
                trend_step,
                impact_step,
                name="Parallel Analysis",
                description="Analyze trends and impact simultaneously"
            )
        ],
        storage=SqliteStorage(
            table_name="test_parallel",
            db_file="tmp/test_parallel.db",
            mode="workflow_v2"
        )
    )
    
    test_feature = {
        "title": "AI-Powered Search",
        "description": "Implement semantic search using AI embeddings"
    }
    
    print(f"\nAnalyzing feature: {test_feature['title']}")
    print(f"Description: {test_feature['description']}")
    print("\n" + "-" * 50 + "\n")
    
    try:
        # Run the workflow
        response = workflow.run(
            message=f"Analyze: {test_feature['title']} - {test_feature['description']}",
            stream=False
        )
        
        print("Parallel Analysis Results:")
        print(response)
        print("\n✅ Parallel workflow executed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error running parallel workflow: {str(e)}")
        import traceback
        traceback.print_exc()


async def test_async_workflow():
    """Test async workflow execution"""
    
    print("\n\nTesting Async Workflow Execution...")
    print("=" * 50)
    
    # Import our service
    from app.services.agno_service import agno_service_v2 as agno_service
    
    # Test data
    feature_data = {
        "id": 1,
        "title": "Real-time Collaboration",
        "description": "Enable multiple users to work on the same document simultaneously",
        "customer_requests": [
            {"customer_id": "123", "urgency": "HIGH", "estimated_deal_impact": 50000},
            {"customer_id": "456", "urgency": "MEDIUM", "estimated_deal_impact": 30000}
        ]
    }
    
    print(f"\nTesting with feature: {feature_data['title']}")
    print("\n" + "-" * 50 + "\n")
    
    try:
        # Create a simple workflow with just trend analysis
        workflow = agno_service.create_feature_workflow(["trend_analysis"])
        
        # Run it directly
        response = workflow.run(
            message=f"Analyze feature: {feature_data['title']}. {feature_data['description']}",
            stream=False
        )
        
        print("Service Workflow Result:")
        print(response)
        print("\n✅ Service workflow executed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error running service workflow: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Check if OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not found in environment variables!")
        print("Please set it in your .env file or environment")
        exit(1)
    
    print("🚀 Starting Agno Workflow Tests\n")
    
    # Run tests
    test_simple_workflow()
    test_parallel_workflow()
    
    # Run async test
    asyncio.run(test_async_workflow())
    
    print("\n\n✨ All tests completed!")