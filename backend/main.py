from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import os
import zipfile
import io

from config import LULC_PALETTE, DATASET_FOLDER
from geo_engine import check_coordinates_in_india, extract_point_timeline, extract_polygon_stats, get_cropped_tiff_bytes, get_all_cropped_tiffs_zip

app = FastAPI(title="India LULC Platform", version="3.0.0")

# FIX #1: Changed allow_credentials to False.
# Browsers reject allow_origins=["*"] combined with allow_credentials=True (CORS spec violation).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

class PolygonRequest(BaseModel):
    geometry: Dict[str, Any]

# --- Serve the Frontend HTML automatically ---
@app.get("/")
def serve_frontend():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.abspath(os.path.join(base_dir, "..", "frontend", "index.html"))
    if os.path.exists(html_path):
        return FileResponse(html_path)
    else:
        return {"error": f"Could not find the website at {html_path}"}

@app.get("/api/legend")
def get_legend():
    return LULC_PALETTE

# FIX #5: Now actually calls check_coordinates_in_india() before processing.
# Previously this guard was imported but never used, allowing any global coordinate
# to be silently queried against the Indian dataset, returning meaningless data.
@app.get("/api/lulc")
def get_lulc_data(lat: float, lon: float):
    india_check = check_coordinates_in_india(lat, lon)
    if "error" in india_check:
        raise HTTPException(status_code=500, detail=india_check["error"])
    if not india_check.get("in_india"):
        raise HTTPException(status_code=400, detail="Coordinates are outside India. Please select a location within India.")
    timeline_data = extract_point_timeline(lat, lon)
    return {
        "status": "success",
        "state": india_check.get("state"),
        "temporal_timeline": timeline_data
    }

@app.post("/api/lulc/polygon")
def analyze_polygon_area(request: PolygonRequest):
    timeline_data = extract_polygon_stats(request.geometry)
    if not timeline_data:
        raise HTTPException(status_code=400, detail="Polygon resulted in no valid satellite data.")
    return {"status": "success", "temporal_timeline": timeline_data}

# --- Cropped Downloads ---
@app.post("/api/download-tiff-cropped")
def download_tiff_cropped(year: int, request: PolygonRequest):
    tiff_bytes = get_cropped_tiff_bytes(request.geometry, year)
    if not tiff_bytes:
        raise HTTPException(status_code=404, detail="Could not crop image for the requested year.")
    return StreamingResponse(
        io.BytesIO(tiff_bytes),
        media_type="image/tiff",
        headers={"Content-Disposition": f"attachment; filename=Cropped_{year}.tif"}
    )

# FIX #3: Added null check before passing zip_buffer to StreamingResponse.
# Previously get_all_cropped_tiffs_zip() could return None (if no TIFs found),
# which caused an immediate Internal Server Error 500 crash.
@app.post("/api/download-all-tiffs-cropped")
def download_all_tiffs_cropped(request: PolygonRequest):
    zip_buffer = get_all_cropped_tiffs_zip(request.geometry)
    if not zip_buffer:
        raise HTTPException(status_code=404, detail="No TIFF files found to create a zip archive.")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=Cropped_All.zip"}
    )

# --- Original Full Downloads ---
@app.get("/api/download-tiff-original")
def download_tiff_original(year: int):
    for filename in os.listdir(DATASET_FOLDER):
        if filename.endswith(".tif") and f"doy{year}" in filename:
            return FileResponse(
                path=os.path.join(DATASET_FOLDER, filename),
                filename=filename,
                media_type='image/tiff'
            )
    raise HTTPException(status_code=404, detail="File not found.")

@app.get("/api/download-all-tiffs-original")
def download_all_tiffs_original():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename in os.listdir(DATASET_FOLDER):
            if filename.endswith(".tif"):
                zip_file.write(os.path.join(DATASET_FOLDER, filename), arcname=filename)
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=Full_India_LULC.zip"}
    )