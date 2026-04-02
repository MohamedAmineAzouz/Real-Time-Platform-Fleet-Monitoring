import random
from faker import Faker
from geopy.distance import geodesic
from config.settings import CITIES
from services.route_service import get_route
from datetime import datetime, timedelta


fake = Faker()

# ── Refuel config ─────────────────────────────────────────────────────────────
REFUEL_RATE_PER_TICK = 5.0
REFUEL_TARGET        = 95.0
FUEL_STOP_THRESHOLD  = 20.0

# ── Anomaly injection config ──────────────────────────────────────────────────
ANOMALY_START_CHANCE  = 0.06
ANOMALY_STOP_CHANCE   = 0.20
ANOMALY_TYPES         = ["overspeed", "overheat", "fuel_leak"]

# ── Driver change config ──────────────────────────────────────────────────────
# Chance to change driver after completing a trajet (30% chance)
DRIVER_CHANGE_CHANCE  = 0.3


def _nearest_city(lat: float, lon: float) -> str:
    best_name, best_dist = None, float("inf")
    for name, (city_lon, city_lat) in CITIES.items():
        d = geodesic((lat, lon), (city_lat, city_lon)).km
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name


class Truck:
    def __init__(self, truck_id, route, start_city, end_city, driver_id=None, trajet_id=None):
        self.truck_id      = truck_id
        self.route         = route
        self.current_index = 0
        self.speed         = random.uniform(60, 90)
        self.fuel_level    = random.uniform(75, 100)
        self.engine_temp   = random.uniform(70, 85)
        self.driver_id     = driver_id if driver_id else fake.uuid4()
        self.start_city    = start_city
        self.end_city      = end_city
        self.trajet_id     = trajet_id
        self._odometer_km  = 0.0

        # Refuel state
        self.is_refueling  = False
        self.refuel_city   = None
        self._stopped_lat  = None
        self._stopped_lon  = None

        # Anomaly mode
        self._anomaly_mode: str | None = None

        # ── Fuel tracking ─────────────────────────────────────────────────────
        self._trip_fuel_start   = self.fuel_level
        self._fuel_consumed_trip = 0.0
        self._fuel_refueled      = 0.0
        self._last_fuel_before_refuel = self.fuel_level

        # ── Driver change tracking ────────────────────────────────────────────
        self._completed_trajets = 0
        self._needs_driver_change = False

    def request_driver_change(self):
        """Mark that this truck needs a new driver."""
        self._needs_driver_change = True

    def should_change_driver(self) -> bool:
        """Check if driver should be changed (random chance after trajet completion)."""
        return self._needs_driver_change or random.random() < DRIVER_CHANGE_CHANCE

    def reset_driver_change_flag(self):
        """Reset the driver change flag after handling."""
        self._needs_driver_change = False
        self._completed_trajets += 1

    # ─────────────────────────────────────────────────────────────────────────
    # Route helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_new_route(self):
        city_names = list(CITIES.keys())
        new_end    = random.choice(city_names)
        new_route  = get_route(CITIES[self.end_city], CITIES[new_end])
        if new_route:
            print(f"  🔄 Truck {self.truck_id}: Route {self.start_city} → {self.end_city} completed ({len(self.route)} points)")
            print(f"     New route: {self.end_city} → {new_end} ({len(new_route)} points)")
            self.route         = new_route
            self.start_city    = self.end_city
            self.end_city      = new_end
            self.current_index = 0
        else:
            print(f"  ⚠️  Truck {self.truck_id}: Failed to get new route, keeping current destination")

    # ─────────────────────────────────────────────────────────────────────────
    # Anomaly mode state machine
    # ─────────────────────────────────────────────────────────────────────────

    def _tick_anomaly_mode(self):
        if self._anomaly_mode is None:
            if random.random() < ANOMALY_START_CHANCE:
                self._anomaly_mode = random.choice(ANOMALY_TYPES)
        else:
            if random.random() < ANOMALY_STOP_CHANCE:
                self._anomaly_mode = None

    # ─────────────────────────────────────────────────────────────────────────
    # Physics
    # ─────────────────────────────────────────────────────────────────────────

    def _update_physics(self, distance_km: float):
        # Normal speed
        self.speed += random.uniform(-5, 5)
        self.speed  = max(40, min(110, self.speed))

        # Normal fuel consumption
        liters_per_km   = 0.08 + (self.speed / 1000)
        fuel_pct_per_km = (liters_per_km / 400) * 100
        fuel_consumed   = distance_km * fuel_pct_per_km
        fuel_before     = self.fuel_level
        self.fuel_level = max(0, round(self.fuel_level - fuel_consumed, 3))

        # Accumulate consumed fuel
        actual_consumed = round(fuel_before - self.fuel_level, 4)
        if actual_consumed > 0:
            self._fuel_consumed_trip = round(self._fuel_consumed_trip + actual_consumed, 4)

        # Normal engine temp
        target_temp      = 75 + (self.speed - 60) * 0.3
        self.engine_temp += (target_temp - self.engine_temp) * 0.1
        self.engine_temp += random.uniform(-1, 1)
        self.engine_temp = round(max(65, min(95, self.engine_temp)), 2)

        self._odometer_km += distance_km

        # Anomaly overrides
        if self._anomaly_mode == "overspeed":
            self.speed = round(random.uniform(125, 165), 2)

        elif self._anomaly_mode == "overheat":
            self.engine_temp = round(random.uniform(103, 135), 2)

        elif self._anomaly_mode == "fuel_leak":
            extra_drain = round(random.uniform(3.0, 7.0), 3)
            self.fuel_level = max(0, round(self.fuel_level - extra_drain, 3))
            self._fuel_consumed_trip = round(self._fuel_consumed_trip + extra_drain, 4)

    # ─────────────────────────────────────────────────────────────────────────
    # Refuel helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _start_refueling(self, lat: float, lon: float):
        self.is_refueling  = True
        self._stopped_lat  = lat
        self._stopped_lon  = lon
        self.refuel_city   = _nearest_city(lat, lon)
        self.speed         = 0.0
        self._anomaly_mode = None
        self._last_fuel_before_refuel = self.fuel_level
        self._fuel_refueled           = 0.0
        print(f"⛽  Truck {self.truck_id} stopping at {self.refuel_city} "
              f"(fuel: {self.fuel_level:.1f}%)")

    def _do_refuel_tick(self):
        fuel_before     = self.fuel_level
        self.fuel_level = min(REFUEL_TARGET, round(self.fuel_level + REFUEL_RATE_PER_TICK, 3))
        self._fuel_refueled = round(
            self._fuel_refueled + (self.fuel_level - fuel_before), 4
        )
        if self.fuel_level >= REFUEL_TARGET:
            print(f"✅  Truck {self.truck_id} refueled to {self.fuel_level:.1f}% "
                  f"(+{self._fuel_refueled:.1f}%) — resuming")
            self.is_refueling = False
            self.refuel_city  = None
            self._trip_fuel_start    = self.fuel_level
            self._fuel_consumed_trip = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Public anomaly hooks
    # ─────────────────────────────────────────────────────────────────────────

    def apply_anomaly_fuel_drain(self, extra_pct: float):
        self.fuel_level = max(0, round(self.fuel_level - extra_pct, 3))
        self._fuel_consumed_trip = round(self._fuel_consumed_trip + extra_pct, 4)

    def apply_anomaly_fuel_theft(self, stolen_pct: float):
        self.fuel_level = max(0, round(self.fuel_level - stolen_pct, 3))

    # ─────────────────────────────────────────────────────────────────────────
    # Main tick
    # ─────────────────────────────────────────────────────────────────────────

    def move(self) -> dict | None:

        # ── CASE 1: Refueling ─────────────────────────────────────────────────
        if self.is_refueling:
            self._do_refuel_tick()
            return {
                "truck_id":           self.truck_id,
                "latitude":           round(self._stopped_lat, 6),
                "longitude":          round(self._stopped_lon, 6),
                "speed":              0.0,
                "fuel_level":         self.fuel_level,
                "engine_temp":        round(self.engine_temp, 2),
                "driver_id":          self.driver_id,
                "start_city":         self.start_city,
                "end_city":           self.end_city,
                "odometer_km":        round(self._odometer_km, 2),
                "refueling":          True,
                "refuel_city":        self.refuel_city,
                "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
                "fuel_refueled":      round(self._fuel_refueled, 4),
                "timestamp":          (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
            }

        # ── CASE 2: Route finished ────────────────────────────────────────────
        if self.current_index >= len(self.route) - 1:
            self._get_new_route()
            self._completed_trajets += 1
            # Mark that driver might need to change
            if self.should_change_driver():
                self._needs_driver_change = True
                print(f"  🔄 Truck {self.truck_id} completed trajet - driver change requested")
            return None

        # ── CASE 3: Normal movement ───────────────────────────────────────────
        current    = self.route[self.current_index]
        next_point = self.route[self.current_index + 1]

        distance = geodesic(
            (current[1],    current[0]),
            (next_point[1], next_point[0])
        ).km

        self._tick_anomaly_mode()
        self._update_physics(distance)
        self.current_index += 1

        lat = round(next_point[1], 6)
        lon = round(next_point[0], 6)

        if self.fuel_level <= FUEL_STOP_THRESHOLD:
            self._start_refueling(lat, lon)

        return {
            "truck_id":           self.truck_id,
            "latitude":           lat,
            "longitude":          lon,
            "speed":              round(self.speed, 2),
            "fuel_level":         self.fuel_level,
            "engine_temp":        self.engine_temp,
            "driver_id":          self.driver_id,
            "start_city":         self.start_city,
            "end_city":           self.end_city,
            "odometer_km":        round(self._odometer_km, 2),
            "refueling":          self.is_refueling,
            "refuel_city":        self.refuel_city,
            "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
            "fuel_refueled":      round(self._fuel_refueled, 4),
            "timestamp":          (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
        }
