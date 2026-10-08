"""Helpers for converting between OpenDRIVE and SUMO networks.

This module uses SUMO's ``netconvert`` binary for OpenDRIVE/SUMO conversion and
returns Python objects for callers.

Attributes:
    _SOURCE_NET_FILE_ATTR: Attribute name used to remember the generated SUMO
        ``.net.xml`` file on returned ``sumolib.net.Net`` objects.
    _TEMP_DIR_ATTR: Attribute name used to retain temporary directories while
        returned objects may still need their generated files.
"""

# Copyright 2026 Xiangyong Luo
#
# This file is part of pyxodr3d.
#
# Licensed under the Apache License, Version 2.0.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.


from __future__ import annotations

import base64
import binascii
import contextlib
import gzip
import hashlib
import io
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping, Sequence, TYPE_CHECKING
import xml.etree.ElementTree as ET

from pyproj import CRS, Proj
from pyproj.exceptions import CRSError, ProjError

from . import OpenDriveMap, readXodr
from .__xodr_reader import _projection_for_sumo

if TYPE_CHECKING:
    import sumolib.net

_SOURCE_NET_FILE_ATTR = "_pyxodr3d_sumo_net_file"
_TEMP_DIR_ATTR = "_pyxodr3d_temp_dir"
_ORIGINAL_NODE_ID_PARAM = "pyxodr3d.original_node_id"
_ORIGINAL_LINK_ID_PARAM = "pyxodr3d.original_link_id"
_ORIGINAL_LANE_ID_PARAM = "pyxodr3d.original_lane_id"
_SNAPSHOT_COMMENT_START = b"<!--pyxodr3d-opendrive-snapshot-v1 "
_SNAPSHOT_COMMENT_END = b"\n-->"
_MAX_EMBEDDED_XODR_BYTES = 100 * 1024 * 1024


def _xml_sha256(xml_bytes: bytes) -> str:
    """Return a stable XML checksum that ignores formatting and comments."""
    canonical_xml = ET.canonicalize(
        xml_data=xml_bytes,
        strip_text=True,
        with_comments=False,
    )
    return hashlib.sha256(canonical_xml.encode("utf-8")).hexdigest()


def _opendrive_identifier_sha256(root: ET.Element) -> str:
    """Hash road, junction, and qualified lane IDs without ambiguity."""
    digest = hashlib.sha256()

    def update_identifier(*values: str) -> None:
        for value in values:
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, byteorder="big"))
            digest.update(encoded)

    for road in root.findall("road"):
        road_id = road.get("id", "")
        update_identifier("road", road_id)
        for section_index, lane_section in enumerate(
            road.findall("./lanes/laneSection")
        ):
            section_s = lane_section.get("s", "")
            for side in ("left", "center", "right"):
                for lane in lane_section.findall(f"./{side}/lane"):
                    update_identifier(
                        "lane",
                        road_id,
                        str(section_index),
                        section_s,
                        side,
                        lane.get("id", ""),
                    )
    for junction in root.findall("junction"):
        update_identifier("junction", junction.get("id", ""))
    return digest.hexdigest()


def _require_sumolib():
    try:
        import sumolib.net  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on local SUMO install
        raise RuntimeError(
            "sumolib is required for SUMO conversion. Install SUMO and make its "
            "tools directory importable, or install a compatible sumolib package."
        ) from exc
    return sumolib.net


def _netconvert_binary(binary: str | Path | None = None) -> str:
    if binary is not None:
        path = shutil.which(str(binary)) or str(binary)
    else:
        path = shutil.which("netconvert") or ""
    if not path:
        raise RuntimeError(
            "SUMO netconvert was not found on PATH. Pass netconvert_binary=... "
            "or add SUMO's bin directory to PATH."
        )
    return path


