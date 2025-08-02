from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
import logging

from app.core.database import get_db
from app.models import Epic, Feature, User, FeatureRequest
from app.schemas.epic import (
    EpicCreate,
    EpicUpdate,
    EpicResponse,
    EpicWithFeatures,
    EpicListResponse,
    EpicSummary
)
from app.schemas.feature import FeatureCreateInEpic, FeatureResponse
from app.schemas.base import PaginationParams
from app.models.enums import EpicStatus

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=EpicResponse, status_code=status.HTTP_201_CREATED)
async def create_epic(
    epic_data: EpicCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new epic"""
    # TODO: Get current user from auth
    # For now, set created_by to None until user authentication is implemented

    epic = Epic(
        **epic_data.model_dump(),
        created_by=None  # Set to None instead of placeholder UUID
    )

    db.add(epic)
    await db.commit()
    await db.refresh(epic)
    
    # Convert to response with features_count
    epic_dict = {
        "id": epic.id,
        "title": epic.title,
        "description": epic.description,
        "business_justification": epic.business_justification,
        "status": epic.status,
        "created_at": epic.created_at,
        "updated_at": epic.updated_at,
        "created_by": epic.created_by,
        "assigned_to": epic.assigned_to,
        "features_count": 0  # New epic has no features
    }

    return EpicResponse(**epic_dict)

@router.get("/", response_model=EpicListResponse)
async def list_epics(
    pagination: PaginationParams = Depends(),
    status: Optional[EpicStatus] = None,
    search: Optional[str] = None,
    created_by: Optional[UUID] = None,
    assigned_to: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """List epics with filtering and pagination"""
    # Create a subquery for feature counts
    feature_count_subquery = (
        select(Feature.epic_id, func.count(Feature.id).label("feature_count"))
        .group_by(Feature.epic_id)
        .subquery()
    )
    
    # Main query with feature count
    query = (
        select(
            Epic,
            func.coalesce(feature_count_subquery.c.feature_count, 0).label("features_count")
        )
        .outerjoin(feature_count_subquery, Epic.id == feature_count_subquery.c.epic_id)
    )
    
    # Apply filters
    if status:
        query = query.where(Epic.status == status)
    if created_by:
        query = query.where(Epic.created_by == created_by)
    if assigned_to:
        query = query.where(Epic.assigned_to == assigned_to)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Epic.title.ilike(search_term),
                Epic.description.ilike(search_term),
                Epic.business_justification.ilike(search_term)
            )
        )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination
    query = query.offset(pagination.skip).limit(pagination.limit)
    query = query.order_by(Epic.created_at.desc())
    
    # Execute query
    result = await db.execute(query)
    rows = result.all()
    
    # Process results to include feature count
    epics_with_counts = []
    for row in rows:
        epic = row[0]
        epic_dict = {
            "id": epic.id,
            "title": epic.title,
            "description": epic.description,
            "business_justification": epic.business_justification,
            "status": epic.status,
            "created_at": epic.created_at,
            "updated_at": epic.updated_at,
            "created_by": epic.created_by,
            "assigned_to": epic.assigned_to,
            "features_count": row[1]  # feature count from the query
        }
        epics_with_counts.append(EpicResponse(**epic_dict))
    
    return EpicListResponse(
        items=epics_with_counts,
        total=total,
        page=pagination.page,
        size=pagination.limit,
        pages=(total + pagination.limit - 1) // pagination.limit
    )

@router.get("/{epic_id}", response_model=EpicWithFeatures)
async def get_epic(
    epic_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get an epic by ID with its features"""
    query = select(Epic).where(Epic.id == epic_id)
    result = await db.execute(query)
    epic = result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    # Get features count
    features_query = select(func.count()).select_from(Feature).where(Feature.epic_id == epic_id)
    features_count = await db.scalar(features_query)
    
    # Convert to response model
    epic_dict = {
        "id": epic.id,
        "title": epic.title,
        "description": epic.description,
        "business_justification": epic.business_justification,
        "status": epic.status,
        "created_at": epic.created_at,
        "updated_at": epic.updated_at,
        "created_by": epic.created_by,
        "assigned_to": epic.assigned_to,
        "features": [],  # Will be populated separately if needed
        "features_count": features_count
    }
    
    return EpicWithFeatures(**epic_dict)

@router.put("/{epic_id}", response_model=EpicResponse)
async def update_epic(
    epic_id: UUID,
    epic_update: EpicUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an epic"""
    query = select(Epic).where(Epic.id == epic_id)
    result = await db.execute(query)
    epic = result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    # Update fields
    update_data = epic_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(epic, field, value)
    
    await db.commit()
    await db.refresh(epic)
    
    # Get features count
    features_query = select(func.count()).select_from(Feature).where(Feature.epic_id == epic_id)
    features_count = await db.scalar(features_query)
    
    # Convert to response with features_count
    epic_dict = {
        "id": epic.id,
        "title": epic.title,
        "description": epic.description,
        "business_justification": epic.business_justification,
        "status": epic.status,
        "created_at": epic.created_at,
        "updated_at": epic.updated_at,
        "created_by": epic.created_by,
        "assigned_to": epic.assigned_to,
        "features_count": features_count
    }
    
    return EpicResponse(**epic_dict)

@router.delete("/{epic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_epic(
    epic_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an epic and all its features"""
    query = select(Epic).where(Epic.id == epic_id)
    result = await db.execute(query)
    epic = result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    await db.delete(epic)
    await db.commit()

@router.post("/{epic_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
async def trigger_epic_analysis(
    epic_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Trigger analysis for all features in an epic"""
    query = select(Epic).where(Epic.id == epic_id)
    result = await db.execute(query)
    epic = result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    # Integrate with Agno workflow
    from app.services.agno_service import get_agno_service_v2
    agno_service = get_agno_service_v2()
    
    # Get all features for this epic
    features_query = select(Feature).where(Feature.epic_id == epic_id)
    features_result = await db.execute(features_query)
    features = features_result.scalars().all()
    
    if not features:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Epic has no features to analyze"
        )
    
    # Prepare epic and features data
    epic_data = {
        "id": str(epic_id),
        "title": epic.title,
        "description": epic.description or ""
    }

    features_data = []
    for feature in features:
        feature_dict = {
            "id": str(feature.id),
            "title": feature.title,
            "description": feature.description or ""
        }
        
        # Get customer requests for business impact
        requests_query = select(FeatureRequest).where(FeatureRequest.feature_id == feature.id)
        requests_result = await db.execute(requests_query)
        feature_requests = requests_result.scalars().all()
        
        feature_dict["customer_requests"] = [
            {
                "customer_id": str(req.customer_id),
                "urgency": req.urgency.value,
                "estimated_deal_impact": req.estimated_deal_impact
            }
            for req in feature_requests
        ]
        
        features_data.append(feature_dict)
    
    try:
        # Update epic status
        epic.status = EpicStatus.ANALYSIS_PENDING
        await db.commit()
        
        # Run the analysis workflow
        result = await agno_service.analyze_epic(
            epic_id=epic_data["id"],
            epic_data=epic_data,
            features_data=features_data,
            db_session=db
        )
        
        if result["status"] == "completed":
            # Update epic status to analyzed
            epic.status = EpicStatus.ANALYZED
            await db.commit()
            
            return {
                "message": "Analysis completed successfully",
                "epic_id": epic_id,
                "status": "completed",
                "features_analyzed": result["features_analyzed"],
                "results": result.get("results", [])
            }
        else:
            # Update epic status back to draft on failure
            epic.status = EpicStatus.DRAFT
            await db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Analysis failed: {result.get('error', 'Unknown error')}"
            )
            
    except Exception as e:
        # Log the error but don't expose internal details
        logger.error(f"Failed to run epic analysis workflow: {str(e)}")
        
        # Update epic status back to draft on error
        epic.status = EpicStatus.DRAFT
        await db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis service temporarily unavailable"
        )

@router.post("/{epic_id}/features", response_model=FeatureResponse, status_code=status.HTTP_201_CREATED)
async def create_feature_in_epic(
    epic_id: UUID,
    feature_data: FeatureCreateInEpic,
    db: AsyncSession = Depends(get_db)
):
    """Create a new feature within this epic"""
    # Import here to avoid circular imports
    from app.schemas.feature import FeatureResponse
    
    # Verify epic exists
    query = select(Epic).where(Epic.id == epic_id)
    result = await db.execute(query)
    epic = result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    # Create normalized text
    normalized_text = f"{feature_data.title} {feature_data.description or ''}".lower()
    
    # Create the feature with the epic_id
    feature = Feature(
        epic_id=epic_id,
        title=feature_data.title,
        description=feature_data.description,
        normalized_text=normalized_text,
        customer_request_count=0
    )
    
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    
    return FeatureResponse(
        id=feature.id,
        epic_id=feature.epic_id,
        title=feature.title,
        description=feature.description,
        normalized_text=feature.normalized_text,
        customer_request_count=feature.customer_request_count,
        created_at=feature.created_at,
        updated_at=feature.updated_at
    )

@router.get("/{epic_id}/features", response_model=List[FeatureResponse])
async def get_epic_features(
    epic_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all features for this epic"""
    from app.schemas.feature import FeatureResponse
    
    # Verify epic exists
    epic_query = select(Epic).where(Epic.id == epic_id)
    epic_result = await db.execute(epic_query)
    epic = epic_result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    # Get all features for this epic
    features_query = select(Feature).where(Feature.epic_id == epic_id).order_by(Feature.created_at.desc())
    features_result = await db.execute(features_query)
    features = features_result.scalars().all()
    
    return [
        FeatureResponse(
            id=feature.id,
            epic_id=feature.epic_id,
            title=feature.title,
            description=feature.description,
            normalized_text=feature.normalized_text,
            customer_request_count=feature.customer_request_count,
            created_at=feature.created_at,
            updated_at=feature.updated_at
        )
        for feature in features
    ]

@router.get("/{epic_id}/analysis/results")
async def get_epic_analysis_results(
    epic_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get the analysis results for all features in an epic"""
    # Verify epic exists
    query = select(Epic).where(Epic.id == epic_id)
    result = await db.execute(query)
    epic = result.scalar_one_or_none()
    
    if not epic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Epic not found"
        )
    
    # Get all features for this epic
    features_query = select(Feature).where(Feature.epic_id == epic_id)
    features_result = await db.execute(features_query)
    features = features_result.scalars().all()
    
    # Collect analysis results for each feature
    features_with_analysis = []

    for feature in features:
        feature_results = {
            "feature_id": str(feature.id),
            "title": feature.title,
            "description": feature.description,
            "analyses": {}
        }

        # Get analysis report from FeatureAnalysisReport table
        from app.models import FeatureAnalysisReport
        report_query = select(FeatureAnalysisReport).where(
            FeatureAnalysisReport.feature_id == feature.id
        ).order_by(FeatureAnalysisReport.created_at.desc()).limit(1)
        report_result = await db.execute(report_query)
        analysis_report = report_result.scalar_one_or_none()

        if analysis_report:
            feature_results["priority_score"] = float(analysis_report.priority_score) if analysis_report.priority_score else 0
            feature_results["analyses"]["report"] = {
                # Core scores
                "priority_score": float(analysis_report.priority_score) if analysis_report.priority_score else None,
                "business_impact_score": analysis_report.business_impact_score,
                
                # Trend Analysis
                "trend_alignment_status": analysis_report.trend_alignment_status,
                "trend_keywords": analysis_report.trend_keywords or [],
                "trend_justification": analysis_report.trend_justification,
                
                # Business Impact
                "revenue_potential": analysis_report.revenue_potential.value if analysis_report.revenue_potential else None,
                "user_adoption_forecast": analysis_report.user_adoption_forecast.value if analysis_report.user_adoption_forecast else None,
                
                # Market Opportunity
                "market_opportunity_score": float(analysis_report.market_opportunity_score) if analysis_report.market_opportunity_score else None,
                "total_competitors_analyzed": analysis_report.total_competitors_analyzed,
                "competitors_providing_count": analysis_report.competitors_providing_count,
                
                # Geographic Insights
                "geographic_insights": analysis_report.geographic_insights,
                
                # Competitive Analysis
                "competitor_pros_cons": analysis_report.competitor_pros_cons,
                "competitive_positioning": analysis_report.competitive_positioning,
                
                # Metadata
                "generated_by_workflow": analysis_report.generated_by_workflow,
                "created_at": analysis_report.created_at.isoformat() if analysis_report.created_at else None,
                "updated_at": analysis_report.updated_at.isoformat() if analysis_report.updated_at else None
            }
        else:
            feature_results["priority_score"] = 0

        features_with_analysis.append(feature_results)
    
    # Sort features by priority score (highest first)
    features_with_analysis.sort(
        key=lambda x: x.get("priority_score", 0),
        reverse=True
    )
    
    return {
        "epic_id": epic_id,
        "epic_title": epic.title,
        "epic_status": epic.status.value,
        "features_count": len(features),
        "features": features_with_analysis
    }

@router.get("/summary/by-status", response_model=List[EpicSummary])
async def get_epics_summary_by_status(
    db: AsyncSession = Depends(get_db)
):
    """Get summary of epics grouped by status"""
    query = select(
        Epic.status,
        func.count(Epic.id).label("count")
    ).group_by(Epic.status)
    
    result = await db.execute(query)
    summaries = []
    
    for row in result:
        summaries.append(EpicSummary(
            status=row.status,
            count=row.count
        ))
    
    return summaries