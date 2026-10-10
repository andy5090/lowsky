# Korean surroundings

The images are free, licensed visual assets from the [ESA WorldCover data service](https://esa-worldcover.org/en/data-access). They cover the same 10 × 10 km as the DEM, centered at 36.23° N, 127.08° E.

- `korea_satellite.png`: rendered 2021 annual Sentinel-2 true-color median composite; 10 m source, requested as 2048 × 2048 pixels.
- `korea_landcover.png`: rendered 2021 v200 WorldCover map, requested as 1024 × 1024 pixels. Green tree-cover pixels guide illustrative forest placement. This WMS image is **not** used as a numeric classification dataset or scientific measurement.
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
- Required attribution: **© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium**.
- Dataset citation: Zanaga, D., et al. (2022), *ESA WorldCover 10 m 2021 v200*, [DOI: 10.5281/zenodo.7254221](https://doi.org/10.5281/zenodo.7254221).
- Modifications: geographic crop/resampling by WMS, color/reflectance adjustment in the ground shader, synthetic graded-site replacement, and illustrative trees sampled from tree-cover pixels. Source PNGs are retained as delivered.

Road centerlines and building footprints in `data/terrain/korea_context.json` are derived from **© OpenStreetMap contributors**, available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). [Copyright and attribution](https://www.openstreetmap.org/copyright). The retained OSM snapshot and normalized database are distributed under ODbL-1.0. Snapshot timestamp: **2026-05-31T22:37:44Z**. Heights, widths where absent, roofs, colors and vegetation instances are visualization assumptions. The fictional site replaces overlapping source objects; these are not surveyed buildings or trees.

Exact request URLs, extent, hashes, snapshot query and processing notes are retained in `data/terrain/context_provenance.json`. The source database is included at `data/terrain/sources/osm_context.json.gz`; rebuild with `python3 tools/build_korean_context.py`. Run `python3 tools/fetch_korean_context.py` to verify all original files without network access. New dependencies and API keys are not required.
