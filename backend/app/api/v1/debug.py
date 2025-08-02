from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.database import get_db
from app.services.agno_service import agno_service_v2 as agno_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/test-agno-agent")
async def test_agno_agent():
    """Test a single Agno agent to see what it returns"""
    
    # Test the trend agent directly
    trend_agent = agno_service.trend_agent
    
    try:
        # Run the agent with a simple test
        response = trend_agent.run(
            "Analyze the trend alignment for a feature: Multi-Factor Authentication (MFA) - Add support for SMS and TOTP-based MFA to enhance login security."
        )
        
        logger.info(f"Agent response type: {type(response)}")
        logger.info(f"Agent response: {response}")
        
        result = {
            "response_type": str(type(response)),
            "has_content": hasattr(response, 'content'),
            "has_messages": hasattr(response, 'messages'),
        }
        
        if hasattr(response, 'content'):
            result["content_type"] = str(type(response.content))
            result["content_value"] = str(response.content)[:500]
            
            # Check if content is a Pydantic model
            if hasattr(response.content, 'model_dump'):
                result["content_model_data"] = response.content.model_dump()
        
        if hasattr(response, 'messages'):
            result["messages_count"] = len(response.messages)
            result["messages"] = []
            for i, msg in enumerate(response.messages[:3]):  # First 3 messages
                msg_info = {
                    "index": i,
                    "type": str(type(msg)),
                    "has_content": hasattr(msg, 'content'),
                }
                if hasattr(msg, 'content'):
                    msg_info["content_type"] = str(type(msg.content))
                    msg_info["content_preview"] = str(msg.content)[:200]
                result["messages"].append(msg_info)
        
        return result
        
    except Exception as e:
        logger.error(f"Error testing agent: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "error_type": str(type(e))
        }

@router.post("/test-agno-workflow") 
async def test_agno_workflow(db: AsyncSession = Depends(get_db)):
    """Test the full Agno workflow to see what it returns"""
    
    # Test data
    test_feature = {
        "id": "test-feature-123",
        "title": "Multi-Factor Authentication (MFA)",
        "description": "Add support for SMS and TOTP-based MFA to enhance login security.",
        "customer_requests": [
            {
                "customer_id": "cust-1",
                "urgency": "HIGH",
                "estimated_deal_impact": 50000
            },
            {
                "customer_id": "cust-2", 
                "urgency": "CRITICAL",
                "estimated_deal_impact": 100000
            }
        ]
    }
    
    try:
        # Create and run a simple workflow
        workflow = agno_service.create_feature_workflow(["trend_analysis", "business_impact"])
        
        # Run the workflow
        response = workflow.run(
            message=f"Analyze feature: {test_feature['title']}. Description: {test_feature['description']}. Customer requests: {test_feature['customer_requests']}",
            stream=False
        )
        
        logger.info(f"Workflow response type: {type(response)}")
        
        result = {
            "response_type": str(type(response)),
            "has_content": hasattr(response, 'content'),
            "has_messages": hasattr(response, 'messages'),
            "response_attrs": dir(response) if response else []
        }
        
        if hasattr(response, 'content'):
            result["content_type"] = str(type(response.content))
            result["content_value"] = str(response.content)[:1000]
        
        if hasattr(response, 'messages'):
            result["messages_count"] = len(response.messages)
            result["messages"] = []
            for i, msg in enumerate(response.messages):
                msg_info = {
                    "index": i,
                    "type": str(type(msg)),
                    "attrs": [attr for attr in dir(msg) if not attr.startswith('_')][:10]
                }
                if hasattr(msg, 'content'):
                    msg_info["content_type"] = str(type(msg.content))
                    msg_info["content_preview"] = str(msg.content)[:500]
                result["messages"].append(msg_info)
        
        return result
        
    except Exception as e:
        logger.error(f"Error testing workflow: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "error_type": str(type(e)),
            "traceback": str(e.__traceback__) if hasattr(e, '__traceback__') else None
        }