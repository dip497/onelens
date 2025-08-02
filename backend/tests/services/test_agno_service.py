import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.services.agno_service import AgnoService


@pytest.fixture
def agno_service():
    """Create an AgnoService instance for testing"""
    with patch("app.services.agno_service.settings") as mock_settings:
        mock_settings.AGNO_SERVICE_URL = "http://test-agno:8080"
        mock_settings.AGNO_API_KEY = "test-api-key"
        mock_settings.DATABASE_URL = "postgresql://test"
        service = AgnoService()
        return service


@pytest.mark.asyncio
async def test_trigger_workflow_success(agno_service):
    """Test successful workflow triggering"""
    execution_id = str(uuid4())
    workflow_config = {"test": "config"}
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "execution_id": execution_id,
            "status": "running"
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await agno_service.trigger_workflow(
            workflow_name="test_workflow",
            workflow_config=workflow_config,
            execution_id=execution_id
        )
        
        assert result["execution_id"] == execution_id
        assert result["status"] == "running"
        
        # Verify the request was made correctly
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://test-agno:8080/workflows/execute"
        assert call_args[1]["json"]["workflow_name"] == "test_workflow"
        assert call_args[1]["json"]["execution_id"] == execution_id
        assert call_args[1]["json"]["config"] == workflow_config
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-api-key"


@pytest.mark.asyncio
async def test_trigger_workflow_retry(agno_service):
    """Test workflow triggering with retry on server error"""
    workflow_config = {"test": "config"}
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        
        # First attempt fails with 503
        mock_response_1 = AsyncMock()
        mock_response_1.status_code = 503
        mock_response_1.raise_for_status.side_effect = Exception("Service unavailable")
        
        # Second attempt succeeds
        mock_response_2 = AsyncMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "execution_id": "test-id",
            "status": "running"
        }
        mock_response_2.raise_for_status = MagicMock()
        
        mock_client.post.side_effect = [mock_response_1, mock_response_2]
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        with patch("asyncio.sleep"):  # Mock sleep to speed up test
            result = await agno_service.trigger_workflow(
                workflow_name="test_workflow",
                workflow_config=workflow_config
            )
        
        assert result["status"] == "running"
        assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_trigger_workflow_bad_request(agno_service):
    """Test workflow triggering with bad request"""
    workflow_config = {"invalid": "config"}
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid workflow configuration"
        
        from httpx import HTTPStatusError, Request, Response
        http_response = Response(400, text="Invalid workflow configuration")
        mock_response.raise_for_status.side_effect = HTTPStatusError(
            "Client error",
            request=Request("POST", "http://test"),
            response=http_response
        )
        
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        with pytest.raises(ValueError, match="Invalid workflow configuration"):
            await agno_service.trigger_workflow(
                workflow_name="test_workflow",
                workflow_config=workflow_config
            )


@pytest.mark.asyncio
async def test_get_workflow_status_success(agno_service):
    """Test successful workflow status retrieval"""
    execution_id = str(uuid4())
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "execution_id": execution_id,
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat()
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await agno_service.get_workflow_status(execution_id)
        
        assert result["execution_id"] == execution_id
        assert result["status"] == "completed"
        
        # Verify the request
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == f"http://test-agno:8080/workflows/status/{execution_id}"


@pytest.mark.asyncio
async def test_get_workflow_status_not_found(agno_service):
    """Test workflow status retrieval when workflow not found"""
    execution_id = str(uuid4())
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 404
        
        from httpx import HTTPStatusError, Request, Response
        http_response = Response(404, text="Not found")
        mock_response.raise_for_status.side_effect = HTTPStatusError(
            "Not found",
            request=Request("GET", "http://test"),
            response=http_response
        )
        
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await agno_service.get_workflow_status(execution_id)
        
        assert result["status"] == "not_found"
        assert execution_id in result["message"]


@pytest.mark.asyncio
async def test_cancel_workflow_success(agno_service):
    """Test successful workflow cancellation"""
    execution_id = str(uuid4())
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "execution_id": execution_id,
            "status": "cancelled"
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        result = await agno_service.cancel_workflow(execution_id)
        
        assert result["status"] == "cancelled"
        
        # Verify the request
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == f"http://test-agno:8080/workflows/cancel/{execution_id}"


def test_prepare_feature_analysis_config(agno_service):
    """Test preparation of feature analysis configuration"""
    feature_id = 123
    analysis_types = ["trend_analysis", "business_impact"]
    user_id = 456
    
    config = agno_service.prepare_feature_analysis_config(
        feature_id=feature_id,
        analysis_types=analysis_types,
        user_id=user_id
    )
    
    assert config["feature_id"] == feature_id
    assert config["analysis_types"] == analysis_types
    assert config["user_id"] == user_id
    assert config["database_url"] == "postgresql://test"
    assert "timestamp" in config


def test_prepare_epic_analysis_config(agno_service):
    """Test preparation of epic analysis configuration"""
    epic_id = 789
    feature_ids = [123, 456, 789]
    user_id = 999
    
    config = agno_service.prepare_epic_analysis_config(
        epic_id=epic_id,
        feature_ids=feature_ids,
        user_id=user_id
    )
    
    assert config["epic_id"] == epic_id
    assert config["feature_ids"] == feature_ids
    assert config["user_id"] == user_id
    assert config["database_url"] == "postgresql://test"
    assert "timestamp" in config