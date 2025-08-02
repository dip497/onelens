#!/usr/bin/env python3
"""
Create module_features table - separate from epic features
"""

import asyncio
from sqlalchemy import text
from app.core.database import engine
from app.models import Base, ModuleFeature

async def create_module_features_table():
    """Create the module_features table"""
    
    async with engine.begin() as conn:
        # First check if table exists
        result = await conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'module_features'
                );
            """)
        )
        table_exists = result.scalar()
        
        if table_exists:
            print("❌ module_features table already exists")
            
            # Ask if we should drop and recreate
            response = input("Do you want to drop and recreate it? (y/n): ")
            if response.lower() == 'y':
                await conn.execute(text("DROP TABLE IF EXISTS module_features CASCADE"))
                print("✅ Dropped existing module_features table")
            else:
                print("Skipping table creation")
                return
        
        # Create the table
        await conn.run_sync(Base.metadata.create_all, tables=[ModuleFeature.__table__])
        print("✅ Created module_features table")
        
        # Add some example module features
        await conn.execute(
            text("""
                -- Get the first module
                WITH first_module AS (
                    SELECT id FROM product_modules LIMIT 1
                )
                INSERT INTO module_features (
                    id, module_id, name, description, value_proposition,
                    is_key_differentiator, status, created_at, updated_at
                )
                SELECT 
                    gen_random_uuid(),
                    (SELECT id FROM first_module),
                    'AI-Powered Analytics',
                    'Real-time analytics powered by machine learning',
                    'Get insights 10x faster than traditional tools',
                    true,
                    'ACTIVE',
                    NOW(),
                    NOW()
                WHERE EXISTS (SELECT 1 FROM first_module);
            """)
        )
        
        # Check if we inserted anything
        result = await conn.execute(
            text("SELECT COUNT(*) FROM module_features")
        )
        count = result.scalar()
        
        if count > 0:
            print(f"✅ Added {count} example module feature(s)")
        
        print("\n📊 Module Features Table Structure:")
        print("- Separate from epic features (development view)")
        print("- Focused on sales/marketing messaging")
        print("- Can link to epic features via epic_feature_id")
        print("- Has sales-specific fields like value_proposition")

async def show_comparison():
    """Show the difference between epic features and module features"""
    
    print("\n🔄 Feature System Comparison:")
    print("=" * 60)
    print("EPIC FEATURES (features table):")
    print("  - Purpose: Development tracking")
    print("  - Required: epic_id")
    print("  - Fields: title, description, normalized_text")
    print("  - Used by: Product managers, developers")
    print("")
    print("MODULE FEATURES (module_features table):")
    print("  - Purpose: Sales/marketing messaging")
    print("  - Required: module_id")
    print("  - Fields: name, value_proposition, competitor_comparison")
    print("  - Used by: Sales, marketing, customer success")
    print("=" * 60)

async def main():
    print("🚀 Creating Module Features Table")
    print("=" * 60)
    
    await create_module_features_table()
    await show_comparison()
    
    print("\n✅ Setup complete!")
    print("\nNext steps:")
    print("1. Update API endpoints to use module_features")
    print("2. Update frontend to create/manage module features")
    print("3. Optionally link module features to epic features")

if __name__ == "__main__":
    asyncio.run(main())