import time
import random
from datetime import datetime, timedelta
from config.settings import CITIES, UPDATE_INTERVAL
from services.route_service import get_route
from models.truck import Truck
from services.anomaly import inject_anomaly
from producers.kafka_producer import send_to_kafka
from services.cassandra_service import get_cassandra_service


def start_simulation(num_trucks: int):
    # Validate data and seed if needed before starting simulation

    # Get Cassandra service
    cassandra = get_cassandra_service()

    # Get all trucks from database
    db_trucks = cassandra.get_all_trucks()
    if not db_trucks:
        print("❌ No trucks found in database. Exiting.")
        return

    # Get available drivers
    available_drivers = cassandra.get_available_drivers()

    print(f"📊 Database state:")
    print(f"   Total trucks: {len(db_trucks)}")
    print(f"   Available drivers: {len(available_drivers)}")

    # Get assigned trucks (trucks that already have drivers)
    assigned_trucks = cassandra.get_assigned_trucks()

    # Load ALL maintenance schedules into memory (ONCE per month)
    # DAG generates data on the 30th for next month - cache it
    maintenance_cache = cassandra.get_all_maintenance_schedules()
    current_month = datetime.now().month  # Track for monthly refresh

    # Create truck objects with real data from database
    trucks: list[Truck] = []
    used_driver_ids = set()

    for truck_info in db_trucks:
        truck_id = truck_info['truck_id']
        driver_id = None

        # Check if truck already has a driver assigned
        if truck_id in assigned_trucks:
            for driver in available_drivers:
                if driver.get('current_truck_id') == truck_id:
                    driver_id = driver['driver_id']
                    used_driver_ids.add(driver_id)
                    break

        # If no driver assigned, try to assign one
        if not driver_id and available_drivers:
            for driver in available_drivers:
                if driver['driver_id'] not in used_driver_ids and driver.get('current_truck_id') is None:
                    driver_id = driver['driver_id']
                    cassandra.assign_driver_to_truck(driver_id, truck_id)
                    used_driver_ids.add(driver_id)
                    print(f"  ✅ Assigned driver {driver_id} to truck {truck_id}")
                    break

        # Random route
        start_city = random.choice(list(CITIES.keys()))
        end_city = random.choice([c for c in CITIES.keys() if c != start_city])

        # Get route coordinates
        route = get_route(CITIES[start_city], CITIES[end_city])
        if route:
            truck = Truck(
                truck_id=truck_id,
                route=route,
                start_city=start_city,
                end_city=end_city,
                driver_id=driver_id
            )
            truck._maintenance_check_needed = True  # Check on first tick
            trucks.append(truck)
        else:
            print(f"⚠️  Could not get route for truck {truck_id}, skipping")

    print(f"\n✅ Started {len(trucks)} trucks with drivers from database")
    print("=" * 72 + "\n")

    # Main simulation loop
    maintenance_check_counter = 0
    MONTH_CHECK_INTERVAL = 	21600  # Check month change every 12 hours (21600 × 2s)

    while True:
        maintenance_check_counter += 1

        # ── Automatic monthly maintenance cache refresh ──
        if maintenance_check_counter % MONTH_CHECK_INTERVAL == 0:
            new_month = datetime.now().month
            if new_month != current_month:
                print(f"\n📅 Month changed ({current_month} → {new_month})")
                print("🔄 Refreshing maintenance schedules from database...")
                maintenance_cache = cassandra.get_all_maintenance_schedules()
                current_month = new_month
                print("✅ Maintenance cache refreshed!\n")

        for truck in trucks:
            # Check maintenance on route completion OR while currently in maintenance
            # (Must keep checking cache to detect when maintenance time ends)
            if truck._maintenance_check_needed or truck._in_maintenance:
                maint = cassandra.is_truck_in_maintenance(truck.truck_id, maintenance_cache)

                if maint and not truck._in_maintenance:
                    truck._in_maintenance = True
                    truck._maintenance_info = maint
                    if truck.current_index < len(truck.route):
                        pos = truck.route[truck.current_index]
                        truck._maintenance_position = (pos[1], pos[0])
                    else:
                        truck._maintenance_position = (CITIES[truck.end_city][1], CITIES[truck.end_city][0])
                    print(f"  🔧 Truck {truck.truck_id} entered maintenance: {maint['maintenance_type']}")
                    print(f"     Mechanic: {maint['assigned_mechanic']} | Duration: {maint['scheduled_start']} → {maint['scheduled_end']}")

                elif not maint and truck._in_maintenance:
                    truck._in_maintenance = False
                    truck._maintenance_info = None
                    print(f"  ✅ Truck {truck.truck_id} maintenance completed - resuming route")

                truck._maintenance_check_needed = False

            # ── Truck in maintenance - return status only ──
            if truck._in_maintenance:
                maint = truck._maintenance_info
                data = {
                    "truck_id":           truck.truck_id,
                    "latitude":           round(truck._maintenance_position[0], 6),
                    "longitude":          round(truck._maintenance_position[1], 6),
                    "speed":              0.0,
                    "fuel_level":         truck.fuel_level,
                    "engine_temp":        round(truck.engine_temp, 2),
                    "driver_id":          truck.driver_id,
                    "start_city":         truck.start_city,
                    "end_city":           truck.end_city,
                    "odometer_km":        round(truck._odometer_km, 2),
                    "refueling":          False,
                    "refuel_city":        None,
                    "in_maintenance":     True,
                    "maintenance_type":   maint.get('maintenance_type') if maint else None,
                    "maintenance_desc":   maint.get('description') if maint else None,
                    "anomaly":            "none",
                    "theft":              False,
                    "theft_amount":       0.0,
                    "fuel_consumed_trip": round(truck._fuel_consumed_trip, 4),
                    "fuel_refueled":      round(truck._fuel_refueled, 4),
                    "timestamp":          (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
                }
                maint_tag = " 🔧 MAINTENANCE"
                print(
                    f"{data['timestamp']} | "
                    f"Truck {data['truck_id']:>2} | "
                    f"{data['speed']:>6.1f} km/h | "
                    f"fuel {data['fuel_level']:>5.1f}% | "
                    f"temp {data['engine_temp']:>5.1f}°C | "
                    f"{data['anomaly']:<10}{maint_tag}"
                )
                send_to_kafka(data)
                continue

            data = truck.move()
            if data is None:
                # Truck completed a route - 30% chance to change driver
                if random.random() < 0.3:
                    # Release current driver
                    if truck.driver_id:
                        cassandra.release_driver(truck.driver_id)
                        print(f"  👋 Driver {truck.driver_id} released from truck {truck.truck_id}")

                    # Assign new driver
                    available_drivers = cassandra.get_available_drivers()
                    if available_drivers:
                        for driver in available_drivers:
                            if driver['driver_id'] != truck.driver_id and driver.get('current_truck_id') is None:
                                new_driver_id = driver['driver_id']
                                cassandra.assign_driver_to_truck(new_driver_id, truck.truck_id)
                                truck.driver_id = new_driver_id
                                print(f"  👋 New driver {new_driver_id} assigned to truck {truck.truck_id}")
                                break

                # Check maintenance status when route completes
                truck._maintenance_check_needed = True

                # Get new route
                city_names = list(CITIES.keys())
                new_end = random.choice(city_names)
                new_route = get_route(CITIES[truck.end_city], CITIES[new_end])
                if new_route:
                    truck.route = new_route
                    truck.start_city = truck.end_city
                    truck.end_city = new_end
                    truck.current_index = 0

                continue

            # Pass the truck object so anomaly module can adjust fuel in-place
            data = inject_anomaly(data, truck)

            theft_tag = " 🚨 THEFT" if data.get("theft") else ""
            maint_tag = " 🔧 MAINTENANCE" if data.get("in_maintenance") else ""
            print(
                f"{data['timestamp']} | "
                f"Truck {data['truck_id']:>2} | "
                f"{data['speed']:>6.1f} km/h | "
                f"fuel {data['fuel_level']:>5.1f}% | "
                f"temp {data['engine_temp']:>5.1f}°C | "
                f"{data['anomaly']:<10}{theft_tag}{maint_tag}"
            )
            send_to_kafka(data)

        time.sleep(UPDATE_INTERVAL)
