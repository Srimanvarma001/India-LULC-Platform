import os
import json
import io
import zipfile
import rasterio
import rasterio.mask
from rasterio.io import MemoryFile
import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform
from config import GEOJSON_PATH, DATASET_FOLDER, LULC_PALETTE

INDIA_STATE_SHAPES = []

try:
    if os.path.exists(GEOJSON_PATH):
        with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for feature in data['features']:
                props = feature.get('properties', {})
                state_name = props.get('ST_NM') or props.get('NAME_1') or props.get('name') or props.get('ADMIN') or "India Map Region"
                INDIA_STATE_SHAPES.append({"name": state_name, "shape": shape(feature['geometry'])})
except Exception as e:
    print(f"GeoEngine ERROR loading boundary data: {e}")

def check_coordinates_in_india(lat, lon):
    if not INDIA_STATE_SHAPES: return {"error": "Internal map data error."}
    user_point = Point(lon, lat) 
    for state in INDIA_STATE_SHAPES:
        if state['shape'].contains(user_point): return {"in_india": True, "state": state['name']}
    return {"in_india": False}

def extract_point_timeline(lat, lon):
    timeline_data = []
    if not os.path.exists(DATASET_FOLDER): return {"error": "Dataset folder not found"}
    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif")]
    if not tif_files: return {"error": "No .tif files found."}
        
    first_tif = os.path.join(DATASET_FOLDER, tif_files[0])
    with rasterio.open(first_tif) as ds:
        transformer = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        transformed_point = transformer.transform(lon, lat)

    for filename in tif_files:
        try:
            year = int(filename.split('doy')[1][:4])
            with rasterio.open(os.path.join(DATASET_FOLDER, filename)) as dataset:
                sample_generator = dataset.sample([transformed_point])
                pixel_value = int(list(sample_generator)[0][0])
                class_info = LULC_PALETTE.get(pixel_value, {"name": "Unknown", "color": "#808080"})
                timeline_data.append({"year": year, "lulc_name": class_info['name'], "lulc_color": class_info['color']})
        except Exception: continue 
    return sorted(timeline_data, key=lambda k: k['year'])

def extract_polygon_stats(geo_polygon_dict):
    if not os.path.exists(DATASET_FOLDER): return {"error": "Dataset folder not found"}
    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif")]
    
    user_poly = shape(geo_polygon_dict)
    first_tif = os.path.join(DATASET_FOLDER, tif_files[0])
    with rasterio.open(first_tif) as src:
        project = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform
    projected_poly = transform(project, user_poly)
    mask_shapes = [mapping(projected_poly)]

    timeline_data = []
    for filename in tif_files:
        try:
            year = int(filename.split('doy')[1][:4])
            with rasterio.open(os.path.join(DATASET_FOLDER, filename)) as src:
                out_image, _ = rasterio.mask.mask(src, mask_shapes, crop=True)
                pixels = out_image[0].flatten()
                valid_pixels = pixels[(pixels != 255) & (pixels != src.nodata)]
                
                if len(valid_pixels) == 0: continue
                unique_classes, counts = np.unique(valid_pixels, return_counts=True)
                total_pixels = len(valid_pixels)
                
                year_stats = {}
                for val, count in zip(unique_classes, counts):
                    class_info = LULC_PALETTE.get(int(val))
                    if class_info:
                        year_stats[class_info['name']] = {
                            "color": class_info['color'],
                            "percentage": round((float(count) / float(total_pixels)) * 100, 1),
                            "area_sqkm": round(float(count) * 0.25, 2)
                        }
                timeline_data.append({"year": year, "stats": year_stats})
        except Exception: continue
    return sorted(timeline_data, key=lambda k: k['year'])

# --- UPGRADED: Optimized Cropped TIFF Generators ---
def get_cropped_tiff_bytes(geo_polygon_dict, year):
    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif") and f"doy{year}" in f]
    if not tif_files: return None
    
    file_path = os.path.join(DATASET_FOLDER, tif_files[0])
    user_poly = shape(geo_polygon_dict)
    
    with rasterio.open(file_path) as src:
        project = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform
        projected_poly = transform(project, user_poly)
        
        try:
            out_image, out_transform = rasterio.mask.mask(src, [mapping(projected_poly)], crop=True)
            out_meta = src.meta.copy()
            # OPTIMIZATION: LZW Compression makes the payload much smaller for faster downloads
            out_meta.update({
                "driver": "GTiff", 
                "height": out_image.shape[1], 
                "width": out_image.shape[2], 
                "transform": out_transform,
                "compress": "lzw" 
            })
            
            with MemoryFile() as memfile:
                with memfile.open(**out_meta) as dest:
                    dest.write(out_image)
                return memfile.read()
        except Exception:
            return None

def get_all_cropped_tiffs_zip(geo_polygon_dict):
    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif")]
    if not tif_files: return None

    # OPTIMIZATION: Calculate projection math ONCE outside the loop
    user_poly = shape(geo_polygon_dict)
    first_tif = os.path.join(DATASET_FOLDER, tif_files[0])
    with rasterio.open(first_tif) as src:
        project = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform
    
    projected_poly = transform(project, user_poly)
    mask_shape = [mapping(projected_poly)]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename in tif_files:
            file_path = os.path.join(DATASET_FOLDER, filename)
            try:
                with rasterio.open(file_path) as src:
                    out_image, out_transform = rasterio.mask.mask(src, mask_shape, crop=True)
                    out_meta = src.meta.copy()
                    out_meta.update({
                        "driver": "GTiff", "height": out_image.shape[1], 
                        "width": out_image.shape[2], "transform": out_transform,
                        "compress": "lzw"
                    })
                    with MemoryFile() as memfile:
                        with memfile.open(**out_meta) as dest:
                            dest.write(out_image)
                        zip_file.writestr(f"Cropped_{filename}", memfile.read())
            except Exception:
                continue
                
    zip_buffer.seek(0)
    return zip_buffer