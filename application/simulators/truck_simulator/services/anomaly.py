import random

THEFT_CHANCE       = 0.0003
THEFT_AMOUNT_RANGE = (0.8, 2.5)


def inject_anomaly(data: dict, truck) -> dict:
    if data.get("refueling"):
        data["anomaly"] = "none"
        data["theft"]   = False
        data.pop("_anomaly_mode", None)
        return data

    anomaly = data.pop("_anomaly_mode", "none")
    if anomaly is None:
        anomaly = "none"
        
    theft_event = False

    if data["speed"] <= 2.0 and data["fuel_level"] > 5 and random.random() < THEFT_CHANCE:
        stolen = round(random.uniform(*THEFT_AMOUNT_RANGE), 2)
        stolen = min(stolen, data["fuel_level"] - 1)
        truck.apply_anomaly_fuel_theft(stolen)
        data["fuel_level"]  = truck.fuel_level
        data["theft_amount"] = stolen
        theft_event = True
        data["fuel_stolen_pct"] = stolen
    else:
        data["fuel_stolen_pct"] = 0.0

    data["anomaly"] = anomaly
    data["theft"]   = theft_event
    return data
