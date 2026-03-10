"""
db/prepared.py
─────────────────────────────────────────────────────────────────────────────
Prepared statement cache.

Prepared statements are compiled once by Cassandra and reused on every
request — faster than SimpleStatement and safer (parameterized, no injection).

Usage:
    stmt = statements.get("truck_latest_all")
    rows = db.session().execute(stmt)
─────────────────────────────────────────────────────────────────────────────
"""

from cassandra.cluster import PreparedStatement
from app.db import cassandra as db

_cache: dict[str, PreparedStatement] = {}


def prepare_all() -> None:
    """
    Compile all statements once at startup.
    Called from lifespan after connect().
    """
    sess = db.session()
    _cache.update({
        # truck_latest
        "truck_latest_all":
            sess.prepare("SELECT * FROM truck_latest"),
        "truck_latest_by_id":
            sess.prepare("SELECT * FROM truck_latest WHERE truck_id = ?"),

        # truck_history
        "truck_history_by_id":
            sess.prepare(
                "SELECT * FROM truck_history WHERE truck_id = ? LIMIT ?"
            ),

        # alerts — must include both partition key columns
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


# All known alert types — used when querying without alert_type filter
ALERT_TYPES = ["OVERSPEED", "OVERHEAT", "FUEL_THEFT", "FUEL_LEAK", "LOW_FUEL"]