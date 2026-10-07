# OpenDRIVE Web Editor

This folder contains the browser editor for OpenDRIVE `.xodr` files. The current
viewer is a Python-backed MapLibre GL application powered by `pyxodr3d`.

## Files

- `index.html` - clean MapLibre GL editor shell and DOM structure.
- `index.css` - shared page and panel styling.
- `index.js` - MapLibre GL editor logic.
- `__init__.py` - local HTTP API server and OpenDRIVE to GeoJSON converters.
- `__main__.py` - command line entry point for `python -m pyxodr3d.web`.
- `data.xodr` - default startup network loaded when no `--xodr` path is given.
- `static/`, `favicon.ico` - local UI assets.

## Run / Tutorial

From the repository root:

```powershell
python -m pyxodr3d.web --no-browser
```

Then open:

```text
http://127.0.0.1:8765/
```

The default map is `pyxodr3d/web/data.xodr`. The page calls
`/api/network` on startup, and the Python server returns the default network as
MapLibre-ready GeoJSON.

### Command Line Arguments

```powershell
python -m pyxodr3d.web --host 127.0.0.1 --port 8765 --no-browser --xodr pyxodr3d\web\data.xodr
```

- `--host` - network interface for the local server. The default is
  `127.0.0.1`, which means only the local machine can connect.
- `--port` - server port. The default is `8765`. Use `0` to let Python choose a
  free port.
- `--no-browser` - start the server without opening the browser automatically.
  This is useful when running from a terminal, test script, or remote session.
- `--xodr` - OpenDRIVE file loaded at startup. If omitted, the viewer loads
  `pyxodr3d/web/data.xodr`.

To start with another map:

```powershell
python -m pyxodr3d.web --no-browser --xodr C:\path\to\map.xodr
```

To let Python pick a free port:

```powershell
python -m pyxodr3d.web --port 0
```

The selected URL is printed to the terminal.

### `run_server()` Tutorial

Use `run_server()` when your code wants to own the server lifetime. It creates
the HTTP server and returns both the server object and the URL, but it does not
block by itself.

```python
from pyxodr3d.web import run_server

server, url = run_server(
    host="127.0.0.1",
    port=8765,
    open_browser=False,
    default_xodr=r"C:\path\to\map.xodr",
)

print(f"Open {url}")

try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
```

Arguments:

- `host` - local interface to bind. Use `127.0.0.1` for local-only access.
- `port` - local port to bind. Use `0` for any free port.
- `open_browser` - when `True`, open the viewer URL in the default browser.
- `default_xodr` - startup `.xodr` file. Pass `None` to start without a loaded
  map.

Return value:

- `server` - a `ThreadingHTTPServer` instance. Call `serve_forever()` to run it.
- `url` - the browser URL, usually `http://127.0.0.1:8765/`.

### `xodr_web_viewer()` Tutorial

Use `xodr_web_viewer()` when you want the simplest Python call. It starts the
server, opens the browser, and keeps Python running while the local API is
needed by the page.

```python
from pyxodr3d.web import xodr_web_viewer

xodr_web_viewer(
    host="127.0.0.1",
    port=8765,
    open_browser=True,
    block=True,
    default_xodr=r"C:\path\to\map.xodr",
)
```

Arguments:

- `host` - local interface to bind.
- `port` - local port to bind. Use `0` for any free port.
- `open_browser` - when `True`, open the viewer URL in the default browser.
- `block` - when `True`, keep the Python process alive until the browser closes
  the server or you press `Ctrl+C`. Use `False` only when your own application
  keeps running after the viewer starts.
- `default_xodr` - startup `.xodr` file. If omitted, `data.xodr` is loaded.

Return value:

- URL string for the viewer. In blocking mode, the URL is also printed before
  the server starts handling requests.

## Main Capabilities

- Loads OpenDRIVE through `pyxodr3d`.
- Converts road, lane, signal, post, and mast-arm geometry to lon/lat with
  `convertXY2LonLat`.
- Displays lane-level polygons on a MapLibre world map.
- Supports basemaps including OpenStreetMap, Google road/satellite, Carto,
  Esri, OpenTopoMap, OSM HOT, and a local `Grid Mesh` basemap similar to the
  original grid-style OpenDRIVE view.
- Automatically uses `Grid Mesh` and displays a dismissible notice when the
  source lacks usable projection information or its converted coordinates
  cannot be placed on a real-world map. Transient raster tile failures do not
  replace an otherwise valid real-world basemap.
- Preserves loaded OpenDRIVE overlays when switching basemaps.
- Shows the OpenDriveViewer panel with editable selected-feature attributes.
- Docks the OpenDriveViewer panel as a full-height left or right sidebar outside
  the map view, resizes the map to the remaining space, and remembers the side.
- Selects map objects with a single click.
- Drags lanes, signal heads, posts, and mast arms directly on the map.
- Supports `Undo Move` and `Ctrl+Z` / `Cmd+Z` for the last drag movement.
- Highlights selected lanes and the selected lane's predecessor/successor
  lanes.
- Saves edited OpenDRIVE XML through `/api/save-xodr`.

## Editing

The OpenDriveViewer panel provides these actions:

- `Add Lane`
- `Delete`
- `Copy Lane Link`
- `Set Pred`
- `Set Succ`
- `Add Signal`
- `Add Post`
- `Add Mast Arm`
- `Undo Move`

The embedded `maplibre-gl-geo-editor` toolbar supports line and polygon drawing.
Drawn polygons can be converted into lane features when a road or lane context is
selected.

Editable fields update the map immediately. For example, changing signal or
object `height`, `width`, `length`, `radius`, `zOffset`, or `map_heading`
updates the visible 3D object. Key fields also cascade where possible:

- Road `road_id`, `name`, and `junction` update related lane/signal fields.
- Lane `lane_id`, `road_id`, and `lanesection_s0` rebuild `lane_key`.
- Lane predecessor/successor key arrays are updated when a linked lane ID/key
  changes.
- Signal `signal_id` rebuilds `signal_key`.
- Object `object_id` rebuilds `object_key`.

## Signal Rendering Rules

Some CARLA maps encode physical signal posts and mast arms as OpenDRIVE
`<object>` entries. In those maps, the viewer renders the physical support
objects and suppresses duplicate original signal-head geometry.

If a map does not include physical support objects, `<signal>` entries are
rendered as 3D signal-head objects.

User-added `User_Signal_Head` entries remain visible after save/reload even on
maps where original signal heads are suppressed.

## Save Behavior

Save sends road, lane, and signal/object GeoJSON to the Python server. The server
updates OpenDRIVE XML and returns a downloadable `edited_network.xodr`.

Persisted edits include:

- Road centerline edits from line features.
- Lane add/delete and lane attributes.
- Lane predecessor/successor links.
- Signal head add/delete and attributes.
- Signal post and mast-arm add/delete and attributes.
- Dragged signal/object positions, converted from lon/lat back to OpenDRIVE
  `s`/`t`.

## Limitations

Lane geometry after reload is regenerated from OpenDRIVE lane definitions. A
drawn lane polygon can be used for editing context before save, but long-term
lane shape is controlled by OpenDRIVE lane width/border records.

MapLibre supports a maximum practical pitch of about `85` degrees, not a true
`90` degree vertical camera.

The viewer depends on CDN-hosted MapLibre, Geoman, and
`maplibre-gl-geo-editor` packages.
