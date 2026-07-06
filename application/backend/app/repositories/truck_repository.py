from typing import Optional
from app.db.prepared import get as stmt
from app.models.truck import TruckLatest, TruckHistory
from ._base import execute, rows_to_models
from datetime import datetime, timedelta, timezone
from typing import Optional


def get_all() -> list[TruckLatest]:
    trucks_rows = execute(stmt("truck_latest_all"))
    trucks_list = rows_to_models(trucks_rows, TruckLatest)

    if not trucks_list:
        return []

    drivers_map = {r.driver_id: r.name for r in execute(stmt("drivers_all"))}
    models_map = {r.truck_id: r.model for r in execute(stmt("trucks_registry_all"))}

    for t in trucks_list:
        t.driver_name = drivers_map.get(t.driver_id, "Unknown Driver")
        t.truck_model = models_map.get(t.truck_id, "Unknown Model")

    return trucks_list


def get_by_id(truck_id: int) -> Optional[TruckLatest]:
    row = execute(stmt("truck_latest_by_id"), (truck_id,)).one()
    if not row:
        return None

    truck = TruckLatest(**dict(row._asdict()))

    driver_row = execute("SELECT name FROM drivers WHERE driver_id = %s", (truck.driver_id,)).one()
    truck_row = execute("SELECT model FROM trucks WHERE truck_id = %s", (truck.truck_id,)).one()

    truck.driver_name = driver_row.name if driver_row else "Unknown Driver"
    truck.truck_model = truck_row.model if truck_row else "Unknown Model"

    return truck


def get_history(truck_id: int, period: str = "24h", limit: int = 1000) -> list[TruckHistory]:
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    if period == "7d":
        start_time = now - timedelta(days=7)
    elif period == "30d":
        start_time = now - timedelta(days=30)
    elif period == "this_month":
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # default 24h
        start_time = now - timedelta(hours=24)

    rows = execute(stmt("truck_history_by_period"), (truck_id, start_time, limit))
    return rows_to_models(rows, TruckHistory)


def get_maintenance_prediction(truck_id: int) -> Optional[dict]:
    from datetime import date, timedelta, datetime
    # Predictions are daily, we fetch today's
    today_str = date.today().strftime("%Y-%m-%d")
    print(datetime.combine(date.today(), datetime.min.time()))
    row = execute(
        stmt("maintenance_prediction_by_truck"),
        ( datetime.combine(date.today(), datetime.min.time()), truck_id)
    ).one()

    if not row:
        # Fallback to yesterday if today hasn't run yet
        yesterday = datetime.combine(
            date.today() - timedelta(days=1),
            datetime.min.time()
        )

        row = execute(
            stmt("maintenance_prediction_by_truck"),
            (yesterday, truck_id)
        ).one()

    return dict(row._asdict()) if row else None


def get_eta_prediction(start_city: str, end_city: str) -> Optional[dict]:
    row = execute(
        stmt("eta_prediction_by_corridor"),
        (start_city, end_city)
    ).one()
    return dict(row._asdict()) if row else None



def get_trip_start_time(
    truck_id: int,
    start_city: str,
    end_city: str,
) -> Optional[str]:

    since = datetime.now(timezone.utc) - timedelta(hours=24)

    rows = execute(
        stmt("trip_start_by_truck"),
        (truck_id, since),
    )

    trip_start = None

    for row in rows:
        if row.start_city == start_city and row.end_city == end_city:
            # Keep updating while we're still on the same corridor.
            # Since rows are newest -> oldest, the last matching row
            # is the departure time.
            trip_start = row.event_time
        else:
            # Corridor changed.
            break
    print(f"Trip start for truck {truck_id} from {start_city} to {end_city}: {trip_start}")
    return trip_start.isoformat() if trip_start else None