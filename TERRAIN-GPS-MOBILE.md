# Terrain, GPS and mobile changes

Base: `87bcfadde51eb1e2b1536ea5b473994329b3c004`. Local branch: `terrain-gps-mobile`. Main was not edited or pushed.

## Exact supplied TIFF metadata

Both TIFFs are LZW compressed. Bounds use west, south, east, north ordering. Sizes are bytes.

| Field | dem.tiff | imagery.tiff |
|---|---|---|
| CRS | EPSG:4326 | EPSG:4326 |
| Width × height | 2141 × 2306 | 4052 × 4365 |
| Bands | 1 | 4 |
| Dtype | Float32 | UInt8 (all four bands) |
| Pixel size X/Y | 0.0002777777777777778° | 0.00014677251283316917° |
| Row direction | North to south | North to south |
| NoData | None declared | None declared in any band |
| Bounds | 57.24902776666667, -20.538749988888885, 57.843749988888895, -19.89819443333333 | 57.249027767, -20.53880322025839, 57.843749989, -19.89814120174161 |
| File size | 9,176,457 | 44,450,618 |

The supplied files were recovered from the earlier chat's attachment paths on this Mac. `/mnt/data` does not exist in this local session.

## Terrain diagnosis

The shipped UTM grid is 2082 × 2373, covering 62,367.5 × 71,084.6 m. Its centre is easting 557143.6, northing 7764222.9 in EPSG:32740. Reprojecting the supplied DEM with the current bilinear method produces an **identical** Int16 decimeter array: maximum difference zero. Reprojection spacing is 29.95556336800646 m. This is roughly 30 m input detail, not a 1 m DEM. The inspected source produced no non-finite elevation values.

The mesh has 4,940,586 vertices and 9,872,264 terrain triangles. It already uses smooth computed vertex normals; flat shading is off. Increasing mesh subdivisions above source density would interpolate existing information, not recover a sharper real ridge.

The screenshot's small stepped silhouette is consistent with the source/grid sampling. The fixed triangle diagonal and linear surface between samples can still show at close range. The strong dark bands are amplified by the original derivative-based `fwidth(vWorldNormal)` ridge outline, unnormalized interpolated normals, fixed 1.22 texture contrast, steep-slope darkening, directional light, and 2.2× exaggeration. These are code-backed contributing factors; the screenshot's exact camera and ridge location were not available, so this is not a controlled reproduction of that exact image.

The change removes the derivative outline and fixed contrast boost, normalizes the interpolated normal, and uses restrained slope shading controlled by the existing relief slider. It keeps desktop elevations, smooth normals, texture, and 2.2× default. Local close-range views were captured at 2.2× and 1×. Residual silhouette steps remain: completely removing them requires a genuinely finer DEM or accepting shape smoothing. No smoothing was applied to measured terrain.

Desktop texture remains 3940 × 4492, with mipmaps and up to 4× anisotropy. The texture and its base64 counterpart are unchanged. Existing independent DEM/imagery reprojection and raster-edge-to-mesh conventions are retained; there can be a roughly half-cell sampling offset at extreme precision. This change does not claim survey-grade GPS alignment.

## WGS84 peak source

`peaks.js` stores all 773 peaks with `lat` and `lon`; stored `x/z` were removed. Conversion used the exact recorded UTM centre and inverse EPSG:32740 transformation. All other existing peak fields are preserved. Runtime derives local meters using the same projection as GPS. Maximum position difference is approximately 0.00000936 m using the browser projection, so existing placement is effectively unchanged. This validates coordinate preservation, not accuracy of the original summit locations.

Add an object to the `PEAKS` array in `peaks.js` with your actual coordinates:

```js
{ name: "Your peak name", lat: /* latitude */, lon: /* longitude */ }
```

Replace the comments with numbers. Elevation is sampled from the loaded terrain if `elev` is omitted. Optional fields include `elev` (meters), `known`, `url`, `fclass`, `id`, and `isNamed`. Copying an existing object is also fine; give it a unique ID. Search, filtering, markers, labels and GPS continue using the existing display logic. New exports leave `peaks.js` alone.

## Mobile performance

