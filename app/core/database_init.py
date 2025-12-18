"""Database initialization module.

Runs idempotent SQL initialization on app startup using only DATABASE_URL from settings.
"""

import logging
from pathlib import Path
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL script into individual statements.

    Handles:
    - single/double quoted strings
    - line/block comments
    - PostgreSQL dollar-quoted blocks (e.g. $$ ... $$, $tag$ ... $tag$)
    """

    statements: list[str] = []
    buf: list[str] = []

    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None

    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue

        if dollar_tag is not None:
            # In dollar-quoted block; only look for the closing tag.
            buf.append(ch)
            if ch == "$":
                tag_len = len(dollar_tag)
                if i + tag_len <= n and sql[i : i + tag_len] == dollar_tag:
                    # add the rest of the tag (we already appended first '$')
                    buf.extend(list(dollar_tag[1:]))
                    i += tag_len
                    dollar_tag = None
                    continue
            i += 1
            continue

        if not in_single and not in_double:
            if ch == "-" and nxt == "-":
                buf.append(ch)
                buf.append(nxt)
                i += 2
                in_line_comment = True
                continue
            if ch == "/" and nxt == "*":
                buf.append(ch)
                buf.append(nxt)
                i += 2
                in_block_comment = True
                continue

        if not in_double and ch == "'":
            buf.append(ch)
            if in_single and nxt == "'":
                buf.append(nxt)
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue

        if not in_single and ch == '"':
            buf.append(ch)
            if in_double and nxt == '"':
                buf.append(nxt)
                i += 2
                continue
            in_double = not in_double
            i += 1
            continue

        if not in_single and not in_double and ch == "$":
            # dollar quote start: $tag$ ... $tag$
            j = i + 1
            while j < n and sql[j] != "$" and sql[j] not in {"\n", "\r"}:
                j += 1
            if j < n and sql[j] == "$":
                tag = sql[i : j + 1]
                if " " not in tag and "\t" not in tag:
                    dollar_tag = tag
            buf.append(ch)
            i += 1
            continue

        if not in_single and not in_double and ch == ";":
            chunk = "".join(buf).strip()
            if chunk:
                statements.append(chunk)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


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
            
            statements = _split_sql_statements(sql_content)
            for statement in statements:
                connection.exec_driver_sql(statement)
            connection.commit()
        
        engine.dispose()
        logger.info("✓ Database schema initialized successfully")
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize database schema: {str(e)}")
        raise
