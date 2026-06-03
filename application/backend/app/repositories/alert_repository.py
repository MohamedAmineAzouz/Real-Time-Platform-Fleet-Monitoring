from typing import Optional
from app.db.prepared import get as stmt, ALERT_TYPES
from app.models.truck import Alert
from ._base import execute, rows_to_models


def get_all(limit: int = 50) -> list[Alert]:
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
    if alert_type:
        rows = execute(stmt("alerts_by_truck_and_type"), (truck_id, alert_type, limit))
        return rows_to_models(rows, Alert)

    all_rows: list = []
    for atype in ALERT_TYPES:
        rows = execute(stmt("alerts_by_truck_and_type"), (truck_id, atype, limit))
        all_rows.extend(rows)

    all_rows.sort(key=lambda r: r.processed_at, reverse=True)
    return [Alert(**dict(r._asdict())) for r in all_rows[:limit]]