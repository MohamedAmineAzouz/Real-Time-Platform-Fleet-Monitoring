import random
import time
from datetime import datetime, timedelta

from config.settings import CITIES, UPDATE_INTERVAL
from models.truck import Truck
from producers.kafka_producer import send_to_kafka
from services.anomaly import inject_anomaly
from services.cassandra_service import get_cassandra_service
from services.route_service import get_route


def _build_maintenance_payload(truck: Truck) -> dict:
    maint = truck._maintenance_info
    latitude, longitude = truck._maintenance_position or truck.get_current_position()

    return {
        "truck_id": truck.truck_id,
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "speed": 0.0,
        "fuel_level": truck.fuel_level,
        "engine_temp": round(truck.engine_temp, 2),
        "driver_id": truck.driver_id,
        "start_city": truck.start_city,
        "end_city": truck.end_city,
        "odometer_km": round(truck._odometer_km, 2),
        "distance_km": 0.0,
        "fuel_consumed_l": 0.0,
        "refueling": False,
        "refuel_city": None,
        "in_maintenance": True,
        "maintenance_type": maint.get("maintenance_type") if maint else None,
        "maintenance_desc": maint.get("description") if maint else None,
        "anomaly": "none",
        "theft": False,
        "theft_amount": 0.0,
        "fuel_consumed_trip": round(truck._fuel_consumed_trip, 4),
        "fuel_refueled": round(truck._fuel_refueled, 4),
        "timestamp": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
    }


def _get_distance(city1_name, city2_name):
    from math import sin, cos, sqrt, atan2, radians
    c1 = CITIES.get(city1_name)
    c2 = CITIES.get(city2_name)
    if not c1 or not c2:
        return float('inf')
    
    # CITIES is (lon, lat)
    lon1, lat1 = radians(c1[0]), radians(c1[1])
    lon2, lat2 = radians(c2[0]), radians(c2[1])
    
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return 6371 * c # km

def _find_next_trajet(current_end_city, db_trajets):
    # 1. Look for trajets starting exactly at current_end_city
    matches = [t for t in db_trajets if t["start_city"] == current_end_city]
    if matches:
        return random.choice(matches)
    
    # 2. Find the closest start_city
    best_trajet = None
    min_dist = float('inf')
    for trajet in db_trajets:
        dist = _get_distance(current_end_city, trajet["start_city"])
        if dist < min_dist:
            min_dist = dist
            best_trajet = trajet
    return best_trajet

