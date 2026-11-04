import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import NUM_TRUCKS

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', '..', '..', 'processing', 'speed_layer'))

CASSANDRA_HOST     = os.getenv("CASSANDRA_HOST",     "cassandra")
CASSANDRA_PORT     = os.getenv("CASSANDRA_PORT",     "9042")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")
CASSANDRA_USER     = os.getenv("CASSANDRA_USER",     "")
CASSANDRA_PASS     = os.getenv("CASSANDRA_PASS",     "")



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
            return session, cluster
        except Exception as exc:
            print(f"⏳ Waiting for Cassandra ({attempt}/{retries}): {exc}")
            time.sleep(delay)

    raise RuntimeError("❌ Cassandra did not become ready in time")


def get_truck_count(session) -> int:
    """Get the current number of trucks in the database."""
    try:
        result = session.execute("SELECT COUNT(*) FROM trucks")
        return result.one().count
    except Exception:
        return 0


def get_driver_count(session) -> int:
    """Get the current number of drivers in the database."""
    try:
        result = session.execute("SELECT COUNT(*) FROM drivers")
        return result.one().count
    except Exception:
        return 0


def get_trajet_count(session) -> int:
    """Get the current number of trajets in the database."""
    try:
        result = session.execute("SELECT COUNT(*) FROM trajets")
        return result.one().count
    except Exception:
        return 0


def validate_and_seed():
    """
    Validate Cassandra data and generate seed data if needed.
    Returns True if validation passes, False otherwise.
    """
    print("\n" + "=" * 72)
    print("  Validating Cassandra Data")
    print("=" * 72)

    try:
        session, cluster = _connect()
    except RuntimeError as e:
        print(f"❌ {e}")
        return False

    try:
        truck_count = get_truck_count(session)
        driver_count = get_driver_count(session)
        trajet_count = get_trajet_count(session)

        print(f"  Current data:")
        print(f"    Trucks  : {truck_count}")
        print(f"    Drivers : {driver_count}")
        print(f"    Trajets : {trajet_count}")
        print(f"  Expected:")
        print(f"    Trucks  : {NUM_TRUCKS}")
        print(f"    Drivers : {int(NUM_TRUCKS * 1.5)}")
        print("-" * 72)

        # If no trucks exist, generate seed data
        if truck_count == 0:
            print("  ⚠️  No trucks found. Generating seed data...")
            cluster.shutdown()

            # Import and run data generator
            from config.data_generator import init_seed_data
            init_seed_data()

            # Reconnect and verify
            session, cluster = _connect()
            truck_count = get_truck_count(session)
            driver_count = get_driver_count(session)
            trajet_count = get_trajet_count(session)

        # Check if truck count matches expected
        if truck_count != NUM_TRUCKS:
            print(f"  ⚠️  Truck count mismatch! Expected {NUM_TRUCKS}, got {truck_count}")
            print(f"  🔄 Regenerating seed data to match NUM_TRUCKS={NUM_TRUCKS}...")
            cluster.shutdown()

            from config.data_generator import init_seed_data
            init_seed_data()

            # Reconnect and verify
            session, cluster = _connect()
            truck_count = get_truck_count(session)

        # Final verification
        if truck_count == NUM_TRUCKS:
            print(f"  ✅ Validation passed! {truck_count} trucks ready.")
            print("=" * 72 + "\n")
            return True
        else:
            print(f"  ❌ Validation failed! Expected {NUM_TRUCKS} trucks, got {truck_count}")
            print("=" * 72 + "\n")
            return False

    except Exception as e:
        print(f"  ❌ Validation error: {e}")
        print("=" * 72 + "\n")
        return False
    finally:
        cluster.shutdown()
