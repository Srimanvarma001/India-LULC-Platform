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
                state_name = (
                    props.get('ST_NM') or
                    props.get('NAME_1') or
                    props.get('name') or
                    props.get('ADMIN') or
                    "India Map Region"
                )
                INDIA_STATE_SHAPES.append({
                    "name": state_name,
                    "shape": shape(feature['geometry'])
                })
except Exception as e:
    print(f"GeoEngine ERROR loading boundary data: {e}")


def check_coordinates_in_india(lat, lon):
    if not INDIA_STATE_SHAPES:
        return {"error": "Internal map data error."}
    user_point = Point(lon, lat)
    for state in INDIA_STATE_SHAPES:
        if state['shape'].contains(user_point):
            return {"in_india": True, "state": state['name']}
    return {"in_india": False}


def extract_point_timeline(lat, lon):
    timeline_data = []
    if not os.path.exists(DATASET_FOLDER):
        return {"error": "Dataset folder not found"}

    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif")]
    if not tif_files:
        return {"error": "No .tif files found."}

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
                timeline_data.append({
                    "year": year,
                    "lulc_name": class_info['name'],
                    "lulc_color": class_info['color']
                })
        except Exception as e:
            # FIX #7: Log skipped files instead of silently swallowing errors.
            print(f"Warning: Skipping {filename} in point timeline → {e}")
            continue

    return sorted(timeline_data, key=lambda k: k['year'])


def extract_polygon_stats(geo_polygon_dict):
    # FIX #6: Added existence check for DATASET_FOLDER.
    if not os.path.exists(DATASET_FOLDER):
        return []

    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif")]

    # FIX #2: Added empty list guard before accessing tif_files[0].
    # Previously this would crash with IndexError if no TIF files were present.
    if not tif_files:
        return []

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

                # FIX #4: src.nodata can be None in many GeoTIFFs (especially MODIS).
                # NumPy comparing an array to None produces wrong or undefined results.
                # Now we only apply the nodata mask when a nodata value actually exists.
                nodata_mask = pixels != 255
                if src.nodata is not None:
                    nodata_mask = nodata_mask & (pixels != src.nodata)
                valid_pixels = pixels[nodata_mask]

                if len(valid_pixels) == 0:
                    continue

                # FIX #8: Calculate pixel area dynamically from the raster's own transform
                # instead of hardcoding 0.25 km² (500m × 500m MODIS assumption).
                # This makes area calculations correct for any resolution dataset.
                pixel_width_m = abs(src.transform.a)
                pixel_height_m = abs(src.transform.e)
                pixel_area_sqkm = (pixel_width_m * pixel_height_m) / 1_000_000

                unique_classes, counts = np.unique(valid_pixels, return_counts=True)
                total_pixels = len(valid_pixels)

                year_stats = {}
                for val, count in zip(unique_classes, counts):
                    class_info = LULC_PALETTE.get(int(val))
                    if class_info:
                        year_stats[class_info['name']] = {
                            "color": class_info['color'],
                            "percentage": round((float(count) / float(total_pixels)) * 100, 1),
                            "area_sqkm": round(float(count) * pixel_area_sqkm, 2)
                        }
                timeline_data.append({"year": year, "stats": year_stats})

        except Exception as e:
            # FIX #7: Log skipped files instead of silently swallowing errors.
            print(f"Warning: Skipping {filename} in polygon stats → {e}")
            continue

    return sorted(timeline_data, key=lambda k: k['year'])


def get_cropped_tiff_bytes(geo_polygon_dict, year):
    # FIX #6: Added existence check for DATASET_FOLDER.
    if not os.path.exists(DATASET_FOLDER):
        return None

    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif") and f"doy{year}" in f]
    if not tif_files:
        return None

    file_path = os.path.join(DATASET_FOLDER, tif_files[0])
    user_poly = shape(geo_polygon_dict)

    with rasterio.open(file_path) as src:
        project = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform
        projected_poly = transform(project, user_poly)

        try:
            out_image, out_transform = rasterio.mask.mask(src, [mapping(projected_poly)], crop=True)
            out_meta = src.meta.copy()
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
        except Exception as e:
            # FIX #7: Log the actual error instead of silently returning None.
            print(f"Warning: Could not crop TIFF for year {year} → {e}")
            return None


def get_all_cropped_tiffs_zip(geo_polygon_dict):
    # FIX #6: Added existence check for DATASET_FOLDER.
    if not os.path.exists(DATASET_FOLDER):
        return None

    tif_files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith(".tif")]
    if not tif_files:
        return None

    # Calculate projection math ONCE outside the loop (performance optimization)
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
                        "driver": "GTiff",
                        "height": out_image.shape[1],
                        "width": out_image.shape[2],
                        "transform": out_transform,
                        "compress": "lzw"
                    })
                    with MemoryFile() as memfile:
                        with memfile.open(**out_meta) as dest:
                            dest.write(out_image)
                        zip_file.writestr(f"Cropped_{filename}", memfile.read())
            except Exception as e:
                # FIX #7: Log the actual error instead of silently skipping.
                print(f"Warning: Skipping {filename} in zip export → {e}")
                continue

    zip_buffer.seek(0)
    return zip_buffer