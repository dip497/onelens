#!/usr/bin/env python3
"""
Script to fix customer table schema by adding missing columns.
"""

import asyncio
import asyncpg
import os
from sqlalchemy import text
from app.core.database import engine

async def fix_customer_schema():
    """Add missing columns to customer table."""
    
    # SQL commands to add missing columns
    alter_commands = [
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS email VARCHAR(255);",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS company VARCHAR(255);", 
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone VARCHAR(50);",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS t_shirt_size VARCHAR(10);"
    ]
    
    try:
        async with engine.begin() as conn:
            for command in alter_commands:
                print(f"Executing: {command}")
                await conn.execute(text(command))
                print("✅ Success")
        
        print("\n🎉 Customer table schema updated successfully!")
        print("Added columns: email, company, phone, t_shirt_size")
        
    except Exception as e:
        print(f"❌ Error updating schema: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_customer_schema())
