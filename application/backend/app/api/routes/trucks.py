"""
api/routes/trucks.py
GET /trucks                          all trucks latest state (live map)
GET /trucks/{truck_id}               single truck
GET /trucks/{truck_id}/history       telemetry time-series
GET /trucks/{truck_id}/alerts        alerts for one truck
GET /trucks/{truck_id}/prediction    AI maintenance prediction
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.models.truck import TruckLatest, TruckHistory, Alert, MaintenancePrediction
from app.repositories import truck_repository, alert_repository

router = APIRouter(prefix="/trucks", tags=["Trucks"])


@router.get("", response_model=list[TruckLatest])
def get_all_trucks():
    """Latest position + telemetry for every truck. Powers the live map."""
    return truck_repository.get_all()


@router.get("/{truck_id}", response_model=TruckLatest)
def get_truck(truck_id: int):
    """Latest state for a single truck."""
    truck = truck_repository.get_by_id(truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail=f"Truck {truck_id} not found")
    return truck


@router.get("/{truck_id}/history", response_model=list[TruckHistory])
def get_truck_history(
    truck_id: int,
    period: str = Query(default="24h", description="24h | 7d | 30d | this_month"),
    limit: int = Query(default=1000, ge=1, le=5000, description="Number of events to return"),
):
    """Telemetry events for a specific period. newest first."""
    return truck_repository.get_history(truck_id, period, limit)


@router.get("/{truck_id}/alerts", response_model=list[Alert])
def get_truck_alerts(
    truck_id: int,
    alert_type: Optional[str] = Query(
        default=None,
        description="OVERSPEED | OVERHEAT | FUEL_THEFT | FUEL_LEAK | LOW_FUEL",
    ),
    limit: int = Query(default=50, ge=1, le=500),
):
    """Alerts for a specific truck, optionally filtered by type."""
    return alert_repository.get_by_truck(truck_id, alert_type, limit)


@router.get("/{truck_id}/prediction", response_model=Optional[MaintenancePrediction])
def get_truck_maintenance_prediction(truck_id: int):
    """Fetch the latest AI maintenance prediction for this truck."""
    prediction = truck_repository.get_maintenance_prediction(truck_id)
    if not prediction:
        return None
    return prediction
