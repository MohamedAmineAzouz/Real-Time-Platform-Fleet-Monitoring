"""
models/truck.py
─────────────────────────────────────────────────────────────────────────────
Pydantic response models — one per Cassandra table.
All fields Optional so partial rows don't crash the API.
─────────────────────────────────────────────────────────────────────────────
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class TruckLatest(BaseModel):
    """
    Latest known state per truck.
    Table: fleet.truck_latest  (PRIMARY KEY: truck_id)
    """
    truck_id:               int
    processed_at:           Optional[datetime] = None
    event_time:             Optional[datetime] = None
    latitude:               Optional[float]    = None
    longitude:              Optional[float]    = None
    speed:                  Optional[float]    = None
    fuel_level:             Optional[float]    = None
    engine_temp:            Optional[float]    = None
    driver_id:              Optional[str]      = None
    start_city:             Optional[str]      = None
    end_city:               Optional[str]      = None
    odometer_km:            Optional[float]    = None
    refueling:              Optional[bool]     = None
    refuel_city:            Optional[str]      = None
    anomaly:                Optional[str]      = None
    theft:                  Optional[bool]     = None
    theft_amount:           Optional[float]    = None
    alert_type:             Optional[str]      = None
    is_alert:               Optional[bool]     = None
    distance_km:            Optional[float]    = None
    fuel_used:              Optional[float]    = None
    fuel_consumption_rate:  Optional[float]    = None
    high_consumption:       Optional[bool]     = None
    fuel_consumed_trip:     Optional[float]    = None
    fuel_refueled:          Optional[float]    = None
    # Enrichment fields (from registry)
    driver_name:            Optional[str]      = None
    truck_model:            Optional[str]      = None
    # Maintenance fields
    in_maintenance:         Optional[bool]     = None
    maintenance_type:       Optional[str]      = None
    maintenance_desc:       Optional[str]      = None


class TruckHistory(BaseModel):
    """
    24h time-series per truck.
    Table: fleet.truck_history  (PRIMARY KEY: truck_id, processed_at DESC)
    """
    truck_id:               int
    processed_at:           datetime
    event_time:             Optional[datetime] = None
    latitude:               Optional[float]    = None
    longitude:              Optional[float]    = None
    speed:                  Optional[float]    = None
    fuel_level:             Optional[float]    = None
    engine_temp:            Optional[float]    = None
    driver_id:              Optional[str]      = None
    start_city:             Optional[str]      = None
    end_city:               Optional[str]      = None
    odometer_km:            Optional[float]    = None
    refueling:              Optional[bool]     = None
    anomaly:                Optional[str]      = None
    theft:                  Optional[bool]     = None
    alert_type:             Optional[str]      = None
    is_alert:               Optional[bool]     = None
    distance_km:            Optional[float]    = None
    fuel_consumption_rate:  Optional[float]    = None
    high_consumption:       Optional[bool]     = None


class Alert(BaseModel):
    """
    Alert events (7-day TTL).
    Table: fleet.alerts  (PRIMARY KEY: (truck_id, alert_type), processed_at DESC)
    """
    truck_id:               int
    alert_type:             str
    processed_at:           datetime
    event_time:             Optional[datetime] = None
    latitude:               Optional[float]    = None
    longitude:              Optional[float]    = None
    speed:                  Optional[float]    = None
    fuel_level:             Optional[float]    = None
    engine_temp:            Optional[float]    = None
    driver_id:              Optional[str]      = None
    anomaly:                Optional[str]      = None
    theft:                  Optional[bool]     = None
    theft_amount:           Optional[float]    = None
    distance_km:            Optional[float]    = None
    fuel_consumption_rate:  Optional[float]    = None