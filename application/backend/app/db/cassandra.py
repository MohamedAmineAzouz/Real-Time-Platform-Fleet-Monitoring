
import time
import logging
from cassandra.cluster import Cluster, Session
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import ExponentialReconnectionPolicy

from app.core.config import settings

logger = logging.getLogger(__name__)

_cluster: Cluster | None = None
_session: Session | None = None



def connect() -> None:
    global _cluster, _session
    _cluster, _session = _create_connection()


def session() -> Session:
    global _cluster, _session

    if _session is not None:
        try:
            _session.execute("SELECT now() FROM system.local")
            return _session
        except Exception as exc:
            logger.warning("⚠️  Session stale, reconnecting: %s", exc)
            _reset()

    _cluster, _session = _create_connection()
    return _session


def disconnect() -> None:
    _reset()
    logger.info("Cassandra disconnected")



def _reset() -> None:
    global _cluster, _session
    _session = None
    if _cluster:
        try:
            _cluster.shutdown()
        except Exception:
            pass
        _cluster = None


def _create_connection(retries: int = 30, delay: int = 6):
    auth = (
        PlainTextAuthProvider(settings.cassandra_user, settings.cassandra_pass)
        if settings.cassandra_user else None
    )

    for attempt in range(1, retries + 1):
        try:
            cluster = Cluster(
                [settings.cassandra_host],
                port=settings.cassandra_port,
                auth_provider=auth,
                protocol_version=4,
                connect_timeout=15,
                idle_heartbeat_interval=30,
                idle_heartbeat_timeout=10,
                reconnection_policy=ExponentialReconnectionPolicy(
                    base_delay=1, max_delay=60
                ),
            )

            sess = cluster.connect()

            _wait_for_keyspace(sess)

            sess.set_keyspace(settings.cassandra_keyspace)
            sess.default_timeout = 10.0
            sess.default_fetch_size = 200

            logger.info(
                "✅ Cassandra  %s:%s  keyspace=%s",
                settings.cassandra_host, settings.cassandra_port,
                settings.cassandra_keyspace,
            )
            return cluster, sess

        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning("⏳ Cassandra not ready (%s/%s): %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(delay)

    raise RuntimeError(
        f"❌ Could not connect to Cassandra at "
        f"{settings.cassandra_host}:{settings.cassandra_port}"
    )


def _wait_for_keyspace(sess: Session, max_attempts: int = 24, delay: int = 5) -> None:
    for attempt in range(1, max_attempts + 1):
        row = sess.execute(
            "SELECT keyspace_name FROM system_schema.keyspaces "
            "WHERE keyspace_name = %s",
            (settings.cassandra_keyspace,)
        ).one()
        if row:
            return
        logger.warning(
            "⏳ Keyspace '%s' not ready (%s/%s) — waiting for Spark...",
            settings.cassandra_keyspace, attempt, max_attempts
        )
        time.sleep(delay)

    raise RuntimeError(
        f"Keyspace '{settings.cassandra_keyspace}' never appeared. "
        "Ensure the speed-layer ran successfully."
    )