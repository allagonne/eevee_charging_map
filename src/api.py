import requests

BASE_URL = "https://map.eeveemobility.com/api"

def get_chargers(top_left_latitude, top_left_longitude, bottom_right_latitude, bottom_right_longitude):
    """
    Fetches chargers within a given bounding box.
    """
    params = {
        "top_left_latitude": top_left_latitude,
        "top_left_longitude": top_left_longitude,
        "bottom_right_latitude": bottom_right_latitude,
        "bottom_right_longitude": bottom_right_longitude,
    }
    response = requests.get(f"{BASE_URL}/chargers", params=params)
    response.raise_for_status()  # Raise an exception for bad status codes
    return response.json()

def get_charger_details(charger_id):
    """
    Fetches details for a specific charger.
    """
    response = requests.get(f"{BASE_URL}/chargers/{charger_id}")
    response.raise_for_status()
    return response.json()
