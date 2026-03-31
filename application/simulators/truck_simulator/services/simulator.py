import time
import random
from config.settings import CITIES, UPDATE_INTERVAL
from services.route_service import get_route
from models.truck import Truck
from services.anomaly import inject_anomaly
from producers.kafka_producer import send_to_kafka
from services.validator import validate_and_seed


def start_simulation(num_trucks: int):
    # Validate data and seed if needed before starting simulation
    if not validate_and_seed():
        print("⚠️  Starting simulation with potential data inconsistencies")
    city_names = list(CITIES.keys())
    trucks: list[Truck] = []

    for i in range(num_trucks):
        start_city = random.choice(city_names)
        end_city   = random.choice([c for c in city_names if c != start_city])

        route = get_route(CITIES[start_city], CITIES[end_city])
        if route:
            trucks.append(Truck(i, route, start_city, end_city))
        else:
            print(f"⚠️  Could not get route for truck {i}, skipping")

    print(f"✅  Started {len(trucks)} trucks")

    while True:
        for truck in trucks:
            data = truck.move()
            if data is None:
                continue  # truck is getting a new route

            # Pass the truck object so anomaly module can adjust fuel in-place
            data = inject_anomaly(data, truck)

            theft_tag = " 🚨 THEFT" if data.get("theft") else ""
            print(
                f"{data['timestamp']} | "  # ADD THIS LINE
                f"Truck {data['truck_id']:>2} | "
                f"{data['speed']:>6.1f} km/h | "
                f"fuel {data['fuel_level']:>5.1f}% | "
                f"temp {data['engine_temp']:>5.1f}°C | "
                f"{data['anomaly']:<10}{theft_tag}"
            )
            send_to_kafka(data)

        time.sleep(UPDATE_INTERVAL)