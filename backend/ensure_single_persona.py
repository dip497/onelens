"""
Script to ensure we have a single product (persona) for the company
and properly set up the system
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, func
from app.models import Product, ProductModule
from app.core.config import settings
import uuid

async def ensure_single_persona():
    # Convert sync postgres URL to async
    async_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(async_url, echo=True)
    
    async with AsyncSession(engine) as session:
        # Check if any products exist
        result = await session.execute(select(func.count(Product.id)))
        product_count = result.scalar()
        
        if product_count == 0:
            # Create the single product/persona for the company
            print("Creating company persona...")
            product = Product(
                id=uuid.uuid4(),
                name="OneLens",  # Default name - should be configured
                description="AI-powered Epic Analysis and Product Management System",
                tagline="Transform customer feedback into strategic product decisions",
                website="https://onelens.ai"
            )
            session.add(product)
            
            # Create default modules
            default_modules = [
                {"name": "Core Features", "icon": "🎯", "description": "Essential functionality", "order_index": 0},
                {"name": "Analytics & Insights", "icon": "📊", "description": "Data analysis and reporting", "order_index": 1},
                {"name": "Integration & API", "icon": "🔌", "description": "Third-party integrations", "order_index": 2},
                {"name": "User Experience", "icon": "✨", "description": "UI/UX improvements", "order_index": 3},
                {"name": "Security & Compliance", "icon": "🔒", "description": "Security features", "order_index": 4},
            ]
            
            for module_data in default_modules:
                module = ProductModule(
                    product_id=product.id,
                    **module_data
                )
                session.add(module)
            
            await session.commit()
            print(f"Created product persona: OneLens with {len(default_modules)} modules")
            
        elif product_count == 1:
            # Perfect - we have exactly one product
            result = await session.execute(select(Product))
            product = result.scalar_one()
            print(f"Single product persona exists: {product.name}")
            
        else:
            # Multiple products exist - this shouldn't happen
            print(f"WARNING: Multiple products exist ({product_count}). System is designed for single persona.")
            print("Please manually consolidate to a single product or update the system design.")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(ensure_single_persona())