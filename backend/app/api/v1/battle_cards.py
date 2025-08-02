from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import BattleCard, BattleCardSection, Product, Competitor, CompetitorScrapingJob
from app.schemas.product import (
    BattleCardCreate,
    BattleCardUpdate,
    BattleCardResponse,
    BattleCardGenerateRequest,
    CompetitorScrapingRequest,
    ScrapingJobResponse
)
from app.models.enums import BattleCardStatus, ScrapingJobStatus
from app.services.battle_card_generator import BattleCardGenerator
from app.services.competitor_scraper import CompetitorScraper

router = APIRouter(prefix="/battle-cards", tags=["battle-cards"])


@router.get("/", response_model=List[BattleCardResponse])
async def list_battle_cards(
    product_id: Optional[UUID] = None,
    competitor_id: Optional[UUID] = None,
    status: Optional[BattleCardStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all battle cards with optional filters"""
    query = select(BattleCard).options(
        selectinload(BattleCard.sections),
        selectinload(BattleCard.product),
        selectinload(BattleCard.competitor)
    )
    
    if product_id:
        query = query.where(BattleCard.product_id == product_id)
    if competitor_id:
        query = query.where(BattleCard.competitor_id == competitor_id)
    if status:
        query = query.where(BattleCard.status == status)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    battle_cards = result.scalars().all()
    
    # Add product and competitor names
    response_cards = []
    for card in battle_cards:
        card_dict = card.__dict__.copy()
        card_dict["product_name"] = card.product.name if card.product else None
        card_dict["competitor_name"] = card.competitor.name if card.competitor else None
        card_dict["sections"] = card.sections
        response_cards.append(BattleCardResponse(**card_dict))
    
    return response_cards


@router.post("/", response_model=BattleCardResponse, status_code=status.HTTP_201_CREATED)
async def create_battle_card(
    battle_card_data: BattleCardCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new battle card"""
    # Verify product and competitor exist
    product_result = await db.execute(
        select(Product).where(Product.id == battle_card_data.product_id)
    )
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {battle_card_data.product_id} not found"
        )
    
    competitor_result = await db.execute(
        select(Competitor).where(Competitor.id == battle_card_data.competitor_id)
    )
    competitor = competitor_result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {battle_card_data.competitor_id} not found"
        )
    
    # Get the latest version for this product-competitor pair
    latest_version_result = await db.execute(
        select(BattleCard.version)
        .where(
            and_(
                BattleCard.product_id == battle_card_data.product_id,
                BattleCard.competitor_id == battle_card_data.competitor_id
            )
        )
        .order_by(BattleCard.version.desc())
        .limit(1)
    )
    latest_version = latest_version_result.scalar()
    new_version = (latest_version or 0) + 1
    
    # Create battle card
    battle_card = BattleCard(
        product_id=battle_card_data.product_id,
        competitor_id=battle_card_data.competitor_id,
        version=new_version,
        status=BattleCardStatus.DRAFT
    )
    db.add(battle_card)
    await db.flush()
    
    # Create sections
    for section_data in battle_card_data.sections:
        section = BattleCardSection(
            battle_card_id=battle_card.id,
            **section_data.model_dump()
        )
        db.add(section)
    
    await db.commit()
    await db.refresh(battle_card)
    
    # Load relationships and return
    result = await db.execute(
        select(BattleCard)
        .options(
            selectinload(BattleCard.sections),
            selectinload(BattleCard.product),
            selectinload(BattleCard.competitor)
        )
        .where(BattleCard.id == battle_card.id)
    )
    card = result.scalar_one()
    
    return BattleCardResponse(
        **card.__dict__,
        product_name=card.product.name,
        competitor_name=card.competitor.name,
        sections=card.sections
    )


@router.get("/{battle_card_id}", response_model=BattleCardResponse)
async def get_battle_card(
    battle_card_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific battle card by ID"""
    result = await db.execute(
        select(BattleCard)
        .options(
            selectinload(BattleCard.sections),
            selectinload(BattleCard.product),
            selectinload(BattleCard.competitor)
        )
        .where(BattleCard.id == battle_card_id)
    )
    battle_card = result.scalar_one_or_none()
    
    if not battle_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battle card with id {battle_card_id} not found"
        )
    
    return BattleCardResponse(
        **battle_card.__dict__,
        product_name=battle_card.product.name,
        competitor_name=battle_card.competitor.name,
        sections=battle_card.sections
    )


@router.put("/{battle_card_id}", response_model=BattleCardResponse)
async def update_battle_card(
    battle_card_id: UUID,
    battle_card_update: BattleCardUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a battle card"""
    result = await db.execute(
        select(BattleCard).where(BattleCard.id == battle_card_id)
    )
    battle_card = result.scalar_one_or_none()
    
    if not battle_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battle card with id {battle_card_id} not found"
        )
    
    # Update basic fields
    if battle_card_update.status is not None:
        battle_card.status = battle_card_update.status
    
    # Update sections if provided
    if battle_card_update.sections is not None:
        # Delete existing sections
        await db.execute(
            select(BattleCardSection)
            .where(BattleCardSection.battle_card_id == battle_card_id)
        )
        
        # Add new sections
        for section_data in battle_card_update.sections:
            section = BattleCardSection(
                battle_card_id=battle_card_id,
                **section_data.model_dump(exclude_unset=True)
            )
            db.add(section)
    
    await db.commit()
    
    # Load relationships and return
    result = await db.execute(
        select(BattleCard)
        .options(
            selectinload(BattleCard.sections),
            selectinload(BattleCard.product),
            selectinload(BattleCard.competitor)
        )
        .where(BattleCard.id == battle_card_id)
    )
    card = result.scalar_one()
    
    return BattleCardResponse(
        **card.__dict__,
        product_name=card.product.name,
        competitor_name=card.competitor.name,
        sections=card.sections
    )


