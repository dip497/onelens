from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.models import Epic, Feature, User
from app.schemas.epic import (
    EpicCreate,
    EpicUpdate,
    EpicResponse,
    EpicWithFeatures,
    EpicListResponse,
    EpicSummary
)
from app.schemas.base import PaginationParams
from app.models.enums import EpicStatus

router = APIRouter()

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
    
    # TODO: Integrate with Agno workflow
    # await agno_service.trigger_workflow("epic_complete_analysis", {"epic_id": epic_id})
    
    # Update epic status
    epic.status = EpicStatus.ANALYSIS_PENDING
    await db.commit()
    
    return {
        "message": "Analysis triggered successfully",
        "epic_id": epic_id,
        "status": "pending"
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