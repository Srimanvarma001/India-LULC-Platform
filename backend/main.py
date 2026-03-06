from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse # Added StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import rasterio
from pyproj import Transformer
from shapely.geometry import Point, shape
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse # NEW: Required for file downloading
from fastapi.middleware.cors import CORSMiddleware
import zipfile # Added for zipping
import io      # Added for handling the zip in memory
# ... the rest of your imports

# Initialize the web server with metadata
app = FastAPI(
    title="India LULC Temporal Analysis Platform",
    description="Analyze 24 years of Land Use/Land Cover (MODIS MCD12Q1) change across India.",
    version="1.1.0"
)

# Enable CORS for frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. Definitive LULC Color Palette & Legend definitions ---
# This is derived from standard USGS/NASA MODIS IGBP color palettes
LULC_PALETTE = {
    1:  {"name": "Evergreen Needleleaf Forest", "color": "#005a00"},
    2:  {"name": "Evergreen Broadleaf Forest", "color": "#006400"},
    3:  {"name": "Deciduous Needleleaf Forest", "color": "#1e821e"},
    4:  {"name": "Deciduous Broadleaf Forest", "color": "#3cb371"},
    5:  {"name": "Mixed Forest", "color": "#32cd32"},
    6:  {"name": "Closed Shrublands", "color": "#a0522d"},
    7:  {"name": "Open Shrublands", "color": "#d2b48c"},
    8:  {"name": "Woody Savannas", "color": "#b8860b"},
    9:  {"name": "Savannas", "color": "#ffd700"},
    10: {"name": "Grasslands", "color": "#9acd32"},
    11: {"name": "Permanent Wetlands", "color": "#4682b4"},
    12: {"name": "Croplands", "color": "#f0e68c"}, # User clicked near desert canal irrigated agriculture
    13: {"name": "Urban and Built-Up", "color": "#ff0000"},
    14: {"name": "Cropland/Natural Vegetation Mosaic", "color": "#bdb76b"},
    15: {"name": "Snow and Ice", "color": "#b0c4de"},
    16: {"name": "Barren or Sparsely Vegetated", "color": "#eee8aa"}, # Rajasthan main cover
    17: {"name": "Water Bodies", "color": "#0000cd"}
}


# --- 2. Efficient Boundary Checker (Now with State Info) ---
# We load this once on startup, not every time a request is made.
GEOJSON_PATH = "india_boundary.geojson"
INDIA_STATE_SHAPES = None

try:
    if os.path.exists(GEOJSON_PATH):
        with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            INDIA_STATE_SHAPES = []
            for feature in data['features']:
                props = feature.get('properties', {})
                # Safely try multiple common keys for the state name, or use a default
                state_name = props.get('ST_NM') or props.get('NAME_1') or props.get('name') or props.get('ADMIN') or "India Map Region"
                
                INDIA_STATE_SHAPES.append({
                    "name": state_name,
                    "shape": shape(feature['geometry'])
                })
                
        print(f"Successfully loaded {len(INDIA_STATE_SHAPES)} India map regions.")
    else:
        print("CRITICAL ERROR: 'india_boundary.geojson' is missing. The system will fail India checks.")
except Exception as e:
    print(f"ERROR loading boundary data: {e}")


def is_in_india(lat, lon):
    if not INDIA_STATE_SHAPES:
        return {"error": "Internal map data error. Contact Admin."}
    
    user_point = Point(lon, lat) 
    # Check all state polygons
    for state in INDIA_STATE_SHAPES:
        if state['shape'].contains(user_point):
            return {"in_india": True, "state": state['name']}
            
    return {"in_india": False}
