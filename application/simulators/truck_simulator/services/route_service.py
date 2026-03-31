import requests

def get_route(start, end):
    url = f"http://router.project-osrm.org/route/v1/driving/{start[0]},{start[1]};{end[0]},{end[1]}?overview=full&geometries=geojson"
    response = requests.get(url)
    data = response.json()

    if "routes" not in data:
        return []

    return data["routes"][0]["geometry"]["coordinates"]


def get_route_distance(start, end):
    """
    Get the real driving distance between two coordinates in km.
    Returns distance in kilometers or None if route not found.
    """
    url = f"http://router.project-osrm.org/route/v1/driving/{start[0]},{start[1]};{end[0]},{end[1]}?overview=false"
    response = requests.get(url, timeout=10)
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    
    if "routes" not in data or not data["routes"]:
        return None
    
    # OSRM returns distance in meters
    distance_meters = data["routes"][0]["distance"]
    return distance_meters / 1000.0  # Convert to km
