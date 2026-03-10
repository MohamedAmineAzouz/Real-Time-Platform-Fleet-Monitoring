"""
repositories/truck_repository.py
─────────────────────────────────────────────────────────────────────────────
Queries against fleet.truck_latest and fleet.truck_history.
All queries use prepared statements (compiled once, reused per request).
Each function retries once on connection errors via _execute().
─────────────────────────────────────────────────────────────────────────────
"""

from typing import Optional
# from app.db import cassandra as db
from app.db.prepared import get as stmt
from app.models.truck import TruckLatest, TruckHistory
from ._base import execute, rows_to_models


def get_all() -> list[TruckLatest]:
    """All trucks — latest state. Powers the live map."""
    rows = execute(stmt("truck_latest_all"))
    return rows_to_models(rows, TruckLatest)


def get_by_id(truck_id: int) -> Optional[TruckLatest]:
    """Single truck latest state."""
    rows = execute(stmt("truck_latest_by_id"), (truck_id,))
    row  = rows.one()
    return TruckLatest(**dict(row._asdict())) if row else None


def get_history(truck_id: int, limit: int = 100) -> list[TruckHistory]:
    """Last N events for a truck, newest first (Cassandra ORDER BY DESC)."""
    rows = execute(stmt("truck_history_by_id"), (truck_id, limit))
    return rows_to_models(rows, TruckHistory)