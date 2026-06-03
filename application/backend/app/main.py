"""
main.py

Fleet Monitoring — Backend API

Data flow:
  Simulator → Kafka → Spark → Cassandra → THIS API → Frontend

Startup sequence (lifespan):
  1. Connect to Cassandra
  2. Compile all prepared statements
  3. Ready to serve requests

"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import cassandra as db
from app.db.prepared import prepare_all
from app.api.routes import trucks, alerts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    prepare_all()
    yield
    db.disconnect()


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Real-time fleet telemetry — data served from Cassandra",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trucks.router)
app.include_router(alerts.router)


@app.get("/health", tags=["Health"])
def health():
    try:
        db.session().execute("SELECT now() FROM system.local")
        return {
            "status": "ok",
            "cassandra": f"{settings.cassandra_host}:{settings.cassandra_port}",
            "keyspace": settings.cassandra_keyspace,
        }
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"Cassandra unavailable: {exc}")