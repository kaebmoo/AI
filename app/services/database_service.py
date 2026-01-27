from typing import List, Dict, Any, Optional
import time
# import pymssql # In production, include pymssql
from sqlalchemy.orm import Session
from app.config import settings
from app.core.logging import logging

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Service to execute SQL queries against the Data Layer (MSSQL/Postgres).
    Supports mocking for development.
    """
    def __init__(self):
        self.host = settings.DATABASE_URL # Placeholder, real MSSQL host would be different
        self.is_mock = "sqlite" in settings.DATABASE_URL or "mock" in settings.DATABASE_URL
        
    async def execute_query(self, sql: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Execute raw SQL query and return results as list of dicts.
        """
        start_time = time.time()
        logger.info(f"Executing SQL: {sql}")
        
        if self.is_mock:
            # Simulate latency
            time.sleep(0.5)
            logger.info("Executing MOCK query logic")
            return self._mock_query_results(sql)
            
        # Real implementation would go here (e.g. using sqlalchemy text() or pymssql)
        # For now, we return empty or mock
        return []

    def _mock_query_results(self, sql: str) -> List[Dict[str, Any]]:
        """Return some fake data based on SQL content"""
        # Simple keywords check to return relevant mock data
        sql_lower = sql.lower()
        if "revenue" in sql_lower:
            return [
                {"region": "North", "revenue": 1500000, "target": 2000000},
                {"region": "South", "revenue": 1200000, "target": 1000000},
                {"region": "Bangkok", "revenue": 5000000, "target": 4500000},
            ]
        elif "count" in sql_lower:
             return [{"count": 1250}]
        else:
             return [{"result": "Mock Data", "id": 1}, {"result": "Mock Data", "id": 2}]
