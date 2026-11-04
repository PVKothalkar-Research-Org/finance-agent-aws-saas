#!/usr/bin/env python3
"""
Database Reset Script
Drops all tables, recreates schema, and loads seed data
"""

import argparse
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
from create_test_data import create_test_data
from src.client import DataAPIClient
from src.models import Database


def drop_all_tables(db: DataAPIClient) -> None:
    """Drop all tables in correct order (respecting foreign keys)"""
    print("🗑️  Dropping existing tables...")
    
    # Order matters due to foreign key constraints
    tables_to_drop = [
        'positions',
        'accounts',
        'jobs',
        'instruments',
        'users'
    ]
    
    for table in tables_to_drop:
        try:
            db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            print(f"   ✅ Dropped {table}")
        except Exception as e:
            print(f"   ⚠️  Error dropping {table}: {e}")
    
    # Also drop the function
    try:
        db.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")
        print("   ✅ Dropped update_updated_at_column function")
    except Exception as e:
        print(f"   ⚠️  Error dropping function: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description='Reset Finance Agent AWS SaaS database')
    parser.add_argument('--with-test-data', action='store_true',
                       help='Create test user with sample portfolio')
    parser.add_argument('--skip-drop', action='store_true',
                       help='Skip dropping tables (just reload data)')
    args = parser.parse_args()
    
    print("🚀 Database Reset Script")
    print("=" * 50)
    
    # Initialize database
    db = DataAPIClient()
    db_models = Database()
    
    if not args.skip_drop:
        # Drop all tables
        drop_all_tables(db)
        
        # Run migrations
        print("\n📝 Running migrations...")
        result = subprocess.run(['uv', 'run', 'run_migrations.py'],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ Migration failed!")
            print(result.stderr)
            sys.exit(1)
        else:
            print("✅ Migrations completed")

    # Load seed data
    print("\n🌱 Loading seed data...")
    result = subprocess.run(['uv', 'run', 'seed_data.py'],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ Seed data failed!")
        print(result.stderr)
        sys.exit(1)
    else:
        if result.stdout and '22/22 instruments loaded' in result.stdout:
            print("✅ Loaded 22 instruments")
        else:
            print("✅ Seed data loaded")
    
    # Create test data if requested
    if args.with_test_data:
        create_test_data(db_models)
    
    # Final verification
    print("\n🔍 Final verification...")
    
    # Count records
    tables = ['users', 'instruments', 'accounts', 'positions', 'jobs']
    for table in tables:
        result = db.query(f"SELECT COUNT(*) as count FROM {table}")
        count = result[0]['count'] if result else 0
        print(f"   • {table}: {count} records")
    
    print("\n" + "=" * 50)
    print("✅ Database reset complete!")
    
    if args.with_test_data:
        print("\n📝 Test user created:")
        print("   • User ID: test_user_001")
        print("   • 3 accounts (401k, Roth IRA, Taxable)")
        print("   • 5 positions in 401k account")


if __name__ == "__main__":
    main()