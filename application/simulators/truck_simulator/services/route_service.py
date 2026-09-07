import time
import requests

_ROUTE_CACHE = {}
_DISTANCE_CACHE = {}


def get_route(start, end, max_retries=3):
    """
    Get the real driving route from OSRM (coordinates in [lon, lat]).
    Returns a list of coordinates or [] if route not found.
    """
    cache_key = (tuple(start), tuple(end))
    if cache_key in _ROUTE_CACHE:
        return _ROUTE_CACHE[cache_key]

    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start[0]},{start[1]};{end[0]},{end[1]}?overview=full&geometries=geojson"
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "routes" in data and data["routes"]:
                    coords = data["routes"][0]["geometry"]["coordinates"]
                    _ROUTE_CACHE[cache_key] = coords
                    return coords
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1.5)
            else:
                print(f"❌ Error fetching real route from OSRM ({start} -> {end}): {e}")

    return []


def get_route_distance(start, end, max_retries=3):
    """
    Get the real driving distance between two coordinates in km from OSRM.
    Returns distance in kilometers or None if route not found.
    """
    cache_key = (tuple(start), tuple(end))
    if cache_key in _DISTANCE_CACHE:
        return _DISTANCE_CACHE[cache_key]

    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start[0]},{start[1]};{end[0]},{end[1]}?overview=false"
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "routes" in data and data["routes"]:
                    distance_km = data["routes"][0]["distance"] / 1000.0
                    _DISTANCE_CACHE[cache_key] = distance_km
                    return distance_km
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1.5)
            else:
                print(f"❌ Error fetching distance from OSRM ({start} -> {end}): {e}")

    return None
