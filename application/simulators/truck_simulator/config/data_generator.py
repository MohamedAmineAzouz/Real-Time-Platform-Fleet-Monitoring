"""
data_generator.py
─────────────────────────────────────────────────────────────────────────────
Generates initial data for drivers, trucks, and trajets tables in Cassandra.
- NUM_DRIVERS = NUM_TRUCKS * 1.5
- Each truck is assigned to a driver
- Creates initial trajets for active trucks
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import uuid
import random
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import NUM_TRUCKS, CITIES
from services.route_service import get_route_distance

CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")

# Sample data pools
FIRST_NAMES = [
    "Ahmed", "Mohammed", "Ali", "Omar", "Hassan", "Ibrahim", "Youssef",
    "Karim", "Saïd", "Rachid", "Mustafa", "Khalid", "Abdallah", "Hamza", "Mehdi",
    "amine", "yassine", "abdellah", "abdessamad", "younes", "hicham", "mohcine",
    "ismail", "nabil", "sami", "adnane",
]

LAST_NAMES = [
    "El Amrani", "Benali", "Idrissi", "Bennani", "Tazi", "Fassi", "Ouazzani", "Chakir",
    "Berrada", "Kabbaj", "Ghazali", "Naciri", "Iraqi", "Alaoui", "Mernissi", "Tahiri",
    "Azouz", "El Yacoubi"
]

TRUCK_MODELS = [
    "Volvo FH16", "Scania R450", "Mercedes Actros", "MAN TGX", "DAF XF",
    "Iveco S-Way", "Renault T", "Freightliner Cascadia", "Peterbilt 579", "Kenworth T680"
]

TRUCK_STATUS = ["active"]
DRIVER_STATUS = ["available"]
TRAJET_STATUS = ["in_progress", "completed", "planned"]


def _connect(retries: int = 30, delay: int = 3):
    from cassandra.cluster import Cluster
    from cassandra.auth import PlainTextAuthProvider

    auth = PlainTextAuthProvider(CASSANDRA_USER, CASSANDRA_PASS) if CASSANDRA_USER else None

    for attempt in range(1, retries + 1):
        try:
            cluster = Cluster(
                [CASSANDRA_HOST],
                port=int(CASSANDRA_PORT),
                auth_provider=auth,
                connect_timeout=10,
            )
            session = cluster.connect()
            session.set_keyspace(CASSANDRA_KEYSPACE)
            print(f"✅ Connected to Cassandra: {CASSANDRA_HOST}:{CASSANDRA_PORT}/{CASSANDRA_KEYSPACE}")
            return session, cluster
        except Exception as exc:
            print(f"⏳ Waiting for Cassandra ({attempt}/{retries}): {exc}")
            time.sleep(delay)

    raise RuntimeError("❌ Cassandra did not become ready in time")


def generate_drivers(session, num_drivers: int):
    """Generate driver records."""
    print(f"  ▶ Generating {num_drivers} drivers...")

    stmt = """
        INSERT INTO drivers (driver_id, name, license_number, phone, status,
                            current_truck_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    now = datetime.utcnow()

    for i in range(num_drivers):
        driver_id = f"DRV-{i+1:04d}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        license_number = f"DL-{random.randint(100000, 999999)}"
        phone = f"+212-{random.randint(10000000, 99999999)}"
        status = random.choice(DRIVER_STATUS)
        current_truck_id = None
        
        session.execute(stmt, (
            driver_id, name, license_number, phone, status,
            current_truck_id, now, now
        ))

    print(f"    ✅ {num_drivers} drivers inserted")


def generate_trucks(session, num_trucks: int, num_drivers: int):
    """Generate truck records and assign to drivers."""
    print(f"  ▶ Generating {num_trucks} trucks...")

    stmt = """
        INSERT INTO trucks (truck_id, license_plate, model, year, status,
                           fuel_capacity, max_load_kg,
                           created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    now = datetime.utcnow()

    for i in range(num_trucks):
        truck_id = i + 1
        license_plate = f"{random.choice(['A', 'B', 'C', 'D', 'E'])}-{random.randint(1000, 9999)}-MA"
        model = random.choice(TRUCK_MODELS)
        year = random.randint(2018, 2025)
        status = random.choice(TRUCK_STATUS)
        # Assign driver (some trucks may not have a driver)
        fuel_capacity = random.choice([300.0, 400.0, 500.0, 600.0])
        max_load_kg = random.choice([20000.0, 24000.0, 26000.0, 30000.0])

        session.execute(stmt, (
            truck_id, license_plate, model, year, status,
            fuel_capacity, max_load_kg, now, now
        ))

    print(f"    ✅ {num_trucks} trucks inserted with driver assignments")


def generate_trajets(session, num_trajets: int = 10):
    """Generate random trajet records (not assigned to specific trucks/drivers)."""
    print(f"  ▶ Generating {num_trajets} trajets...")

    stmt = """
        INSERT INTO trajets (trajet_id, start_city, end_city,
                            distance_km, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    now = datetime.utcnow()
    city_list = list(CITIES.keys())

    for j in range(num_trajets):
        trajet_id = uuid.uuid4()
        start_city = random.choice(city_list)
        end_city = random.choice([c for c in city_list if c != start_city])

        # Get real distance using route service
        distance_km = get_route_distance(CITIES[start_city], CITIES[end_city])
        if distance_km is None:
            distance_km = random.uniform(100, 2000)  # Fallback

        session.execute(stmt, (
            trajet_id, start_city, end_city,
            distance_km, now, now
        ))

    print(f"    ✅ {num_trajets} trajets inserted")


def init_seed_data():
    """Main function to initialize all seed data."""
    print("\n" + "=" * 72)
    print("  Cassandra Seed Data Generator")
    print("=" * 72)
    print(f"  Configuration:")
    print(f"    NUM_TRUCKS  : {NUM_TRUCKS}")
    print(f"    NUM_DRIVERS : {int(NUM_TRUCKS * 1.5)}")
    print(f"    CITIES      : {len(CITIES)}")
    print("=" * 72)

    session, cluster = _connect()

    try:
        num_drivers = int(NUM_TRUCKS * 1.5)

        # Generate data
        generate_drivers(session, num_drivers)
        generate_trucks(session, NUM_TRUCKS, num_drivers)
        generate_trajets(session, 100)

        print("\n✅ Seed data generation completed!")
        print("=" * 72 + "\n")

    finally:
        cluster.shutdown()


if __name__ == "__main__":
    init_seed_data()
