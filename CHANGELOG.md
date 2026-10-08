# Changelog

## 2026-10-07

### Added

- Add controls to dock the OpenDrive 3D Viewer panel as a full-height left or
  right sidebar outside the map, with persistent side and width settings.

- Add a checked-by-default Road Shoulder view option that hides or restores
  OpenDRIVE shoulder lane fills and borders without reparsing the network.

- Add a checked-by-default Road Sidewalk view option that independently hides
  or restores OpenDRIVE sidewalk lane fills and borders.

### Changed

- Auto-dismiss the Grid Mesh fallback notice after seven seconds with a short
  fade transition while retaining its manual close button.

- Disable View controls when the loaded source file has no corresponding road,
  lane type, signal, object, arrow, roadmark, or grid data, and explain the
  disabled state directly in the View panel.

- Organize the web sidebar into Editor, Routing, and View tabs, keep their
  icons available in the collapsed rail, and add pyxodr3d, GitHub, and issue
  tracker links at the top.

- Add map-based start and destination lane selection, Python shortest-path
  routing over the directed OpenDRIVE lane graph, route highlighting, and route
  distance reporting. View choices continue to control object, signal,
  reference-line, arrow, roadmark, grid, wireframe, and road layers.

- Use the supplied ORNL JPEG logo as the web viewer favicon.

- Refresh the web viewer layout with aligned rounded map/sidebar surfaces, a
  three-dot resize affordance, and clearer sidebar control spacing and states.

- Comment out CARTO Light and Dark because they require an external API key,
  and add the keyless OpenFreeMap Positron vector style as a light basemap.

- Reduce lane-arrow clutter by grouping parallel lanes by travel direction and
  junction connectors by incoming approach, orienting each representative
  arrow from predecessor/successor geometry with an RHT/LHT fallback.

### Fixed

- Declare `pyproj` as a runtime dependency and enable every previously
  skipped coordinate, web-server, dragged-lane, tutorial, and SUMO conversion
  test so missing dependencies now fail with their actionable error messages.

- Recalculate lane-width previews with the Python OpenDRIVE mesh generator
  from a reusable parsed-map copy instead of temporary save/reload cycles. The
  global control scales only driving-lane width polynomials, preserves every
  piecewise record and taper, and smoothly blends linked junction endpoints
  across the connector length so gaps close without sharp wedges. Shoulder,
  sidewalk, and parking widths remain unchanged. Reuse each sampled road frame,
  restore cached width coefficients in place, exchange compact preview payloads,
  and refresh MapLibre once per result to reduce recalculation latency.

- Disambiguate web lane keys only when sub-micrometer lane-section starts round
  to the same six-decimal value, keeping each section's connection data attached
  to the correct geometry while preserving normal lane-key formatting.

- Keep the Editor card fixed to the sidebar height while its attribute fields
  use the remaining space and scroll independently when data overflows.

- Prevent populated lane attributes from changing the sidebar's height by
  excluding their content from flex sizing and scrolling only the fields area.

- Keep Editor inputs and text areas within the sidebar as its width changes by
  allowing both attribute columns to shrink without horizontal overflow.

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
