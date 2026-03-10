"""
repositories/alert_repository.py
─────────────────────────────────────────────────────────────────────────────
Queries against fleet.alerts.

The alerts table is partitioned by (truck_id, alert_type).
To get all alerts for a truck across all types we must query each type
separately and merge — Cassandra requires full partition key.
─────────────────────────────────────────────────────────────────────────────
"""

from typing import Optional
from app.db.prepared import get as stmt, ALERT_TYPES
from app.models.truck import Alert
from ._base import execute, rows_to_models


def get_all(limit: int = 50) -> list[Alert]:
    """
    Recent alerts across all trucks and types.
    ALLOW FILTERING is acceptable: alerts table is small (7-day TTL, alert rows only).
    """
    rows = execute(
        "SELECT * FROM alerts LIMIT %s ALLOW FILTERING",
        (limit,),
        use_simple=True,
    )
    return rows_to_models(rows, Alert)


def get_by_truck(
    truck_id: int,
    alert_type: Optional[str] = None,
    limit: int = 50,
) -> list[Alert]:
    """
    Alerts for one truck, optionally filtered by alert_type.
    Without filter: queries all 5 types and merges by processed_at.
    """
    if alert_type:
        rows = execute(stmt("alerts_by_truck_and_type"), (truck_id, alert_type, limit))
        return rows_to_models(rows, Alert)

    # No filter — query each partition key (truck_id, alert_type) separately
    all_rows: list = []
    for atype in ALERT_TYPES:
        rows = execute(stmt("alerts_by_truck_and_type"), (truck_id, atype, limit))
        all_rows.extend(rows)

    all_rows.sort(key=lambda r: r.processed_at, reverse=True)
    return [Alert(**dict(r._asdict())) for r in all_rows[:limit]]