# --- 3. Optimized GeoTIFF Temporal Logic (Now returns color data) ---
def get_time_series_lulc(dataset_folder, lat, lon):
    timeline_data = []
    
    if not os.path.exists(dataset_folder):
        return {"error": f"Cannot find dataset folder '{dataset_folder}'"}

    # Optimization: Open datasets sequentially to minimize memory load
    tif_files = [f for f in os.listdir(dataset_folder) if f.endswith(".tif")]
    
    # Pre-configure Transformer once
    first_tif = os.path.join(dataset_folder, tif_files[0])
    with rasterio.open(first_tif) as ds:
        transformer = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        transformed_point = transformer.transform(lon, lat)

    print(f"Sampling {len(tif_files)} years of data for {lat}, {lon}...")

    # We reuse the transformed point for all files. 
    for filename in tif_files:
        file_path = os.path.join(dataset_folder, filename)
        
        try:
            year = int(filename.split('doy')[1][:4])
            with rasterio.open(file_path) as dataset:
                sample_generator = dataset.sample([transformed_point])
                pixel_value = int(list(sample_generator)[0][0])
                
                # Retrieve the full palette info for this pixel value
                class_info = LULC_PALETTE.get(pixel_value, {"name": "Unknown", "color": "#808080"})
                
                timeline_data.append({
                    "year": year, 
                    "lulc_name": class_info['name'], 
                    "lulc_color": class_info['color'] # Now sending color code too
                })
        except Exception:
            # Silently skip files that are locked or corrupt
            continue
    
    return sorted(timeline_data, key=lambda k: k['year'])



# --- 4. The Main API Endpoints ---
@app.get("/")
def welcome():
    return {"message": "India Land Use Land Cover API. Use /docs for documentation or /api/legend for palette codes."}

# New endpoint: Get the master legend (useful for frontend legend generation)
@app.get("/api/legend")
def get_legend():
    return LULC_PALETTE

@app.get("/api/lulc")
def get_lulc_data(lat: float, lon: float):
    # Decision Gate 1: Check if inside India (this uses pre-loaded data for speed)
    india_status = is_in_india(lat, lon)
    
    if "error" in india_status:
        raise HTTPException(status_code=500, detail=india_status['error'])
        
    if not india_status['in_india']:
        raise HTTPException(status_code=400, detail="Click outside of Indian borders. Map only covers India.")

    # Decision Gate 2: Get the satellite history
    folder_path = "../../indian_dataset" 
    timeline_data = get_time_series_lulc(folder_path, lat, lon)

    if isinstance(timeline_data, dict) and "error" in timeline_data:
        raise HTTPException(status_code=500, detail=timeline_data['error'])

    return {
        "status": "success",
        "location": {
            "lat": lat, 
            "lon": lon, 
            "state_detected": india_status['state']
        },
        "temporal_timeline": timeline_data
    }
    
    
    # --- NEW ENDPOINT: Download raw GeoTIFF ---
@app.get("/api/download-tiff")
def download_tiff(year: int):
    folder_path = "../../indian_dataset"
    
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=500, detail="Dataset folder not found.")

    # Search the folder for the file matching the requested year
    for filename in os.listdir(folder_path):
        if filename.endswith(".tif") and f"doy{year}" in filename:
            file_path = os.path.join(folder_path, filename)
            # FileResponse automatically handles sending the heavy file to the browser
            return FileResponse(path=file_path, filename=filename, media_type='image/tiff')
            
    raise HTTPException(status_code=404, detail=f"No GeoTIFF file found for the year {year}.")
# --- NEW ENDPOINT: Download ALL GeoTIFFs as a ZIP ---
@app.get("/api/download-all-tiffs")
def download_all_tiffs():
    folder_path = "../../indian_dataset"
    
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=500, detail="Dataset folder not found.")

    # Create a temporary zip file in the server's memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename in os.listdir(folder_path):
            if filename.endswith(".tif"):
                file_path = os.path.join(folder_path, filename)
                # Add each file to the zip folder
                zip_file.write(file_path, arcname=filename)
    
    # Reset the buffer's position to the beginning before sending
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer, 
        media_type="application/zip", 
        headers={"Content-Disposition": "attachment; filename=India_LULC_All_Years.zip"}
    )