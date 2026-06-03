from typing import Optional
from app.db.prepared import get as stmt
from app.models.truck import TruckLatest, TruckHistory
from ._base import execute, rows_to_models


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


def get_history(truck_id: int, limit: int = 100) -> list[TruckHistory]:
    rows = execute(stmt("truck_history_by_id"), (truck_id, limit))
    return rows_to_models(rows, TruckHistory)