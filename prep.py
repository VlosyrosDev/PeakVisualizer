"""
Build static web assets for Mauritius Peak Visualizer.
Reprojects DEM and Satellite imagery to UTM EPSG:32740 (metric coordinates)
at native full spatial resolution while preserving original JS data formats.
Generates:
  1. texture.jpg         - High-res satellite drape in UTM coordinates
  2. texture_data.js     - Base64 data URI for zero-CORS file:// execution
  3. data.js             - High-res Terrain grid (Int16 decimeters) + Peak coordinates & metadata
"""

import base64
import io
import json
import os
import sys

import numpy as np
from PIL import Image
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

DEM_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_DIR, "dem.tiff")
SATELLITE_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(PROJECT_DIR, "imagery.tiff")
TARGET_CRS = "EPSG:32740"


def main():
    print("--- 1. Reprojecting DEM to UTM Zone 40S (Full Native Resolution) ---")
    with rasterio.open(DEM_PATH) as dem_src:
        # Calculate native full-resolution output dimensions automatically
        transform, out_w, out_h = calculate_default_transform(
            dem_src.crs,
            TARGET_CRS,
            dem_src.width,
            dem_src.height,
            *dem_src.bounds,
        )

        elevation = np.empty((out_h, out_w), dtype=np.float32)
        reproject(
            source=rasterio.band(dem_src, 1),
            destination=elevation,
            src_transform=dem_src.transform,
            src_crs=dem_src.crs,
            dst_transform=transform,
            dst_crs=TARGET_CRS,
            resampling=Resampling.bilinear,
        )

    # Reprojection holes / undeclared non-finite data are ocean, not giant spikes.
    elevation = np.nan_to_num(elevation, nan=0.0, posinf=0.0, neginf=0.0)
    elevation = np.where(elevation < 0, 0, elevation)
    if np.max(elevation) * 10 > 32767:
        raise ValueError("Elevation exceeds Int16 decimeter range")
    max_elev = float(np.max(elevation))
    min_elev = float(np.min(elevation))

    # Dynamic metric dimensions from native raster output
    grid_cols = out_w
    grid_rows = out_h
    world_width = abs(transform.a) * grid_cols
    world_height = abs(transform.e) * grid_rows
    x_min = transform.c
    x_max = transform.c + world_width
    y_max = transform.f
    y_min = transform.f - world_height
    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0

    print(f"  Elevation Grid: {grid_cols} x {grid_rows} pixels")
    print(f"  Elevation: {min_elev:.1f}m to {max_elev:.1f}m")
    print(f"  World size: {world_width:.1f}m x {world_height:.1f}m ({world_width/1000:.1f}km x {world_height/1000:.1f}km)")
    print(f"  Center UTM: ({center_x:.1f}, {center_y:.1f})")

    # Encode elevation as Int16 in decimeters (0.1m precision) expected by buildTerrain()
    elev_decimeters = np.round(elevation * 10.0).astype(np.int16)
    elev_bytes = elev_decimeters.tobytes()
    elev_b64 = base64.b64encode(elev_bytes).decode("ascii")
    print(f"  Elevation data base64 length: {len(elev_b64)} chars ({len(elev_b64)/1024:.1f} KB)")

    print("\n--- 2. Reprojecting Satellite Imagery (Full Native Resolution) ---")
    with rasterio.open(SATELLITE_PATH) as sat_src:
        tex_transform, tex_w, tex_h = calculate_default_transform(
            sat_src.crs,
            TARGET_CRS,
            sat_src.width,
            sat_src.height,
            *sat_src.bounds,
        )

        sat_rgb = np.empty((3, tex_h, tex_w), dtype=np.uint8)
        for band in range(1, 4):
            reproject(
                source=rasterio.band(sat_src, band),
                destination=sat_rgb[band - 1],
                src_transform=sat_src.transform,
                src_crs=sat_src.crs,
                dst_transform=tex_transform,
                dst_crs=TARGET_CRS,
                resampling=Resampling.lanczos,
            )

    print(f"  Texture Resolution: {tex_w} x {tex_h} pixels")
    sat_image = Image.fromarray(np.transpose(sat_rgb, (1, 2, 0)), "RGB")
    tex_path = os.path.join(BASE_DIR, "texture.jpg")
    sat_image.save(tex_path, format="JPEG", quality=95, optimize=True)
    tex_size_kb = os.path.getsize(tex_path) / 1024.0
    print(f"  Saved {tex_path} ({tex_size_kb:.1f} KB)")

    # Base64 data URI for file:// compatibility
    with open(tex_path, "rb") as f:
        tex_b64 = base64.b64encode(f.read()).decode("ascii")
    tex_data_js_path = os.path.join(BASE_DIR, "texture_data.js")
    with open(tex_data_js_path, "w", encoding="utf-8") as f:
        f.write(f'// Satellite texture as base64 data URI for file:// execution\nwindow.TEXTURE_DATA_URI = "data:image/jpeg;base64,{tex_b64}";\n')
    print(f"  Saved {tex_data_js_path} ({os.path.getsize(tex_data_js_path)/1024:.1f} KB)")

    # peaks.js is the editable WGS84 source. Asset builds never overwrite it.
    print("\n--- 4. Writing data.js ---")
    data_js_path = os.path.join(BASE_DIR, "data.js")
    terrain_data = {
        "width": round(world_width, 1),
        "height": round(world_height, 1),
        "centerUtmX": round(center_x, 1),
        "centerUtmY": round(center_y, 1),
        "cols": grid_cols,
        "rows": grid_rows,
        "minElev": round(min_elev, 1),
        "maxElev": round(max_elev, 1),
        "elevationBase64": elev_b64,
    }

    with open(data_js_path, "w", encoding="utf-8") as f:
        f.write("// Mauritius 3D Peak Visualizer Data\n")
        f.write("const TERRAIN = ")
        json.dump(terrain_data, f, separators=(",", ":"))
        f.write(";\n")

    print(f"  Saved {data_js_path} ({os.path.getsize(data_js_path)/1024:.1f} KB)")
    print("\nAssets prepared successfully with full spatial resolution!")


if __name__ == "__main__":
    main()
    import runpy
    runpy.run_path(os.path.join(BASE_DIR, "prepare-mobile.py"), run_name="__main__")