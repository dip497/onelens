from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Product, ProductSegment, ProductModule, Feature
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductSegmentCreate,
    ProductSegmentUpdate,
    ProductSegmentResponse,
    ProductModuleCreate,
    ProductModuleUpdate,
    ProductModuleResponse,
    ModuleReorderRequest,
    ModuleFeaturesUpdate
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=List[ProductResponse])
async def list_products(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all products with their segments and modules"""
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.segments))
        .options(selectinload(Product.modules))
        .offset(skip)
        .limit(limit)
    )
    products = result.scalars().all()
    return products


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new product"""
    product = Product(**product_data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    
    # Load relationships
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.segments))
        .options(selectinload(Product.modules))
        .where(Product.id == product.id)
    )
    return result.scalar_one()


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific product by ID"""
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.segments))
        .options(selectinload(Product.modules))
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )
    
    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    product_update: ProductUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a product"""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )
    
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    await db.commit()
    await db.refresh(product)
    
    # Load relationships
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.segments))
        .options(selectinload(Product.modules))
        .where(Product.id == product.id)
    )
    return result.scalar_one()


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a product"""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )
    
    await db.delete(product)
    await db.commit()


# Product Segments endpoints
@router.get("/{product_id}/segments", response_model=List[ProductSegmentResponse])
async def list_product_segments(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all segments for a product"""
    result = await db.execute(
        select(ProductSegment)
        .where(ProductSegment.product_id == product_id)
        .order_by(ProductSegment.created_at)
    )
    segments = result.scalars().all()
    return segments


@router.post("/{product_id}/segments", response_model=ProductSegmentResponse, status_code=status.HTTP_201_CREATED)
async def create_product_segment(
    product_id: UUID,
    segment_data: ProductSegmentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new segment for a product"""
    # Verify product exists
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )
    
    segment = ProductSegment(
        product_id=product_id,
        **segment_data.model_dump()
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)
    
    return segment


@router.put("/segments/{segment_id}", response_model=ProductSegmentResponse)
async def update_segment(
    segment_id: UUID,
    segment_update: ProductSegmentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a segment"""
    result = await db.execute(
        select(ProductSegment).where(ProductSegment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    
    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment with id {segment_id} not found"
        )
    
    update_data = segment_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(segment, field, value)
    
    await db.commit()
    await db.refresh(segment)
    
    return segment


@router.delete("/segments/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a segment"""
    result = await db.execute(
        select(ProductSegment).where(ProductSegment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    
    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment with id {segment_id} not found"
        )
    
    await db.delete(segment)
    await db.commit()


# Product Modules endpoints
@router.get("/{product_id}/modules", response_model=List[ProductModuleResponse])
async def list_product_modules(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all modules for a product"""
    result = await db.execute(
        select(
            ProductModule,
            func.count(Feature.id).label("feature_count")
        )
        .outerjoin(Feature, Feature.module_id == ProductModule.id)
        .where(ProductModule.product_id == product_id)
        .group_by(ProductModule.id)
        .order_by(ProductModule.order_index)
    )
    
    modules = []
    for module, feature_count in result:
        module_dict = {
            "id": module.id,
            "product_id": module.product_id,
            "name": module.name,
            "description": module.description,
            "icon": module.icon,
            "order_index": module.order_index,
            "created_at": module.created_at,
            "updated_at": module.updated_at,
            "feature_count": feature_count or 0
        }
        modules.append(ProductModuleResponse(**module_dict))
    
    return modules


@router.post("/{product_id}/modules", response_model=ProductModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_product_module(
    product_id: UUID,
    module_data: ProductModuleCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new module for a product"""
    # Verify product exists
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )
    
    module = ProductModule(
        product_id=product_id,
        **module_data.model_dump()
    )
    db.add(module)
    await db.commit()
    await db.refresh(module)
    
    return ProductModuleResponse(
        **module.__dict__,
        feature_count=0
    )


@router.put("/modules/{module_id}", response_model=ProductModuleResponse)
async def update_module(
    module_id: UUID,
    module_update: ProductModuleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a module"""
    result = await db.execute(
        select(ProductModule).where(ProductModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module with id {module_id} not found"
        )
    
    update_data = module_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(module, field, value)
    
    await db.commit()
    await db.refresh(module)
    
    # Get feature count
    result = await db.execute(
        select(func.count(Feature.id))
        .where(Feature.module_id == module.id)
    )
    feature_count = result.scalar() or 0
    
    return ProductModuleResponse(
        **module.__dict__,
        feature_count=feature_count
    )


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a module"""
    result = await db.execute(
        select(ProductModule).where(ProductModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module with id {module_id} not found"
        )
    
    await db.delete(module)
    await db.commit()


@router.put("/{product_id}/modules/reorder", response_model=List[ProductModuleResponse])
async def reorder_modules(
    product_id: UUID,
    reorder_request: ModuleReorderRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reorder modules for a product"""
    # Update order indices
    for item in reorder_request.module_orders:
        await db.execute(
            select(ProductModule)
            .where(
                ProductModule.id == item["id"],
                ProductModule.product_id == product_id
            )
            .execution_options(synchronize_session="fetch")
        )
        result = await db.execute(
            select(ProductModule).where(ProductModule.id == item["id"])
        )
        module = result.scalar_one_or_none()
        if module:
            module.order_index = item["order_index"]
    
    await db.commit()
    
    # Return updated list
    return await list_product_modules(product_id, db)


@router.put("/modules/{module_id}/features", response_model=dict)
async def update_module_features(
    module_id: UUID,
    features_update: ModuleFeaturesUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update feature assignments for a module"""
    # Verify module exists
    result = await db.execute(
        select(ProductModule).where(ProductModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module with id {module_id} not found"
        )
    
    # Update feature assignments
    updated_count = 0
    for assignment in features_update.feature_assignments:
        result = await db.execute(
            select(Feature).where(Feature.id == assignment.feature_id)
        )
        feature = result.scalar_one_or_none()
        
        if feature:
            feature.module_id = assignment.module_id
            feature.is_key_differentiator = assignment.is_key_differentiator
            updated_count += 1
    
    await db.commit()
    
    return {"updated_features": updated_count}