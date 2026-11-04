
from fastapi import APIRouter, Query

from app.models.truck import Alert
from app.repositories import alert_repository

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=list[Alert])
def get_all_alerts(
    limit: int = Query(default=50, ge=1, le=500, description="Number of alerts to return"),
):
    """Recent alerts across all trucks and types. Powers the alerts dashboard."""
    return alert_repository.get_all(limit)