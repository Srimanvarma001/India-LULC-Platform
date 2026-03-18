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

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class PolygonRequest(BaseModel):
    geometry: Dict[str, Any]

# --- NEW: Serve the Frontend HTML automatically ---
@app.get("/")
def serve_frontend():
    # This mathematically finds your frontend folder no matter whose PC it runs on
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.abspath(os.path.join(base_dir, "..", "frontend", "index.html"))
    
    if os.path.exists(html_path):
        return FileResponse(html_path)
    else:
        return {"error": f"Could not find the website at {html_path}"}

@app.get("/api/legend")
def get_legend():
    return LULC_PALETTE

@app.get("/api/lulc")
def get_lulc_data(lat: float, lon: float):
    # Old point endpoint (kept for safety)
    timeline_data = extract_point_timeline(lat, lon)
    return {"status": "success", "temporal_timeline": timeline_data}

@app.post("/api/lulc/polygon")
def analyze_polygon_area(request: PolygonRequest):
    timeline_data = extract_polygon_stats(request.geometry)
    if not timeline_data: raise HTTPException(status_code=400, detail="Polygon resulted in no valid satellite data.")
    return {"status": "success", "temporal_timeline": timeline_data}

# --- Cropped Downloads ---
@app.post("/api/download-tiff-cropped")
def download_tiff_cropped(year: int, request: PolygonRequest):
    tiff_bytes = get_cropped_tiff_bytes(request.geometry, year)
    if not tiff_bytes: raise HTTPException(status_code=404, detail="Could not crop image.")
    return StreamingResponse(io.BytesIO(tiff_bytes), media_type="image/tiff", headers={"Content-Disposition": f"attachment; filename=Cropped_{year}.tif"})

@app.post("/api/download-all-tiffs-cropped")
def download_all_tiffs_cropped(request: PolygonRequest):
    zip_buffer = get_all_cropped_tiffs_zip(request.geometry)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=Cropped_All.zip"})

# --- Original Full Downloads ---
@app.get("/api/download-tiff-original")
def download_tiff_original(year: int):
    for filename in os.listdir(DATASET_FOLDER):
        if filename.endswith(".tif") and f"doy{year}" in filename:
            return FileResponse(path=os.path.join(DATASET_FOLDER, filename), filename=filename, media_type='image/tiff')
    raise HTTPException(status_code=404, detail="File not found.")

@app.get("/api/download-all-tiffs-original")
def download_all_tiffs_original():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename in os.listdir(DATASET_FOLDER):
            if filename.endswith(".tif"): zip_file.write(os.path.join(DATASET_FOLDER, filename), arcname=filename)
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=Full_India_LULC.zip"})