
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    cassandra_host:     str = os.getenv("CASSANDRA_HOST",     "cassandra")
    cassandra_port:     int = int(os.getenv("CASSANDRA_PORT", "9042"))
    cassandra_keyspace: str = os.getenv("CASSANDRA_KEYSPACE", "fleet")
    cassandra_user:     str = os.getenv("CASSANDRA_USER",     "")
    cassandra_pass:     str = os.getenv("CASSANDRA_PASS",     "")

    api_title:   str = "Fleet Monitoring API"
    api_version: str = "1.0.0"
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")


settings = Settings()