import random
from bisect import bisect_right
from datetime import datetime, timedelta

from faker import Faker
from geopy.distance import geodesic

from config.settings import CITIES, UPDATE_INTERVAL


fake = Faker()

# Refuel config
REFUEL_RATE_L_PER_MIN = 45.0
REFUEL_TARGET = 95.0
FUEL_STOP_THRESHOLD = 20.0

# Anomaly injection config
ANOMALY_START_CHANCE = 0.0001
ANOMALY_STOP_CHANCE = 0.18
ANOMALY_TYPES = ["overspeed", "overheat", "fuel_leak"]

# Fuel leak rate in liters per hour while the anomaly is active.
LEAK_RATE_L_PER_HOUR_RANGE = (2.0, 8.0)

# Rest config
MAX_DRIVE_TIME_HOURS = 9.0
MANDATORY_BREAK_MINS = 45

SHORT_BREAK_CHANCE = 0.01
SHORT_BREAK_MINS_RANGE = (5, 15)

MEAL_BREAK_CHANCE = 0.005
MEAL_BREAK_MINS_RANGE = (30, 60)

NIGHT_REST_START = 23
NIGHT_REST_END = 5

# Realistic operating envelopes for line-haul trucks.
MIN_NORMAL_SPEED_KMH = 42.0
MAX_NORMAL_SPEED_KMH = 96.0
BASE_FUEL_PER_100KM = 23.0
MAX_FUEL_PER_100KM = 45.0


def _nearest_city(lat: float, lon: float) -> str:
    best_name, best_dist = None, float("inf")
    for name, (city_lon, city_lat) in CITIES.items():
        distance = geodesic((lat, lon), (city_lat, city_lon)).km
        if distance < best_dist:
            best_dist = distance
            best_name = name
    return best_name


