#!/usr/bin/env python3
"""
Create a demo user with three accounts and sample positions.

Requires the schema (run_migrations.py) and the instrument seed (seed_data.py).
Idempotent: existing user, accounts and positions are left unchanged.

Usage:
    cd backend/database
    uv run create_test_data.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv(override=True)

from src.models import Database
from src.schemas import AccountCreate, PositionCreate, UserCreate

TEST_USER_ID = "test_user_001"

def create_test_data(db_models: Database) -> None:
    """Create test user with sample portfolio"""
    print("\n👤 Creating test user and portfolio...")
    
    # Create test user with Pydantic validation
    user_data = UserCreate(
        clerk_user_id='test_user_001',
        display_name='Test User',
        years_until_retirement=25,
        target_retirement_income=Decimal('100000')
    )
    
    # Check if user exists
    existing = db_models.users.find_by_clerk_id('test_user_001')
    if existing:
        print("   ℹ️  Test user already exists")
    else:
        # Use validated data from Pydantic model
        validated = user_data.model_dump()
        db_models.users.create_user(
            clerk_user_id=validated['clerk_user_id'],
            display_name=validated['display_name'],
            years_until_retirement=validated['years_until_retirement'],
            target_retirement_income=validated['target_retirement_income']
        )
        print("   ✅ Created test user")
    
    # Create test accounts with Pydantic validation
    accounts = [
        AccountCreate(
            account_name='401(k)',
            account_purpose='Primary retirement savings',
            cash_balance=Decimal('5000'),
            cash_interest=Decimal('0.045')
        ),
        AccountCreate(
            account_name='Roth IRA',
            account_purpose='Tax-free retirement savings',
            cash_balance=Decimal('1000'),
            cash_interest=Decimal('0.04')
        ),
        AccountCreate(
            account_name='Taxable Brokerage',
            account_purpose='General investment account',
            cash_balance=Decimal('2500'),
            cash_interest=Decimal('0.035')
        )
    ]
    
    user_accounts = db_models.accounts.find_by_user('test_user_001')
    
    if user_accounts:
        print(f"   ℹ️  User already has {len(user_accounts)} accounts")
        account_ids = [acc['id'] for acc in user_accounts]
    else:
        account_ids = []
        for acc_data in accounts:
            validated = acc_data.model_dump()
            acc_id = db_models.accounts.create_account(
                'test_user_001',
                account_name=validated['account_name'],
                account_purpose=validated['account_purpose'],
                cash_balance=validated['cash_balance'],
                cash_interest=validated['cash_interest']
            )
            account_ids.append(acc_id)
            print(f"   ✅ Created account: {validated['account_name']}")
    
    holdings_by_account = [
        [("SPY", "100"), ("QQQ", "50"), ("BND", "200"), ("VEA", "150"), ("GLD", "25")],  # 401(k)
        [("IWM", "40"), ("VWO", "60"), ("AGG", "30")],  # Roth IRA
        [("VUG", "20"), ("VNQ", "35"), ("TLT", "25")],  # Taxable Brokerage
    ]

    for account_id, holdings in zip(account_ids, holdings_by_account, strict=False):
        existing_positions = db_models.positions.find_by_account(account_id)
        if existing_positions:
            print(f"   ℹ️  Account already has {len(existing_positions)} positions")
            continue
        for symbol, quantity in holdings:
            if not db_models.instruments.find_by_symbol(symbol):
                print(f"   ⚠️  {symbol} is not in instruments (run seed_data.py); skipped")
                continue
            position = PositionCreate(
                account_id=account_id, symbol=symbol, quantity=Decimal(quantity)
            ).model_dump()
            db_models.positions.add_position(
                position["account_id"], position["symbol"], position["quantity"]
            )
            print(f"   ✅ Added position: {quantity} shares of {symbol}")


def main() -> None:
    create_test_data(Database())
    print("\n✅ Test data ready (user: test_user_001)")


if __name__ == "__main__":
    main()
