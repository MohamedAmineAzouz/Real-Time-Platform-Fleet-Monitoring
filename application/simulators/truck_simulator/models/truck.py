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

# Realistic fuel leak: 0.02% to 0.08% per tick (~0.08 to 0.32 L per tick)
LEAK_RATE_RANGE       = (0.02, 0.08)

# ── Driver change config ──────────────────────────────────────────────────────
DRIVER_CHANGE_CHANCE  = 0.3

# ── Rest config ───────────────────────────────────────────────────────────────
# Mandatory break: After 9 hours of driving, rest for 45 mins
MAX_DRIVE_TIME_HOURS = 9.0
MANDATORY_BREAK_MINS = 45

# Short breaks (Bathroom): 5-15 mins, random chance after 2-4 hours
SHORT_BREAK_CHANCE = 0.01 # per tick (~2s) after 2 hours
SHORT_BREAK_MINS_RANGE = (5, 15)

# Meal breaks: 30-60 mins, random chance after 4-6 hours
MEAL_BREAK_CHANCE = 0.005 # per tick after 4 hours
MEAL_BREAK_MINS_RANGE = (30, 60)

# Night rest: 23:00 to 05:00
NIGHT_REST_START = 23
NIGHT_REST_END   = 5


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
        self._last_tick_fuel_l   = 0.0

        # ── Driver change tracking ────────────────────────────────────────────
        self._completed_trajets = 0
        self._needs_driver_change = False

        # ── Maintenance state ─────────────────────────────────────────────────
        self._in_maintenance = False
        self._maintenance_info = None
        self._maintenance_position = None
        self._maintenance_check_needed = False

        # ── Rest state ────────────────────────────────────────────────────────
        self.is_resting = False
        self.rest_reason = None
        self._rest_end_time: datetime | None = None
        self._driving_time_since_last_rest = timedelta(0)
        self._last_tick_time = datetime.utcnow()

    def _check_rest_requirements(self):
        """Check if truck should start resting."""
        now = datetime.utcnow() + timedelta(hours=1) # Offset matching simulator logs
        
        # 1. Night Rest (23:00 - 05:00)
        if now.hour >= NIGHT_REST_START or now.hour < NIGHT_REST_END:
            if not self.is_resting:
                self.is_resting = True
                self.rest_reason = "night_rest"
                # Stop until NIGHT_REST_END
                if now.hour >= NIGHT_REST_START:
                    self._rest_end_time = (now + timedelta(days=1)).replace(hour=NIGHT_REST_END, minute=0, second=0)
                else:
                    self._rest_end_time = now.replace(hour=NIGHT_REST_END, minute=0, second=0)
                self.speed = 0.0
                print(f"💤 Truck {self.truck_id} entering night rest until {NIGHT_REST_END}:00")
            return

        # 2. Mandatory Driver Break (45 mins after 9 hours)
        hours_driven = self._driving_time_since_last_rest.total_seconds() / 3600.0
        if hours_driven >= MAX_DRIVE_TIME_HOURS:
            if not self.is_resting:
                self.is_resting = True
                self.rest_reason = "mandatory_break"
                self._rest_end_time = now + timedelta(minutes=MANDATORY_BREAK_MINS)
                self.speed = 0.0
                print(f"🛑 Truck {self.truck_id} taking mandatory {MANDATORY_BREAK_MINS}m driver break")
            return

        # 3. Meal Break (30-60 mins, random chance after 4 hours)
        if hours_driven >= 4.0:
            if not self.is_resting and random.random() < MEAL_BREAK_CHANCE:
                self.is_resting = True
                self.rest_reason = "meal_break"
                duration = random.randint(*MEAL_BREAK_MINS_RANGE)
                self._rest_end_time = now + timedelta(minutes=duration)
                self.speed = 0.0
                print(f"🍴 Truck {self.truck_id} stopping for meal ({duration} mins)")
                return

        # 4. Short Break / Bathroom (5-15 mins, random chance after 2 hours)
        if hours_driven >= 2.0:
            if not self.is_resting and random.random() < SHORT_BREAK_CHANCE:
                self.is_resting = True
                self.rest_reason = "bathroom_break"
                duration = random.randint(*SHORT_BREAK_MINS_RANGE)
                self._rest_end_time = now + timedelta(minutes=duration)
                self.speed = 0.0
                print(f"🚻 Truck {self.truck_id} taking short bathroom break ({duration} mins)")
                return

    def _tick_rest(self):
        """Handle resting logic during a tick."""
        if not self.is_resting:
            return

        now = datetime.utcnow() + timedelta(hours=1)
        if self._rest_end_time and now >= self._rest_end_time:
            # End rest
            print(f"✅ Truck {self.truck_id} finished {self.rest_reason} - resuming")
            self.is_resting = False
            self.rest_reason = None
            self._rest_end_time = None
            self._driving_time_since_last_rest = timedelta(0)

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

    def _update_physics(self, distance_km: float, time_delta: timedelta):
        if self.is_resting or self.is_refueling or self._in_maintenance:
            self._last_tick_fuel_l = 0.0
            return

        # Increment drive time
        self._driving_time_since_last_rest += time_delta

        # Normal speed
        self.speed += random.uniform(-5, 5)
        self.speed  = max(40, min(110, self.speed))

        # Normal fuel consumption
        liters_per_km   = 0.3 + (self.speed / 1000)
        fuel_pct_per_km = (liters_per_km / 400) * 100
        fuel_consumed_pct = distance_km * fuel_pct_per_km
        
        fuel_before     = self.fuel_level
        self.fuel_level = max(0, round(self.fuel_level - fuel_consumed_pct, 3))

        self._last_tick_fuel_l = round(distance_km * liters_per_km, 4)

        actual_consumed_pct = round(fuel_before - self.fuel_level, 4)
        if actual_consumed_pct > 0:
            self._fuel_consumed_trip = round(self._fuel_consumed_trip + actual_consumed_pct, 4)

        # Temp logic
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
            # Leak is a percentage of total tank (400L)
            leak_pct = round(random.uniform(*LEAK_RATE_RANGE), 4)
            
            # Ensure we don't leak more than we have
            actual_leak_pct = min(leak_pct, self.fuel_level)
            
            self.fuel_level = max(0, round(self.fuel_level - actual_leak_pct, 3))
            self._fuel_consumed_trip = round(self._fuel_consumed_trip + actual_leak_pct, 4)
            
            # Convert percentage to liters (assuming 400L capacity)
            leak_liters = round(actual_leak_pct * 4, 4)
            self._last_tick_fuel_l = round(self._last_tick_fuel_l + leak_liters, 4)

    # ─────────────────────────────────────────────────────────────────────────
    # Public anomaly hooks
    # ─────────────────────────────────────────────────────────────────────────

    def apply_anomaly_fuel_drain(self, extra_pct: float):
        if not (self.is_resting or self.is_refueling or self._in_maintenance):
            actual_drain = min(extra_pct, self.fuel_level)
            self.fuel_level = max(0, round(self.fuel_level - actual_drain, 3))
            self._fuel_consumed_trip = round(self._fuel_consumed_trip + actual_drain, 4)
            self._last_tick_fuel_l = round(self._last_tick_fuel_l + (actual_drain * 4), 4)

    def apply_anomaly_fuel_theft(self, stolen_pct: float):
        actual_stolen = min(stolen_pct, self.fuel_level)
        self.fuel_level = max(0, round(self.fuel_level - actual_stolen, 3))
        # Theft is NOT added to _last_tick_fuel_l as it's not consumption

    # ─────────────────────────────────────────────────────────────────────────
    # Main tick
    # ─────────────────────────────────────────────────────────────────────────

    def move(self) -> dict | None:
        now = datetime.utcnow()
        time_delta = now - self._last_tick_time
        self._last_tick_time = now

        # ── Rest Cycle ──
        self._check_rest_requirements()
        self._tick_rest()

        # ── CASE 0: Maintenance ───────────────────────────────────────────────
        if self._in_maintenance:
            return {
                "truck_id":           self.truck_id,
                "latitude":           round(self._maintenance_position[0], 6) if self._maintenance_position else 0.0,
                "longitude":          round(self._maintenance_position[1], 6) if self._maintenance_position else 0.0,
                "speed":              0.0,
                "fuel_level":         self.fuel_level,
                "engine_temp":        round(self.engine_temp, 2),
                "driver_id":          self.driver_id,
                "start_city":         self.start_city,
                "end_city":           self.end_city,
                "odometer_km":        round(self._odometer_km, 2),
                "distance_km":        0.0,
                "fuel_consumed_l":    0.0,
                "refueling":          False,
                "refuel_city":        None,
                "in_maintenance":     True,
                "maintenance_type":   self._maintenance_info.get('maintenance_type') if self._maintenance_info else None,
                "maintenance_desc":   self._maintenance_info.get('description') if self._maintenance_info else None,
                "anomaly":            "none",
                "theft":              False,
                "theft_amount":       0.0,
                "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
                "fuel_refueled":      round(self._fuel_refueled, 4),
                "_anomaly_mode":      self._anomaly_mode,
                "timestamp":          (now + timedelta(hours=1)).isoformat() + "Z",
            }

        # ── CASE 1: Resting ───────────────────────────────────────────────────
        if self.is_resting:
            # When resting, truck is stationary but sends telemetry
            if self.current_index < len(self.route):
                pos = self.route[self.current_index]
            else:
                pos = (CITIES[self.end_city][0], CITIES[self.end_city][1])
            
            return {
                "truck_id":           self.truck_id,
                "latitude":           round(pos[1], 6),
                "longitude":          round(pos[0], 6),
                "speed":              0.0,
                "fuel_level":         self.fuel_level,
                "engine_temp":        round(self.engine_temp, 2),
                "driver_id":          self.driver_id,
                "start_city":         self.start_city,
                "end_city":           self.end_city,
                "odometer_km":        round(self._odometer_km, 2),
                "distance_km":        0.0,
                "fuel_consumed_l":    0.0,
                "refueling":          False,
                "refuel_city":        None,
                "in_maintenance":     False,
                "anomaly":            "none",
                "theft":              False,
                "theft_amount":       0.0,
                "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
                "fuel_refueled":      round(self._fuel_refueled, 4),
                "_anomaly_mode":      self._anomaly_mode,
                "timestamp":          (now + timedelta(hours=1)).isoformat() + "Z",
            }

        # ── CASE 2: Refueling ─────────────────────────────────────────────────
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
                "distance_km":        0.0,
                "fuel_consumed_l":    0.0,
                "refueling":          True,
                "refuel_city":        self.refuel_city,
                "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
                "fuel_refueled":      round(self._fuel_refueled, 4),
                "_anomaly_mode":      self._anomaly_mode,
                "timestamp":          (now + timedelta(hours=1)).isoformat() + "Z",
            }

        # ── CASE 3: Route finished ────────────────────────────────────────────
        if self.current_index >= len(self.route) - 1:
            return None # Simulator handles new route assignment

        # ── CASE 4: Normal movement ───────────────────────────────────────────
        current    = self.route[self.current_index]
        next_point = self.route[self.current_index + 1]

        distance = geodesic(
            (current[1],    current[0]),
            (next_point[1], next_point[0])
        ).km

        self._tick_anomaly_mode()
        self._update_physics(distance, time_delta)
        self.current_index += 1

        lat = round(next_point[1], 6)
        lon = round(next_point[0], 6)

        if self.fuel_level <= FUEL_STOP_THRESHOLD:
            self.is_refueling  = True
            self._stopped_lat  = lat
            self._stopped_lon  = lon
            self.refuel_city   = _nearest_city(lat, lon)
            self.speed         = 0.0
            self._last_tick_fuel_l = 0.0

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
            "distance_km":        round(distance, 4),
            "fuel_consumed_l":    round(self._last_tick_fuel_l, 4),
            "refueling":          self.is_refueling,
            "refuel_city":        self.refuel_city,
            "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
            "fuel_refueled":      round(self._fuel_refueled, 4),
            "_anomaly_mode":      self._anomaly_mode,
            "timestamp":          (now + timedelta(hours=1)).isoformat() + "Z",
        }
