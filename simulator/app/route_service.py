import requests

def get_route(start, end):
    url = f"http://router.project-osrm.org/route/v1/driving/{start[0]},{start[1]};{end[0]},{end[1]}?overview=full&geometries=geojson"
    response = requests.get(url)
    data = response.json()

    if "routes" not in data:
        return []

    return data["routes"][0]["geometry"]["coordinates"]
