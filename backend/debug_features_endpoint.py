#!/usr/bin/env python3
"""
Debug the /api/v1/features endpoint issue
"""

import asyncio
from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models import Feature, Epic

async def debug_features():
    """Debug why features endpoint is failing"""
    
    print("=" * 60)
    print("Debugging Features Endpoint")
    print("=" * 60)
    
    async with AsyncSessionLocal() as db:
        # 1. Check if features table exists
        try:
            result = await db.execute(select(func.count(Feature.id)))
            count = result.scalar()
            print(f"✅ Features table exists with {count} records")
        except Exception as e:
            print(f"❌ Error accessing features table: {e}")
            return
        
        # 2. Check if we can query features
        try:
            result = await db.execute(select(Feature).limit(1))
            feature = result.scalar_one_or_none()
            if feature:
                print(f"✅ Can query features - found: {feature.title}")
                print(f"   Epic ID: {feature.epic_id}")
                print(f"   Module ID: {feature.module_id}")
            else:
                print("⚠️  No features found in database")
        except Exception as e:
            print(f"❌ Error querying features: {e}")
            return
        
        # 3. Check epic relationship
        try:
            result = await db.execute(
                select(Feature, Epic)
                .join(Epic, Feature.epic_id == Epic.id)
                .limit(1)
            )
            row = result.first()
            if row:
                feature, epic = row
                print(f"✅ Epic relationship works - Epic: {epic.title}")
            else:
                print("⚠️  No features with epics found")
        except Exception as e:
            print(f"❌ Error with epic relationship: {e}")
        
        # 4. Test the actual query from the endpoint
        try:
            from app.models import PriorityScore
            
            # Test the subquery that might be causing issues
            subquery = select(PriorityScore.feature_id).distinct()
            result = await db.execute(subquery)
            priority_feature_ids = result.scalars().all()
            print(f"✅ Found {len(priority_feature_ids)} features with priority scores")
            
            # Test the full query
            query = select(Feature)
            count_query = select(func.count()).select_from(query.subquery())
            total = await db.scalar(count_query)
            print(f"✅ Full query works - total features: {total}")
            
        except Exception as e:
            print(f"❌ Error with complex query: {e}")
            print(f"   This might be the issue!")
        
        # 5. Check if the issue is with pagination
        try:
            query = select(Feature).offset(0).limit(10).order_by(Feature.created_at.desc())
            result = await db.execute(query)
            features = result.scalars().all()
            print(f"✅ Pagination query works - got {len(features)} features")
        except Exception as e:
            print(f"❌ Error with pagination: {e}")
    
    print("\n" + "=" * 60)
    print("Debugging Complete")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(debug_features())