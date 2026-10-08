from __future__ import annotations

import csv
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import threading
import urllib.request
import xml.etree.ElementTree as ET

import pytest

# Add system path for imports from pyxodr3d package
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyxodr3d as odr


def _opendrive_identifier_inventory(
    root: ET.Element,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Return road, junction, and qualified lane IDs in document order."""
    road_ids = tuple(road.get("id", "") for road in root.findall("road"))
    junction_ids = tuple(
        junction.get("id", "") for junction in root.findall("junction")
    )
    lane_ids: list[tuple[str, ...]] = []
    for road in root.findall("road"):
        road_id = road.get("id", "")
        for section_index, lane_section in enumerate(
            road.findall("./lanes/laneSection")
        ):
            section_s = lane_section.get("s", "")
            for side in ("left", "center", "right"):
                for lane in lane_section.findall(f"./{side}/lane"):
                    lane_ids.append(
                        (
                            road_id,
                            str(section_index),
                            section_s,
                            side,
                            lane.get("id", ""),
                        )
                    )
    return road_ids, junction_ids, tuple(lane_ids)


SYNTHETIC_XODR = """<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="4" name="unit">
    <geoReference>+proj=tmerc +lat_0=0</geoReference>
  </header>
  <road name="main" length="40" id="1" junction="-1" rule="RHT">
    <link>
      <successor elementType="junction" elementId="10"/>
      <neighbor elementId="2" side="right" direction="same"/>
    </link>
    <type s="0" type="town">
      <speed max="35" unit="mph"/>
    </type>
    <planView>
      <geometry s="0" x="100" y="50" hdg="0" length="10"><line/></geometry>
      <geometry s="10" x="110" y="50" hdg="0" length="10"><arc curvature="0.02"/></geometry>
      <geometry s="20" x="119.93" y="51.0" hdg="0.2" length="10"><spiral curvStart="0.0" curvEnd="0.0"/></geometry>
      <geometry s="30" x="129.73" y="52.99" hdg="0.2" length="10">
        <paramPoly3 aU="0" bU="10" cU="0" dU="0" aV="0" bV="0" cV="0" dV="0" pRange="normalized"/>
      </geometry>
    </planView>
    <elevationProfile>
      <elevation s="0" a="0" b="0.01" c="0" d="0"/>
    </elevationProfile>
    <lateralProfile>
      <superelevation s="0" a="0.01" b="0" c="0" d="0"/>
      <crossfall s="0" side="both" a="0.02" b="0" c="0" d="0"/>
      <crossfall s="20" side="left" a="0.03" b="0" c="0" d="0"/>
    </lateralProfile>
    <lanes>
      <laneOffset s="0" a="0.2" b="0" c="0" d="0"/>
      <laneSection s="0">
        <left>
          <lane id="1" type="driving" level="false">
            <link><successor id="1"/></link>
            <width sOffset="0" a="3.5" b="0" c="0" d="0"/>
            <height sOffset="0" inner="0.1" outer="0.2"/>
            <roadMark sOffset="0" type="solid" weight="standard" color="white" laneChange="none"/>
          </lane>
        </left>
        <center>
          <lane id="0" type="none" level="false">
            <roadMark sOffset="0" type="none"/>
          </lane>
        </center>
        <right>
          <lane id="-1" type="driving" level="false">
            <link><successor id="-1"/></link>
            <width sOffset="0" a="3.25" b="0" c="0" d="0"/>
            <roadMark sOffset="0" type="broken" weight="bold">
              <type name="dash" width="0.15">
                <line length="2" space="1" tOffset="0.1" sOffset="0" rule="none"/>
              </type>
            </roadMark>
          </lane>
        </right>
      </laneSection>
    </lanes>
    <objects>
      <object id="obj1" s="5" t="1" zOffset="0.2" length="2" validLength="3" width="1" height="2"
              hdg="0.1" pitch="0.2" roll="0.3" type="pole" name="Pole" orientation="+" subtype="sign" dynamic="yes">
        <repeat s="6" length="5" distance="2" tStart="1" tEnd="2" widthStart="1" widthEnd="2"
                heightStart="2" heightEnd="3" zOffsetStart="0.1" zOffsetEnd="0.2"/>
        <outlines>
          <outline id="1" fillType="grass" laneType="driving" outer="true" closed="true">
            <cornerLocal id="1" u="0" v="0" z="0" height="1"/>
            <cornerRoad id="2" s="6" t="1" dz="0" height="1"/>
          </outline>
        </outlines>
        <validity fromLane="-1" toLane="1"/>
      </object>
    </objects>
    <signals>
      <signal id="sig1" name="Speed" s="4" t="-1" dynamic="true" zOffset="1" value="35"
              height="1" width="0.5" hOffset="0.1" pitch="0.2" roll="0.3" orientation="+"
              country="US" type="274" subtype="35" unit="mph" text="35">
        <validity fromLane="-1" toLane="-1"/>
      </signal>
    </signals>
  </road>
  <road name="connector" length="12" id="2" junction="10" rule="LHT">
    <link>
      <predecessor elementType="road" elementId="1" contactPoint="end"/>
    </link>
    <planView>
      <geometry s="0" x="140" y="55" hdg="0.2" length="12"><spiral curvStart="0.01" curvEnd="0.02"/></geometry>
    </planView>
    <lanes>
      <laneSection s="0">
        <center><lane id="0" type="none"/></center>
        <right>
          <lane id="-1" type="driving">
            <link><predecessor id="-1"/></link>
            <width sOffset="0" a="3" b="0" c="0" d="0"/>
          </lane>
        </right>
      </laneSection>
    </lanes>
  </road>
  <junction name="junction" id="10">
    <connection id="0" incomingRoad="1" connectingRoad="2" contactPoint="start">
      <laneLink from="-1" to="-1"/>
    </connection>
    <priority high="1" low="2"/>
    <controller id="ctrl" type="signal" sequence="1"/>
  </junction>
</OpenDRIVE>
"""


@pytest.fixture()
def synthetic_file(tmp_path: Path) -> Path:
    xodr = tmp_path / "synthetic.xodr"
    xodr.write_text(SYNTHETIC_XODR, encoding="utf-8")
    return xodr


@pytest.fixture()
def synthetic_map(synthetic_file: Path) -> odr.OpenDriveMap:
    return odr.readXodr(synthetic_file)


def assert_vec_finite(vec: tuple[float, ...]) -> None:
    assert all(math.isfinite(v) for v in vec)


def elems_by_id(root: ET.Element, tag: str) -> dict[str, ET.Element]:
    """Return a dict mapping element id to element for all elements matching tag.

    Elements without an 'id' attribute are skipped so the returned dict has
    only string keys (matching the declared return type).
    """
    elems: dict[str, ET.Element] = {}
    for e in root.findall(tag):
        _id = e.get("id")
        if _id is not None:
            elems[_id] = e
    return elems


def lane_polygon_center(feature: dict) -> list[float]:
    ring = feature["geometry"]["coordinates"][0]
    points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    half = len(points) // 2
    outer = points[:half]
    inner = list(reversed(points[half:]))
    return [
        (sum(point[0] for point in outer) + sum(point[0] for point in inner))
        / (2 * len(outer)),
        (sum(point[1] for point in outer) + sum(point[1] for point in inner))
        / (2 * len(outer)),
    ]


def meters_between_lonlat(a: list[float], b: list[float]) -> float:
    lat = (a[1] + b[1]) * 0.5
    return math.hypot(
        (a[0] - b[0]) * 111_320 * math.cos(math.radians(lat)),
        (a[1] - b[1]) * 110_540,
    )


def test_open_drive_map_can_be_built_empty_with_add_methods() -> None:
    odr_map = odr.OpenDriveMap()
    road = odr.xodr.Road("manual_road", 10.0, "-1", "manual")
    junction = odr.xodr.Junction("manual junction", "manual_junction")

    assert odr_map.getRoads() == []
    assert odr_map.addRoad(road) is road
    assert odr_map.addJunction(junction) is junction

    assert odr_map.getRoad("manual_road") is road
    assert odr_map.getJunction("manual_junction") is junction


def test_synthetic_map_parses_roads_junctions_and_metadata(
    synthetic_map: odr.OpenDriveMap,
) -> None:
    assert synthetic_map.proj4.startswith("+proj=tmerc")
    assert synthetic_map.getGeoProj().startswith("+proj=tmerc")
    assert len(synthetic_map.getRoads()) == 2
    assert len(synthetic_map.getJunctions()) == 1

    road = synthetic_map.getRoad("1")
    assert road.name == "main"
    assert road.successor.type == "junction"
    assert road.neighbors[0].id == "2"
    assert road.s_to_type[0.0] == "town"
    assert road.s_to_speed[0.0].max == "35"
    assert len(road.ref_line.get_geometries()) == 4

    connector = synthetic_map.getRoad("2")
    assert connector.left_hand_traffic is True
    assert connector.predecessor.id == "1"

    junction = synthetic_map.getJunction("10")
    assert junction.id_to_connection["0"].lane_links[0].from_lane == -1
    assert junction.priorities[0].high == "1"
    assert junction.id_to_controller["ctrl"].sequence == 1


def test_open_drive_map_global_query_helpers(synthetic_map: odr.OpenDriveMap) -> None:
    west, south, east, north = synthetic_map.getBoundary()
    assert west <= east
    assert south <= north

    assert synthetic_map.getSignal("sig1").id == "sig1"
    assert synthetic_map.getSignal("sig1", road_id="1").road_id == "1"
    assert [signal.id for signal in synthetic_map.getSignals()] == ["sig1"]
    assert [signal.id for signal in synthetic_map.getSignals("1")] == ["sig1"]
    assert synthetic_map.getSignals("2") == []

    lane = synthetic_map.getLane(-1)
    assert lane.id == -1
    assert [lane.id for lane in synthetic_map.getLanes("1")] == [-1, 0, 1]
    assert len(synthetic_map.getLanes()) == 5


def test_open_drive_map_lon_lat_conversion_without_header_offset(
    tmp_path: Path,
) -> None:
    xodr = tmp_path / "no_offset.xodr"
    proj4 = "+proj=tmerc +lat_0=0 +lon_0=0 +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +geoidgrids=egm96_15.gtx +vunits=m +no_defs"
    xodr.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="4" north="10" south="0" east="10" west="0">
    <geoReference><![CDATA[{proj4} ]]></geoReference>
  </header>
  <road name="main" length="10" id="1" junction="-1">
    <planView>
      <geometry s="0" x="0" y="0" hdg="0" length="10"><line/></geometry>
    </planView>
    <lanes><laneSection s="0"><center><lane id="0" type="none"/></center></laneSection></lanes>
  </road>
</OpenDRIVE>
""",
        encoding="utf-8",
    )

    odr_map = odr.readXodr(xodr)

    assert odr_map.getGeoProj() == proj4
    lon, lat = odr_map.convertXY2LonLat(0.0, 0.0)
    x, y = odr_map.convertLonLat2XY(lon, lat)

    assert_vec_finite((lon, lat, x, y))
    assert lon == pytest.approx(0.0, abs=1e-9)
    assert lat == pytest.approx(0.0, abs=1e-9)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)


