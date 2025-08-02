import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EpicStatus


@pytest.mark.asyncio
async def test_trigger_feature_analysis(client, db_session: AsyncSession, test_epic, test_feature):
    """Test triggering feature analysis via API"""
    feature_id = test_feature.id
    
    with patch("app.api.v1.features.agno_service") as mock_agno:
        mock_agno.prepare_feature_analysis_config.return_value = {
            "feature_id": 123,
            "analysis_types": ["trend_analysis", "business_impact"]
        }
        mock_agno.trigger_workflow = AsyncMock(return_value={
            "execution_id": "test-execution-123",
            "status": "running"
        })
        
        response = await client.post(
            f"/api/v1/features/{feature_id}/analyze",
            json={
                "analysis_types": ["trend_analysis", "business_impact"]
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["message"] == "Feature analysis triggered successfully"
        assert data["feature_id"] == str(feature_id)
        assert data["workflow_execution_id"] == "test-execution-123"
        assert "trend_analysis" in data["analysis_types"]
        assert "business_impact" in data["analysis_types"]
        
        # Verify workflow was triggered
        mock_agno.trigger_workflow.assert_called_once_with(
            workflow_name="feature_analysis",
            workflow_config={
                "feature_id": 123,
                "analysis_types": ["trend_analysis", "business_impact"]
            }
        )


@pytest.mark.asyncio
async def test_trigger_feature_analysis_all_types(client, db_session: AsyncSession, test_epic, test_feature):
    """Test triggering feature analysis with all analysis types when none specified"""
    feature_id = test_feature.id
    
    with patch("app.api.v1.features.agno_service") as mock_agno:
        mock_agno.prepare_feature_analysis_config.return_value = {
            "feature_id": 123,
            "analysis_types": [
                "trend_analysis",
                "business_impact", 
                "competitive_analysis",
                "geographic_analysis",
                "priority_scoring"
            ]
        }
        mock_agno.trigger_workflow = AsyncMock(return_value={
            "execution_id": "test-execution-456",
            "status": "running"
        })
        
        response = await client.post(
            f"/api/v1/features/{feature_id}/analyze",
            json={}  # No analysis_types specified
        )
        
        assert response.status_code == 202
        data = response.json()
        assert len(data["analysis_types"]) == 5  # All types included


@pytest.mark.asyncio
async def test_trigger_feature_analysis_service_unavailable(client, db_session: AsyncSession, test_epic, test_feature):
    """Test feature analysis when Agno service is unavailable"""
    feature_id = test_feature.id
    
    with patch("app.api.v1.features.agno_service") as mock_agno:
        mock_agno.prepare_feature_analysis_config.return_value = {"test": "config"}
        mock_agno.trigger_workflow = AsyncMock(side_effect=Exception("Connection failed"))
        
        response = await client.post(
            f"/api/v1/features/{feature_id}/analyze",
            json={"analysis_types": ["trend_analysis"]}
        )
        
        assert response.status_code == 503
        assert response.json()["detail"] == "Analysis service temporarily unavailable"


@pytest.mark.asyncio
async def test_trigger_epic_analysis(client, db_session: AsyncSession, test_epic, test_feature):
    """Test triggering epic analysis via API"""
    epic_id = test_epic.id
    
    with patch("app.api.v1.epics.agno_service") as mock_agno:
        mock_agno.prepare_epic_analysis_config.return_value = {
            "epic_id": 456,
            "feature_ids": [123]
        }
        mock_agno.trigger_workflow = AsyncMock(return_value={
            "execution_id": "test-epic-execution-789",
            "status": "running"
        })
        
        response = await client.post(f"/api/v1/epics/{epic_id}/analyze")
        
        assert response.status_code == 202
        data = response.json()
        assert data["message"] == "Analysis triggered successfully"
        assert data["epic_id"] == str(epic_id)
        assert data["workflow_execution_id"] == "test-epic-execution-789"
        assert data["feature_count"] == 1
        
        # Verify epic status was updated
        await db_session.refresh(test_epic)
        assert test_epic.status == EpicStatus.ANALYSIS_PENDING
        
        # Verify workflow was triggered
        mock_agno.trigger_workflow.assert_called_once_with(
            workflow_name="epic_complete_analysis",
            workflow_config={
                "epic_id": 456,
                "feature_ids": [123]
            }
        )


@pytest.mark.asyncio
async def test_trigger_epic_analysis_no_features(client, db_session: AsyncSession):
    """Test triggering epic analysis when epic has no features"""
    from app.models import Epic
    
    # Create epic without features
    epic = Epic(
        title="Empty Epic",
        description="No features",
        status=EpicStatus.DRAFT
    )
    db_session.add(epic)
    await db_session.commit()
    
    response = await client.post(f"/api/v1/epics/{epic.id}/analyze")
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Epic has no features to analyze"


@pytest.mark.asyncio
async def test_get_feature_analysis_status(client, db_session: AsyncSession, test_epic, test_feature):
    """Test getting feature analysis workflow status"""
    feature_id = test_feature.id
    execution_id = "test-execution-123"
    
    with patch("app.api.v1.features.agno_service") as mock_agno:
        mock_agno.get_workflow_status = AsyncMock(return_value={
            "status": "completed",
            "execution_id": execution_id,
            "completed_at": "2024-01-01T00:00:00"
        })
        
        response = await client.get(
            f"/api/v1/features/{feature_id}/analysis/status",
            params={"execution_id": execution_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["feature_id"] == str(feature_id)
        assert data["execution_id"] == execution_id
        assert data["status"] == "completed"
        assert data["details"]["completed_at"] == "2024-01-01T00:00:00"
        
        mock_agno.get_workflow_status.assert_called_once_with(execution_id)


@pytest.mark.asyncio
async def test_get_epic_analysis_status(client, db_session: AsyncSession, test_epic):
    """Test getting epic analysis workflow status"""
    epic_id = test_epic.id
    execution_id = "test-epic-execution-789"
    
    with patch("app.api.v1.epics.agno_service") as mock_agno:
        mock_agno.get_workflow_status = AsyncMock(return_value={
            "status": "running",
            "execution_id": execution_id,
            "progress": 50
        })
        
        response = await client.get(
            f"/api/v1/epics/{epic_id}/analysis/status",
            params={"execution_id": execution_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["epic_id"] == str(epic_id)
        assert data["execution_id"] == execution_id
        assert data["status"] == "running"
        assert data["details"]["progress"] == 50
        
        mock_agno.get_workflow_status.assert_called_once_with(execution_id)