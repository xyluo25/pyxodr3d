# pyxodr3d

OpenDRIVE 3D viewer and editor. OpenDRIVE to SUMO conversation and vise versa. Converted from libOpenDRIVE (C++)(https://github.com/pageldev/libOpenDRIVE) to Python with multiple additions.

## Features

- View OpenDRIVE network on 3D map.
- Convert OpenDRIVE maps to SUMO networks and convert SUMO networks back to OpenDRIVE.
- Parse OpenDRIVE files into an object model with roads, lanes, junctions, objects, and signals.
- Query geometry, lane sections, road marks, routing graphs, and derived meshes.
- Save loaded maps back to `.xodr`.

> [!NOTE]
> This file is adapted from [libOpenDRIVE (C++)](https://github.com/pageldev/libOpenDRIVE) with additional modifications
>
> Modifications:
>
> - Converted from C++ to Python
> - Refactored APIs for Python package usage
> - Integrated web viewer: editable network on real-world basemaps
> - OpenDrive coordination conversion: LonLat2XY, XY2LonLat
> - OpenDrive to SUMO:  xodr_to_net_xml, xodr_from_net_xml
> - Create OpenDrive Network, edit, inspecting etc...
> - Existing open-source OpenDRIVE viewer: [odrviewer.io](https://odrviewer.io/)

## Example

![Bigtowngif](docs/img/bigtown.gif)

<video width="100%" height="480" controls>
  <source src="./docs/img/bigtown.mp4" type="video/mp4">
</video>

[![Bigtownpng](docs/img/bigtown.png)](docs/img/bigtown.mp4)
![Bigtownpng01](docs/img/bigtown01.png)
![chatpng](docs/img/chatt.png)

## Installation

Install from the repository root:

```powershell
pip install -e .
```

The package depends on `sumolib` for SUMO conversion support and `pyproj`
for OpenDRIVE coordinate conversion. To use the SUMO conversion helpers, you
also need the SUMO `netconvert` executable available on `PATH`.

Call the cross-platform setup function to check the operating system, reuse an
existing SUMO installation when possible, or install the official
`eclipse-sumo` package and configure `SUMO_HOME` and the persistent user
`PATH`:

```python
import pyxodr3d as odr

installation = odr.setup_netconvert()
```

The function supports Windows, Linux, and macOS. It verifies `sumo --version`
and `netconvert --version` after setup; the SUMO `bin` directory added to
`PATH` contains both executables. Open a new terminal afterward so it receives
the persistent environment settings. Use `odr.setup_netconvert(check=True)`
for a read-only check.

## Tutorial

<details open>
<summary><b>Click to expand/collapse Quick Start</b></summary>

If this is your first time using the package, think of the examples below as little recipes. Each one shows one simple thing the package can do.

### Open a map and look around

This reads a sample road map file and shows a few things that are inside it.

```python
import pyxodr3d as odr

Map = odr.readXodr("datasets/chatt.xodr")
# Map = odr.OpenDriveMap()
# Map = Map.loadXodr("datasets/chatt.xodr")

print(len(Map.getRoads()))
print(len(Map.getJunctions()))
print(Map.getRoad("1").name)
```

### Convert map coordinates to longitude and latitude

This turns the map's coordinates into the kind of numbers used on a globe.

```python
import pyxodr3d as odr

x = 1377.14000000
y = 221.29000000

lon, lat = Map.convertXY2LonLat(x, y)

# Convert back to the map's original coordinate system
x, y = Map.convertLonLat2XY(lon, lat)
```

### Open the Web Viewer

This opens a browser window so you can look at the map visually.

```python
import pyxodr3d as odr

odr.xodr_web_viewer()
```

The viewer's Open button accepts OpenDRIVE `.xodr` files and SUMO `.net.xml`
files. SUMO files are converted with `xodr_from_net_xml` before rendering.
Generic or externally modified SUMO files require the SUMO `netconvert`
executable on `PATH`.

The Save button opens the browser's native Save As dialog with OpenDRIVE
`.xodr` and SUMO `.net.xml` file types. Saving as SUMO exports the edited
network through `xodr_to_net_xml`; browsers without the native picker safely
fall back to downloading OpenDRIVE `.xodr`.

SUMO exports made by pyxodr3d include a compressed, checksummed copy of the
edited OpenDRIVE document in an XML comment that SUMO ignores. When that SUMO
file is opened again without being modified, pyxodr3d restores the exact roads,
lane sections, and junction connections instead of asking `netconvert` to
reconstruct them. If another tool changes or rewrites the SUMO network, the
checksum no longer matches and pyxodr3d safely uses normal SUMO conversion.
The exact restore keeps every OpenDRIVE road/edge ID, junction ID, and lane ID.
Because SUMO and OpenDRIVE use different lane-ID schemas, the intermediate SUMO
elements also retain the source values in `pyxodr3d.original_link_id`,
`pyxodr3d.original_node_id`, and `pyxodr3d.original_lane_id` parameters.

### Convert OpenDRIVE and SUMO files

This shows how to move a map between OpenDRIVE and SUMO.

```python
import pyxodr3d as odr

path_xodr = "datasets/chatt.xodr"
path_net = "datasets/chatt.net.xml"

Map = odr.readXodr(path_xodr)

# Convert OpenDRIVE to a SUMO network
sumo_net = xodr_to_net_xml(xodr_file, path_net)

# Convert OpenDRIVE from a SUMO network file
Map = xodr_from_net_xml(net_file, xodr_file)
```

If `netconvert` is not available, the SUMO helpers will raise an error.

### Save a map

This writes the map back out as a `.xodr` file.

```python
saved_path = Map.saveXodr("output/saved.xodr")
```

### Ask questions about the map

This gathers a few counts and sample values so you can see what is in the road network.

```python
import pyxodr3d as odr

path_xodr = "datasets/chatt.xodr"

Map = odr.readXodr(path_xodr)

roads = Map.getRoads()
junctions = Map.getJunctions()
graph = Map.getRoutingGraph()

lane_count = len(Map.getLanes())
geometry_count = sum(len(road.ref_line.s0_to_geometry) for road in roads)
object_count = sum(len(road.id_to_object) for road in roads)
signal_count = sum(len(road.id_to_signal) for road in roads)

first_road = roads[0]
s = min(1.0, first_road.length)
xyz = first_road.ref_line.get_xyz(s)
surface = first_road.get_surface_pt(s, 0.0)

print(f"roads={len(roads)}")
print(f"junctions={len(junctions)}")
print(f"lane_sections={sum(len(road.s_to_lanesection) for road in roads)}")
print(f"lanes={lane_count}")
print(f"geometries={geometry_count}")
print(f"objects={object_count}")
print(f"signals={signal_count}")
print(f"routing_edges={len(graph.edges)}")
print(f"sample_ref_xyz={xyz}")
print(f"sample_surface_xyz={surface}")
```

</details>

The repository includes a sample map at [datasets/chatt.xodr](datasets/chatt.xodr) and a simple smoke-test script at [tutorial.py](tutorial.py).

There is also a browser-based viewer in [web](web) that can be opened locally or served from a static HTTP server. See [pyxodr3d/web/README.md](pyxodr3d/web/README.md) for viewer instructions.

## Testing

Run the test suite with:

```powershell
pytest

# or generate coverage report (pytest-cov requried)
pytest --cov=pyxodr3d --cov-report=html  --cov-report=term

# or generate pylint report (pylint required)
pylint . --output=pylint_report.txt
```

The SUMO round-trip tests are skipped automatically when `netconvert` is not installed.

## License

`pyxodr3d` is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.

The repository also includes third-party assets under [third_party](third_party) with their own notices and licenses.
