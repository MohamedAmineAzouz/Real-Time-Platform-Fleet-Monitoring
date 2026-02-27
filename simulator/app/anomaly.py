import random

# ── Fuel-theft event (still random, independent) ──────────────────────────────
THEFT_CHANCE       = 0.004
THEFT_AMOUNT_RANGE = (8, 20)


def inject_anomaly(data: dict, truck) -> dict:
    """
    anomaly.py is now a thin pass-through:
    - The anomaly type is already decided by truck._anomaly_mode (set in truck.py)
    - The physics (speed, temp, fuel drain) are already applied by _update_physics()
    - This module just: reads the mode, handles theft, and writes data["anomaly"]
    """

    # ── Skip while refueling ──────────────────────────────────────────────────
    if data.get("refueling"):
        data["anomaly"] = "none"
        data["theft"]   = False
        data.pop("_anomaly_mode", None)
        return data

    # ── Read anomaly mode that truck.py already decided ───────────────────────
    anomaly = data.pop("_anomaly_mode", "none")   # consume internal field

    # ── Fuel theft (independent one-shot event) ───────────────────────────────
    theft_event = False
    if data["fuel_level"] > 5 and random.random() < THEFT_CHANCE:
        stolen = round(random.uniform(*THEFT_AMOUNT_RANGE), 2)
        stolen = min(stolen, data["fuel_level"] - 1)
        truck.apply_anomaly_fuel_theft(stolen)
        data["fuel_level"]  = truck.fuel_level
        theft_event         = True
        data["theft_amount"] = stolen

    # ── Annotate ──────────────────────────────────────────────────────────────
    data["anomaly"] = anomaly
    data["theft"]   = theft_event

    return data