| Setting | Previous mobile | Updated mobile | Desktop |
|---|---|---|---|
| Terrain grid | 2082 × 2373 | 513 × 585 | 2082 × 2373 |
| Terrain triangles | 9,872,264 | 598,016 | 9,872,264 |
| Texture | 3940 × 4492 | 1796 × 2048 | Original unchanged |
| Material | Standard/PBR | Lambert + inexpensive slope shading | Standard/PBR + restrained slope shading |
| Pixel ratio cap | 1.5 | 1.0; fallback 0.75 | 2.0 |
| MSAA | Enabled | Disabled | Enabled |
| Anisotropy cap | 4 | 1 | 4 |
| Visible named labels | No explicit count cap | 12, ordered by elevation | Existing behavior |
| Label refresh while moving | Every dirty frame | At most about 10 Hz while controls move | Existing behavior |
| Peak markers | 773, one instanced draw | All retained | All retained |

The mobile grid has about **94% fewer terrain triangles**. Approximate geometry buffers drop from 276.7 MB to 16.8 MB before driver overhead. Texture memory including mipmaps drops from roughly 94.4 MB to 19.6 MB (RGBA GPU estimate). These are calculated buffer sizes, not device memory measurements. Only mobile terrain/texture scripts load on mobile; the high-resolution base64 exports are not downloaded first. Mobile texture JPEG is about 756 KiB; mobile terrain script about 782 KiB.

Mobile quality is chosen once at load using a coarse pointer or width below 768 px. Reload after changing emulation/device class. A conservative one-way fallback lowers DPR to 0.75 after 90 consecutive active frames over 40 ms; it does not rebuild terrain or oscillate between levels. This is a guard, not a measured optimal threshold.

The original loop already resets `renderRequested` and does not draw continuously when idle. That behavior is preserved. Hidden pages skip scene work; visibility changes reset timing and request a fresh render. RAF scheduling still exists for damping/keyboard handling. Markers already share one draw call and represent only about 61,840 triangles; reducing them was less useful than reducing terrain and would change browsing behavior. All 95 named label objects remain available, but only 12 are shown at once on mobile. Label overlap is still possible.

## Validation and limits

- Headless Chrome, desktop 1440 × 1000 and touch/mobile 390 × 844, mobile device scale factor 3.
- Desktop grid, original texture dimensions, mobile grid, texture dimensions, material choice, DPR and label cap checked.
- Selection/highlight, exaggeration slider, relief slider and reset passed with no page errors.
- Both modes produced zero additional WebGL frames in a settled 500 ms idle window.
- Existing peak coordinates compared across all 773 peaks; maximum browser placement difference below 0.00001 m.
- Supplied DEM reprojected and compared to original stored elevations: exact equality.
- Python files compile; Git whitespace check passes.
- Overview screenshots inspected, plus local close-range 2.2×/1× views. The screenshot camera was not reproduced exactly.
- No real phone FPS, thermal, battery or GPS hardware/compass test was performed. No network-throttled mobile benchmark was performed. The full `prep.py` asset rebuild was not run; its DEM reprojection was verified separately and the mobile generator was run.

## Exact changed files

Modified: `index.html`, `data.js` (same terrain payload; peak list moved), `prep.py`.

Added: `peaks.js`, `data-mobile.js`, `prepare-mobile.py`, `texture-mobile.jpg`, `texture-mobile.js`, `TERRAIN-GPS-MOBILE.md`.

Unchanged: `texture.jpg`, `texture_data.js`, libraries, trail pages and their assets. No uploaded TIFF was modified.

## Rebuild and local test

Python dependencies: rasterio, numpy and Pillow. Recreate only mobile assets with `python prepare-mobile.py`. To export from supplied TIFFs, run `python prep.py /absolute/path/dem.tiff /absolute/path/imagery.tiff`; this overwrites generated desktop/mobile assets in your test checkout, not the peak source. Serve the folder with `python3 -m http.server 8765` and open http://localhost:8765/. The exports retain base64 assets for file-based use, but HTTP is the tested path.

## Revert

The original main branch remains at the base commit. In the clean local clone, `git switch main` restores the original files. If this commit is later applied elsewhere, `git revert <change-commit>` undoes it without rewriting history. Do not use a hard reset over unrelated work.