@router.delete("/{battle_card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_battle_card(
    battle_card_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a battle card"""
    result = await db.execute(
        select(BattleCard).where(BattleCard.id == battle_card_id)
    )
    battle_card = result.scalar_one_or_none()
    
    if not battle_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battle card with id {battle_card_id} not found"
        )
    
    await db.delete(battle_card)
    await db.commit()


@router.post("/{battle_card_id}/publish", response_model=BattleCardResponse)
async def publish_battle_card(
    battle_card_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Publish a battle card"""
    result = await db.execute(
        select(BattleCard).where(BattleCard.id == battle_card_id)
    )
    battle_card = result.scalar_one_or_none()
    
    if not battle_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battle card with id {battle_card_id} not found"
        )
    
    battle_card.status = BattleCardStatus.PUBLISHED
    battle_card.published_at = datetime.utcnow()
    
    await db.commit()
    
    # Load relationships and return
    result = await db.execute(
        select(BattleCard)
        .options(
            selectinload(BattleCard.sections),
            selectinload(BattleCard.product),
            selectinload(BattleCard.competitor)
        )
        .where(BattleCard.id == battle_card_id)
    )
    card = result.scalar_one()
    
    return BattleCardResponse(
        **card.__dict__,
        product_name=card.product.name,
        competitor_name=card.competitor.name,
        sections=card.sections
    )


@router.post("/{battle_card_id}/archive", response_model=BattleCardResponse)
async def archive_battle_card(
    battle_card_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Archive a battle card"""
    result = await db.execute(
        select(BattleCard).where(BattleCard.id == battle_card_id)
    )
    battle_card = result.scalar_one_or_none()
    
    if not battle_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battle card with id {battle_card_id} not found"
        )
    
    battle_card.status = BattleCardStatus.ARCHIVED
    
    await db.commit()
    
    # Load relationships and return
    result = await db.execute(
        select(BattleCard)
        .options(
            selectinload(BattleCard.sections),
            selectinload(BattleCard.product),
            selectinload(BattleCard.competitor)
        )
        .where(BattleCard.id == battle_card_id)
    )
    card = result.scalar_one()
    
    return BattleCardResponse(
        **card.__dict__,
        product_name=card.product.name,
        competitor_name=card.competitor.name,
        sections=card.sections
    )


@router.post("/products/{product_id}/generate", response_model=BattleCardResponse)
async def generate_battle_card(
    product_id: UUID,
    generate_request: BattleCardGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Generate a battle card using AI analysis"""
    # Verify product and competitor exist
    product_result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )
    
    competitor_result = await db.execute(
        select(Competitor).where(Competitor.id == generate_request.competitor_id)
    )
    competitor = competitor_result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {generate_request.competitor_id} not found"
        )
    
    # Generate battle card content
    generator = BattleCardGenerator()
    sections = await generator.generate_battle_card(
        product=product,
        competitor=competitor,
        include_sections=generate_request.include_sections,
        db=db
    )
    
    # Create battle card
    battle_card_data = BattleCardCreate(
        product_id=product_id,
        competitor_id=generate_request.competitor_id,
        sections=sections
    )
    
    return await create_battle_card(battle_card_data, db)


# Competitor Scraping endpoints
@router.post("/competitors/{competitor_id}/scrape", response_model=ScrapingJobResponse)
async def trigger_competitor_scraping(
    competitor_id: UUID,
    scraping_request: CompetitorScrapingRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Trigger web scraping for a competitor"""
    # Verify competitor exists
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with id {competitor_id} not found"
        )
    
    # Create scraping job
    scraping_job = CompetitorScrapingJob(
        competitor_id=competitor_id,
        job_type=scraping_request.job_type,
        status=ScrapingJobStatus.PENDING
    )
    db.add(scraping_job)
    await db.commit()
    await db.refresh(scraping_job)
    
    # Trigger background scraping task
    scraper = CompetitorScraper()
    background_tasks.add_task(
        scraper.scrape_competitor,
        competitor_id=competitor_id,
        job_id=scraping_job.id,
        job_type=scraping_request.job_type,
        target_urls=scraping_request.target_urls
    )
    
    return scraping_job


@router.get("/competitors/{competitor_id}/scraping-jobs", response_model=List[ScrapingJobResponse])
async def get_competitor_scraping_jobs(
    competitor_id: UUID,
    status: Optional[ScrapingJobStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get scraping job history for a competitor"""
    query = select(CompetitorScrapingJob).where(
        CompetitorScrapingJob.competitor_id == competitor_id
    )
    
    if status:
        query = query.where(CompetitorScrapingJob.status == status)
    
    query = query.order_by(CompetitorScrapingJob.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return jobs