def _append_options(command: list[str], options: Mapping[str, Any] | None) -> None:
    if not options:
        return
    for key, value in options.items():
        option = key if key.startswith("-") else f"--{key}"
        if value is None or value is False:
            continue
        if value is True:
            command.append(option)
        elif isinstance(value, (list, tuple)):
            command.append(option)
            command.append(",".join(str(item) for item in value))
        else:
            command.extend([option, str(value)])


def _run_netconvert(command: Sequence[str]) -> None:
    proc = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
        raise RuntimeError(f"netconvert failed with code {proc.returncode}:\n{detail}")


def _make_output_path(path: str | Path | None, suffix: str) -> tuple[Path, str | None]:
    if path is not None:
        return Path(path), None
    temp_dir = tempfile.mkdtemp(prefix="pyxodr3d_sumo_")
    return Path(temp_dir) / suffix, temp_dir


def _embed_opendrive_snapshot(xodr_file: Path, net_file: Path) -> None:
    """Embed an exact, checksummed OpenDRIVE snapshot in a SUMO XML comment.

    SUMO and ``sumolib`` ignore XML comments, so the network remains a normal
    ``.net.xml`` file. The snapshot lets pyxodr3d reverse its own export
    without asking ``netconvert`` to reconstruct and simplify junction lanes.
    """
    xodr_bytes = xodr_file.read_bytes()
    xodr_root = ET.fromstring(xodr_bytes)
    if str(xodr_root.tag).rsplit("}", maxsplit=1)[-1] != "OpenDRIVE":
        raise ValueError(f"Expected an OpenDRIVE document: {xodr_file}")

    net_bytes = net_file.read_bytes()
    closing_tag_index = net_bytes.rfind(b"</net>")
    if closing_tag_index < 0:
        raise ValueError(f"Expected a SUMO <net> document: {net_file}")

    compressed = gzip.compress(xodr_bytes, compresslevel=9, mtime=0)
    encoded = base64.b64encode(compressed)
    encoded_lines = b"\n".join(
        encoded[index : index + 120]
        for index in range(0, len(encoded), 120)
    )
    metadata = (
        f"sumo-sha256={_xml_sha256(net_bytes)} "
        f"xodr-sha256={hashlib.sha256(xodr_bytes).hexdigest()} "
        f"id-sha256={_opendrive_identifier_sha256(xodr_root)} "
        f"size={len(xodr_bytes)} encoding=gzip+base64"
    ).encode("ascii")
    comment = (
        _SNAPSHOT_COMMENT_START
        + metadata
        + b"\n"
        + encoded_lines
        + _SNAPSHOT_COMMENT_END
    )
    net_file.write_bytes(
        net_bytes[:closing_tag_index] + comment + net_bytes[closing_tag_index:]
    )


