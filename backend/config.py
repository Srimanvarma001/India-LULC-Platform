import os

# --- System Paths ---
# This automatically finds the correct folders no matter whose PC this runs on
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_FOLDER = os.path.abspath(os.path.join(BASE_DIR, "..", "indian_dataset"))
GEOJSON_PATH = os.path.join(BASE_DIR, "india_boundary.geojson")

# --- LULC Canonical Palette ---
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
    12: {"name": "Croplands", "color": "#f0e68c"}, 
    13: {"name": "Urban and Built-Up", "color": "#ff0000"},
    14: {"name": "Cropland/Natural Vegetation Mosaic", "color": "#bdb76b"},
    15: {"name": "Snow and Ice", "color": "#b0c4de"},
    16: {"name": "Barren or Sparsely Vegetated", "color": "#eee8aa"}, 
    17: {"name": "Water Bodies", "color": "#0000cd"}
}