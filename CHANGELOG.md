# Changelog

## 2026-10-07

### Added

- Add controls to dock the OpenDrive 3D Viewer panel as a full-height left or
  right sidebar outside the map, with persistent side and width settings.

### Changed

- Use the supplied ORNL JPEG logo as the web viewer favicon.

- Refresh the web viewer layout with aligned rounded map/sidebar surfaces, a
  three-dot resize affordance, and clearer sidebar control spacing and states.

- Comment out CARTO Light and Dark because they require an external API key,
  and add the keyless OpenFreeMap Positron vector style as a light basemap.

- Reduce lane-arrow clutter by grouping parallel lanes by travel direction and
  junction connectors by incoming approach, orienting each representative
  arrow from predecessor/successor geometry with an RHT/LHT fallback.

### Fixed

- Replace the sidebar-owned resize handles with one dedicated, keyboard
  accessible middle splitter whose vertical three-dot grip stays centered
  between the map and sidebar on either side.

- Prevent the web viewer from remaining on its loading screen because the lane
  arrow optimization duplicated an existing module-level helper name.

- Fall back to Grid Mesh with a visible explanation when source projection
  information or converted coordinates are unusable, while preserving a valid
  real-world basemap when individual raster tile requests fail.

## 2026-10-01

### Fixed

- Pin the web editor dependencies to MapLibre 5.24.0 so the CDN cannot select
  an incompatible MapLibre release and leave the viewer stuck loading.
- Reset the OpenDrive 3D Viewer panel to the right side on each page load instead
  of restoring obsolete drag coordinates from browser storage.
- Resolve the `tutorial.py` sample OpenDRIVE file relative to the script so the
  tutorial runs correctly from any working directory.
