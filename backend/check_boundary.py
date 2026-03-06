import os
import json
import requests
from shapely.geometry import Point, shape

def is_in_india(lat, lon):
    geojson_path = "india_boundary.geojson"
    
    # 1. Download the file only if we don't already have it
    if not os.path.exists(geojson_path):
        print("Downloading India boundary file (this only happens once)...")
        # Reliable URL for India's state outlines
        url = "https://raw.githubusercontent.com/geohacker/india/master/state/india_state.geojson"
        try:
            response = requests.get(url)
            response.raise_for_status() # Raise an error if download fails
            
            with open(geojson_path, 'w') as f:
                json.dump(response.json(), f)
            print("Download complete!")
            
        except Exception as e:
            return f"Failed to download map: {e}"
            
    # 2. Read the local file and check the coordinates
    try:
        with open(geojson_path, 'r') as f:
            data = json.load(f)
            
        # Shapely uses (Longitude, Latitude) order for coordinates
        user_point = Point(lon, lat) 
        
        # Check if the point is inside any Indian state
        for feature in data['features']:
            state_polygon = shape(feature['geometry'])
            if state_polygon.contains(user_point):
                return True
                
        return False # If it loops through all states and doesn't find it
        
    except Exception as e:
         return f"Error reading map: {e}"

# --- Test the boundary function ---
test_lat_1, test_lon_1 = 18.8756, 79.4451
print(f"\nTesting Mancherial (Lat: {test_lat_1}, Lon: {test_lon_1})")
result1 = is_in_india(test_lat_1, test_lon_1)
print(f"Result: {result1}")

test_lat_2, test_lon_2 = 51.5072, -0.1276
print(f"\nTesting London (Lat: {test_lat_2}, Lon: {test_lon_2})")
result2 = is_in_india(test_lat_2, test_lon_2)
print(f"Result: {result2}")