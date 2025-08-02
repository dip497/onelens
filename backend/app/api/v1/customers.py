"""Customer API endpoints."""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.customer import Customer
from app.models.enums import CustomerSegment, CustomerVertical, ImpactLevel, TShirtSize
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
    CustomerListItem
)

router = APIRouter()


@router.post("/", response_model=CustomerResponse)
async def create_customer(
    customer: CustomerCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new customer."""
    
    db_customer = Customer(**customer.model_dump())
    db.add(db_customer)
    await db.commit()
    await db.refresh(db_customer)
    
    return db_customer


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    skip: int = 0,
    limit: int = 20,
    segment: Optional[CustomerSegment] = None,
    vertical: Optional[CustomerVertical] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all customers with optional filtering."""
    
    query = select(Customer)
    
    if segment:
        query = query.where(Customer.segment == segment)
    
    if vertical:
        query = query.where(Customer.vertical == vertical)
    
    if search:
        from sqlalchemy import or_
        query = query.where(
            or_(
                Customer.name.ilike(f"%{search}%"),
                Customer.company.ilike(f"%{search}%"),
                Customer.email.ilike(f"%{search}%")
            )
        )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get items with pagination
    query = query.offset(skip).limit(limit).order_by(Customer.created_at.desc())
    result = await db.execute(query)
    customers = result.scalars().all()
    
    return CustomerListResponse(
        items=customers,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific customer by ID."""
    
    result = await db.execute(
        select(Customer)
        .options(
            selectinload(Customer.feature_requests),
            selectinload(Customer.rfp_documents)
        )
        .where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    return customer


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    customer_update: CustomerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a customer."""
    
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Update fields
    update_data = customer_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    await db.commit()
    await db.refresh(customer)
    
    return customer


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a customer."""
    
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    await db.delete(customer)
    await db.commit()
    
    return {"message": "Customer deleted successfully"}


@router.get("/{customer_id}/rfps")
async def get_customer_rfps(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all RFP documents for a specific customer."""
    
    # First check if customer exists
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Get RFP documents for this customer
    from app.models.rfp import RFPDocument
    rfp_result = await db.execute(
        select(RFPDocument)
        .filter(RFPDocument.customer_id == customer_id)
        .order_by(RFPDocument.created_at.desc())
    )
    rfps = rfp_result.scalars().all()
    
    return {
        "customer": customer,
        "rfp_documents": rfps,
        "total_rfps": len(rfps)
    }