def _embedded_opendrive_snapshot(net_file: Path) -> bytes | None:
    """Return a valid embedded OpenDRIVE snapshot for an unchanged SUMO net."""
    try:
        net_bytes = net_file.read_bytes()
    except OSError:
        return None

    comment_start = net_bytes.find(_SNAPSHOT_COMMENT_START)
    if comment_start < 0:
        return None
    comment_end = net_bytes.find(_SNAPSHOT_COMMENT_END, comment_start)
    if comment_end < 0:
        return None

    body_start = comment_start + len(_SNAPSHOT_COMMENT_START)
    comment_body = net_bytes[body_start:comment_end]
    metadata_line, separator, encoded = comment_body.partition(b"\n")
    if not separator:
        return None
    try:
        metadata = dict(
            field.split("=", maxsplit=1)
            for field in metadata_line.decode("ascii").split()
        )
        expected_size = int(metadata["size"])
    except (KeyError, UnicodeDecodeError, ValueError):
        return None
    if (
        metadata.get("encoding") != "gzip+base64"
        or expected_size <= 0
        or expected_size > _MAX_EMBEDDED_XODR_BYTES
    ):
        return None

    base_net_bytes = (
        net_bytes[:comment_start]
        + net_bytes[comment_end + len(_SNAPSHOT_COMMENT_END) :]
    )
    try:
        sumo_checksum = _xml_sha256(base_net_bytes)
    except (ET.ParseError, TypeError, ValueError):
        return None
    if sumo_checksum != metadata.get("sumo-sha256"):
        return None

    try:
        compressed = base64.b64decode(b"".join(encoded.split()), validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as archive:
            xodr_bytes = archive.read(expected_size + 1)
        if len(xodr_bytes) != expected_size:
            return None
        if hashlib.sha256(xodr_bytes).hexdigest() != metadata.get("xodr-sha256"):
            return None
        xodr_root = ET.fromstring(xodr_bytes)
    except (binascii.Error, EOFError, ET.ParseError, OSError, ValueError):
        return None
    if str(xodr_root.tag).rsplit("}", maxsplit=1)[-1] != "OpenDRIVE":
        return None
    expected_identifier_checksum = metadata.get("id-sha256")
    if (
        expected_identifier_checksum is not None
        and _opendrive_identifier_sha256(xodr_root)
        != expected_identifier_checksum
    ):
        return None
    return xodr_bytes


def xodr_to_net_xml(
    xodr_file: str | Path,
    net_file: str | Path | None = None,
    *,
    netconvert_binary: str | Path | None = None,
    netconvert_options: Mapping[str, Any] | None = None,
    read_options: Mapping[str, Any] | None = None,
    import_all_lanes: bool = True,
    with_internal: bool = True,
) -> sumolib.net.Net:
    """Convert an OpenDRIVE ``.xodr`` file to a ``sumolib.net.Net`` object.

    Args:
        xodr_file: Source OpenDRIVE file.
        net_file: output SUMO ``.net.xml`` path.
        netconvert_binary: Optional path or executable name for SUMO
            ``netconvert``. When omitted, ``netconvert`` is resolved from
            ``PATH``.
        netconvert_options: Extra command-line options for ``netconvert`` as
            ``{"option": value}``.
        read_options: Extra keyword arguments passed to
            ``sumolib.net.readNet``.
        import_all_lanes: Whether to pass ``--opendrive.import-all-lanes``.
        with_internal: Value passed as ``withInternal`` to
            ``sumolib.net.readNet`` unless overridden by ``read_options``.

    Returns:
        sumolib.net.Net: The converted network object.
            The generated SUMO net XML file is retained and its path is attached
            to the returned object as an attribute. The file also contains a
            checksummed, compressed OpenDRIVE snapshot in an XML comment for an
            exact pyxodr3d round trip.

    Raises:
        RuntimeError: If ``sumolib`` or ``netconvert`` is unavailable, or if
            ``netconvert`` exits with an error.
    """

    sumo_net = _require_sumolib()
    output_file, temp_dir = _make_output_path(net_file, "network.net.xml")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    command = [
        _netconvert_binary(netconvert_binary),
        "--opendrive-files",
        str(xodr_file),
        "--output-file",
        str(output_file),
    ]
    if import_all_lanes:
        command.append("--opendrive.import-all-lanes")
    _append_options(command, netconvert_options)
    _run_netconvert(command)
    _preserve_xodr_projection(Path(xodr_file), output_file)
    _annotate_sumo_net_ids(output_file)
    _embed_opendrive_snapshot(Path(xodr_file), output_file)

    read_kwargs = {"withInternal": with_internal}
    if read_options:
        read_kwargs |= read_options
    net = sumo_net.readNet(str(output_file), **read_kwargs)
    setattr(net, _SOURCE_NET_FILE_ATTR, str(output_file))
    if temp_dir is not None:
        setattr(net, _TEMP_DIR_ATTR, temp_dir)
    return net


def _preserve_xodr_projection(xodr_file: Path, net_file: Path) -> None:
    """Carry usable OpenDRIVE projection metadata into a generated SUMO net."""
    xodr_root = ET.parse(xodr_file).getroot()
    projection = (xodr_root.findtext("./header/geoReference") or "").strip()
    if not projection or projection == "!":
        return
    try:
        CRS.from_user_input(projection)
    except CRSError:
        return

    net_tree = ET.parse(net_file)
    location = net_tree.getroot().find("location")
    if location is None:
        return
    sumo_projection = _projection_for_sumo(projection)
    try:
        CRS.from_user_input(sumo_projection)
    except CRSError:
        return
    location.set("projParameter", sumo_projection)
    _write_xml(net_tree, net_file)


def _sumo_net_has_valid_projection(net_file: Path) -> bool:
    """Return whether a SUMO network has usable projection and offset metadata."""
    try:
        location = ET.parse(net_file).getroot().find("location")
        if location is None:
            return False
        projection = (location.get("projParameter") or "").strip()
        if not projection or projection in {"!", "-"}:
            return False
        offset = [
            float(value)
            for value in (location.get("netOffset") or "").split(",")
        ]
        boundary = [
            float(value)
            for value in (location.get("convBoundary") or "").split(",")
        ]
        if len(offset) != 2 or len(boundary) != 4:
            return False

        coordinate_projection = Proj(CRS.from_user_input(projection))
        projected_corners = (
            (boundary[0] - offset[0], boundary[1] - offset[1]),
            (boundary[2] - offset[0], boundary[3] - offset[1]),
        )
        lon_lat_corners = [
            coordinate_projection(x, y, inverse=True)
            for x, y in projected_corners
        ]
    except (
        CRSError,
        ET.ParseError,
        OSError,
        OverflowError,
        ProjError,
        TypeError,
        ValueError,
    ):
        return False
    return all(
        math.isfinite(lon)
        and math.isfinite(lat)
        and -180.0 <= lon <= 180.0
        and -85.0 <= lat <= 85.0
        for lon, lat in lon_lat_corners
    )


def xodr_from_net_xml(
    net_file: str | Path | None = None,
    xodr_file: str | Path | None = None,
    *,
    net: sumolib.net.Net | None = None,
    netconvert_binary: str | Path | None = None,
    netconvert_options: Mapping[str, Any] | None = None,
    opendrive_map_kwargs: Mapping[str, Any] | None = None,
) -> OpenDriveMap:
    """Convert a SUMO file or network object to an OpenDRIVE map.

    Files created by :func:`xodr_to_net_xml` restore their embedded OpenDRIVE
    snapshot when its SUMO checksum still matches. This preserves the exact
    source roads, lane sections, and junction connectors. Generic or modified
    SUMO networks fall back to ``netconvert`` reconstruction.

    ``sumolib.net.Net`` does not provide a native writer. If ``net_file`` is not
    passed, this function first reuses the source file attached by
    :func:`xodr_to_net_xml`. If no source path is available, it writes a minimal
    SUMO net XML representation from the in-memory object.

    Args:
        net_file: Optional SUMO ``.net.xml`` path to use as the source for
            ``netconvert``.
        xodr_file: Optional output OpenDRIVE ``.xodr`` path. When omitted, a
            temporary file is created and retained through an attribute on the
            returned map.
        net: Optional ``sumolib.net.Net`` object to convert. if net_file is not provided,
            this is required to resolve the source net.
        netconvert_binary: Optional path or executable name for SUMO
            ``netconvert``. When omitted, ``netconvert`` is resolved from
            ``PATH``.
        netconvert_options: Extra command-line options for ``netconvert`` as
            ``{"option": value}``.
        opendrive_map_kwargs: Extra keyword arguments passed to
            :class:`pyxodr3d.OpenDriveMap`.

    Returns:
        A :class:`pyxodr3d.OpenDriveMap` loaded from the generated
        OpenDRIVE file.

    Raises:
        RuntimeError: If ``netconvert`` is unavailable or exits with an error.
    """

    source_net_file, temp_dir = _resolve_sumo_net_file(net, net_file)
    output_file, output_temp_dir = _make_output_path(xodr_file, "network.xodr")

    embedded_xodr = _embedded_opendrive_snapshot(source_net_file)
    if embedded_xodr is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(embedded_xodr)
        conversion_mode = "embedded_opendrive"
    else:
        command = [
            _netconvert_binary(netconvert_binary),
            "--sumo-net-file",
            str(source_net_file),
            "--opendrive-output",
            str(output_file),
        ]
        _append_options(command, netconvert_options)
        _run_netconvert(command)
        _restore_opendrive_ids(output_file, source_net_file)
        conversion_mode = "netconvert"

    kwargs = dict(opendrive_map_kwargs or {})
    odr_map = readXodr(output_file, **kwargs)
    setattr(odr_map, "sumo_net_file", str(source_net_file))
    setattr(odr_map, "xodr_file", str(output_file))
    setattr(odr_map, "sumo_conversion_mode", conversion_mode)
    setattr(odr_map, "identifiers_preserved", embedded_xodr is not None)
    if temp_dir is not None:
        setattr(odr_map, "_pyxodr3d_sumo_temp_dir", temp_dir)
    if output_temp_dir is not None:
        setattr(odr_map, "_pyxodr3d_xodr_temp_dir", output_temp_dir)
    return odr_map


def _resolve_sumo_net_file(net, net_file: str | Path | None) -> tuple[Path, str | None]:
    if net_file is not None:
        return Path(net_file), None

    attached = getattr(net, _SOURCE_NET_FILE_ATTR, None)
    if attached:
        attached_path = Path(attached)
        if attached_path.exists():
            return attached_path, None

    output_file, temp_dir = _make_output_path(None, "in_memory.net.xml")
    _write_minimal_sumo_net_xml(net, output_file)
    return output_file, temp_dir


def _write_minimal_sumo_net_xml(net, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("net", version=str(getattr(net, "getVersion", lambda: "")() or ""))

    boundary = _safe_call(net, "getBoundary") or _safe_call(net, "getBBoxXY")
    if boundary and len(boundary) >= 4:
        min_x, min_y, max_x, max_y = (float(v) for v in boundary[:4])
        ET.SubElement(
            root,
            "location",
            {
                "netOffset": "0.00,0.00",
                "convBoundary": f"{min_x:.2f},{min_y:.2f},{max_x:.2f},{max_y:.2f}",
                "origBoundary": f"{min_x:.2f},{min_y:.2f},{max_x:.2f},{max_y:.2f}",
                "projParameter": "!",
            },
        )

    for node in net.getNodes():
        x, y = node.getCoord()
        ET.SubElement(
            root,
            "junction",
            {
                "id": str(node.getID()),
                "type": str(node.getType() or "priority"),
                "x": f"{float(x):.6f}",
                "y": f"{float(y):.6f}",
            },
        )

    for edge in net.getEdges():
        if edge.getFunction():
            continue
        edge_elem = ET.SubElement(
            root,
            "edge",
            {
                "id": str(edge.getID()),
                "from": str(edge.getFromNode().getID()),
                "to": str(edge.getToNode().getID()),
                "priority": str(edge.getPriority()),
                "speed": f"{float(edge.getSpeed()):.6f}",
            },
        )
        edge_type = edge.getType()
        if edge_type:
            edge_elem.set("type", str(edge_type))
        for idx, lane in enumerate(edge.getLanes()):
            lane_shape = " ".join(
                f"{float(x):.6f},{float(y):.6f}" for x, y in lane.getShape()
            )
            attrs = {
                "id": str(lane.getID()),
                "index": str(idx),
                "speed": f"{float(lane.getSpeed()):.6f}",
                "length": f"{float(lane.getLength()):.6f}",
                "width": f"{float(lane.getWidth()):.6f}",
            }
            if lane_shape:
                attrs["shape"] = lane_shape
            ET.SubElement(edge_elem, "lane", attrs)

    for edge in net.getEdges():
        if edge.getFunction():
            continue
        for to_edge, connections in edge.getOutgoing().items():
            if to_edge.getFunction():
                continue
            for conn in connections:
                ET.SubElement(
                    root,
                    "connection",
                    {
                        "from": str(edge.getID()),
                        "to": str(to_edge.getID()),
                        "fromLane": str(conn.getFromLane().getIndex()),
                        "toLane": str(conn.getToLane().getIndex()),
                    },
                )

    ET.ElementTree(root).write(output_file, encoding="utf-8", xml_declaration=True)


def _annotate_sumo_net_ids(net_file: Path) -> None:
    tree = ET.parse(net_file)
    root = tree.getroot()

    for junction in root.findall("junction"):
        node_id = junction.get("id")
        if node_id:
            _set_param(junction, _ORIGINAL_NODE_ID_PARAM, node_id)

    edge_id_map: dict[str, str] = {}
    existing_edge_ids = {
        edge_id
        for edge_id in (edge.get("id") for edge in root.findall("edge"))
        if edge_id
    }

    for edge in root.findall("edge"):
        edge_id = edge.get("id")
        if not edge_id:
            continue
        original_link_id = _original_link_id_from_edge_id(edge_id)
        _set_param(edge, _ORIGINAL_LINK_ID_PARAM, original_link_id)
        if (
            edge.get("function") != "internal"
            and original_link_id != edge_id
            and original_link_id not in existing_edge_ids
        ):
            edge.set("id", original_link_id)
            edge_id_map[edge_id] = original_link_id
            existing_edge_ids.remove(edge_id)
            existing_edge_ids.add(original_link_id)
        for lane in edge.findall("lane"):
            lane_id = lane.get("id")
            lane_index = lane.get("index")
            original_lane_id = _original_lane_id_from_sumo_lane(
                edge_id,
                lane_id,
                lane_index,
            )
            _set_param(lane, _ORIGINAL_LANE_ID_PARAM, original_lane_id)
            if edge_id in edge_id_map and lane_id:
                lane.set(
                    "id",
                    _replace_edge_id_prefix(lane_id, edge_id, edge_id_map[edge_id]),
                )

    _restore_sumo_edge_references(root, edge_id_map)

    _write_xml(tree, net_file)


def _restore_sumo_edge_references(
    root: ET.Element,
    edge_id_map: Mapping[str, str],
) -> None:
    if not edge_id_map:
        return

    for connection in root.findall("connection"):
        for attr in ("from", "to"):
            edge_id = connection.get(attr)
            if edge_id is not None and edge_id in edge_id_map:
                connection.set(attr, edge_id_map[edge_id])


def _replace_edge_id_prefix(value: str, old_edge_id: str, new_edge_id: str) -> str:
    if value == old_edge_id:
        return new_edge_id
    prefix = f"{old_edge_id}_"
    if value.startswith(prefix):
        return f"{new_edge_id}_{value[len(prefix):]}"
    return value


def _restore_opendrive_ids(xodr_file: Path, source_net_file: Path) -> None:
    edge_ids = _sumo_edge_original_ids(source_net_file)
    if not edge_ids:
        return

    tree = ET.parse(xodr_file)
    root = tree.getroot()
    roads = root.findall("road")
    used_ids: set[str] = set()
    road_id_map: dict[str, str] = {}
    edge_iter = iter(edge_ids)

    for road in roads:
        old_id = road.get("id", "")
        if road.get("junction", "-1") == "-1":
            try:
                edge_id = next(edge_iter)
            except StopIteration:
                edge_id = old_id
            new_id = _unique_id(edge_id, used_ids)
            road.set("id", new_id)
            if not road.get("name"):
                road.set("name", edge_id)
            _set_xodr_user_data(road, _ORIGINAL_LINK_ID_PARAM, edge_id)
        else:
            new_id = _unique_id(old_id, used_ids)
            road.set("id", new_id)

        if old_id:
            road_id_map[old_id] = new_id

        for lane in road.findall("./lanes/laneSection/*/lane"):
            lane_id = lane.get("id")
            if lane_id:
                _set_xodr_user_data(lane, _ORIGINAL_LANE_ID_PARAM, lane_id)

    _restore_road_references(root, road_id_map)

    for junction in root.findall("junction"):
        junction_id = junction.get("id")
        if junction_id:
            _set_xodr_user_data(junction, _ORIGINAL_NODE_ID_PARAM, junction_id)

    _write_xml(tree, xodr_file)


def _restore_road_references(root: ET.Element, road_id_map: Mapping[str, str]) -> None:
    for road in root.findall("road"):
        for link in road.findall("./link/*"):
            if link.get("elementType") == "road":
                element_id = link.get("elementId")
                if element_id is not None and element_id in road_id_map:
                    link.set("elementId", road_id_map[element_id])

    for connection in root.findall("./junction/connection"):
        for attr in ("incomingRoad", "connectingRoad"):
            road_id = connection.get(attr)
            if road_id is not None and road_id in road_id_map:
                connection.set(attr, road_id_map[road_id])

    for priority in root.findall("./junction/priority"):
        for attr in ("high", "low"):
            road_id = priority.get(attr)
            if road_id is not None and road_id in road_id_map:
                priority.set(attr, road_id_map[road_id])


def _sumo_edge_original_ids(net_file: Path) -> list[str]:
    root = ET.parse(net_file).getroot()
    edge_ids: list[str] = []
    for edge in root.findall("edge"):
        edge_id = edge.get("id")
        if not edge_id or edge.get("function") == "internal" or edge_id.startswith(":"):
            continue
        edge_ids.append(
            _get_param(edge, _ORIGINAL_LINK_ID_PARAM)
            or edge.get("origId")
            or _original_link_id_from_edge_id(edge_id)
        )
    return edge_ids


def _original_link_id_from_edge_id(edge_id: str) -> str:
    if edge_id.startswith(":"):
        return edge_id
    if edge_id.startswith("-") and edge_id[1:].isdigit():
        return edge_id[1:]
    return edge_id


def _original_lane_id_from_sumo_lane(
    edge_id: str,
    lane_id: str | None,
    lane_index: str | None,
) -> str:
    if lane_index is not None:
        try:
            index = int(lane_index)
        except ValueError:
            index = None
        if index is not None:
            return str(-(index + 1)) if edge_id.startswith("-") else str(index + 1)
    if lane_id and "_" in lane_id:
        return lane_id.rsplit("_", 1)[-1]
    return lane_id or ""


def _set_param(parent: ET.Element, key: str, value: str) -> None:
    for param in parent.findall("param"):
        if param.get("key") == key:
            param.set("value", value)
            return
    ET.SubElement(parent, "param", {"key": key, "value": value})


def _get_param(parent: ET.Element, key: str) -> str | None:
    return next(
        (
            param.get("value")
            for param in parent.findall("param")
            if param.get("key") == key
        ),
        None,
    )


def _set_xodr_user_data(parent: ET.Element, key: str, value: str) -> None:
    user_data = parent.find("userData")
    if user_data is None:
        user_data = ET.SubElement(parent, "userData")
    for vector in user_data.findall("vector"):
        if vector.get("key") == key:
            vector.set("value", value)
            return
    ET.SubElement(user_data, "vector", {"key": key, "value": value})


def _unique_id(id_value: str, used_ids: set[str]) -> str:
    candidate = id_value
    suffix = 1
    while candidate in used_ids:
        suffix += 1
        candidate = f"{id_value}.{suffix}"
    used_ids.add(candidate)
    return candidate


def _write_xml(tree: ET.ElementTree[Any], output_file: Path) -> None:
    with contextlib.suppress(AttributeError):
        ET.indent(tree, space="    ")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)


def _safe_call(obj, name: str):
    method = getattr(obj, name, None)
    if method is None:
        return None
    try:
        return method()
    except Exception:
        return None


__all__ = [
    "xodr_to_net_xml",
    "xodr_from_net_xml",
]
