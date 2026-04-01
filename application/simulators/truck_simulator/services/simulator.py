import time
import random
from config.settings import CITIES, UPDATE_INTERVAL
from services.route_service import get_route
from models.truck import Truck
from services.anomaly import inject_anomaly
from producers.kafka_producer import send_to_kafka
from services.validator import validate_and_seed
from services.cassandra_service import get_cassandra_service


def start_simulation(num_trucks: int):
    # Validate data and seed if needed before starting simulation
    if not validate_and_seed():
        print("⚠️  Starting simulation with potential data inconsistencies")

    # Get Cassandra service
    cassandra = get_cassandra_service()

    # Get all trucks from database
    db_trucks = cassandra.get_all_trucks()
    if not db_trucks:
        print("❌ No trucks found in database. Exiting.")
        return

    # Get available drivers
    available_drivers = cassandra.get_available_drivers()

    # Get trajets for reference (not assigned in DB since schema doesn't support it)
    all_trajets = cassandra.get_all_trajets()

    print(f"📊 Database state:")
    print(f"   Total trucks: {len(db_trucks)}")
    print(f"   Available drivers: {len(available_drivers)}")
    print(f"   Available trajets: {len(all_trajets)}")

    # Get assigned trucks (trucks that already have drivers)
    assigned_trucks = cassandra.get_assigned_trucks()

    # Create truck objects with real data from database
    trucks: list[Truck] = []
    used_driver_ids = set()

    for truck_info in db_trucks:
        truck_id = truck_info['truck_id']
        driver_id = None
        trajet_id = None

        # Check if truck already has a driver assigned
        if truck_id in assigned_trucks:
            # Get the driver from drivers table
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
                    # Assign driver to truck in database
                    cassandra.assign_driver_to_truck(driver_id, truck_id)
                    used_driver_ids.add(driver_id)
                    print(f"  ✅ Assigned driver {driver_id} to truck {truck_id}")
                    break

        # Pick a random trajet for reference (not stored in DB)
        if all_trajets:
            trajet = random.choice(all_trajets)
            trajet_id = trajet['trajet_id']
            start_city = trajet['start_city']
            end_city = trajet['end_city']
        else:
            # No trajets in database, create random route
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
                driver_id=driver_id,
                trajet_id=trajet_id
            )
            trucks.append(truck)
        else:
            print(f"⚠️  Could not get route for truck {truck_id}, skipping")

    print(f"\n✅ Started {len(trucks)} trucks with drivers from database")
    print("=" * 72 + "\n")

    # Main simulation loop
    while True:
        for truck in trucks:
            data = truck.move()
            if data is None:
                # Truck completed a route - get new route and possibly new driver
                if truck._needs_driver_change:
                    # Release current driver
                    if truck.driver_id:
                        cassandra.release_driver(truck.driver_id)
                        print(f"  👋 Driver {truck.driver_id} released from truck {truck.truck_id}")

                    # Assign new driver (30% chance, or if requested)
                    available_drivers = cassandra.get_available_drivers()
                    if available_drivers:
                        for driver in available_drivers:
                            # Don't reassign the same driver immediately
                            if driver['driver_id'] != truck.driver_id and driver.get('current_truck_id') is None:
                                new_driver_id = driver['driver_id']
                                cassandra.assign_driver_to_truck(new_driver_id, truck.truck_id)
                                truck.driver_id = new_driver_id
                                print(f"  👋 New driver {new_driver_id} assigned to truck {truck.truck_id}")
                                break

                    truck.reset_driver_change_flag()

                # Get new route
                city_names = list(CITIES.keys())
                new_end = random.choice(city_names)
                new_route = get_route(CITIES[truck.end_city], CITIES[new_end])
                if new_route:
                    truck.route = new_route
                    truck.start_city = truck.end_city
                    truck.end_city = new_end
                    truck.current_index = 0

                    # Create new trajet record
                    trajet_id = cassandra.create_trajet(
                        start_city=truck.start_city,
                        end_city=truck.end_city,
                        distance_km=0,
                        truck_id=truck.truck_id,
                        driver_id=truck.driver_id
                    )
                    truck.trajet_id = trajet_id

                continue

            # Pass the truck object so anomaly module can adjust fuel in-place
            data = inject_anomaly(data, truck)

            theft_tag = " 🚨 THEFT" if data.get("theft") else ""
            print(
                f"{data['timestamp']} | "
                f"Truck {data['truck_id']:>2} | "
                f"{data['speed']:>6.1f} km/h | "
                f"fuel {data['fuel_level']:>5.1f}% | "
                f"temp {data['engine_temp']:>5.1f}°C | "
                f"{data['anomaly']:<10}{theft_tag}"
            )
            send_to_kafka(data)

        time.sleep(UPDATE_INTERVAL)
