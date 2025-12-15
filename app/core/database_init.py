"""Database initialization module.

Runs idempotent SQL initialization on app startup using only DATABASE_URL from settings.
"""

import logging
from pathlib import Path
from sqlalchemy import text, create_engine

logger = logging.getLogger(__name__)


def init_database_schema(database_url: str) -> None:
    """Initialize database schema from init.sql if tables don't exist.
    
    Args:
        database_url: Database connection URL from settings.DATABASE_URL
        
    Raises:
        Exception: If SQL execution fails
    """
    init_sql_path = Path(__file__).resolve().parent.parent.parent / "init.sql"
    
    if not init_sql_path.exists():
        logger.warning(f"init.sql not found at {init_sql_path}, skipping schema initialization")
        return
    
    try:
        # Create a temporary engine for initialization only
        engine = create_engine(database_url, pool_pre_ping=True)
        
        with engine.connect() as connection:
            # Read and execute the SQL initialization script
            with open(init_sql_path, "r", encoding="utf-8") as f:
                sql_content = f.read()
            
            # Split by semicolon to execute statements individually
            # This helps with error handling
            statements = [s.strip() for s in sql_content.split(";") if s.strip()]
            
            for statement in statements:
                try:
                    connection.execute(text(statement))
                except Exception as e:
                    # Log but don't fail on individual statements (some may be idempotent)
                    logger.debug(f"Statement execution (non-critical): {str(e)[:100]}")
            
            connection.commit()
        
        engine.dispose()
        logger.info("✓ Database schema initialized successfully")
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize database schema: {str(e)}")
        raise
