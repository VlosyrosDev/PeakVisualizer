"""
Build static web assets for Mauritius Peak Visualizer.
Reprojects DEM and Satellite imagery to UTM EPSG:32740 (metric coordinates).
Generates:
  1. texture.jpg         - High-res satellite drape in UTM coordinates
  2. texture_data.js     - Base64 data URI for zero-CORS file:// execution
  3. data.js             - Terrain grid (elevation) + Peak coordinates & metadata
"""

import base64
import io
import json
import os
import sys

import geopandas as gpd
import numpy as np
from PIL import Image
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

DEM_PATH = os.path.join(PROJECT_DIR, "dem.tif")
SATELLITE_PATH = os.path.join(PROJECT_DIR, "imagery.tif")
PEAKS_PATH = os.path.join(PROJECT_DIR, "mauritius_public_peaks_named.geojson")
TARGET_CRS = "EPSG:32740"

# Dimensions
GRID_COLS = 300
GRID_ROWS = 342
TEX_WIDTH = 1561
TEX_HEIGHT = 1779


def main():
    print("--- 1. Reprojecting DEM to UTM Zone 40S ---")
    with rasterio.open(DEM_PATH) as dem_src:
        transform, out_w, out_h = calculate_default_transform(
            dem_src.crs,
            TARGET_CRS,
            dem_src.width,
            dem_src.height,
            *dem_src.bounds,
            dst_width=GRID_COLS,
            dst_height=GRID_ROWS,
        )

        elevation = np.empty((GRID_ROWS, GRID_COLS), dtype=np.float32)
        reproject(
            source=rasterio.band(dem_src, 1),
            destination=elevation,
            src_transform=dem_src.transform,
            src_crs=dem_src.crs,
            dst_transform=transform,
            dst_crs=TARGET_CRS,
            resampling=Resampling.bilinear,
        )

    # Sea level clamp
    elevation = np.where(elevation < 0, 0, elevation)
    max_elev = float(np.max(elevation))
    min_elev = float(np.min(elevation))

    # Metric dimensions
    world_width = abs(transform.a) * GRID_COLS
    world_height = abs(transform.e) * GRID_ROWS
    x_min = transform.c
    x_max = transform.c + world_width
    y_max = transform.f
    y_min = transform.f - world_height
    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0

    print(f"  Elevation: {min_elev:.1f}m to {max_elev:.1f}m")
    print(f"  World size: {world_width:.1f}m x {world_height:.1f}m ({world_width/1000:.1f}km x {world_height/1000:.1f}km)")
    print(f"  Center UTM: ({center_x:.1f}, {center_y:.1f})")

    # Encode elevation as Int16 in decimeters (0.1m precision)
    elev_decimeters = np.round(elevation * 10.0).astype(np.int16)
    elev_bytes = elev_decimeters.tobytes()
    elev_b64 = base64.b64encode(elev_bytes).decode("ascii")
    print(f"  Elevation data base64 length: {len(elev_b64)} chars ({len(elev_b64)/1024:.1f} KB)")

    print("\n--- 2. Reprojecting Satellite Imagery ---")
    tex_transform, _, _ = calculate_default_transform(
        dem_src.crs,
        TARGET_CRS,
        dem_src.width,
        dem_src.height,
        *dem_src.bounds,
        dst_width=TEX_WIDTH,
        dst_height=TEX_HEIGHT,
    )

    sat_rgb = np.empty((3, TEX_HEIGHT, TEX_WIDTH), dtype=np.uint8)
    with rasterio.open(SATELLITE_PATH) as sat_src:
        for band in range(1, 4):
            reproject(
                source=rasterio.band(sat_src, band),
                destination=sat_rgb[band - 1],
                src_transform=sat_src.transform,
                src_crs=sat_src.crs,
                dst_transform=tex_transform,
                dst_crs=TARGET_CRS,
                resampling=Resampling.bilinear,
            )

    sat_image = Image.fromarray(np.transpose(sat_rgb, (1, 2, 0)), "RGB")
    tex_path = os.path.join(BASE_DIR, "texture.jpg")
    sat_image.save(tex_path, format="JPEG", quality=82, optimize=True)
    tex_size_kb = os.path.getsize(tex_path) / 1024.0
    print(f"  Saved {tex_path} ({tex_size_kb:.1f} KB)")

    # Base64 data URI for file:// compatibility
    with open(tex_path, "rb") as f:
        tex_b64 = base64.b64encode(f.read()).decode("ascii")
    tex_data_js_path = os.path.join(BASE_DIR, "texture_data.js")
    with open(tex_data_js_path, "w", encoding="utf-8") as f:
        f.write(f'// Satellite texture as base64 data URI for file:// execution\nwindow.TEXTURE_DATA_URI = "data:image/jpeg;base64,{tex_b64}";\n')
    print(f"  Saved {tex_data_js_path} ({os.path.getsize(tex_data_js_path)/1024:.1f} KB)")

    print("\n--- 3. Processing Peak Data ---")
    peaks_gdf = gpd.read_file(PEAKS_PATH).to_crs(TARGET_CRS)
    peaks_list = []

    for idx, row in peaks_gdf.iterrows():
        px = float(row.geometry.x)
        py = float(row.geometry.y)
        elev = float(row["dem_elevation"])
        name = str(row["name"]).strip() if row["name"] is not None else ""
        is_named = bool(name and name.lower() != "unnamed peak")

        known_val = row.get("known_elev")
        known_elev = float(known_val) if known_val is not None and not np.isnan(known_val) else None
        url = str(row.get("url", "")).strip() if row.get("url") is not None else ""
        fclass = str(row.get("fclass", "")).strip() if row.get("fclass") is not None else ""

        # Coordinates relative to terrain center
        rel_x = px - center_x
        # In Three.js: +X is East, -Z is North
        rel_z = -(py - center_y)

        peaks_list.append({
            "id": idx,
            "name": name if name else "Unnamed Peak",
            "isNamed": is_named,
            "elev": round(elev, 1),
            "known": round(known_elev, 1) if known_elev else None,
            "url": url,
            "fclass": fclass,
            "x": round(rel_x, 1),
            "z": round(rel_z, 1),
        })

    named_count = sum(1 for p in peaks_list if p["isNamed"])
    print(f"  Total peaks: {len(peaks_list)} ({named_count} named)")

    print("\n--- 4. Writing data.js ---")
    data_js_path = os.path.join(BASE_DIR, "data.js")
    terrain_data = {
        "width": round(world_width, 1),
        "height": round(world_height, 1),
        "cols": GRID_COLS,
        "rows": GRID_ROWS,
        "minElev": round(min_elev, 1),
        "maxElev": round(max_elev, 1),
        "elevationBase64": elev_b64,
    }

    with open(data_js_path, "w", encoding="utf-8") as f:
        f.write("// Mauritius 3D Peak Visualizer Data\n")
        f.write("const TERRAIN = ")
        json.dump(terrain_data, f, separators=(",", ":"))
        f.write(";\n\n")
        f.write("const PEAKS = ")
        json.dump(peaks_list, f, separators=(",", ":"))
        f.write(";\n")

    print(f"  Saved {data_js_path} ({os.path.getsize(data_js_path)/1024:.1f} KB)")
    print("\nAssets prepared successfully!")


if __name__ == "__main__":
    main()
