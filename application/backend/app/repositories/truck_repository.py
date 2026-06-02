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
    """All trucks — latest state enriched with driver name and truck model."""
    trucks_rows = execute(stmt("truck_latest_all"))
    trucks_list = rows_to_models(trucks_rows, TruckLatest)

    if not trucks_list:
        return []

    # Fetch enrichment data
    drivers_map = {r.driver_id: r.name for r in execute(stmt("drivers_all"))}
    models_map = {r.truck_id: r.model for r in execute(stmt("trucks_registry_all"))}

    for t in trucks_list:
        t.driver_name = drivers_map.get(t.driver_id, "Unknown Driver")
        t.truck_model = models_map.get(t.truck_id, "Unknown Model")

    return trucks_list


def get_by_id(truck_id: int) -> Optional[TruckLatest]:
    """Single truck latest state enriched."""
    row = execute(stmt("truck_latest_by_id"), (truck_id,)).one()
    if not row:
        return None

    truck = TruckLatest(**dict(row._asdict()))

    # Enrich single record
    driver_row = execute("SELECT name FROM drivers WHERE driver_id = %s", (truck.driver_id,)).one()
    truck_row = execute("SELECT model FROM trucks WHERE truck_id = %s", (truck.truck_id,)).one()

    truck.driver_name = driver_row.name if driver_row else "Unknown Driver"
    truck.truck_model = truck_row.model if truck_row else "Unknown Model"

    return truck


def get_history(truck_id: int, limit: int = 100) -> list[TruckHistory]:
    """Last N events for a truck, newest first (Cassandra ORDER BY DESC)."""
    rows = execute(stmt("truck_history_by_id"), (truck_id, limit))
    return rows_to_models(rows, TruckHistory)