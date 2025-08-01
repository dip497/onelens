#!/usr/bin/env python3
"""
Script to create initial database migration
Run this after setting up the database models
"""
import subprocess
import sys

def main():
    print("Creating initial migration...")
    
    # Create migration
    result = subprocess.run(
        ["alembic", "revision", "--autogenerate", "-m", "Initial migration"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error creating migration: {result.stderr}")
        sys.exit(1)
    
    print("Migration created successfully!")
    print(result.stdout)
    
    print("\nTo apply the migration, run:")
    print("alembic upgrade head")

if __name__ == "__main__":
    main()