def start_simulation(num_trucks: int):
    cassandra = get_cassandra_service()

    db_trucks = cassandra.get_all_trucks()
    if not db_trucks:
        print("No trucks found in database. Exiting.")
        return

    all_drivers = cassandra.get_all_drivers()
    available_drivers = [driver for driver in all_drivers if driver["status"] in ("available", "resting")]

    db_trajets = cassandra.get_all_trajets()
    if not db_trajets:
        print("No trajets found in database. Exiting.")
        return

    print("Database state:")
    print(f"  Total trucks: {len(db_trucks)}")
    print(f"  Available drivers: {len(available_drivers)}")
    print(f"  Available trajets: {len(db_trajets)}")

    assigned_trucks = cassandra.get_assigned_trucks()
    maintenance_cache = cassandra.get_all_maintenance_schedules()
    current_month = datetime.now().month

    trucks: list[Truck] = []
    used_driver_ids = set()

    for truck_info in db_trucks[:num_trucks]:
        truck_id = truck_info["truck_id"]
        driver_id = None

        if truck_id in assigned_trucks:
            for driver in all_drivers:
                if driver.get("current_truck_id") == truck_id:
                    driver_id = driver["driver_id"]
                    used_driver_ids.add(driver_id)
                    print(f"Recovered driver {driver_id} for truck {truck_id} (status: {driver['status']})")
                    break

        if not driver_id and available_drivers:
            for driver in available_drivers:
                if driver["driver_id"] not in used_driver_ids:
                    driver_id = driver["driver_id"]
                    cassandra.assign_driver_to_truck(driver_id, truck_id)
                    used_driver_ids.add(driver_id)
                    print(f"Assigned new driver {driver_id} to truck {truck_id}")
                    break

        trajet = random.choice(db_trajets)
        start_city = trajet["start_city"]
        end_city = trajet["end_city"]
        trajet_id = trajet["trajet_id"]

        start_coords = CITIES.get(start_city)
        end_coords = CITIES.get(end_city)
        if not start_coords or not end_coords:
            print(f"Skipping truck {truck_id}: unknown city mapping for {start_city} -> {end_city}")
            continue

        route = get_route(start_coords, end_coords)
        if not route:
            print(f"Skipping truck {truck_id}: could not load route {start_city} -> {end_city}")
            continue

        truck = Truck(
            truck_id=truck_id,
            route=route,
            start_city=start_city,
            end_city=end_city,
            driver_id=driver_id,
            trajet_id=trajet_id,
            fuel_capacity_l=truck_info.get("fuel_capacity", 400.0),
            max_load_kg=truck_info.get("max_load_kg", 24000.0),
        )
        truck._maintenance_check_needed = True
        trucks.append(truck)

    print(f"\nStarted {len(trucks)} trucks with drivers and trajets from database")
    print("=" * 72 + "\n")

    maintenance_check_counter = 0
    month_check_interval = 21600

    while True:
        maintenance_check_counter += 1

        if maintenance_check_counter % month_check_interval == 0:
            new_month = datetime.now().month
            if new_month != current_month:
                print(f"\nMonth changed ({current_month} -> {new_month})")
                print("Refreshing maintenance schedules from database...")
                maintenance_cache = cassandra.get_all_maintenance_schedules()
                current_month = new_month
                print("Maintenance cache refreshed.\n")

        for truck in trucks:
            if truck._maintenance_check_needed or truck._in_maintenance:
                maint = cassandra.is_truck_in_maintenance(truck.truck_id, maintenance_cache)

                if maint and not truck._in_maintenance:
                    truck._in_maintenance = True
                    truck._maintenance_info = maint
                    truck._maintenance_position = truck.get_current_position()
                    print(
                        f"Truck {truck.truck_id} entered maintenance: "
                        f"{maint['maintenance_type']} ({maint['scheduled_start']} -> {maint['scheduled_end']})"
                    )
                elif not maint and truck._in_maintenance:
                    truck._in_maintenance = False
                    truck._maintenance_info = None
                    print(f"Truck {truck.truck_id} maintenance completed - resuming route")

                truck._maintenance_check_needed = False

            if truck._in_maintenance:
                data = _build_maintenance_payload(truck)
                maint_tag = " MAINTENANCE"
                print(
                    f"{data['timestamp']} | "
                    f"start city: {truck.start_city} -> end city: {truck.end_city} | "
                    f"Truck {data['truck_id']:>2} | "
                    f"{data['speed']:>6.1f} km/h | "
                    f"fuel {data['fuel_level']:>5.1f}% | "
                    f"temp {data['engine_temp']:>5.1f}C | "
                    f"{data['anomaly']:<10}{maint_tag}"
                )
                send_to_kafka(data)
                continue

            data = truck.move()
            if data is None:
                if random.random() < 0.3:
                    if truck.driver_id and str(truck.driver_id).startswith("DRV-"):
                        cassandra.release_driver(truck.driver_id)
                        print(f"Driver {truck.driver_id} released from truck {truck.truck_id}")

                    available_drivers = cassandra.get_available_drivers()
                    if available_drivers:
                        for driver in available_drivers:
                            if driver["driver_id"] != truck.driver_id and driver.get("current_truck_id") is None:
                                new_driver_id = driver["driver_id"]
                                cassandra.assign_driver_to_truck(new_driver_id, truck.truck_id)
                                truck.driver_id = new_driver_id
                                print(f"New driver {new_driver_id} assigned to truck {truck.truck_id}")
                                break

                truck._maintenance_check_needed = True

                new_trajet = _find_next_trajet(truck.end_city, db_trajets)
                start_city = new_trajet["start_city"]
                end_city = new_trajet["end_city"]
                new_route = get_route(CITIES[start_city], CITIES[end_city])
                if new_route:
                    if start_city != truck.end_city:
                        print(f"Truck {truck.truck_id} finished at {truck.end_city}. Closest start found at {start_city}. Redirecting...")
                    else:
                        print(f"Truck {truck.truck_id} continuing from {start_city} to {end_city}")
                    
                    truck.set_route(
                        new_route,
                        start_city=start_city,
                        end_city=end_city,
                        trajet_id=new_trajet["trajet_id"],
                    )
                continue

            data = inject_anomaly(data, truck)

            theft_tag = " THEFT" if data.get("theft") else ""
            maint_tag = " MAINTENANCE" if data.get("in_maintenance") else ""
            print(
                f"{data['timestamp']} | "
                f"start city: {truck.start_city} -> end city: {truck.end_city} | "
                f"Truck {data['truck_id']:>2} | "
                f"{data['speed']:>6.1f} km/h | "
                f"fuel {data['fuel_level']:>5.1f}% | "
                f"temp {data['engine_temp']:>5.1f}C | "
                f"{data['anomaly']:<10}{theft_tag}{maint_tag}"
            )
            send_to_kafka(data)

        time.sleep(UPDATE_INTERVAL)
