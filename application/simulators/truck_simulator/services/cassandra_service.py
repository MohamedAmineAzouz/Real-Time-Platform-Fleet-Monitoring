"""
cassandra_service.py
─────────────────────────────────────────────────────────────────────────────
Cassandra operations for drivers, trucks, and trajets management.
Works with existing schema (no table modifications).
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import time
import random
from datetime import datetime
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'processing', 'speed_layer'))
CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")


class CassandraService:
    def __init__(self):
        self.session = None
        self.cluster = None
        self._connect()

    def _connect(self, retries: int = 30, delay: int = 3):
        from cassandra.cluster import Cluster
        from cassandra.auth import PlainTextAuthProvider

        auth = PlainTextAuthProvider(CASSANDRA_USER, CASSANDRA_PASS) if CASSANDRA_USER else None

        for attempt in range(1, retries + 1):
            try:
                self.cluster = Cluster(
                    [CASSANDRA_HOST],
                    port=int(CASSANDRA_PORT),
                    auth_provider=auth,
                    connect_timeout=10,
                )
                self.session = self.cluster.connect()
                self.session.set_keyspace(CASSANDRA_KEYSPACE)
                print(f"✅ Cassandra connected: {CASSANDRA_HOST}:{CASSANDRA_PORT}/{CASSANDRA_KEYSPACE}")
                return
            except Exception as exc:
                print(f"⏳ Waiting for Cassandra ({attempt}/{retries}): {exc}")
                time.sleep(delay)

        raise RuntimeError("❌ Cassandra did not become ready in time")

    # ─────────────────────────────────────────────────────────────────────────
    # Driver operations
    # ─────────────────────────────────────────────────────────────────────────

    def get_available_drivers(self) -> List[Dict[str, Any]]:
        """Get all drivers with status 'available' or 'resting'."""
        query = """
            SELECT driver_id, name, license_number, phone, status, 
                   current_truck_id
            FROM drivers 
            WHERE status IN ('available', 'resting')
            ALLOW FILTERING
        """
        try:
            result = self.session.execute(query)
            drivers = []
            for row in result:
                drivers.append({
                    'driver_id': row.driver_id,
                    'name': row.name,
                    'license_number': row.license_number,
                    'phone': row.phone,
                    'status': row.status,
                    'current_truck_id': row.current_truck_id,
                })
            return drivers
        except Exception as e:
            print(f"❌ Error fetching available drivers: {e}")
            return []

    def get_all_drivers(self) -> List[Dict[str, Any]]:
        """Get all drivers."""
        query = "SELECT * FROM drivers"
        try:
            result = self.session.execute(query)
            drivers = []
            for row in result:
                drivers.append({
                    'driver_id': row.driver_id,
                    'name': row.name,
                    'status': row.status,
                    'current_truck_id': row.current_truck_id,
                })
            return drivers
        except Exception as e:
            print(f"❌ Error fetching all drivers: {e}")
            return []

    def get_driver(self, driver_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific driver by ID."""
        query = "SELECT * FROM drivers WHERE driver_id = %s"
        try:
            result = self.session.execute(query, (driver_id,))
            row = result.one()
            if row:
                return {
                    'driver_id': row.driver_id,
                    'name': row.name,
                    'status': row.status,
                    'current_truck_id': row.current_truck_id,
                }
            return None
        except Exception as e:
            print(f"❌ Error fetching driver {driver_id}: {e}")
            return None

    def assign_driver_to_truck(self, driver_id: str, truck_id: int):
        """Assign a driver to a truck by updating driver's current_truck_id and status."""
        update_driver = """
            UPDATE drivers 
            SET current_truck_id = %s, status = 'on_trip', updated_at = %s
            WHERE driver_id = %s
        """
        now = datetime.utcnow()
        try:
            self.session.execute(update_driver, (truck_id, now, driver_id))
            print(f"  🚚 Driver {driver_id} assigned to Truck {truck_id}")
        except Exception as e:
            print(f"❌ Error assigning driver {driver_id} to truck {truck_id}: {e}")

    def release_driver(self, driver_id: str):
        """Release a driver from current truck (set to resting)."""
        query = """
            UPDATE drivers 
            SET current_truck_id = NULL, status = 'resting', updated_at = %s
            WHERE driver_id = %s
        """
        try:
            self.session.execute(query, (datetime.utcnow(), driver_id))
        except Exception as e:
            print(f"❌ Error releasing driver {driver_id}: {e}")

    def get_driver_by_truck(self, truck_id: int) -> Optional[str]:
        """Get driver ID assigned to a specific truck by querying drivers table."""
        query = "SELECT driver_id, current_truck_id FROM drivers WHERE current_truck_id = %s ALLOW FILTERING"
        try:
            result = self.session.execute(query, (truck_id,))
            row = result.one()
            return row.driver_id if row and row.current_truck_id == truck_id else None
        except Exception as e:
            print(f"❌ Error getting driver for truck {truck_id}: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Truck operations
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_trucks(self) -> List[Dict[str, Any]]:
        """Get all trucks from database."""
        query = "SELECT * FROM trucks"
        try:
            result = self.session.execute(query)
            trucks = []
            for row in result:
                trucks.append({
                    'truck_id': row.truck_id,
                    'license_plate': row.license_plate,
                    'model': row.model,
                    'year': row.year,
                    'status': row.status,
                })
            return trucks
        except Exception as e:
            print(f"❌ Error fetching trucks: {e}")
            return []

    def get_truck(self, truck_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific truck by ID."""
        query = "SELECT * FROM trucks WHERE truck_id = %s"
        try:
            result = self.session.execute(query, (truck_id,))
            row = result.one()
            if row:
                return {
                    'truck_id': row.truck_id,
                    'license_plate': row.license_plate,
                    'model': row.model,
                    'status': row.status,
                }
            return None
        except Exception as e:
            print(f"❌ Error fetching truck {truck_id}: {e}")
            return None

    def update_truck_status(self, truck_id: int, status: str):
        """Update truck status."""
        query = "UPDATE trucks SET status = %s, updated_at = %s WHERE truck_id = %s"
        try:
            self.session.execute(query, (status, datetime.utcnow(), truck_id))
        except Exception as e:
            print(f"❌ Error updating truck {truck_id} status: {e}")

    def get_assigned_trucks(self) -> set:
        """Get set of truck IDs that have drivers assigned."""
        query = "SELECT current_truck_id FROM drivers"
        try:
            result = self.session.execute(query)
            return {row.current_truck_id for row in result if row.current_truck_id is not None}
        except Exception as e:
            print(f"❌ Error fetching assigned trucks: {e}")
            return set()

    # ─────────────────────────────────────────────────────────────────────────
    # Trajet operations
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_trajets(self) -> List[Dict[str, Any]]:
        """Get all available trajets from database."""
        query = "SELECT trajet_id, start_city, end_city, distance_km FROM trajets"
        try:
            result = self.session.execute(query)
            trajets = []
            for row in result:
                trajets.append({
                    'trajet_id': row.trajet_id,
                    'start_city': row.start_city,
                    'end_city': row.end_city,
                    'distance_km': row.distance_km,
                })
            return trajets
        except Exception as e:
            print(f"❌ Error fetching trajets: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Maintenance operations
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_maintenance_schedules(self) -> dict:
        """
        Load maintenance schedules for the CURRENT month only.
        Returns dict: {truck_id: [{schedule_id, start, end, type, ...}]}
        Call this once at startup. Refresh monthly (e.g., 1st of each month).
        """
        now = datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            month_end = now.replace(year=now.year + 1, month=1, day=1)
        else:
            month_end = now.replace(month=now.month + 1, day=1)

        # Use ALLOW FILTERING since maintenance_schedules has partition key schedule_id
        query = """
            SELECT schedule_id, truck_id, maintenance_type, description,
                   scheduled_start, scheduled_end, assigned_mechanic, cost
            FROM maintenance_schedules
            WHERE scheduled_start >= %s AND scheduled_start < %s
            ALLOW FILTERING
        """

        schedules = {}
        try:
            result = self.session.execute(query, (month_start, month_end))
            for row in result:
                if row.truck_id not in schedules:
                    schedules[row.truck_id] = []
                schedules[row.truck_id].append({
                    'schedule_id':       row.schedule_id,
                    'maintenance_type':  row.maintenance_type,
                    'description':       row.description,
                    'scheduled_start':   row.scheduled_start,
                    'scheduled_end':     row.scheduled_end,
                    'assigned_mechanic': row.assigned_mechanic,
                    'cost':              row.cost,
                })
            total = sum(len(v) for v in schedules.values())
            print(f"✅ Loaded {total} maintenance schedules for {len(schedules)} trucks ({now.strftime('%Y-%m')})")
            return schedules
        except Exception as e:
            print(f"❌ Error loading maintenance schedules: {e}")
            return {}

    def is_truck_in_maintenance(self, truck_id: int, schedules_cache: dict) -> dict | None:
        """
        Check if a truck is currently under maintenance using CACHED data only.
        NO database queries. Returns maintenance info if current time is between
        scheduled_start and scheduled_end.
        """
        now = datetime.utcnow()
        truck_schedules = schedules_cache.get(truck_id, [])

        for sched in truck_schedules:
            if sched['scheduled_start'] <= now <= sched['scheduled_end']:
                return sched

        return None

    def shutdown(self):
        """Close Cassandra connection."""
        if self.cluster:
            self.cluster.shutdown()


# Global instance
_cassandra_service: Optional[CassandraService] = None


def get_cassandra_service() -> CassandraService:
    """Get or create the global Cassandra service instance."""
    global _cassandra_service
    if _cassandra_service is None:
        _cassandra_service = CassandraService()
    return _cassandra_service
