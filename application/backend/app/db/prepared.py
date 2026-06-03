
from cassandra.cluster import PreparedStatement
from app.db import cassandra as db

_cache: dict[str, PreparedStatement] = {}


def prepare_all() -> None:
    sess = db.session()
    _cache.update({
        "truck_latest_all":
            sess.prepare("SELECT * FROM truck_latest"),
        "truck_latest_by_id":
            sess.prepare("SELECT * FROM truck_latest WHERE truck_id = ?"),

        "drivers_all":
            sess.prepare("SELECT driver_id, name FROM drivers"),
        "trucks_registry_all":
            sess.prepare("SELECT truck_id, model FROM trucks"),

        "truck_history_by_id":
            sess.prepare(
                "SELECT * FROM truck_history WHERE truck_id = ? LIMIT ?"
            ),

        "alerts_by_truck_and_type":
            sess.prepare(
                "SELECT * FROM alerts "
                "WHERE truck_id = ? AND alert_type = ? LIMIT ?"
            ),
    })


def get(name: str) -> PreparedStatement:
    if name not in _cache:
        raise KeyError(f"Prepared statement '{name}' not found. Call prepare_all() first.")
    return _cache[name]


ALERT_TYPES = ["OVERSPEED", "OVERHEAT", "FUEL_THEFT", "FUEL_LEAK", "LOW_FUEL"]