import os
import rasterio
from pyproj import Transformer

def get_time_series_lulc(dataset_folder, lat, lon):
    lulc_classes = {
        1: "Evergreen Needleleaf Forests", 2: "Evergreen Broadleaf Forests",
        3: "Deciduous Needleleaf Forests", 4: "Deciduous Broadleaf Forests",
        5: "Mixed Forests", 6: "Closed Shrublands", 7: "Open Shrublands",
        8: "Woody Savannas", 9: "Savannas", 10: "Grasslands",
        11: "Permanent Wetlands", 12: "Croplands", 13: "Urban and Built-up Lands",
        14: "Cropland/Natural Vegetation Mosaics", 15: "Snow and Ice",
        16: "Barren", 17: "Water Bodies"
    }

    timeline_data = []

    # Check if folder exists
    if not os.path.exists(dataset_folder):
        return f"Error: Cannot find folder {dataset_folder}"

    # Loop through every file in your dataset folder
    for filename in os.listdir(dataset_folder):
        if filename.endswith(".tif"):
            file_path = os.path.join(dataset_folder, filename)
            
            # Extract the year from the filename (e.g., finding '2009' right after 'doy')
            try:
                year_str = filename.split('doy')[1][:4]
                year = int(year_str)
            except (IndexError, ValueError):
                year = 0 # Default if filename format is weird

            try:
                with rasterio.open(file_path) as dataset:
                    transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                    x, y = transformer.transform(lon, lat)
                    
                    sample_generator = dataset.sample([(x, y)])
                    pixel_value = list(sample_generator)[0][0]
                    class_name = lulc_classes.get(pixel_value, f"Unknown ({pixel_value})")
                    
                    # Add this year's data to our list
                    timeline_data.append({"Year": year, "LULC": class_name})
            except Exception as e:
                print(f"Skipping {filename} due to error: {e}")

    # Sort the list chronologically by year before returning
    timeline_data = sorted(timeline_data, key=lambda k: k['Year'])
    return timeline_data

# --- Test the multi-year function ---
folder_path = "../../indian_dataset" 

# Testing coordinates for Mancherial, Telangana
test_lat = 18.8756  
test_lon = 79.4451  

print(f"Scanning all years for Lat: {test_lat}, Lon: {test_lon}...\n")
results = get_time_series_lulc(folder_path, test_lat, test_lon)

# Print the final timeline nicely formatted
for entry in results:
    print(f"Year: {entry['Year']} | Classification: {entry['LULC']}")