def test_ego_select_existing_mode_highlights_selected_vehicle(tmp_path: Path) -> None:
    from pyxodr3d.sim.config import EgoVehicleConfig, ScenarioConfig
    from pyxodr3d.sim.sumo_builder import apply_ego_vehicle_config

    route_file = tmp_path / "routes.rou.xml"
    route_file.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<routes>\n"
        '  <vehicle id="veh_0" depart="0" type="car"/>\n'
        '  <vehicle id="veh_1" depart="0" type="car"/>\n'
        "</routes>\n",
        encoding="utf-8",
    )
    scenario = ScenarioConfig(
        ego=EgoVehicleConfig(
            enabled=True,
            mode="select_existing",
            highlight_color="255,0,0",
            vehicle_ids=["veh_1"],
            vehicle_attributes={"departSpeed": "max"},
        )
    )

    ego_ids = apply_ego_vehicle_config(route_file, scenario)
    root = ET.parse(route_file).getroot()
    vehicles = elems_by_id(root, "vehicle")

    assert ego_ids == ["veh_1"]
    assert vehicles["veh_0"].get("type") == "car"
    assert vehicles["veh_1"].get("type") == "ego_passenger"
    assert vehicles["veh_1"].get("color") == "255,0,0"
    assert vehicles["veh_1"].get("departSpeed") == "max"


def test_ego_add_mode_supports_od_pairs_and_edge_routes(tmp_path: Path) -> None:
    from pyxodr3d.sim.config import EgoVehicleConfig, ScenarioConfig
    from pyxodr3d.sim.sumo_builder import apply_ego_vehicle_config

    route_file = tmp_path / "routes.rou.xml"
    route_file.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<routes />\n',
        encoding="utf-8",
    )
    scenario = ScenarioConfig(
        ego=EgoVehicleConfig(
            enabled=True,
            mode="add",
            highlight_color="0,0,255",
            od_pairs=[
                {
                    "id": "ego_od",
                    "depart": "27000",
                    "origin_edge": "edge_a",
                    "destination_edge": "edge_c",
                }
            ],
            route_vehicles=[
                {
                    "id": "ego_route",
                    "depart": "27010",
                    "edges": ["edge_a", "edge_b", "edge_c"],
                }
            ],
        )
    )

    ego_ids = apply_ego_vehicle_config(route_file, scenario)
    root = ET.parse(route_file).getroot()
    trips = elems_by_id(root, "trip")
    vehicles = elems_by_id(root, "vehicle")

    assert ego_ids == ["ego_od", "ego_route"]
    assert trips["ego_od"].get("type") == "ego_passenger"
    assert trips["ego_od"].get("from") == "edge_a"
    assert trips["ego_od"].get("to") == "edge_c"
    assert trips["ego_od"].get("color") == "0,0,255"
    assert vehicles["ego_route"].get("type") == "ego_passenger"
    assert vehicles["ego_route"].get("color") == "0,0,255"
    assert vehicles["ego_route"].find("route").get("edges") == ("edge_a edge_b edge_c")


def test_sumo_additional_sanitizer_removes_missing_lane_detectors(
    tmp_path: Path,
) -> None:
    from pyxodr3d.sim.sumo_builder import sanitize_sumo_project_additional_files

    sumo_dir = tmp_path / "sumo"
    sumo_dir.mkdir()
    (sumo_dir / "network.net.xml").write_text(
        """<net>
  <edge id="edge_a">
    <lane id="edge_a_0" index="0"/>
  </edge>
</net>
""",
        encoding="utf-8",
    )
    (sumo_dir / "detectors.add.xml").write_text(
        """<additional>
  <inductionLoop id="valid_loop" lane="edge_a_0" pos="-8" file="loop.xml"/>
  <inductionLoop id="missing_loop" lane="missing_0" pos="-8" file="loop.xml"/>
  <laneAreaDetector id="mixed_area" lanes="edge_a_0 missing_1" pos="0" endPos="5" file="area.xml"/>
  <vType id="passenger"/>
</additional>
""",
        encoding="utf-8",
    )
    (sumo_dir / "scenario.sumocfg").write_text(
        """<configuration>
  <input>
    <net-file value="network.net.xml"/>
    <additional-files value="detectors.add.xml"/>
  </input>
</configuration>
""",
        encoding="utf-8",
    )

    summary = sanitize_sumo_project_additional_files(sumo_dir)
    root = ET.parse(sumo_dir / "detectors.add.xml").getroot()
    element_ids = {element.get("id") for element in root}

    assert summary["status"] == "sanitized"
    assert summary["removed_count"] == 2
    assert element_ids == {"valid_loop", "passenger"}


def test_run_sumo_sanitizes_additional_files_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pyxodr3d.sim import cli

    sumo_dir = tmp_path / "sumo"
    sumo_dir.mkdir()
    (sumo_dir / "outputs").mkdir()
    (sumo_dir / "network.net.xml").write_text(
        """<net><edge id="edge_a"><lane id="edge_a_0" index="0"/></edge></net>""",
        encoding="utf-8",
    )
    (sumo_dir / "routes.rou.xml").write_text("<routes />", encoding="utf-8")
    (sumo_dir / "detectors.add.xml").write_text(
        """<additional>
  <inductionLoop id="bad_detector" lane="missing_0" pos="-8" file="loop.xml"/>
</additional>
""",
        encoding="utf-8",
    )
    (sumo_dir / "scenario.sumocfg").write_text(
        """<configuration>
  <input>
    <net-file value="network.net.xml"/>
    <route-files value="routes.rou.xml"/>
    <additional-files value="detectors.add.xml"/>
  </input>
</configuration>
""",
        encoding="utf-8",
    )

    launched_commands: list[list[str]] = []
    monkeypatch.setattr(cli, "find_sumo_tool", lambda _tool_name: tmp_path / "sumo.exe")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda command, cwd, check: launched_commands.append(list(command)),
    )

    cli.run_sumo(tmp_path)
    captured = capsys.readouterr()

    assert "removed 1 lane-based element" in captured.out
    assert launched_commands == [[str(tmp_path / "sumo.exe"), "-c", "scenario.sumocfg"]]
    root = ET.parse(sumo_dir / "detectors.add.xml").getroot()
    assert root.findall("inductionLoop") == []


