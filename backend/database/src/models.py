"""
Database models and query builders
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, ClassVar, cast

from .client import DataAPIClient
from .rows import (
    AccountRow,
    InstrumentRow,
    JobRow,
    PortfolioValue,
    PositionRow,
    UserRow,
)
from .schemas import InstrumentCreate


def utcnow() -> datetime:
    """Naive UTC timestamp (the schema stores TIMESTAMP without time zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Repository[RowT]:
    """Base class for table repositories (one subclass per table; ``RowT`` is its row type)."""

    table_name: ClassVar[str] = ""

    def __init__(self, db: DataAPIClient) -> None:
        self.db = db
        if not self.table_name:
            raise ValueError("table_name must be defined")

    def _query(self, sql: str, params: list[dict[str, Any]] | None = None) -> list[RowT]:
        return cast(list[RowT], self.db.query(sql, params))

    def _query_one(self, sql: str, params: list[dict[str, Any]] | None = None) -> RowT | None:
        return cast(RowT | None, self.db.query_one(sql, params))
    
    def find_by_id(self, id: Any) -> RowT | None:
        """Find a record by ID"""
        sql = f"SELECT * FROM {self.table_name} WHERE id = :id::uuid"
        return self._query_one(sql, [{'name': 'id', 'value': {'stringValue': str(id)}}])
    
    def find_all(self, limit: int = 100, offset: int = 0) -> list[RowT]:
        """Find all records with pagination"""
        sql = f"SELECT * FROM {self.table_name} LIMIT :limit OFFSET :offset"
        params = [
            {'name': 'limit', 'value': {'longValue': limit}},
            {'name': 'offset', 'value': {'longValue': offset}}
        ]
        return self._query(sql, params)
    
    def create(self, data: dict[str, Any], returning: str = 'id') -> str | None:
        """Create a new record"""
        return self.db.insert(self.table_name, data, returning=returning)
    
    def update(self, id: Any, data: dict[str, Any]) -> int:
        """Update a record by ID"""
        return self.db.update(self.table_name, data, "id = :id::uuid", {'id': str(id)})
    
    def delete(self, id: Any) -> int:
        """Delete a record by ID"""
        return self.db.delete(self.table_name, "id = :id::uuid", {'id': str(id)})


class UserRepository(Repository[UserRow]):
    """Users table operations"""
    table_name = 'users'
    
    def find_by_clerk_id(self, clerk_user_id: str) -> UserRow | None:
        """Find user by Clerk ID"""
        sql = f"SELECT * FROM {self.table_name} WHERE clerk_user_id = :clerk_id"
        params = [{'name': 'clerk_id', 'value': {'stringValue': clerk_user_id}}]
        return self._query_one(sql, params)
    
    def create_user(self, clerk_user_id: str, display_name: str | None = None, 
                   years_until_retirement: int | None = None,
                   target_retirement_income: Decimal | None = None) -> str | None:
        """Create a new user"""
        data = {
            'clerk_user_id': clerk_user_id,
            'display_name': display_name,
            'years_until_retirement': years_until_retirement,
            'target_retirement_income': target_retirement_income
        }
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        return self.db.insert(self.table_name, data, returning='clerk_user_id')


class InstrumentRepository(Repository[InstrumentRow]):
    """Instruments table operations"""
    table_name = 'instruments'

    def find_all(self, limit: int | None = None, offset: int = 0) -> list[InstrumentRow]:
        """Find all instruments - no limit by default for autocomplete"""
        sql = f"SELECT * FROM {self.table_name} ORDER BY symbol"
        return self._query(sql, [])

    def find_by_symbol(self, symbol: str) -> InstrumentRow | None:
        """Find instrument by symbol"""
        sql = f"SELECT * FROM {self.table_name} WHERE symbol = :symbol"
        params = [{'name': 'symbol', 'value': {'stringValue': symbol}}]
        return self._query_one(sql, params)
    
    def create_instrument(self, instrument: InstrumentCreate) -> str | None:
        """Create a new instrument with validation"""
        # Validate using Pydantic
        validated = instrument.model_dump()
        
        # Convert allocations to JSON strings for storage
        data = {
            'symbol': validated['symbol'],
            'name': validated['name'],
            'instrument_type': validated['instrument_type'],
            'allocation_regions': validated['allocation_regions'],
            'allocation_sectors': validated['allocation_sectors'],
            'allocation_asset_class': validated['allocation_asset_class']
        }
        
        return self.db.insert(self.table_name, data, returning='symbol')
    
    def find_by_type(self, instrument_type: str) -> list[InstrumentRow]:
        """Find all instruments of a specific type"""
        sql = f"SELECT * FROM {self.table_name} WHERE instrument_type = :type ORDER BY symbol"
        params = [{'name': 'type', 'value': {'stringValue': instrument_type}}]
        return self._query(sql, params)
    
    def search(self, query: str) -> list[InstrumentRow]:
        """Search instruments by symbol or name"""
        sql = f"""
            SELECT * FROM {self.table_name} 
            WHERE LOWER(symbol) LIKE LOWER(:query) 
               OR LOWER(name) LIKE LOWER(:query)
            ORDER BY symbol
            LIMIT 20
        """
        params = [{'name': 'query', 'value': {'stringValue': f'%{query}%'}}]
        return self._query(sql, params)


class AccountRepository(Repository[AccountRow]):
    """Accounts table operations"""
    table_name = 'accounts'
    
    def find_by_user(self, clerk_user_id: str) -> list[AccountRow]:
        """Find all accounts for a user"""
        sql = f"""
            SELECT * FROM {self.table_name} 
            WHERE clerk_user_id = :user_id 
            ORDER BY created_at DESC
        """
        params = [{'name': 'user_id', 'value': {'stringValue': clerk_user_id}}]
        return self._query(sql, params)
    
    def create_account(self, clerk_user_id: str, account_name: str,
                      account_purpose: str | None = None, cash_balance: Decimal = Decimal(0),
                      cash_interest: Decimal = Decimal(0)) -> str | None:
        """Create a new account"""
        data = {
            'clerk_user_id': clerk_user_id,
            'account_name': account_name,
            'account_purpose': account_purpose,
            'cash_balance': cash_balance,
            'cash_interest': cash_interest
        }
        return self.db.insert(self.table_name, data, returning='id')


class PositionRepository(Repository[PositionRow]):
    """Positions table operations"""
    table_name = 'positions'
    
    def find_by_account(self, account_id: str) -> list[PositionRow]:
        """Find all positions in an account"""
        sql = f"""
            SELECT p.*, i.name as instrument_name, i.instrument_type, i.current_price
            FROM {self.table_name} p
            JOIN instruments i ON p.symbol = i.symbol
            WHERE p.account_id = :account_id::uuid
            ORDER BY p.symbol
        """
        params = [{'name': 'account_id', 'value': {'stringValue': account_id}}]
        return self._query(sql, params)
    
    def get_portfolio_value(self, account_id: str) -> PortfolioValue:
        """Calculate total portfolio value using current prices from instruments table"""
        sql = """
            SELECT 
                COUNT(DISTINCT p.symbol) as num_positions,
                SUM(p.quantity * i.current_price) as total_value,
                SUM(p.quantity) as total_shares
            FROM positions p
            JOIN instruments i ON p.symbol = i.symbol
            WHERE p.account_id = :account_id::uuid
        """
        params = [
            {'name': 'account_id', 'value': {'stringValue': account_id}}
        ]
        result = self.db.query_one(sql, params)
        if result:
            return {
                'num_positions': result.get('num_positions', 0),
                'total_value': float(result.get('total_value', 0)) if result.get('total_value') else 0,
                'total_shares': float(result.get('total_shares', 0)) if result.get('total_shares') else 0
            }
        return {'num_positions': 0, 'total_value': 0, 'total_shares': 0}
    
    def add_position(self, account_id: str, symbol: str, quantity: Decimal) -> str | None:
        """Add or update a position"""
        # Use UPSERT to handle existing positions
        sql = """
            INSERT INTO positions (account_id, symbol, quantity, as_of_date)
            VALUES (:account_id::uuid, :symbol, :quantity::numeric, :as_of_date::date)
            ON CONFLICT (account_id, symbol) 
            DO UPDATE SET 
                quantity = EXCLUDED.quantity,
                as_of_date = EXCLUDED.as_of_date,
                updated_at = NOW()
            RETURNING id
        """
        params = [
            {'name': 'account_id', 'value': {'stringValue': account_id}},
            {'name': 'symbol', 'value': {'stringValue': symbol}},
            {'name': 'quantity', 'value': {'stringValue': str(quantity)}},
            {'name': 'as_of_date', 'value': {'stringValue': date.today().isoformat()}}
        ]
        response = self.db.execute(sql, params)
        if response.get('records'):
            return response['records'][0][0].get('stringValue')
        return None


class JobRepository(Repository[JobRow]):
    """Jobs table operations"""
    table_name = 'jobs'
    
    def create_job(self, clerk_user_id: str, job_type: str,
                  request_payload: dict[str, Any] | None = None) -> str | None:
        """Create a new job"""
        data = {
            'clerk_user_id': clerk_user_id,
            'job_type': job_type,
            'status': 'pending',
            'request_payload': request_payload
        }
        return self.db.insert(self.table_name, data, returning='id')
    
    def update_status(self, job_id: str, status: str, error_message: str | None = None) -> int:
        """Update job status"""
        data: dict[str, Any] = {'status': status}
        
        if status == 'running':
            data['started_at'] = utcnow()
        elif status in ['completed', 'failed']:
            data['completed_at'] = utcnow()
        
        if error_message:
            data['error_message'] = error_message
        
        return self.db.update(self.table_name, data, "id = :id::uuid", {'id': job_id})
    
    def update_report(self, job_id: str, report_payload: dict[str, Any]) -> int:
        """Update job with Reporter agent's analysis"""
        data = {'report_payload': report_payload}
        return self.db.update(self.table_name, data, "id = :id::uuid", {'id': job_id})
    
    def update_charts(self, job_id: str, charts_payload: dict[str, Any]) -> int:
        """Update job with Charter agent's visualization data"""
        data = {'charts_payload': charts_payload}
        return self.db.update(self.table_name, data, "id = :id::uuid", {'id': job_id})
    
    def update_retirement(self, job_id: str, retirement_payload: dict[str, Any]) -> int:
        """Update job with Retirement agent's projections"""
        data = {'retirement_payload': retirement_payload}
        return self.db.update(self.table_name, data, "id = :id::uuid", {'id': job_id})
    
    def update_summary(self, job_id: str, summary_payload: dict[str, Any]) -> int:
        """Update job with Planner's final summary"""
        data = {'summary_payload': summary_payload}
        return self.db.update(self.table_name, data, "id = :id::uuid", {'id': job_id})
    
    def find_by_user(self, clerk_user_id: str, status: str | None = None,
                    limit: int = 20) -> list[JobRow]:
        """Find jobs for a user"""
        if status:
            sql = f"""
                SELECT * FROM {self.table_name}
                WHERE clerk_user_id = :user_id AND status = :status
                ORDER BY created_at DESC
                LIMIT :limit
            """
            params = [
                {'name': 'user_id', 'value': {'stringValue': clerk_user_id}},
                {'name': 'status', 'value': {'stringValue': status}},
                {'name': 'limit', 'value': {'longValue': limit}}
            ]
        else:
            sql = f"""
                SELECT * FROM {self.table_name}
                WHERE clerk_user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit
            """
            params = [
                {'name': 'user_id', 'value': {'stringValue': clerk_user_id}},
                {'name': 'limit', 'value': {'longValue': limit}}
            ]
        
        return self._query(sql, params)


class Database:
    """Main database interface providing access to all models"""
    
    def __init__(self, cluster_arn: str | None = None, secret_arn: str | None = None,
                 database: str | None = None, region: str | None = None) -> None:
        """Initialize database with all model classes"""
        self.client = DataAPIClient(cluster_arn, secret_arn, database, region)
        
        # Initialize all models
        self.users = UserRepository(self.client)
        self.instruments = InstrumentRepository(self.client)
        self.accounts = AccountRepository(self.client)
        self.positions = PositionRepository(self.client)
        self.jobs = JobRepository(self.client)
    
    def execute_raw(self, sql: str, parameters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Execute raw SQL for complex queries"""
        return self.client.execute(sql, parameters)
    
    def query_raw(self, sql: str, parameters: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Execute raw SELECT query"""
        return self.client.query(sql, parameters)