class Truck:
    def __init__(
        self,
        truck_id,
        route,
        start_city,
        end_city,
        driver_id=None,
        trajet_id=None,
        fuel_capacity_l=400.0,
        max_load_kg=24000.0,
    ):
        self.truck_id = truck_id
        self.driver_id = driver_id if driver_id else fake.uuid4()
        self.start_city = start_city
        self.end_city = end_city
        self.trajet_id = trajet_id

        self.fuel_capacity_l = max(float(fuel_capacity_l or 400.0), 1.0)
        self.max_load_kg = max(float(max_load_kg or 24000.0), 1000.0)
        self.current_load_kg = 0.0

        self.speed = random.uniform(62, 78)
        self.fuel_level = random.uniform(70, 96)
        self.engine_temp = random.uniform(70, 82)
        self._odometer_km = 0.0

        self.route = []
        self.current_index = 0
        self._route_segment_lengths_km = []
        self._route_cumulative_km = [0.0]
        self._route_total_km = 0.0
        self._route_progress_km = 0.0
        self._current_lon = 0.0
        self._current_lat = 0.0
        self._cruise_speed_target = random.uniform(68, 82)
        self.set_route(route, start_city=start_city, end_city=end_city, trajet_id=trajet_id)

        # Refuel state
        self.is_refueling = False
        self.refuel_city = None
        self._stopped_lat = None
        self._stopped_lon = None

        # Anomaly mode
        self._anomaly_mode: str | None = None

        # Fuel tracking
        self._trip_fuel_start = self.fuel_level
        self._fuel_consumed_trip = 0.0
        self._fuel_refueled = 0.0
        self._last_tick_fuel_l = 0.0

        # Driver change tracking
        self._completed_trajets = 0
        self._needs_driver_change = False

        # Maintenance state
        self._in_maintenance = False
        self._maintenance_info = None
        self._maintenance_position = None
        self._maintenance_check_needed = False

        # Rest state
        self.is_resting = False
        self.rest_reason = None
        self._rest_end_time: datetime | None = None
        self._driving_time_since_last_rest = timedelta(0)
        self._last_tick_time = datetime.utcnow()

    def set_route(self, route, start_city=None, end_city=None, trajet_id=None):
        if not route:
            raise ValueError("Route must contain at least one coordinate")

        if len(route) == 1:
            route = [route[0], route[0]]

        self.route = [(float(lon), float(lat)) for lon, lat in route]
        self.start_city = start_city or self.start_city
        self.end_city = end_city or self.end_city
        self.trajet_id = trajet_id if trajet_id is not None else self.trajet_id

        self._route_segment_lengths_km = []
        self._route_cumulative_km = [0.0]
        total_distance = 0.0

        for index in range(len(self.route) - 1):
            start_lon, start_lat = self.route[index]
            end_lon, end_lat = self.route[index + 1]
            segment_km = geodesic((start_lat, start_lon), (end_lat, end_lon)).km
            self._route_segment_lengths_km.append(segment_km)
            total_distance += segment_km
            self._route_cumulative_km.append(total_distance)

        self._route_total_km = total_distance
        self._route_progress_km = 0.0
        self.current_index = 0
        self._current_lon, self._current_lat = self.route[0]
        self._assign_trip_profile()

    def get_current_position(self) -> tuple[float, float]:
        return round(self._current_lat, 6), round(self._current_lon, 6)

    def _assign_trip_profile(self):
        load_ratio = random.uniform(0.35, 0.95)
        self.current_load_kg = round(self.max_load_kg * load_ratio, 1)
        self._cruise_speed_target = round(random.uniform(68.0, 84.0) - load_ratio * 6.0, 2)
        self.speed = max(MIN_NORMAL_SPEED_KMH, min(self.speed, MAX_NORMAL_SPEED_KMH))

    def _segment_index_for_progress(self, progress_km: float) -> int:
        if len(self.route) < 2:
            return 0

        clamped_progress = max(0.0, min(progress_km, self._route_total_km))
        raw_index = bisect_right(self._route_cumulative_km, clamped_progress) - 1
        return max(0, min(raw_index, len(self.route) - 2))

    def _sync_position_from_progress(self):
        if len(self.route) == 1 or self._route_total_km <= 0:
            self.current_index = 0
            self._current_lon, self._current_lat = self.route[0]
            return

        clamped_progress = max(0.0, min(self._route_progress_km, self._route_total_km))
        segment_index = self._segment_index_for_progress(clamped_progress)
        segment_start_km = self._route_cumulative_km[segment_index]
        segment_length_km = self._route_segment_lengths_km[segment_index]
        start_lon, start_lat = self.route[segment_index]
        end_lon, end_lat = self.route[segment_index + 1]

        if segment_length_km <= 0:
            progress_ratio = 0.0
        else:
            progress_ratio = (clamped_progress - segment_start_km) / segment_length_km

        self.current_index = segment_index
        self._current_lon = start_lon + (end_lon - start_lon) * progress_ratio
        self._current_lat = start_lat + (end_lat - start_lat) * progress_ratio

    def _remaining_route_km(self) -> float:
        return max(self._route_total_km - self._route_progress_km, 0.0)

    def _elapsed_since_last_tick(self, now: datetime) -> timedelta:
        elapsed = now - self._last_tick_time
        self._last_tick_time = now

        if elapsed.total_seconds() <= 0:
            return timedelta(seconds=max(UPDATE_INTERVAL, 1))

        return elapsed

    def _check_rest_requirements(self):
        now = datetime.utcnow() + timedelta(hours=1)

        if now.hour >= NIGHT_REST_START or now.hour < NIGHT_REST_END:
            if not self.is_resting:
                self.is_resting = True
                self.rest_reason = "night_rest"
                if now.hour >= NIGHT_REST_START:
                    self._rest_end_time = (now + timedelta(days=1)).replace(
                        hour=NIGHT_REST_END,
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                else:
                    self._rest_end_time = now.replace(
                        hour=NIGHT_REST_END,
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                self.speed = 0.0
                print(f"Truck {self.truck_id} entering night rest until {NIGHT_REST_END}:00")
            return

        hours_driven = self._driving_time_since_last_rest.total_seconds() / 3600.0
        if hours_driven >= MAX_DRIVE_TIME_HOURS:
            if not self.is_resting:
                self.is_resting = True
                self.rest_reason = "mandatory_break"
                self._rest_end_time = now + timedelta(minutes=MANDATORY_BREAK_MINS)
                self.speed = 0.0
                print(f"Truck {self.truck_id} taking mandatory {MANDATORY_BREAK_MINS}m driver break")
            return

        if hours_driven >= 4.0 and not self.is_resting and random.random() < MEAL_BREAK_CHANCE:
            self.is_resting = True
            self.rest_reason = "meal_break"
            duration = random.randint(*MEAL_BREAK_MINS_RANGE)
            self._rest_end_time = now + timedelta(minutes=duration)
            self.speed = 0.0
            print(f"Truck {self.truck_id} stopping for meal ({duration} mins)")
            return

        if hours_driven >= 2.0 and not self.is_resting and random.random() < SHORT_BREAK_CHANCE:
            self.is_resting = True
            self.rest_reason = "bathroom_break"
            duration = random.randint(*SHORT_BREAK_MINS_RANGE)
            self._rest_end_time = now + timedelta(minutes=duration)
            self.speed = 0.0
            print(f"Truck {self.truck_id} taking short bathroom break ({duration} mins)")

    def _tick_rest(self):
        if not self.is_resting:
            return

        now = datetime.utcnow() + timedelta(hours=1)
        if self._rest_end_time and now >= self._rest_end_time:
            print(f"Truck {self.truck_id} finished {self.rest_reason} - resuming")
            self.is_resting = False
            self.rest_reason = None
            self._rest_end_time = None
            self._driving_time_since_last_rest = timedelta(0)

    def _tick_anomaly_mode(self):
        if self._anomaly_mode is None:
            if random.random() < ANOMALY_START_CHANCE:
                self._anomaly_mode = random.choice(ANOMALY_TYPES)
        elif random.random() < ANOMALY_STOP_CHANCE:
            self._anomaly_mode = None

    def _update_speed_for_tick(self, remaining_route_km: float):
        load_ratio = self.current_load_kg / self.max_load_kg

        if self._anomaly_mode == "overspeed":
            self.speed = round(random.uniform(125, 165), 2)
            return

        if remaining_route_km < 1.0:
            target_speed = min(self._cruise_speed_target, 42.0)
        elif remaining_route_km < 5.0:
            target_speed = min(self._cruise_speed_target, 60.0)
        else:
            target_speed = self._cruise_speed_target

        target_speed += random.uniform(-4.0, 4.0)
        self.speed += (target_speed - self.speed) * 0.35 + random.uniform(-2.0, 2.0)

        speed_floor = MIN_NORMAL_SPEED_KMH - (load_ratio * 4.0)
        speed_ceiling = MAX_NORMAL_SPEED_KMH - (load_ratio * 8.0)
        self.speed = round(max(speed_floor, min(speed_ceiling, self.speed)), 2)

    def _fuel_burn_per_100km(self) -> float:
        load_ratio = self.current_load_kg / self.max_load_kg
        speed_penalty = max(0.0, self.speed - 72.0) * 0.20
        stop_go_penalty = max(0.0, 58.0 - self.speed) * 0.08
        load_penalty = load_ratio * 7.0
        thermal_penalty = max(0.0, self.engine_temp - 88.0) * 0.04

        liters_per_100km = (
            BASE_FUEL_PER_100KM
            + speed_penalty
            + stop_go_penalty
            + load_penalty
            + thermal_penalty
        )
        return max(20.0, min(liters_per_100km, MAX_FUEL_PER_100KM))

    def _consume_drive_fuel(self, distance_km: float):
        if distance_km <= 0:
            self._last_tick_fuel_l = 0.0
            return

        planned_liters = distance_km * (self._fuel_burn_per_100km() / 100.0)
        planned_pct = (planned_liters / self.fuel_capacity_l) * 100.0
        actual_pct = min(planned_pct, self.fuel_level)
        actual_liters = self.fuel_capacity_l * (actual_pct / 100.0)

        self.fuel_level = max(0.0, round(self.fuel_level - actual_pct, 3))
        self._last_tick_fuel_l = round(actual_liters, 4)

        if actual_pct > 0:
            self._fuel_consumed_trip = round(self._fuel_consumed_trip + actual_pct, 4)

    def _update_engine_temp(self):
        load_ratio = self.current_load_kg / self.max_load_kg
        target_temp = 70.0 + max(self.speed - 40.0, 0.0) * 0.22 + load_ratio * 5.5
        self.engine_temp += (target_temp - self.engine_temp) * 0.18
        self.engine_temp += random.uniform(-0.6, 0.8)
        self.engine_temp = round(max(66.0, min(98.0, self.engine_temp)), 2)

        if self._anomaly_mode == "overheat":
            self.engine_temp = round(random.uniform(103, 135), 2)

    def _apply_fuel_leak_if_needed(self, time_delta: timedelta):
        if self._anomaly_mode != "fuel_leak":
            return

        leak_rate_lph = random.uniform(*LEAK_RATE_L_PER_HOUR_RANGE)
        leak_liters = leak_rate_lph * (time_delta.total_seconds() / 3600.0)
        if leak_liters <= 0:
            return

        available_liters = self.fuel_capacity_l * (self.fuel_level / 100.0)
        actual_leak_liters = min(leak_liters, available_liters)
        if actual_leak_liters <= 0:
            return

        leak_pct = (actual_leak_liters / self.fuel_capacity_l) * 100.0
        self.fuel_level = max(0.0, round(self.fuel_level - leak_pct, 3))

    def _advance_route(self, time_delta: timedelta) -> float:
        remaining_route_km = self._remaining_route_km()
        if remaining_route_km <= 0:
            self.speed = 0.0
            self._last_tick_fuel_l = 0.0
            return 0.0

        self._driving_time_since_last_rest += time_delta
        self._update_speed_for_tick(remaining_route_km)

        hours_elapsed = time_delta.total_seconds() / 3600.0
        distance_km = min(self.speed * hours_elapsed, remaining_route_km)

        self._route_progress_km += distance_km
        self._sync_position_from_progress()
        self._odometer_km += distance_km

        self._consume_drive_fuel(distance_km)
        self._update_engine_temp()
        self._apply_fuel_leak_if_needed(time_delta)
        return round(distance_km, 4)

    def _start_refuel(self):
        self.is_refueling = True
        self.speed = 0.0
        self._stopped_lat, self._stopped_lon = self.get_current_position()
        self.refuel_city = _nearest_city(self._stopped_lat, self._stopped_lon)

    def _do_refuel_tick(self, time_delta: timedelta):
        if self._stopped_lat is None or self._stopped_lon is None:
            self._stopped_lat, self._stopped_lon = self.get_current_position()

        liters_per_second = REFUEL_RATE_L_PER_MIN / 60.0
        liters_to_add = liters_per_second * time_delta.total_seconds()
        current_liters = self.fuel_capacity_l * (self.fuel_level / 100.0)
        target_liters = self.fuel_capacity_l * (REFUEL_TARGET / 100.0)
        actual_liters = min(liters_to_add, max(target_liters - current_liters, 0.0))

        added_pct = (actual_liters / self.fuel_capacity_l) * 100.0
        if added_pct > 0:
            self.fuel_level = min(100.0, round(self.fuel_level + added_pct, 3))
            self._fuel_refueled = round(self._fuel_refueled + added_pct, 4)

        self.engine_temp = round(max(68.0, self.engine_temp - 0.4), 2)
        self._last_tick_fuel_l = 0.0

        if self.fuel_level >= REFUEL_TARGET - 0.001:
            self.is_refueling = False
            self.refuel_city = None
            self._stopped_lat = None
            self._stopped_lon = None
            self._trip_fuel_start = self.fuel_level
            self._fuel_consumed_trip = 0.0

    def apply_anomaly_fuel_drain(self, extra_pct: float):
        if self.is_resting or self.is_refueling or self._in_maintenance:
            return

        actual_drain_pct = min(extra_pct, self.fuel_level)
        if actual_drain_pct <= 0:
            return

        self.fuel_level = max(0.0, round(self.fuel_level - actual_drain_pct, 3))
        self._fuel_consumed_trip = round(self._fuel_consumed_trip + actual_drain_pct, 4)
        drain_liters = self.fuel_capacity_l * (actual_drain_pct / 100.0)
        self._last_tick_fuel_l = round(self._last_tick_fuel_l + drain_liters, 4)

    def apply_anomaly_fuel_theft(self, stolen_pct: float):
        actual_stolen_pct = min(stolen_pct, self.fuel_level)
        if actual_stolen_pct <= 0:
            return

        self.fuel_level = max(0.0, round(self.fuel_level - actual_stolen_pct, 3))

    def _stationary_payload(self, now: datetime, *, refueling=False, in_maintenance=False):
        if in_maintenance and self._maintenance_position:
            latitude, longitude = self._maintenance_position
        elif refueling and self._stopped_lat is not None and self._stopped_lon is not None:
            latitude, longitude = self._stopped_lat, self._stopped_lon
        else:
            latitude, longitude = self.get_current_position()

        return {
            "truck_id": self.truck_id,
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
            "speed": 0.0,
            "fuel_level": self.fuel_level,
            "engine_temp": round(self.engine_temp, 2),
            "driver_id": self.driver_id,
            "start_city": self.start_city,
            "end_city": self.end_city,
            "odometer_km": round(self._odometer_km, 2),
            "distance_km": 0.0,
            "fuel_consumed_l": 0.0,
            "refueling": refueling,
            "refuel_city": self.refuel_city if refueling else None,
            "in_maintenance": in_maintenance,
            "maintenance_type": self._maintenance_info.get("maintenance_type") if self._maintenance_info else None,
            "maintenance_desc": self._maintenance_info.get("description") if self._maintenance_info else None,
            "anomaly": "none",
            "theft": False,
            "theft_amount": 0.0,
            "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
            "fuel_refueled": round(self._fuel_refueled, 4),
            "_anomaly_mode": self._anomaly_mode,
            "timestamp": (now + timedelta(hours=1)).isoformat() + "Z",
        }

    def move(self) -> dict | None:
        now = datetime.utcnow()
        time_delta = self._elapsed_since_last_tick(now)

        self._check_rest_requirements()
        self._tick_rest()

        if self._in_maintenance:
            return self._stationary_payload(now, in_maintenance=True)

        if self.is_resting:
            return self._stationary_payload(now)

        if self._remaining_route_km() <= 0:
            self.speed = 0.0
            return None

        if self.is_refueling or self.fuel_level <= FUEL_STOP_THRESHOLD:
            if not self.is_refueling:
                self._start_refuel()
            self._do_refuel_tick(time_delta)
            return self._stationary_payload(now, refueling=True)

        self._tick_anomaly_mode()
        distance_km = self._advance_route(time_delta)
        latitude, longitude = self.get_current_position()

        return {
            "truck_id": self.truck_id,
            "latitude": latitude,
            "longitude": longitude,
            "speed": round(self.speed, 2),
            "fuel_level": self.fuel_level,
            "engine_temp": round(self.engine_temp, 2),
            "driver_id": self.driver_id,
            "start_city": self.start_city,
            "end_city": self.end_city,
            "odometer_km": round(self._odometer_km, 2),
            "distance_km": distance_km,
            "fuel_consumed_l": round(self._last_tick_fuel_l, 4),
            "refueling": False,
            "refuel_city": None,
            "in_maintenance": False,
            "maintenance_type": None,
            "maintenance_desc": None,
            "anomaly": "none",
            "theft": False,
            "theft_amount": 0.0,
            "fuel_consumed_trip": round(self._fuel_consumed_trip, 4),
            "fuel_refueled": round(self._fuel_refueled, 4),
            "_anomaly_mode": self._anomaly_mode,
            "timestamp": (now + timedelta(hours=1)).isoformat() + "Z",
        }