def test_cli_reports_missing_sumo_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pyxodr3d.sim import cli

    sumo_dir = tmp_path / "sumo"
    sumo_dir.mkdir()
    (sumo_dir / "scenario.sumocfg").write_text(
        "<configuration />",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "find_sumo_tool", lambda _tool_name: None)

    exit_code = cli.main(["run-sumo", "--project", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "SUMO is missing on this operating system" in captured.err
    assert "sumo" in captured.err
    assert "SUMO_HOME" in captured.err


def test_cli_reports_missing_carla_python_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pyxodr3d.sim import cli

    carla_dir = tmp_path / "carla"
    carla_dir.mkdir()
    (carla_dir / "load_opendrive_world.py").write_text(
        "print('unused')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_python_module_available", lambda _module_name: False)

    exit_code = cli.main(["run-carla", "--project", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "CARLA Python API is missing on this operating system" in captured.err
    assert "PYTHONPATH" in captured.err


def test_analysis_writes_csv_when_figures_are_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pyxodr3d.sim import analysis

    tripinfo_path = tmp_path / "tripinfo.xml"
    tripinfo_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<tripinfos>
  <tripinfo id="ego_1" depart="0" arrival="12" duration="12" routeLength="120"
            waitingTime="1" waitingCount="1" timeLoss="2"/>
</tripinfos>
""",
        encoding="utf-8",
    )

    def fail_to_load_plotter() -> object:
        raise analysis.FigureGenerationError("plot stack missing")

    monkeypatch.setattr(analysis, "_load_matplotlib_pyplot", fail_to_load_plotter)
    outputs = analysis.analyze_project(
        tripinfo_path=tripinfo_path,
        out_dir=tmp_path / "analysis",
        scenario_id="csv_without_figures",
        skip_carla=True,
    )

    metadata = json.loads(outputs["run_metadata"].read_text(encoding="utf-8"))
    assert outputs["scenario_summary"].exists()
    assert outputs["mobility_energy_table"].exists()
    assert metadata["figure_generation_status"].startswith("skipped:")
    assert metadata["figures"] == {}
    assert not any(name.startswith("figure_") for name in outputs)


def test_tripinfo_summary_reports_energy_without_pollutant_outputs() -> None:
    from pyxodr3d.sim.analysis import summarize_tripinfo

    rows: list[dict[str, object]] = [
        {
            "depart": 0.0,
            "arrival": 100.0,
            "duration": 100.0,
            "routeLength": 1000.0,
            "emissions_fuel_abs": 1_000_000.0,
            "emissions_electricity_abs": 1000.0,
            "battery_totalEnergyConsumed": 2000.0,
            "battery_totalEnergyRegenerated": 500.0,
        }
    ]

    summary = summarize_tripinfo(rows, "energy_check")

    assert "total_co2_mg" not in summary
    assert "co2_g_per_km" not in summary
    assert summary["fuel_energy_kwh"] == pytest.approx(44.0 / 3.6)
    assert summary["electricity_energy_kwh"] == pytest.approx(1.0)
    assert summary["battery_consumed_kwh"] == pytest.approx(2.0)
    assert summary["battery_regenerated_kwh"] == pytest.approx(0.5)
    assert summary["net_energy_kwh"] == pytest.approx((44.0 / 3.6) + 2.0 - 0.5)
    assert summary["energy_kwh_per_km"] == pytest.approx(summary["net_energy_kwh"])


def test_summarize_replicates_writes_energy_savings(tmp_path: Path) -> None:
    from pyxodr3d.sim.analysis import summarize_replicates

    baseline_summary = tmp_path / "baseline_summary.csv"
    optimized_summary = tmp_path / "optimized_summary.csv"
    baseline_summary.write_text(
        "scenario_id,net_energy_kwh,energy_kwh_per_km\nbaseline,10,1.0\n",
        encoding="utf-8",
    )
    optimized_summary.write_text(
        "scenario_id,net_energy_kwh,energy_kwh_per_km\nsignal_optimized,8,0.8\n",
        encoding="utf-8",
    )

    outputs = summarize_replicates(
        [baseline_summary, optimized_summary],
        tmp_path / "analysis",
    )

    with outputs["energy_savings"].open("r", newline="", encoding="utf-8") as file_obj:
        rows = list(csv.DictReader(file_obj))
    optimized_row = next(
        row for row in rows if row["scenario_id"] == "signal_optimized"
    )

    assert optimized_row["baseline_scenario_id"] == "baseline"
    assert float(optimized_row["energy_saved_kwh"]) == pytest.approx(2.0)
    assert float(optimized_row["energy_saved_percent"]) == pytest.approx(20.0)


def test_open_drive_map_save_xodr_preserves_loaded_xml(
    synthetic_map: odr.OpenDriveMap,
    tmp_path: Path,
) -> None:
    saved = synthetic_map.saveXodr(tmp_path / "nested" / "saved.xodr")

    assert saved == tmp_path / "nested" / "saved.xodr"
    assert saved.exists()

    root = ET.parse(saved).getroot()
    assert root.tag == "OpenDRIVE"
    assert root.find("./road[@id='1']") is not None
    assert root.find("./junction[@id='10']") is not None

    reloaded = odr.readXodr(saved)
    assert len(reloaded.getRoads()) == len(synthetic_map.getRoads())
    assert len(reloaded.getJunctions()) == len(synthetic_map.getJunctions())


def test_web_save_persists_dragged_lane_geometry(synthetic_file: Path) -> None:
    from pyxodr3d.web._editor import _ViewerState

    state = _ViewerState(synthetic_file)
    payload = state.as_response()
    lane = deepcopy(payload["lane_geojson"]["features"][0])
    original_center = lane_polygon_center(lane)

    for ring in lane["geometry"]["coordinates"]:
        for coord in ring:
            coord[0] += 0.00004
            coord[1] += 0.00002
    lane["geometry_edited"] = True
    edited_center = lane_polygon_center(lane)

    for index, feature in enumerate(payload["lane_geojson"]["features"]):
        if feature["id"] == lane["id"]:
            payload["lane_geojson"]["features"][index] = lane
            break

    saved = state.save_geojson(
        payload["geojson"],
        payload["lane_geojson"],
        payload["signal_geojson"],
    )
    assert saved["saved_filename"] == "edited_network.xodr"
    assert saved["saved_format"] == "xodr"
    assert saved["download_text"] == saved["xodr"]
    reloaded_lane = next(
        feature
        for feature in saved["lane_geojson"]["features"]
        if feature["id"] == lane["id"]
    )
    reloaded_center = lane_polygon_center(reloaded_lane)

    assert meters_between_lonlat(original_center, reloaded_center) > 1.0
    assert meters_between_lonlat(
        edited_center, reloaded_center
    ) < meters_between_lonlat(
        original_center,
        edited_center,
    )


def test_web_package_exports_default_xodr() -> None:
    """The module CLI imports DEFAULT_XODR from the package namespace."""
    from pyxodr3d.web import DEFAULT_XODR

    assert DEFAULT_XODR.name == "data.xodr"
    assert DEFAULT_XODR.exists()


def test_web_static_javascript_uses_module_mime_type() -> None:
    """Browsers reject module scripts unless JavaScript has a JS MIME type."""
    from pyxodr3d.web import run_server

    server, url = run_server(open_browser=False, port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        script_urls = [
            f"{url}index.js?v=cache_bust",
            f"{url}static/odr-3d-objects.js",
        ]
        for script_url in script_urls:
            with urllib.request.urlopen(script_url, timeout=30) as response:
                content_type = response.getheader("Content-Type")
            assert content_type is not None
            assert content_type.split(";", 1)[0] == "text/javascript"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_javascript_pins_editor_maplibre_dependency() -> None:
    """Editor modules must use the same MapLibre version as the viewer."""
    repo_root = Path(__file__).resolve().parents[1]
    index_javascript = (repo_root / "pyxodr3d" / "web" / "index.js").read_text(
        encoding="utf-8"
    )

    expected_import_urls = (
        "https://esm.sh/@geoman-io/maplibre-geoman-free@0.7.1"
        "?deps=maplibre-gl@5.24.0",
        "https://esm.sh/maplibre-gl-geo-editor@0.7.3"
        "?deps=maplibre-gl@5.24.0",
    )
    for import_url in expected_import_urls:
        assert f'from "{import_url}"' in index_javascript


def test_web_uses_ornl_logo_as_favicon() -> None:
    """The browser tab must use the supplied ORNL JPEG logo."""
    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "pyxodr3d" / "web"
    index_html = (web_root / "index.html").read_text(encoding="utf-8")
    logo_bytes = (web_root / "ornl_logo.png").read_bytes()

    assert '<link rel="icon" type="image/png" href="./ornl_logo.png" />' in index_html
    assert logo_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_web_uses_keyless_openfreemap_light_basemap() -> None:
    """The light basemap must not require API-key configuration."""
    repo_root = Path(__file__).resolve().parents[1]
    index_javascript = (repo_root / "pyxodr3d" / "web" / "index.js").read_text(
        encoding="utf-8"
    )
    editor_source = (repo_root / "pyxodr3d" / "web" / "_editor.py").read_text(
        encoding="utf-8"
    )

    assert "openfreemap_positron: {" in index_javascript
    assert (
        'styleUrl: "https://tiles.openfreemap.org/styles/positron"'
        in index_javascript
    )
    assert "if (basemap.styleUrl) return basemap.styleUrl;" in index_javascript
    assert "// carto_light: {" in index_javascript
    assert "// carto_dark: {" in index_javascript
    assert "CARTO_BASEMAP_API_KEY" not in index_javascript
    assert "CARTO_BASEMAP_API_KEY" not in editor_source
    assert 'path == "/api/config"' not in editor_source


def test_web_spotlight_panel_can_dock_on_either_side() -> None:
    """The full-height viewer sidebar must sit outside the main map view."""
    repo_root = Path(__file__).resolve().parents[1]
    index_html = (repo_root / "pyxodr3d" / "web" / "index.html").read_text(
        encoding="utf-8"
    )
    index_css = (repo_root / "pyxodr3d" / "web" / "index.css").read_text(
        encoding="utf-8"
    )
    index_javascript = (repo_root / "pyxodr3d" / "web" / "index.js").read_text(
        encoding="utf-8"
    )
    main_view_rule = index_css.partition("#main_view {")[2].partition("}")[0]
    map_rule = index_css.partition("#map {")[2].partition("}")[0]
    spotlight_rule = index_css.partition("#spotlight {")[2].partition("}")[0]
    splitter_rule = index_css.partition("#spotlight_splitter {")[2].partition("}")[0]
    resize_dots_rule = index_css.partition("#spotlight_splitter::after {")[2].partition(
        "}"
    )[0]
    attribute_row_rule = index_css.partition(".attribute-row {")[2].partition("}")[0]
    attribute_input_rule = index_css.partition(
        ".attribute-row input,\n.attribute-row textarea {"
    )[2].partition("}")[0]
    spotlight_content_rule = index_css.partition("#spotlight_content {")[2].partition(
        "}"
    )[0]
    attribute_editor_rule = index_css.partition("#attribute_editor {")[2].partition(
        "}"
    )[0]
    attribute_fields_rule = index_css.partition("#attribute_fields {")[2].partition(
        "}"
    )[0]
    attribute_fields_data_rule = index_css.partition(
        "#attribute_fields:not(:empty) {"
    )[2].partition("}")[0]

    assert '<main id="main_view">' in index_html
    assert '<body data-spotlight-side="right">' in index_html
    assert 'id="spotlight_splitter"' in index_html
    assert 'role="separator"' in index_html
    assert '<aside id="spotlight" data-side="right"' in index_html
    assert index_html.index('id="spotlight_splitter"') < index_html.index(
        '<aside id="spotlight"'
    )
    assert "spotlight_resize_handle_left" not in index_html
    assert "spotlight_resize_handle_right" not in index_html
    assert 'id="spotlight_dock_left"' in index_html
    assert 'id="spotlight_dock_right"' in index_html
    assert "flex: 1 1 auto;" in main_view_rule
    assert "min-width: 0;" in main_view_rule
    assert "margin: 0 !important;" in main_view_rule
    assert "padding: 0 !important;" in main_view_rule
    assert "border-radius: 12px;" in main_view_rule
    assert "inset: 0;" in map_rule
    assert "margin: 0;" in map_rule
    assert "padding: 0;" in map_rule
    assert "#map .maplibregl-canvas-container" in index_css
    assert "#map .maplibregl-canvas {" in index_css
    assert 'href="./index.css?v=20261007_basemap_notice_autohide"' in index_html
    assert "position: relative;" in spotlight_rule
    assert "flex: 0 0 auto;" in spotlight_rule
    assert "height: 100%;" in spotlight_rule
    assert "border-radius: 12px;" in spotlight_rule
    assert "--panel-gap" not in index_css
    assert "gap: 0;" in index_css
    assert "order: 1;" in splitter_rule
    assert "width: 8px;" in splitter_rule
    assert "height: 100%;" in splitter_rule
    assert 'body[data-spotlight-side="left"] #main_view' in index_css
    assert "top: 50%;" in resize_dots_rule
    assert "left: 50%;" in resize_dots_rule
    assert "margin: -2px 0 0 -2px;" in resize_dots_rule
    assert "width: 4px;" in resize_dots_rule
    assert (
        "box-shadow: 0 -5px 0 currentColor, 0 5px 0 currentColor;"
        in resize_dots_rule
    )
    assert "#attribute_fields:not(:empty)" in index_css
    assert "minmax(62px, 0.42fr) minmax(0, 1fr)" in attribute_row_rule
    assert "min-width: 0;" in attribute_row_rule
    assert "box-sizing: border-box;" in attribute_input_rule
    assert "max-width: 100%;" in attribute_input_rule
    assert "overflow: hidden;" in spotlight_content_rule
    assert "overflow: hidden;" in attribute_editor_rule
    assert "min-height: 0;" in attribute_fields_rule
    assert "#attribute_fields:empty" in index_css
    assert "display: none;" in index_css.partition("#attribute_fields:empty {")[2].partition("}")[0]
    assert "flex: 1 1 0;" in attribute_fields_data_rule
    assert "height: 0;" in attribute_fields_data_rule
    assert "box-sizing: border-box;" in attribute_fields_data_rule
    assert "overflow-y: auto;" in attribute_fields_data_rule
    assert "align-content: start;" in attribute_fields_data_rule
    assert '#spotlight[data-side="left"]' in index_css
    assert '#spotlight[data-side="right"]' in index_css
    assert (
        'const SPOTLIGHT_SIDE_STORAGE_KEY = "opendriveviewer_side"'
        in index_javascript
    )
    assert 'setSpotlightSide(storedSide === "left" ? "left" : "right", false)' in (
        index_javascript
    )
    assert 'spotlightDockLeft.addEventListener("click"' in index_javascript
    assert 'spotlightDockRight.addEventListener("click"' in index_javascript
    assert "document.body.dataset.spotlightSide = nextSide;" in index_javascript
    assert 'spotlightSplitter.addEventListener("pointerdown"' in index_javascript
    assert 'spotlightSplitter.addEventListener("keydown"' in index_javascript
    assert "spotlightSplitter.hidden = collapsed;" in index_javascript
    assert "spotlightResizeHandleLeft" not in index_javascript
    assert "spotlightResizeHandleRight" not in index_javascript
    assert "map.resize();" in index_javascript
    assert "mainView.getBoundingClientRect()" in index_javascript
    assert "setSpotlightPosition" not in index_javascript
    assert 'localStorage.removeItem("opendriveviewer_left")' in index_javascript
    assert 'localStorage.removeItem("opendriveviewer_top")' in index_javascript


def test_web_sidebar_has_project_links_and_section_navigation() -> None:
    """The sidebar exposes project links, useful sections, and collapsed icons."""
    repo_root = Path(__file__).resolve().parents[1]
    index_html = (repo_root / "pyxodr3d" / "web" / "index.html").read_text(
        encoding="utf-8"
    )
    index_css = (repo_root / "pyxodr3d" / "web" / "index.css").read_text(
        encoding="utf-8"
    )
    index_javascript = (repo_root / "pyxodr3d" / "web" / "index.js").read_text(
        encoding="utf-8"
    )

    assert 'id="spotlight_project_links"' in index_html
    assert 'href="./" title="pyxodr3d home"' in index_html
    assert 'href="https://github.com/ORNL-Real-Sim/pyxodr3d"' in index_html
    assert 'href="https://github.com/ORNL-Real-Sim/pyxodr3d/issues"' in index_html
    assert '<span>pyxodr3d</span>' in index_html
    assert '<span>GitHub</span>' in index_html
    assert '<span>Issue Tracker</span>' in index_html
    assert 'id="spotlight_section_nav" role="tablist"' in index_html
    assert 'data-spotlight-section="editor"' in index_html
    assert 'data-spotlight-section="routing"' in index_html
    assert 'data-spotlight-section="view"' in index_html
    assert 'class="fa fa-pencil-square-o"' in index_html
    assert 'class="fa fa-random"' in index_html
    assert 'class="fa fa-eye"' in index_html
    assert '>Selected Data<' not in index_html
    assert 'id="attribute_editor_title" class="spotlight-section-title">Editor<' in index_html
    assert '#spotlight.collapsed #spotlight_section_nav' in index_css
    assert '#spotlight.collapsed .spotlight-section-label' in index_css
    assert 'function setSpotlightSection(sectionName)' in index_javascript
    assert 'panel.hidden = panel.dataset.spotlightPanel !== sectionName;' in index_javascript
    assert 'setSpotlightCollapsed(false);' in index_javascript
    assert 'button.addEventListener("keydown", navigateSpotlightSections);' in index_javascript


def test_web_sidebar_includes_routing_and_view_options() -> None:
    """The sidebar provides Python-backed routing and layer visibility choices."""
    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "pyxodr3d" / "web"
    index_html = (web_root / "index.html").read_text(encoding="utf-8")
    index_javascript = (web_root / "index.js").read_text(encoding="utf-8")

    for element_id in [
        "route_select_start_btn",
        "route_select_end_btn",
        "route_calculate_btn",
        "route_clear_btn",
        "route_start_lane",
        "route_end_lane",
        "route_summary",
    ]:
        assert f'id="{element_id}"' in index_html

    view_options = {
        "view_road_objects": "roadObjects",
        "view_road_signals": "roadSignals",
        "view_road_shoulder": "roadShoulder",
        "view_road_sidewalk": "roadSidewalk",
        "view_reference_line": "referenceLine",
        "view_reference_line_arrows": "referenceLineArrows",
        "view_roadmarks": "roadmarks",
        "view_grid": "grid",
        "view_wireframe": "wireframe",
        "view_roads": "roads",
    }
    for element_id, option_name in view_options.items():
        assert f'id="{element_id}"' in index_html
        assert f'data-view-option="{option_name}"' in index_html

    assert 'requestJson("/api/route"' in index_javascript
    assert "start_lane_key: routeStartLaneKey" in index_javascript
    assert "end_lane_key: routeEndLaneKey" in index_javascript
    assert 'addEditorGeoJsonSource("opendrive-route"' in index_javascript
    assert 'setRouteEndpoint(routeSelectionTarget, lane);' in index_javascript
    assert "parse_options" not in index_javascript
    assert "Parse Options" not in index_html
    assert 'map.setPaintProperty(' in index_javascript
    assert 'map.setFilter(layerId, featureFilter);' in index_javascript
    assert "function applyLaneViewOptions()" in index_javascript
    assert 'viewOptions.roadShoulder' in index_javascript
    assert 'viewOptions.roadSidewalk' in index_javascript
    assert '["opendrive-lanes", "opendrive-lane-borders"]' in index_javascript
    assert 'hiddenLaneTypes.push("shoulder")' in index_javascript
    assert 'hiddenLaneTypes.push("sidewalk")' in index_javascript
    assert (
        "Unselectable fields indicate that the source file contains no related data."
        in " ".join(index_html.split())
    )
    assert "function viewOptionAvailability()" in index_javascript
    assert "function updateViewOptionAvailability()" in index_javascript
    assert 'roadObjects: signalFeatureTypes.has("signal_object")' in index_javascript
    assert 'roadShoulder: laneTypes.has("shoulder")' in index_javascript
    assert 'roadSidewalk: laneTypes.has("sidewalk")' in index_javascript
    assert "input.disabled = !available;" in index_javascript
    assert 'row.classList.toggle("unavailable", !available);' in index_javascript
    assert ".spotlight-option-row.unavailable" in (
        web_root / "index.css"
    ).read_text(encoding="utf-8")
    assert '["opendrive-road-casing", "opendrive-roads"]' in index_javascript
    assert '["gridmesh-lines-minor", "gridmesh-lines-major"]' in index_javascript


def test_web_routing_uses_python_lane_graph(
    synthetic_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The web route response follows the directed Python lane graph."""
    from pyxodr3d.web._editor import _ViewerState

    monkeypatch.setattr(
        odr.OpenDriveMap,
        "convertXY2LonLat",
        lambda self, x, y: (float(x) / 111_320.0, float(y) / 110_540.0),
    )
    monkeypatch.setattr(
        odr.OpenDriveMap,
        "convertLonLat2XY",
        lambda self, lon, lat: (float(lon) * 111_320.0, float(lat) * 110_540.0),
    )
    state = _ViewerState(synthetic_file)
    start = "1/0.000000/-1"
    end = "2/0.000000/-1"

    route = state.route_between_lanes(start, end)

    assert route["lane_keys"] == [start, end]
    assert route["lane_count"] == 2
    assert route["length_m"] > 0
    assert [
        feature["properties"]["route_role"]
        for feature in route["route_geojson"]["features"]
    ] == ["start", "end"]

    with pytest.raises(ValueError, match="Unknown start lane key"):
        state.route_between_lanes("missing", end)
    with pytest.raises(ValueError, match="No directed lane route exists"):
        state.route_between_lanes(end, start)


def test_web_basemap_fallback_requires_invalid_projection() -> None:
    """Invalid map coordinates use Grid Mesh without reacting to tile errors."""
    repo_root = Path(__file__).resolve().parents[1]
    index_html = (repo_root / "pyxodr3d" / "web" / "index.html").read_text(
        encoding="utf-8"
    )
    index_css = (repo_root / "pyxodr3d" / "web" / "index.css").read_text(
        encoding="utf-8"
    )
    index_javascript = (repo_root / "pyxodr3d" / "web" / "index.js").read_text(
        encoding="utf-8"
    )
    normalized_html = " ".join(index_html.split())

    assert 'id="basemap_fallback_notice" role="status" aria-live="polite"' in (
        index_html
    )
    assert (
        "source file does not include usable projection information"
        in normalized_html
    )
    assert "could not be rendered on a real-world map" in normalized_html
    assert "#basemap_fallback_notice[hidden]" in index_css
    assert "#basemap_fallback_notice.is-visible" in index_css
    assert "payloadSupportsRealWorldBasemap === false" in index_javascript
    assert 'const nextBasemapId = unsupportedRealWorldBasemap ? "gridmesh"' in (
        index_javascript
    )
    assert (
        'const basemapId = payloadSupportsRealWorldBasemap ? "google_satellite"'
        in index_javascript
    )
    assert "return changeBasemap(basemapId, { persist: false });" in index_javascript
    assert 'map.on("error", handleBasemapRenderError)' not in index_javascript
    assert "isActiveBasemapRenderError" not in index_javascript
    assert "basemapFallbackNoticeClose.addEventListener" in index_javascript
    assert "const BASEMAP_FALLBACK_NOTICE_DURATION_MS = 7000;" in index_javascript
    assert 'basemapFallbackNotice.classList.add("is-visible")' in index_javascript
    assert 'basemapFallbackNotice.classList.remove("is-visible")' in index_javascript
    assert "BASEMAP_FALLBACK_NOTICE_FADE_MS" in index_javascript


def test_web_lane_arrows_use_connected_representative_movements() -> None:
    """Lane arrows must use topology and collapse redundant lane polygons."""
    repo_root = Path(__file__).resolve().parents[1]
    index_javascript = (repo_root / "pyxodr3d" / "web" / "index.js").read_text(
        encoding="utf-8"
    )

    assert "orientLaneCandidate(candidate, rawCandidatesByKey)" in index_javascript
    assert "function laneArrowCenterline(feature)" in index_javascript
    assert index_javascript.count("function laneCenterline(feature)") == 1
    assert (
        'connectedExternalRoadIds(candidate, "predecessor_keys", candidatesByKey)'
        in index_javascript
    )
    assert "selectLaneArrowRepresentative(group)" in index_javascript
    assert 'laneType && laneType !== "driving"' in index_javascript
    assert "represented_lane_count: group.length" in index_javascript


def test_web_lane_width_uses_exact_server_mesh() -> None:
    """Width changes must request an exact mesh and preserve non-driving widths."""
    repo_root = Path(__file__).resolve().parents[1]
    index_javascript = (repo_root / "pyxodr3d" / "web" / "index.js").read_text(
        encoding="utf-8"
    )

    assert 'requestJson("/api/preview-lane-geometry"' in index_javascript
    assert "function scheduleLaneGeometryPreview(" in index_javascript
    assert "function laneGeometryPreviewPayload()" in index_javascript
    assert "lane_geojson: laneGeometryPreviewPayload()" in index_javascript
    assert "const LANE_GEOMETRY_PREVIEW_DEBOUNCE_MS = 120;" in index_javascript
    assert 'laneType === "driving"' in index_javascript
    assert "lane.width_scale" in index_javascript
    assert "rebuildAllLaneSectionGeometry" not in index_javascript
    assert "stitchConnectedLaneEndpoints" not in index_javascript


def test_web_lane_geometry_preview_is_exact_and_nonmutating(
    synthetic_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Width previews must use parser geometry without changing loaded state."""
    from pyxodr3d.web._editor import _ViewerState

    monkeypatch.setattr(
        odr.OpenDriveMap,
        "convertXY2LonLat",
        lambda self, x, y: (float(x) / 111_320.0, float(y) / 110_540.0),
    )
    state = _ViewerState(synthetic_file)
    original = state.as_response()["lane_geojson"]
    edited = deepcopy(original)
    width_scale = 1.25
    for feature in edited["features"]:
        if feature["properties"]["lane_type"] == "driving":
            feature["width_scale"] = width_scale

    cached_preview_map_id = id(state._lane_preview_map)
    preview_response = state.preview_lane_geojson(edited)
    preview = preview_response["lane_geojson"]
    preview_widths = [
        feature["properties"]["width"]
        for feature in preview["features"]
        if feature["properties"]["lane_type"] == "driving"
    ]
    loaded_widths = [
        feature["properties"]["width"]
        for feature in state.as_response()["lane_geojson"]["features"]
        if feature["properties"]["lane_type"] == "driving"
    ]
    original_widths = [
        feature["properties"]["width"]
        for feature in original["features"]
        if feature["properties"]["lane_type"] == "driving"
    ]

    assert preview_widths
    assert preview_response["preview_mode"] == "memory"
    assert id(state._lane_preview_map) == cached_preview_map_id
    preview_property_names = {
        "feature_type",
        "lane_key",
        "lane_id",
        "lane_type",
        "junction",
        "width",
    }
    assert all(
        set(feature["properties"]) <= preview_property_names
        for feature in preview["features"]
    )
    assert preview_widths == pytest.approx(
        [width * width_scale for width in original_widths],
        rel=1e-4,
    )
    assert loaded_widths == original_widths

    restored = state.preview_lane_geojson(original)["lane_geojson"]
    restored_widths = [
        feature["properties"]["width"]
        for feature in restored["features"]
        if feature["properties"]["lane_type"] == "driving"
    ]
    assert restored_widths == pytest.approx(original_widths, rel=1e-4)


def test_lane_geometry_smoothly_repairs_linked_junction_gap() -> None:
    """A linked junction endpoint must close its gap without moving its far end."""
    from pyxodr3d.web._editor import (
        _lane_endpoint,
        _lon_lat_distance_m,
        _repair_lane_connection_geometry,
    )

    def lane_feature(
        lane_key: str,
        centers: list[tuple[float, float]],
        *,
        junction: str,
        successor_keys: list[str],
    ) -> dict[str, object]:
        half_width = 0.00001
        outer = [[lon, lat + half_width] for lon, lat in centers]
        inner = [[lon, lat - half_width] for lon, lat in centers]
        ring = [*outer, *reversed(inner), outer[0]]
        return {
            "type": "Feature",
            "properties": {
                "feature_type": "lane",
                "lane_key": lane_key,
                "lane_id": -1,
                "lane_type": "driving",
                "junction": junction,
                "successor_keys": successor_keys,
            },
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }

    approach = lane_feature(
        "approach",
        [(0.0, 0.0), (0.00010, 0.0)],
        junction="-1",
        successor_keys=["connector"],
    )
    connector = lane_feature(
        "connector",
        [
            (0.00016, 0.0),
            (0.00020, 0.00005),
            (0.00022, 0.00014),
            (0.00020, 0.00024),
        ],
        junction="10",
        successor_keys=[],
    )
    connector_far_before = _lane_endpoint(connector, "end")["center"]
    lane_geojson = {
        "type": "FeatureCollection",
        "features": [approach, connector],
    }

    repaired_count = _repair_lane_connection_geometry(lane_geojson)
    approach_exit = _lane_endpoint(approach, "end")["center"]
    connector_entry = _lane_endpoint(connector, "start")["center"]
    connector_far_after = _lane_endpoint(connector, "end")["center"]

    assert repaired_count == 1
    assert _lon_lat_distance_m(approach_exit, connector_entry) < 1e-6
    assert _lon_lat_distance_m(
        connector_far_before,
        connector_far_after,
    ) < 1e-6


def test_lane_boundary_parser_preserves_natural_taper_closure() -> None:
    """A zero-width taper point is data, not an extra polygon closure point."""
    from pyxodr3d.web._editor import _lane_polygon_boundaries

    tapered_lane = {
        "type": "Feature",
        "properties": {"feature_type": "lane"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [0.0, 0.0],
                    [1.0, 1.0],
                    [2.0, 1.0],
                    [2.0, -1.0],
                    [1.0, -1.0],
                    [0.0, 0.0],
                ]
            ],
        },
    }

    boundaries = _lane_polygon_boundaries(tapered_lane)

    assert boundaries is not None
    outer, inner = boundaries
    assert len(outer) == 3
    assert len(inner) == 3
    assert outer[0] == inner[0] == [0.0, 0.0]


def test_lane_width_scaling_preserves_piecewise_polynomials() -> None:
    """Width scaling must retain taper coefficients and all width records."""
    from pyxodr3d.web._editor import _scale_lane_width

    lane_node = ET.fromstring(
        """
        <lane id="-1" type="driving">
          <width sOffset="0" a="3.5" b="-0.1" c="0.02" d="0"/>
          <width sOffset="12" a="2.0" b="0.25" c="0" d="-0.01"/>
        </lane>
        """
    )

    assert _scale_lane_width(lane_node, 0.5) is True
    widths = lane_node.findall("width")

    assert len(widths) == 2
    assert [float(node.get("sOffset", "0")) for node in widths] == [0.0, 12.0]
    assert [
        float(widths[0].get(name, "0")) for name in ("a", "b", "c", "d")
    ] == pytest.approx([1.75, -0.05, 0.01, 0.0])
    assert [
        float(widths[1].get(name, "0")) for name in ("a", "b", "c", "d")
    ] == pytest.approx(
        [1.0, 0.125, 0.0, -0.005]
    )


def test_unedited_lane_width_payload_preserves_source_polynomials() -> None:
    """Exported display widths must not flatten untouched source profiles."""
    from pyxodr3d.web._editor import _apply_lane_geojson_edits

    root = ET.fromstring(
        """
        <OpenDRIVE>
          <road id="1" length="20" junction="-1">
            <lanes>
              <laneSection s="0">
                <right>
                  <lane id="-1" type="shoulder">
                    <width sOffset="0" a="1" b="0.1" c="0" d="0"/>
                    <width sOffset="10" a="2" b="-0.1" c="0" d="0"/>
                  </lane>
                </right>
              </laneSection>
            </lanes>
          </road>
        </OpenDRIVE>
        """
    )
    stub_map = type("StubMap", (), {"root": root})()
    lane_geojson = {
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "feature_type": "lane",
                    "road_id": "1",
                    "lanesection_s0": 0.0,
                    "lane_id": -1,
                    "lane_type": "shoulder",
                    "level": False,
                    "width": 9.0,
                },
                "geometry": {"type": "Polygon", "coordinates": []},
            }
        ]
    }

    _apply_lane_geojson_edits(stub_map, lane_geojson)
    widths = root.findall("./road/lanes/laneSection/right/lane/width")

    assert len(widths) == 2
    assert [
        tuple(float(node.get(name, "0")) for name in ("a", "b", "c", "d"))
        for node in widths
    ] == [(1.0, 0.1, 0.0, 0.0), (2.0, -0.1, 0.0, 0.0)]


def test_web_lane_keys_disambiguate_rounded_section_collisions() -> None:
    """Sub-micrometer lane sections must keep distinct web topology keys."""
    from pyxodr3d.web._editor import _web_lane_key_names

    first = odr.xodr.LaneKey("687", 9.227933795217893, 1)
    second = odr.xodr.LaneKey("687", 9.227933929029831, 1)
    ordinary = odr.xodr.LaneKey("12", 0.0, -1)

    names = _web_lane_key_names([first, second, ordinary])

    assert first.to_string() == second.to_string()
    assert names[first] != names[second]
    assert names[ordinary] == ordinary.to_string()


def test_lane_geojson_exports_traffic_side(
    synthetic_map: odr.OpenDriveMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lane payloads must preserve RHT/LHT for direction fallback."""
    from pyxodr3d.web._editor import _map_to_lane_geojson

    monkeypatch.setattr(synthetic_map, "convertXY2LonLat", lambda x, y: (x, y))
    features = _map_to_lane_geojson(synthetic_map)["features"]
    traffic_side_by_road = {
        str(feature["properties"]["road_id"]): feature["properties"][
            "left_hand_traffic"
        ]
        for feature in features
    }

    assert traffic_side_by_road["1"] is False
    assert traffic_side_by_road["2"] is True


def test_xodr_web_viewer_background_thread_serves_network() -> None:
    """Background mode must still serve the startup network API."""
    from pyxodr3d.web import xodr_web_viewer
    from pyxodr3d.web._editor import _ACTIVE_SERVERS

    url = xodr_web_viewer(port=0, open_browser=False, block=False)
    server = _ACTIVE_SERVERS[-1]
    try:
        with urllib.request.urlopen(f"{url}api/network", timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        if server in _ACTIVE_SERVERS:
            _ACTIVE_SERVERS.remove(server)

    assert payload["filename"] == "data.xodr"
    assert len(payload["geojson"]["features"]) > 0
    assert len(payload["lane_geojson"]["features"]) > 0


def test_web_open_button_accepts_only_xodr_and_sumo_net_xml() -> None:
    """The browser picker and validation must expose only supported formats."""
    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "pyxodr3d" / "web"
    index_html = (web_root / "index.html").read_text(encoding="utf-8")
    index_javascript = (web_root / "index.js").read_text(encoding="utf-8")

    assert 'accept=".xodr,.net.xml"' in index_html
    assert "Open an OpenDRIVE .xodr or SUMO .net.xml network" in index_html
    assert "function uploadedNetworkFormat(filename)" in index_javascript
    assert 'lowercaseName.endsWith(".net.xml")' in index_javascript
    assert 'lowercaseName.endsWith(".xodr")' in index_javascript
    assert "Choose an OpenDRIVE .xodr or SUMO .net.xml file." in index_javascript
    assert "Converting SUMO network" in index_javascript
    assert "Restored the exact embedded OpenDRIVE data" in index_javascript
    assert "Road/edge, junction, and lane IDs were preserved." in index_javascript
    assert "payloadFileSize(payload)" in index_javascript
    open_file_function = index_javascript.split(
        "async function openXodrFile(file)",
        maxsplit=1,
    )[1].split("function saveFormatForFilename(filename)", maxsplit=1)[0]
    assert open_file_function.count("showLoadingOverlay(") == 1
    assert open_file_function.count("hideLoadingOverlay();") == 1
    assert "setLoadingOverlayMessage(loadingMessage);" in open_file_function


def test_web_upload_loads_xodr_and_converts_sumo_net_xml(
    synthetic_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploads load OpenDRIVE directly and dispatch SUMO files to conversion."""
    from pyxodr3d.web import _editor

    state = _editor._ViewerState()
    direct_response = state.load_text(
        synthetic_file.read_text(encoding="utf-8"),
        "direct.xodr",
    )

    assert direct_response["filename"] == "direct.xodr"
    assert direct_response["source_filename"] == "direct.xodr"
    assert direct_response["source_format"] == "opendrive"
    assert direct_response["geojson"]["features"]

    conversion_call: dict[str, Path] = {}

    def fake_xodr_from_net_xml(
        net_file: str | Path,
        xodr_file: str | Path,
    ) -> odr.OpenDriveMap:
        net_path = Path(net_file)
        xodr_path = Path(xodr_file)
        conversion_call["net_file"] = net_path
        conversion_call["xodr_file"] = xodr_path
        assert net_path.read_text(encoding="utf-8") == "<net/>"
        xodr_path.write_text(SYNTHETIC_XODR, encoding="utf-8")
        return odr.readXodr(xodr_path)

    monkeypatch.setattr(_editor, "xodr_from_net_xml", fake_xodr_from_net_xml)
    converted_response = state.load_text("<net/>", "city.NET.XML")

    assert conversion_call["net_file"].name == "city.NET.XML"
    assert conversion_call["xodr_file"].name == "city.xodr"
    assert converted_response["filename"] == "city.xodr"
    assert converted_response["source_filename"] == "city.NET.XML"
    assert converted_response["source_format"] == "sumo_net_xml"
    assert converted_response["lane_geojson"]["features"]

    with pytest.raises(ValueError, match=r"\.xodr and SUMO \.net\.xml"):
        state.load_text("<network/>", "unsupported.xml")


def test_web_save_uses_native_file_type_picker() -> None:
    """Save format selection belongs in the native Save As dialog."""
    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "pyxodr3d" / "web"
    index_html = (web_root / "index.html").read_text(encoding="utf-8")
    index_javascript = (web_root / "index.js").read_text(encoding="utf-8")

    assert 'id="save_format_select"' not in index_html
    assert 'id="save_network_controls"' not in index_html
    assert "Save as OpenDRIVE .xodr or SUMO .net.xml" in index_html
    assert "window.showSaveFilePicker" in index_javascript
    assert 'suggestedName: "edited_network.xodr"' in index_javascript
    assert 'description: "OpenDRIVE File (*.xodr)"' in index_javascript
    assert 'accept: { "application/xml": [".xodr"] }' in index_javascript
    assert 'description: "SUMO Network File (*.net.xml)"' in index_javascript
    assert 'accept: { "application/xml": [".net.xml"] }' in index_javascript
    assert "excludeAcceptAllOption: true" in index_javascript
    assert "fileHandle.createWritable()" in index_javascript
    assert 'savePayload.save_format = saveFormat;' in index_javascript
    assert "payload.download_text || payload.xodr" in index_javascript
    save_function = index_javascript.split(
        "async function saveEditedXodr()",
        maxsplit=1,
    )[1].split("window.OpenDriveViewer =", maxsplit=1)[0]
    assert save_function.index("await writeTextFile(") < save_function.index(
        "await loadPayload(payload)"
    )


def test_web_save_can_convert_download_to_sumo_net_xml(
    synthetic_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SUMO save converts the refreshed OpenDRIVE file and returns its XML."""
    from pyxodr3d.web import _editor

    state = _editor._ViewerState(synthetic_file)
    payload = state.as_response()
    conversion_call: dict[str, Path] = {}

    def fake_xodr_to_net_xml(
        xodr_file: str | Path,
        net_file: str | Path | None = None,
    ) -> object:
        xodr_path = Path(xodr_file)
        net_path = Path(net_file or "")
        conversion_call["xodr_file"] = xodr_path
        conversion_call["net_file"] = net_path
        assert ET.parse(xodr_path).getroot().tag == "OpenDRIVE"
        net_path.write_text('<net version="1.20"/>', encoding="utf-8")
        return object()

    monkeypatch.setattr(_editor, "xodr_to_net_xml", fake_xodr_to_net_xml)
    saved = state.save_geojson(
        payload["geojson"],
        payload["lane_geojson"],
        payload["signal_geojson"],
        output_format="sumo_net_xml",
    )

    assert conversion_call["xodr_file"].name == "edited_network.xodr"
    assert conversion_call["net_file"].name == "edited_network.net.xml"
    assert saved["saved_filename"] == "edited_network.net.xml"
    assert saved["saved_format"] == "sumo_net_xml"
    assert saved["download_text"] == '<net version="1.20"/>'
    assert saved["filename"] == "edited_network.xodr"
    assert state.current_file is not None
    assert state.current_file.name == "edited_network.xodr"

    with pytest.raises(ValueError, match="Save format must be"):
        state.save_geojson(payload["geojson"], output_format="xml")


def test_web_saved_xodr_reloads_with_content() -> None:
    """A web-exported OpenDRIVE file must be non-empty and loadable."""
    from pyxodr3d.web import _editor

    repo_root = Path(__file__).resolve().parents[1]
    state = _editor._ViewerState(repo_root / "datasets/data.xodr")
    payload = state.as_response()
    saved = state.save_geojson(
        payload["geojson"],
        payload["lane_geojson"],
        payload["signal_geojson"],
        output_format="xodr",
    )

    assert saved["download_text"].lstrip().startswith("<?xml")
    reloaded = _editor._ViewerState().load_text(
        saved["download_text"],
        saved["saved_filename"],
    )

    assert reloaded["filename"] == "edited_network.xodr"
    assert reloaded["geojson"]["features"]
    assert reloaded["lane_geojson"]["features"]


def test_web_saved_sumo_net_xml_reloads_with_projection(tmp_path: Path) -> None:
    """A web-exported SUMO network must convert back to browser-ready data."""
    from pyxodr3d.web import _editor

    repo_root = Path(__file__).resolve().parents[1]
    source_xodr = repo_root / "datasets/chatt.xodr"
    source_payload = _editor._ViewerState(source_xodr).as_response()
    net_file = tmp_path / "edited_network.net.xml"
    odr.xodr_to_net_xml(source_xodr, net_file=net_file)

    net_root = ET.parse(net_file).getroot()
    location = net_root.find("location")
    assert location is not None
    assert location.get("netOffset")
    valid_projection = location.get("projParameter")
    assert valid_projection not in {None, "", "!"}

    payload = _editor._ViewerState().load_text(
        net_file.read_text(encoding="utf-8"),
        net_file.name,
    )

    assert payload["filename"] == "edited_network.xodr"
    assert payload["source_projection_valid"] is True
    assert payload["sumo_conversion_mode"] == "embedded_opendrive"
    assert payload["file_size_bytes"] == source_xodr.stat().st_size
    assert payload["proj4"]
    assert len(payload["geojson"]["features"]) == len(
        source_payload["geojson"]["features"]
    )
    assert len(payload["lane_geojson"]["features"]) == len(
        source_payload["lane_geojson"]["features"]
    )
    assert payload["geojson"]["bbox"] == pytest.approx(
        source_payload["geojson"]["bbox"],
        abs=1e-5,
    )

    net_text = net_file.read_text(encoding="utf-8")
    net_file.write_text(
        net_text.replace(
            f'projParameter="{valid_projection}"',
            'projParameter="!"',
            1,
        ),
        encoding="utf-8",
    )
    legacy_payload = _editor._ViewerState().load_text(
        net_file.read_text(encoding="utf-8"),
        net_file.name,
    )

    assert not legacy_payload["proj4"]
    assert legacy_payload["source_projection_valid"] is False
    assert legacy_payload["sumo_conversion_mode"] == "netconvert"
    assert legacy_payload["identifiers_preserved"] is False
    assert legacy_payload["geojson"]["features"]
    assert legacy_payload["lane_geojson"]["features"]
    legacy_bbox = legacy_payload["geojson"]["bbox"]
    assert legacy_bbox is not None
    assert all(-1.0 < coordinate < 1.0 for coordinate in legacy_bbox)


def test_web_saved_sumo_preserves_data_with_incomplete_projection() -> None:
    """The real save/reload flow preserves topology and rejects an invalid CRS."""
    from pyxodr3d.web import _editor

    repo_root = Path(__file__).resolve().parents[1]
    source_xodr = repo_root / "datasets/data.xodr"
    source_state = _editor._ViewerState(source_xodr)
    source_payload = source_state.as_response()
    saved = source_state.save_geojson(
        source_payload["geojson"],
        source_payload["lane_geojson"],
        source_payload["signal_geojson"],
        output_format="sumo_net_xml",
    )

    location = ET.fromstring(saved["download_text"]).find("location")
    assert location is not None
    assert location.get("projParameter") == "!"

    reloaded_state = _editor._ViewerState()
    payload = reloaded_state.load_text(
        saved["download_text"],
        saved["saved_filename"],
    )

    assert len(source_payload["geojson"]["features"]) == 234
    assert len(source_payload["lane_geojson"]["features"]) == 1028
    assert len(source_payload["signal_geojson"]["features"]) == 0
    assert payload["source_projection_valid"] is False
    assert payload["sumo_conversion_mode"] == "embedded_opendrive"
    assert payload["identifiers_preserved"] is True
    assert payload["proj4"] == saved["proj4"]
    assert len(payload["geojson"]["features"]) == len(
        saved["geojson"]["features"]
    )
    assert len(payload["lane_geojson"]["features"]) == len(
        saved["lane_geojson"]["features"]
    )
    assert reloaded_state.current_file is not None
    source_identifiers = _opendrive_identifier_inventory(
        ET.parse(source_xodr).getroot()
    )
    assert _opendrive_identifier_inventory(
        ET.fromstring(saved["xodr"])
    ) == source_identifiers
    assert _opendrive_identifier_inventory(
        ET.parse(reloaded_state.current_file).getroot()
    ) == source_identifiers


def test_lane_queries_roadmarks_and_surface_points(
    synthetic_map: odr.OpenDriveMap,
) -> None:
    road = synthetic_map.getRoad("1")
    section = road.get_lanesection(1.0)
    lanes = section.get_lanes()
    assert [lane.id for lane in lanes] == [-1, 0, 1]

    left_lane = section.get_lane(1)
    right_lane = section.get_lane(-1)
    assert left_lane.outer_border.get(0.0) == pytest.approx(3.7)
    assert right_lane.outer_border.get(0.0) == pytest.approx(-3.05)
    assert section.get_lane_id(1.0, 3.0) == 1
    assert section.get_lane(1.0, -1.0).id == -1

    left_marks = left_lane.get_roadmarks(0.0, road.length)
    right_marks = right_lane.get_roadmarks(0.0, 7.0)
    assert left_marks[0].type == "solid"
    assert {mark.type for mark in right_marks} == {"brokendash"}

    assert_vec_finite(road.ref_line.get_xyz(5.0))
    assert_vec_finite(road.ref_line.get_grad(5.0))
    assert_vec_finite(road.get_xyz(5.0, 1.0, 0.5))
    assert_vec_finite(road.get_surface_pt(5.0, 1.0))
    assert road.crossfall.get_crossfall(25.0, on_left_side=False) == 0.0

    border = road.get_lane_border_line(left_lane, eps=2.0)
    assert len(border) >= 2
    assert all(len(point) == 3 for point in border)


def test_objects_signals_mesh_and_routing(synthetic_map: odr.OpenDriveMap) -> None:
    road = synthetic_map.getRoad("1")
    road_object = road.id_to_object["obj1"]
    signal = road.id_to_signal["sig1"]

    assert road_object.is_dynamic is True
    assert road_object.repeats[0].distance == 2.0
    assert road_object.outlines[0].outline[0].type == "local_rel_z"
    assert road_object.lane_validities[0].from_lane == -1
    assert signal.country == "US"
    assert signal.lane_validities[0].to_lane == -1

    lane = road.get_lanesection(1.0).get_lane(1)
    lane_mesh = road.get_lane_mesh(lane, eps=2.0)
    assert len(lane_mesh.vertices) >= 4
    assert len(lane_mesh.indices) >= 6
    inner_lane = road.get_lanesection(1.0).get_lane(0)
    sample_positions = set(
        road.ref_line.approximate_linear(
            2.0,
            lane.lanesection_s0,
            road.get_lanesection_end(lane.lanesection_s0),
        )
    )
    sample_positions.update(
        lane.outer_border.approximate_linear(
            2.0,
            lane.lanesection_s0,
            road.get_lanesection_end(lane.lanesection_s0),
        )
    )
    sample_positions.update(
        inner_lane.outer_border.approximate_linear(
            2.0,
            lane.lanesection_s0,
            road.get_lanesection_end(lane.lanesection_s0),
        )
    )
    expected_vertices = []
    for s in sorted(sample_positions):
        outer_t = lane.outer_border.get(s)
        inner_t = math.nextafter(inner_lane.outer_border.get(s), outer_t)
        expected_vertices.extend(
            [road.get_surface_pt(s, outer_t), road.get_surface_pt(s, inner_t)]
        )
    assert lane_mesh.vertices == pytest.approx(expected_vertices)

    roadmark_mesh = road.get_roadmark_mesh(
        lane,
        lane.get_roadmarks(0.0, road.length)[0],
        eps=2.0,
    )
    assert len(roadmark_mesh.vertices) >= 4

    network_mesh = synthetic_map.getRoadNetworkMesh(eps=4.0)
    assert len(network_mesh.lanes_mesh.vertices) > 0
    assert len(network_mesh.roadmarks_mesh.vertices) > 0
    assert len(network_mesh.get_mesh().vertices) >= len(
        network_mesh.lanes_mesh.vertices
    )

    graph = synthetic_map.getRoutingGraph()
    start = odr.xodr.LaneKey("1", 0.0, -1)
    end = odr.xodr.LaneKey("2", 0.0, -1)
    assert end in graph.get_lane_successors(start)
    assert graph.get_lane_predecessors(end)
    assert graph.shortest_path(start, end) == [start, end]


def test_centering_and_outline_z_mode(synthetic_file: Path) -> None:
    centered = odr.OpenDriveMap(
        str(synthetic_file),
        center_map=True,
        abs_z_for_for_local_road_obj_outline=True,
    )
    assert centered.x_offs > 0
    assert centered.y_offs > 0
    road_object = centered.getRoad("1").id_to_object["obj1"]
    assert road_object.outlines[0].outline[0].type == "local_abs_z"


def test_geometry_and_spline_helpers() -> None:
    poly = odr.xodr.Poly3.from_odr(2.0, 1.0, 2.0, 3.0, 4.0)
    assert math.isfinite(poly.get(3.0))
    assert math.isfinite(poly.get_grad(3.0))
    assert not poly.isnan()
    assert poly.negate().get(3.0) == pytest.approx(-poly.get(3.0))
    assert len(poly.approximate_linear(0.5, 0.0, 2.0)) >= 2

    spline = odr.xodr.CubicSpline(
        {0.0: odr.xodr.Poly3.from_odr(0.0, 1.0, 0.0, 0.0, 0.0)}
    )
    other = odr.xodr.CubicSpline(
        {1.0: odr.xodr.Poly3.from_odr(1.0, 2.0, 0.0, 0.0, 0.0)}
    )
    assert spline.size() == 1
    assert not spline.empty()
    assert spline.get(0.5) == pytest.approx(1.0)
    assert spline.add(other).get(1.0) == pytest.approx(3.0)
    assert spline.negate().get(0.0) == pytest.approx(-1.0)
    assert len(spline.approximate_linear(0.5, 0.0, 2.0)) >= 2

    line = odr.xodr.Line(0.0, 0.0, 0.0, 0.0, 10.0)
    arc = odr.xodr.Arc(0.0, 0.0, 0.0, 0.0, 10.0, 0.1)
    spiral = odr.xodr.Spiral(0.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.1)
    param = odr.xodr.ParamPoly3(
        0.0,
        0.0,
        0.0,
        0.0,
        10.0,
        0.0,
        10.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    for geom in (line, arc, spiral, param):
        assert_vec_finite(geom.get_xy(5.0))
        assert_vec_finite(geom.get_grad(5.0))
        assert len(geom.approximate_linear(1.0)) >= 2

    ref_line = odr.xodr.RefLine("r", 10.0)
    ref_line.s0_to_geometry[0.0] = line
    ref_line.elevation_profile.s0_to_poly[0.0] = odr.xodr.Poly3.from_odr(
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    assert ref_line.get_geometry_s0(5.0) == 0.0
    assert ref_line.get_geometry(5.0) is line
    assert len(ref_line.get_line(0.0, 10.0, 1.0)) >= 2
    assert 0.0 <= ref_line.match(5.0, 0.0) <= 10.0


def test_mesh_obj_and_routing_unreachable() -> None:
    mesh = odr.xodr.Mesh3D(vertices=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
    mesh.indices.extend([0, 1, 2])
    mesh.normals.append((0.0, 0.0, 1.0))
    obj_text = mesh.get_obj()
    assert "v 0.0 0.0 0.0" in obj_text
    assert "f 1 2 3" in obj_text

    other = odr.xodr.Mesh3D(vertices=[(0.0, 0.0, 1.0)])
    mesh.add_mesh(other)
    assert len(mesh.vertices) == 4

    graph = odr.xodr.RoutingGraph()
    a = odr.xodr.LaneKey("a", 0.0, -1)
    b = odr.xodr.LaneKey("b", 0.0, -1)
    assert graph.shortest_path(a, b) == []
    assert a.to_string() == "a/0.000000/-1"


def test_real_chatt_file_smoke() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    xodr = repo_root / "datasets/chatt.xodr"
    odr_map = odr.readXodr(xodr)

    assert len(odr_map.getRoads()) == 189
    assert len(odr_map.getJunctions()) == 24
    assert odr_map.getBoundary() == pytest.approx((0.0, 0.0, 1377.14, 919.81))
    first = odr_map.getRoads()[0]
    assert len(first.get_lanesections()) == 1
    assert_vec_finite(first.ref_line.get_xyz(0.0))

    graph = odr_map.getRoutingGraph()
    assert len(graph.edges) == 474


def test_tutorial_runs_outside_repository_root(tmp_path: Path) -> None:
    """The tutorial must resolve its bundled dataset independently of cwd."""
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "tutorial.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "roads=189" in completed.stdout


def test_chatt_xodr_converts_to_sumo_net_and_back(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    xodr = repo_root / "datasets/chatt.xodr"
    net_file = tmp_path / "chatt.net.xml"
    roundtrip_xodr = tmp_path / "chatt_roundtrip.xodr"

    sumo_net = odr.xodr_to_net_xml(
        xodr,
        net_file=net_file,
        netconvert_options={"no-turnarounds": True},
    )

    assert type(sumo_net).__module__.startswith("sumolib.net")
    assert net_file.exists()
    assert len(sumo_net.getNodes()) > 0
    assert len(sumo_net.getEdges()) > 0
    assert sumo_net.getBoundary()[2] > sumo_net.getBoundary()[0]
    edge_280 = sumo_net.getEdge("280")
    assert edge_280.getParam("pyxodr3d.original_link_id") == "280"
    assert edge_280.getLanes()[0].getParam("pyxodr3d.original_lane_id") == "-1"
    assert edge_280.getLanes()[1].getParam("pyxodr3d.original_lane_id") == "-2"
    assert sumo_net.getNode("1").getParam("pyxodr3d.original_node_id") == "1"

    source_root = ET.parse(xodr).getroot()
    source_road_ids = {road.get("id") for road in source_root.findall("road")}
    source_junction_ids = {
        junction.get("id") for junction in source_root.findall("junction")
    }
    source_lane_ids_by_road = {
        road.get("id"): {
            lane.get("id")
            for lane in road.findall("./lanes/laneSection/*/lane")
        }
        for road in source_root.findall("road")
    }
    net_root = ET.parse(net_file).getroot()

    def net_param(element: ET.Element, key: str) -> str | None:
        return next(
            (
                param.get("value")
                for param in element.findall("param")
                if param.get("key") == key
            ),
            None,
        )

    normal_edges = [
        edge
        for edge in net_root.findall("edge")
        if edge.get("function") != "internal"
    ]
    for edge in normal_edges:
        original_road_id = net_param(edge, "pyxodr3d.original_link_id")
        assert original_road_id in source_road_ids
        for lane in edge.findall("lane"):
            assert net_param(lane, "pyxodr3d.original_lane_id") in (
                source_lane_ids_by_road[original_road_id]
            )
    annotated_junction_ids = {
        net_param(junction, "pyxodr3d.original_node_id")
        for junction in net_root.findall("junction")
    }
    assert source_junction_ids <= annotated_junction_ids

    roundtrip_map = odr.xodr_from_net_xml(
        net=sumo_net,
        xodr_file=roundtrip_xodr,
    )

    assert isinstance(roundtrip_map, odr.OpenDriveMap)
    assert roundtrip_xodr.exists()
    assert roundtrip_xodr.read_bytes() == xodr.read_bytes()
    assert roundtrip_map.sumo_conversion_mode == "embedded_opendrive"
    assert roundtrip_map.identifiers_preserved is True
    assert _opendrive_identifier_inventory(
        ET.parse(roundtrip_xodr).getroot()
    ) == _opendrive_identifier_inventory(source_root)
    assert len(roundtrip_map.getRoads()) > 0
    assert len(roundtrip_map.getJunctions()) > 0
    assert roundtrip_map.getRoad("280").id == "280"
    assert roundtrip_map.getRoad("280").get_lanesections()[0].get_lane(-1).id == -1
    assert roundtrip_map.getRoad("280").get_lanesections()[0].get_lane(-2).id == -2
    assert_vec_finite(roundtrip_map.getRoads()[0].ref_line.get_xyz(0.0))


def test_xodr_to_net_xml_annotation_restores_positive_numeric_edge_ids(
    tmp_path: Path,
) -> None:
    import pyxodr3d.__xodr_sumo as xodr_sumo

    net_file = tmp_path / "network.net.xml"
    net_file.write_text(
        """<net>
        <junction id="1"/>
        <edge id="-280" from="1" to="2">
            <lane id="-280_0" index="0"/>
            <lane id="-280_1" index="1"/>
        </edge>
        <edge id="-281" from="2" to="3">
            <lane id="-281_0" index="0"/>
        </edge>
        <connection from="-280" to="-281" fromLane="0" toLane="0"/>
        <connection from=":1_0" to="-280" fromLane="0" toLane="1"/>
        </net>""",
        encoding="utf-8",
    )

    xodr_sumo._annotate_sumo_net_ids(net_file)

    root = ET.parse(net_file).getroot()
    edges = {edge.get("id"): edge for edge in root.findall("edge")}
    assert set(edges) == {"280", "281"}
    param = edges["280"].find("./param")
    assert param is not None
    assert param.get("value") == "280"
    assert [lane.get("id") for lane in edges["280"].findall("lane")] == [
        "280_0",
        "280_1",
    ]
    lane_params = []
    for lane in edges["280"].findall("lane"):
        lane_param = lane.find("./param")
        assert lane_param is not None
        lane_params.append(lane_param.get("value"))
    assert lane_params == ["-1", "-2"]

    connections = root.findall("connection")
    assert connections[0].get("from") == "280"
    assert connections[0].get("to") == "281"
    assert connections[1].get("from") == ":1_0"
    assert connections[1].get("to") == "280"


def test_chatt_sumo_net_xml_converts_to_opendrive_map(tmp_path: Path) -> None:
    from sumolib import net as sumolib_net
    repo_root = Path(__file__).resolve().parents[1]
    net_file = repo_root / "datasets/chatt.net.xml"
    roundtrip_xodr = tmp_path / "chatt_from_sumo.xodr"

    sumo_net = sumolib_net.readNet(str(net_file), withInternal=True)

    assert len(sumo_net.getNodes()) > 0
    assert len(sumo_net.getEdges()) > 0

    odr_map = odr.xodr_from_net_xml(
        net=sumo_net,
        net_file=net_file,
        xodr_file=roundtrip_xodr,
    )

    assert isinstance(odr_map, odr.OpenDriveMap)
    assert roundtrip_xodr.exists()
    assert len(odr_map.getRoads()) > 0
    assert len(odr_map.getJunctions()) > 0
    source_edge_ids = [
        edge.get("id")
        for edge in ET.parse(net_file).getroot().findall("edge")
        if edge.get("id") and edge.get("function") != "internal"
    ]
    roundtrip_road_ids = [
        road.get("id")
        for road in ET.parse(roundtrip_xodr).getroot().findall("road")
        if road.get("junction", "-1") == "-1"
    ]
    assert roundtrip_road_ids[: len(source_edge_ids)] == source_edge_ids
    assert_vec_finite(odr_map.getRoads()[0].ref_line.get_xyz(0.0))


def test_xodr_from_net_xml_restores_road_references_to_planview_roads(
    tmp_path: Path,
) -> None:
    import pyxodr3d.__xodr_sumo as xodr_sumo

    net_file = tmp_path / "network.net.xml"
    net_file.write_text(
        """<net>
        <edge id="edge_a"/>
        <edge id="edge_b"/>
        </net>""",
        encoding="utf-8",
    )
    xodr_file = tmp_path / "network.xodr"
    xodr_file.write_text(
        """<OpenDRIVE>
        <road id="100" length="10" junction="-1">
            <link><successor elementType="road" elementId="101" contactPoint="start"/></link>
            <planView>
                <geometry s="0" x="0" y="0" hdg="0" length="10"><line/></geometry>
            </planView>
        </road>
        <road id="101" length="10" junction="-1">
            <link><predecessor elementType="road" elementId="100" contactPoint="end"/></link>
            <planView>
                <geometry s="0" x="10" y="0" hdg="0" length="10"><line/></geometry>
            </planView>
        </road>
        <junction id="1">
            <connection id="0" incomingRoad="100" connectingRoad="101" contactPoint="start"/>
            <priority high="100" low="101"/>
        </junction>
        </OpenDRIVE>""",
        encoding="utf-8",
    )

    xodr_sumo._restore_opendrive_ids(xodr_file, net_file)

    root = ET.parse(xodr_file).getroot()
    roads = {road.get("id"): road for road in root.findall("road")}
    assert set(roads) == {"edge_a", "edge_b"}
    succ = roads["edge_a"].find("./link/successor")
    assert succ is not None and succ.get("elementId") == "edge_b"
    pred = roads["edge_b"].find("./link/predecessor")
    assert pred is not None and pred.get("elementId") == "edge_a"
    assert roads["edge_a"].find("./planView/geometry") is not None
    assert roads["edge_b"].find("./planView/geometry") is not None

    connection = root.find("./junction/connection")
    assert connection is not None and connection.get("incomingRoad") == "edge_a"
    assert connection is not None and connection.get("connectingRoad") == "edge_b"
    priority = root.find("./junction/priority")
    assert priority is not None and priority.get("high") == "edge_a"
    assert priority is not None and priority.get("low") == "edge_b"


def test_bad_lane_section_without_center_lane_raises(tmp_path: Path) -> None:
    xodr = tmp_path / "bad.xodr"
    xodr.write_text(
        """<OpenDRIVE><road id="1" length="1" junction="-1"><planView>
        <geometry s="0" x="0" y="0" hdg="0" length="1"><line/></geometry>
        </planView><lanes><laneSection s="0"><right><lane id="-1">
        <width sOffset="0" a="1" b="0" c="0" d="0"/></lane></right>
        </laneSection></lanes></road></OpenDRIVE>""",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="lane section does not have lane #0"):
        odr.OpenDriveMap(str(xodr))
