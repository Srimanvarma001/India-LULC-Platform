# India LULC Platform

A web platform for exploring how **land use and land cover (LULC)** changed across India from **2001 to 2024**. This is my B.Tech project at IIT Kharagpur.

It's built on NASA's MODIS land cover product, **MCD12Q1 (v6.1, IGBP classification)**: one raster per year on a ~500 m grid (0.0042° in WGS84 lat/lon), with every pixel in one of 17 land cover classes such as croplands, forests, urban areas and water bodies.

## Features

- **Point timeline**: pick any point in India to see its land cover class for every year from 2001 to 2024, and which state it's in. Points outside India's boundary are rejected.
- **Area analysis**: draw a polygon, rectangle or circle on the map, or type in bounds or a centre and radius. You get the share (%) of each land cover class for every year, as charts and a downloadable CSV.
- **Cropped GeoTIFF export**: download the rasters clipped to your shape, for one year or all 24 years as a ZIP, LZW-compressed.
- **Full dataset download**: the original uncropped GeoTIFFs, one year or all years.

## How it works

- **Backend**: Python and FastAPI. `rasterio` reads and masks the GeoTIFFs, `shapely` handles geometries and the India boundary check, and `pyproj` reprojects coordinates from WGS84 into the raster's projection.
- **Area statistics**: the shape is reprojected into the raster's CRS, the raster is masked and cropped to it, and classes are counted over the valid pixels. No-data pixels are excluded.
- **Frontend**: a single HTML page using Leaflet and Leaflet.draw for the map and shapes, and Chart.js for the charts.
- **Hosting**: the backend runs on my machine and is exposed through a Cloudflare Tunnel at `api.sriman.online`. If the backend is offline, the page shows an inline message instead of failing.

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/legend` | The 17 LULC classes with names and colours |
| GET | `/api/lulc?lat=&lon=` | Year-by-year land cover at a point, plus the state |
| POST | `/api/lulc/polygon` | Per-class share per year for a GeoJSON geometry |
| POST | `/api/download-tiff-cropped?year=` | One year's raster cropped to a geometry |
| POST | `/api/download-all-tiffs-cropped` | All years cropped to a geometry, as a ZIP |
| GET | `/api/download-tiff-original?year=` | One year's full raster |
| GET | `/api/download-all-tiffs-original` | All full rasters, as a ZIP |

The POST endpoints take a body of the form `{"geometry": <GeoJSON geometry>}`.

## Run locally

You need Python 3.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The backend also serves the frontend at <http://127.0.0.1:8000/>.

The frontend calls the hosted API by default. To use your local backend, change `API_BASE_URL` in `frontend/index.html`:

```js
const API_BASE_URL = "http://127.0.0.1:8000";
```

## Project structure

```
backend/
  main.py                 FastAPI app and API routes
  geo_engine.py           point timelines, polygon stats, raster cropping
  config.py               dataset paths and the LULC class palette
  india_boundary.geojson  India state boundaries (used for the inside-India check)
  check_boundary.py       script used to fetch and test the boundary file
  test_tiff.py            script for checking point values in the rasters
frontend/
  index.html              map UI (Leaflet, Leaflet.draw, Chart.js)
indian_dataset/
  MCD12Q1.061_LC_Type1_doy<YEAR>001000000_aid0001.tif   one raster per year, 2001-2024
```

## Data

The land cover data is **MODIS/Terra+Aqua Land Cover Type Yearly L3 Global 500 m (MCD12Q1, Collection 6.1)**, Land Cover Type 1 (IGBP), from NASA's LP DAAC, clipped to India. The state boundary file is from [geohacker/india](https://github.com/geohacker/india).
