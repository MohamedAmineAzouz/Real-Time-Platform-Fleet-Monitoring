"""
repositories/_base.py
─────────────────────────────────────────────────────────────────────────────
Shared helpers used by all repositories:
  - execute()        runs CQL with one auto-retry on stale session
  - rows_to_models() converts Cassandra rows to Pydantic models safely
─────────────────────────────────────────────────────────────────────────────
"""

import logging
from typing import Type, TypeVar
from cassandra.query import SimpleStatement
from app.db import cassandra as db

logger = logging.getLogger(__name__)
T = TypeVar("T")


def execute(stmt, params=None, use_simple: bool = False):
    """
    Execute a prepared or simple CQL statement.
    Retries once on connection errors (handles session going stale mid-request).
    """
    if use_simple:
        stmt = SimpleStatement(stmt)

    for attempt in range(2):
        try:
            session = db.session()
            return session.execute(stmt, params) if params else session.execute(stmt)
        except Exception as exc:
            if attempt == 0:
                logger.warning("Query failed, retrying after reconnect: %s", exc)
                # Force session refresh on next db.session() call
                db._session = None
                continue
            raise


def rows_to_models(rows, model_class: Type[T]) -> list[T]:
    """
    Convert Cassandra result rows to a list of Pydantic models.
    Skips rows that fail validation instead of crashing the whole request.
    """
    result = []
    for row in rows:
        try:
            result.append(model_class(**dict(row._asdict())))
        except Exception as exc:
            logger.warning("Skipping malformed row for %s: %s", model_class.__name__, exc)
    return result