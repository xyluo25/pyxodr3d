import maplibregl from "https://esm.sh/maplibre-gl@5.24.0";
import { Geoman } from "https://esm.sh/@geoman-io/maplibre-geoman-free@0.7.1?deps=maplibre-gl@5.24.0";
import { GeoEditor } from "https://esm.sh/maplibre-gl-geo-editor@0.7.3?deps=maplibre-gl@5.24.0";
import { odrObjectDefinitions } from "./static/odr-3d-objects.js?v=20260515_objects_color";

const status = document.getElementById("status");
const mainView = document.getElementById("main_view");
const loadingScreen = document.getElementById("loading_screen");
const loadingScreenText = document.getElementById("loading_screen_msg_txt");
const fileInput = document.getElementById("xodr_file_input");
const objectPalette = document.getElementById("object_palette");
const objectPaletteGrid = document.getElementById("object_palette_grid");
const saveButton = document.getElementById("save_xodr_btn");
const fitButton = document.getElementById("fit_btn");
const reloadButton = document.getElementById("reload_btn");
const basemapSelect = document.getElementById("basemap_select");
const basemapFallbackNotice = document.getElementById("basemap_fallback_notice");
const basemapFallbackNoticeClose = document.getElementById("basemap_fallback_notice_close");
const spotlight = document.getElementById("spotlight");
const spotlightToggle = document.getElementById("spotlight_toggle");
const spotlightDockLeft = document.getElementById("spotlight_dock_left");
const spotlightDockRight = document.getElementById("spotlight_dock_right");
const spotlightResizeHandleLeft = document.getElementById("spotlight_resize_handle_left");
const spotlightResizeHandleRight = document.getElementById("spotlight_resize_handle_right");
const attributeFields = document.getElementById("attribute_fields");
const addLaneButton = document.getElementById("add_lane_btn");
const deleteFeatureButton = document.getElementById("delete_feature_btn");
const copyLaneLinkButton = document.getElementById("copy_lane_link_btn");
const addSignalButton = document.getElementById("add_signal_btn");
const addPostButton = document.getElementById("add_post_btn");
const addMastArmButton = document.getElementById("add_mastarm_btn");
const undoMoveButton = document.getElementById("undo_move_btn");
const globalLaneWidthInput = document.getElementById("global_lane_width");
const laneArrowSizeInput = document.getElementById("lane_arrow_size");
const toggleLaneArrowsButton = document.getElementById("toggle_lane_arrows_btn");
const SPOTLIGHT_SIDE_STORAGE_KEY = "opendriveviewer_side";

// The browser keeps three editable data sets:
// roads for OpenDRIVE planView centerlines, lanes for lane-level polygons,
// and signals for signal heads plus physical posts/mast arms.
let geoEditor = null;
let geoman = null;
let geoEditorStarted = false;
let initialNetworkLoaded = false;
let currentFilename = "network.xodr";
let spotlightEventsRegistered = false;
let laneSelectionEventsRegistered = false;
let selectedFeature = null;
let copiedLaneLink = null;
let armedObjectDefinition = null;
let pendingSignalDetailKind = null;
let dragState = null;
let undoStack = [];
let currentLaneWidth = 3.5;
let laneArrowsVisible = true;
let laneArrowSize = 1;
let generatedFeatureCounter = 0;
const objectDefinitions = odrObjectDefinitions;
const processedEditorFeatureKeys = new Set();
let geoEditorLiveDrawActive = false;
let geoEditorSyncPending = false;
let geoEditorSyncToken = 0;
let pendingPayloadAfterStyle = null;
let pendingPayloadLoadResolver = null;
const MAPLIBRE_SAFE_SOURCE_MAXZOOM = 24;
let currentGeoJson = {
  type: "FeatureCollection",
  features: [],
};
let currentLaneGeoJson = {
  type: "FeatureCollection",
  features: [],
};
let currentSignalGeoJson = {
  type: "FeatureCollection",
  features: [],
};
let pendingStyleRestore = null;
let restoreRequestId = 0;
let loadingOverlayCount = 0;

// Basemaps are only the background.  OpenDRIVE layers are restored after
// every style change so loaded lanes/signals do not disappear.
const basemaps = {
  openstreetmap: {
    label: "OpenStreetMap",
    tiles: [
      "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
      "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
      "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
    ],
    attribution: "&copy; OpenStreetMap contributors",
  },
  google: {
    label: "Google Road",
    tiles: ["https://mt0.google.com/vt/lyrs=m&x={x}&y={y}&z={z}"],
    attribution: "&copy; Google",
  },
  google_satellite: {
    label: "Google Satellite",
    tiles: ["https://mt0.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"],
    attribution: "&copy; Google",
  },
  carto_light: {
    label: "Carto Light",
    tiles: [
      "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    ],
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  },
  carto_dark: {
    label: "Carto Dark",
    tiles: [
      "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    ],
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  },
  esri_imagery: {
    label: "Esri Imagery",
    tiles: [
      "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    ],
    attribution: "Tiles &copy; Esri",
  },
  opentopomap: {
    label: "OpenTopoMap",
    tiles: ["https://a.tile.opentopomap.org/{z}/{x}/{y}.png"],
    attribution: "Map data &copy; OpenStreetMap contributors, SRTM | Style &copy; OpenTopoMap",
  },
  // osm_hot: {
  //   label: "OSM Humanitarian",
  //   tiles: ["https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png"],
  //   attribution: "&copy; OpenStreetMap contributors, HOT",
  // },
  gridmesh: {
    label: "Grid Mesh",
    kind: "gridmesh",
    attribution: "Local OpenDRIVE grid",
  },
};

function basemapStyle(basemapId) {
  const basemap = basemaps[basemapId] || basemaps.openstreetmap;
  if (basemap.kind === "gridmesh") {
    return {
      version: 8,
      glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      sources: {},
      layers: [
        {
          id: "gridmesh-background",
          type: "background",
          paint: {
            "background-color": "#05070a",
          },
        },
      ],
    };
  }
  return {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      osm: {
        type: "raster",
        tiles: basemap.tiles,
        tileSize: 256,
        maxzoom: MAPLIBRE_SAFE_SOURCE_MAXZOOM,
        attribution: basemap.attribution,
      },
    },
    layers: [
      {
        id: "osm",
        type: "raster",
        source: "osm",
      },
    ],
  };
}

for (const [id, basemap] of Object.entries(basemaps)) {
  const option = document.createElement("option");
  option.value = id;
  option.textContent = basemap.label;
  basemapSelect.appendChild(option);
}
basemapSelect.value = "gridmesh";
let activeBasemapId = basemapSelect.value;
let payloadSupportsRealWorldBasemap = null;

const map = new maplibregl.Map({
  container: "map",
  style: basemapStyle(basemapSelect.value),
  center: [-85.31, 35.05],
  zoom: 14,
  pitch: 15,
  maxPitch: 180,
  bearing: 180,
  attributionControl: true,
});

function withSafeSourceMaxZoom(sourceSpec) {
  if (!sourceSpec || !["geojson", "raster"].includes(sourceSpec.type)) return sourceSpec;
  const currentMaxZoom = Number(sourceSpec.maxzoom);
  if (Number.isFinite(currentMaxZoom) && currentMaxZoom >= MAPLIBRE_SAFE_SOURCE_MAXZOOM) return sourceSpec;
  return {
    ...sourceSpec,
    maxzoom: MAPLIBRE_SAFE_SOURCE_MAXZOOM,
  };
}

const mapAddSource = map.addSource.bind(map);
map.addSource = (sourceId, sourceSpec) => mapAddSource(sourceId, withSafeSourceMaxZoom(sourceSpec));

map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");
map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
map.once("style.load", () => scheduleGridMeshRefresh());

function showBasemapFallbackNotice() {
  basemapFallbackNotice.hidden = false;
}

function hideBasemapFallbackNotice() {
  basemapFallbackNotice.hidden = true;
}

function requiresRealWorldProjection(basemapId) {
  return basemaps[basemapId]?.kind !== "gridmesh";
}

// Changing a MapLibre style removes custom sources and layers.  Keep the
// current selection, swap the basemap, then rebuild the OpenDRIVE overlays.
function changeBasemap(basemapId, options = {}) {
  const requestedBasemapId = basemaps[basemapId] ? basemapId : "openstreetmap";
  const unsupportedRealWorldBasemap = (
    payloadSupportsRealWorldBasemap === false &&
    requiresRealWorldProjection(requestedBasemapId)
  );
  const nextBasemapId = unsupportedRealWorldBasemap ? "gridmesh" : requestedBasemapId;
  const persist = options.persist !== false;
  if (unsupportedRealWorldBasemap) {
    showBasemapFallbackNotice();
  }
  basemapSelect.value = nextBasemapId;
  if (persist) {
    localStorage.setItem("opendriveviewer_basemap", nextBasemapId);
  }
  if (activeBasemapId === nextBasemapId) {
    setGridMeshSource();
    refreshFeatureSources();
    return false;
  }
  const selected = selectedFeature;
  pendingStyleRestore = selected;
  restoreRequestId += 1;
  activeBasemapId = nextBasemapId;
  map.setStyle(basemapStyle(nextBasemapId));
  scheduleOverlayRestore(restoreRequestId);
  return true;
}

function proj4Value(proj4Text, key) {
  const match = String(proj4Text || "").match(new RegExp(`\\+${key}=([^\\s]+)`));
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}

function hasExplicitProjection(proj4Text) {
  return /(?:^|\s)\+(proj|init|epsg|crs)=/.test(String(proj4Text || ""));
}

function hasUsableProjection(proj4Text) {
  const text = String(proj4Text || "").trim();
  if (!hasExplicitProjection(text)) return false;
  const tokens = new Set(text.split(/\s+/).map((token) => token.split("=")[0]));
  if (tokens.has("+epsg") || tokens.has("+init") || tokens.has("+crs")) return true;
  if (!tokens.has("+proj")) return false;
  if (/\+proj=tmerc(?:\s|$)/.test(text)) {
    return (
      tokens.has("+lat_0") &&
      tokens.has("+lon_0") &&
      tokens.has("+k") &&
      tokens.has("+x_0") &&
      tokens.has("+y_0") &&
      tokens.has("+units") &&
      (tokens.has("+datum") || tokens.has("+ellps"))
    );
  }
  return tokens.has("+units") || tokens.has("+datum") || tokens.has("+ellps");
}

function collectCoordinateSamples(collection, limit = 120) {
  const samples = [];
  const addCoordinate = (coord) => {
    if (samples.length >= limit) return;
    const lon = Number(coord?.[0]);
    const lat = Number(coord?.[1]);
    if (Number.isFinite(lon) && Number.isFinite(lat)) samples.push([lon, lat]);
  };
  const walk = (coords) => {
    if (samples.length >= limit || !Array.isArray(coords)) return;
    if (typeof coords[0] === "number") {
      addCoordinate(coords);
      return;
    }
    for (const item of coords) walk(item);
  };
  for (const feature of collection?.features || []) {
    walk(feature.geometry?.coordinates);
    if (samples.length >= limit) break;
  }
  return samples;
}

function coordinateExtentStats(samples) {
  if (!samples.length) return null;
  let maxAbs = 0;
  for (const [lon, lat] of samples) {
    maxAbs = Math.max(maxAbs, Math.abs(lon), Math.abs(lat));
  }
  return { maxAbs };
}

function isNullIslandScale(samples) {
  const stats = coordinateExtentStats(samples);
  if (!stats) return false;

  // Several CARLA example maps have a complete tmerc projection string but
  // convert into tiny coordinates around 0,0. Those are local engineering
  // maps, so a world satellite basemap is misleading.
  return stats.maxAbs < 0.01;
}

function payloadHasRealWorldLonLat(payload) {
  const proj4Text = String(payload?.proj4 || "").trim();
  if (!hasUsableProjection(proj4Text)) return false;

  const samples = [
    ...collectCoordinateSamples(payload?.lane_geojson),
    ...collectCoordinateSamples(payload?.signal_geojson),
    ...collectCoordinateSamples(payload?.geojson),
  ];
  if (samples.length > 0) {
    const validLonLat = samples.every(([lon, lat]) => {
      return lon >= -180 && lon <= 180 && lat >= -85 && lat <= 85;
    });
    return validLonLat && !isNullIslandScale(samples);
  }

  const lon0 = proj4Value(proj4Text, "lon_0");
  const lat0 = proj4Value(proj4Text, "lat_0");
  if (lon0 === null || lat0 === null) return false;
  if (Math.max(Math.abs(lon0), Math.abs(lat0)) < 0.01) return false;
  return lon0 >= -180 && lon0 <= 180 && lat0 >= -85 && lat0 <= 85;
}

function applyDefaultBasemapForPayload(payload) {
  payloadSupportsRealWorldBasemap = payloadHasRealWorldLonLat(payload);
  const basemapId = payloadSupportsRealWorldBasemap ? "google_satellite" : "gridmesh";
  if (payloadSupportsRealWorldBasemap) {
    hideBasemapFallbackNotice();
  } else {
    showBasemapFallbackNotice();
  }
  return changeBasemap(basemapId, { persist: false });
}

function featureCoordinates(feature) {
  if (feature.geometry?.type === "LineString") {
    return feature.geometry.coordinates;
  }
  if (feature.geometry?.type === "Polygon") {
    return feature.geometry.coordinates.flat();
  }
  if (feature.geometry?.type === "Point") {
    return [feature.geometry.coordinates];
  }
  return [];
}

function laneDirectionGeoJson(geojson = currentLaneGeoJson) {
  const features = [];
  for (const feature of geojson?.features || []) {
    const ring = feature.geometry?.type === "Polygon" ? feature.geometry.coordinates?.[0] : null;
    if (!Array.isArray(ring) || ring.length < 4) continue;
    const half = Math.floor((ring.length - 1) / 2);
    const outerEdge = ring.slice(0, Math.max(2, half));
    const innerEdge = ring.slice(half, ring.length - 1).reverse();
    const pairCount = Math.min(outerEdge.length, innerEdge.length);
    if (pairCount < 2) continue;
    const centerline = [];
    for (let index = 0; index < pairCount; index += 1) {
      const outer = outerEdge[index];
      const inner = innerEdge[index];
      centerline.push([
        (Number(outer[0]) + Number(inner[0])) * 0.5,
        (Number(outer[1]) + Number(inner[1])) * 0.5,
      ]);
    }
    const middle = Math.max(0, Math.min(centerline.length - 2, Math.floor((centerline.length - 1) / 2)));
    const start = centerline[middle];
    const end = centerline[middle + 1];
    if (!start || !end) continue;
    const dx = Number(end[0]) - Number(start[0]);
    const dy = Number(end[1]) - Number(start[1]);
    const length = Math.hypot(dx, dy);
    if (!Number.isFinite(length) || length <= 1e-12) continue;
    const ux = dx / length;
    const uy = dy / length;
    const px = -uy;
    const py = ux;
    const center = [(Number(start[0]) + Number(end[0])) * 0.5, (Number(start[1]) + Number(end[1])) * 0.5];
    const laneWidth = Math.max(0.2, Number(feature.properties?.width) || currentLaneWidth || 3.5);
    const latScale = 110_540;
    const lonScale = Math.max(1e-9, 111_320 * Math.cos(center[1] * Math.PI / 180));
    const scale = Math.max(0.2, Math.min(3, Number(laneArrowSize) || 1));
    const arrowLength = Math.max(0.28, Math.min(1.6, laneWidth * 0.28 * scale));
    const arrowWidth = Math.max(0.16, Math.min(1.0, laneWidth * 0.16 * scale));
    const lengthLon = arrowLength / lonScale;
    const lengthLat = arrowLength / latScale;
    const widthLon = arrowWidth / lonScale;
    const widthLat = arrowWidth / latScale;
    const tip = [center[0] + ux * lengthLon * 0.5, center[1] + uy * lengthLat * 0.5];
    const base = [center[0] - ux * lengthLon * 0.5, center[1] - uy * lengthLat * 0.5];
    const left = [base[0] + px * widthLon * 0.5, base[1] + py * widthLat * 0.5];
    const right = [base[0] - px * widthLon * 0.5, base[1] - py * widthLat * 0.5];
    features.push({
      type: "Feature",
      id: `${feature.id || feature.properties?.lane_key || features.length}:direction`,
      properties: {
        lane_key: feature.properties?.lane_key || feature.id,
        road_id: feature.properties?.road_id,
        lane_id: feature.properties?.lane_id,
      },
      geometry: {
        type: "Polygon",
        coordinates: [[tip, left, right, tip]],
      },
    });
  }
  return { type: "FeatureCollection", features };
}

function mergedOverlayBounds() {
  const coords = [
    ...currentLaneGeoJson.features.flatMap(featureCoordinates),
    ...currentSignalGeoJson.features.flatMap(featureCoordinates),
    ...currentGeoJson.features.flatMap(featureCoordinates),
  ].filter((coord) => Array.isArray(coord) && coord.length >= 2);
  if (coords.length === 0) return null;
  return coords.reduce(
    (box, coord) => box.extend(coord),
    new maplibregl.LngLatBounds(coords[0], coords[0])
  );
}

function niceGridStep(span) {
  const target = Math.max(span / 36, 0.00001);
  const exponent = Math.floor(Math.log10(target));
  const base = 10 ** exponent;
  for (const multiplier of [1, 2, 5, 10]) {
    const step = multiplier * base;
    if (step >= target) return step;
  }
  return base;
}

function gridMeshGeoJson() {
  const bounds = mergedOverlayBounds() || (map.isStyleLoaded() ? map.getBounds() : null);
  if (!bounds) return emptyFeatureCollection();
  const west = bounds.getWest();
  const east = bounds.getEast();
  const south = bounds.getSouth();
  const north = bounds.getNorth();
  const lonPad = Math.max((east - west) * 0.25, 0.002);
  const latPad = Math.max((north - south) * 0.25, 0.002);
  const minLon = west - lonPad;
  const maxLon = east + lonPad;
  const minLat = south - latPad;
  const maxLat = north + latPad;
  const step = niceGridStep(Math.max(maxLon - minLon, maxLat - minLat));
  const majorStep = step * 5;
  const features = [];

  const startLon = Math.floor(minLon / step) * step;
  for (let lon = startLon; lon <= maxLon + step * 0.5; lon += step) {
    const major = Math.abs(Math.round(lon / majorStep) * majorStep - lon) < step * 0.01;
    features.push({
      type: "Feature",
      properties: { grid_type: major ? "major" : "minor" },
      geometry: { type: "LineString", coordinates: [[lon, minLat], [lon, maxLat]] },
    });
  }

  const startLat = Math.floor(minLat / step) * step;
  for (let lat = startLat; lat <= maxLat + step * 0.5; lat += step) {
    const major = Math.abs(Math.round(lat / majorStep) * majorStep - lat) < step * 0.01;
    features.push({
      type: "Feature",
      properties: { grid_type: major ? "major" : "minor" },
      geometry: { type: "LineString", coordinates: [[minLon, lat], [maxLon, lat]] },
    });
  }

  return {
    type: "FeatureCollection",
    features,
  };
}

function ensureGridMeshLayers() {
  if (!map.getSource("gridmesh-lines")) return;
  if (!map.getLayer("gridmesh-lines-minor")) {
    map.addLayer({
      id: "gridmesh-lines-minor",
      type: "line",
      source: "gridmesh-lines",
      filter: ["==", ["get", "grid_type"], "minor"],
      paint: {
        "line-color": "#1b2330",
        "line-width": 1,
        "line-opacity": 0.92,
      },
    });
  }
  if (!map.getLayer("gridmesh-lines-major")) {
    map.addLayer({
      id: "gridmesh-lines-major",
      type: "line",
      source: "gridmesh-lines",
      filter: ["==", ["get", "grid_type"], "major"],
      paint: {
        "line-color": "#344054",
        "line-width": 1.35,
        "line-opacity": 0.98,
      },
    });
  }
}

function setGridMeshSource() {
  if ((basemapSelect.value || "") !== "gridmesh") return;
  if (!map.isStyleLoaded()) return;
  const geojson = gridMeshGeoJson();
  if (map.getSource("gridmesh-lines")) {
    map.getSource("gridmesh-lines").setData(geojson);
    ensureGridMeshLayers();
    return;
  }
  addEditorGeoJsonSource("gridmesh-lines", geojson);
  ensureGridMeshLayers();
}

function scheduleGridMeshRefresh() {
  setGridMeshSource();
  setTimeout(setGridMeshSource, 0);
  setTimeout(setGridMeshSource, 120);
  setTimeout(setGridMeshSource, 350);
  setTimeout(setGridMeshSource, 750);
}

function isBasemapLayer(layer) {
  return layer.id === "osm" || layer.id === "gridmesh-background";
}

function isEditableOverlayLayer(layer) {
  if (!layer?.id || isBasemapLayer(layer)) return false;
  const id = String(layer.id || "").toLowerCase();
  return (
    id.startsWith("opendrive-") ||
    id.startsWith("gridmesh-lines") ||
    isGeoEditorLayer(layer)
  );
}

function isGeoEditorLayer(layer) {
  const id = String(layer?.id || "").toLowerCase();
  const source = String(layer?.source || "").toLowerCase();
  return (
    id.includes("geoman") ||
    id.includes("geo-editor") ||
    id.includes("draw") ||
    id.includes("vertex") ||
    id.includes("helper") ||
    id.includes("snap") ||
    id.startsWith("gm") ||
    source.includes("geoman") ||
    source.includes("geo-editor") ||
    source.includes("draw") ||
    source.startsWith("gm")
  );
}

function moveLayerToTop(layerId) {
  if (!map.getLayer(layerId)) return;
  try {
    map.moveLayer(layerId);
  } catch (error) {
    console.debug("Could not move overlay layer", layerId, error);
  }
}

function elevateEditableOverlayLayers() {
  if (!map.isStyleLoaded()) return;
  const layers = map.getStyle()?.layers || [];
  for (const layer of layers) {
    if (isEditableOverlayLayer(layer) && !isGeoEditorLayer(layer)) moveLayerToTop(layer.id);
  }
  for (const layer of layers) {
    if (isEditableOverlayLayer(layer) && isGeoEditorLayer(layer)) moveLayerToTop(layer.id);
  }
}

function scheduleEditableOverlayElevation() {
  if (!map.isStyleLoaded()) return;
  setTimeout(elevateEditableOverlayLayers, 0);
  setTimeout(elevateEditableOverlayLayers, 80);
  setTimeout(elevateEditableOverlayLayers, 240);
}

function setGeoEditorLiveDrawActive(active) {
  geoEditorLiveDrawActive = active;
  scheduleEditableOverlayElevation();
}

function syncGeoEditorToCurrentStyle() {
  if (!geoEditor || !geoman || !map.isStyleLoaded()) return;
  try {
    geoEditor.setGeoman(geoman);
  } catch (error) {
    console.debug("Could not rebind GeoEditor to Geoman", error);
  }
  loadIntoEditor(currentGeoJson);
  scheduleEditableOverlayElevation();
  hideGeoEditorToolbarButtons();
  setTimeout(hideGeoEditorToolbarButtons, 250);
}

function restoreOverlayLayersAfterStyleChange(requestId = restoreRequestId, attempt = 0) {
  if (requestId !== restoreRequestId) return;
  if (!map.isStyleLoaded()) {
    if (attempt < 20) {
      setTimeout(() => restoreOverlayLayersAfterStyleChange(requestId, attempt + 1), 100);
    }
    return;
  }

  setGridMeshSource();
  setLaneSource(currentLaneGeoJson);
  setSignalSource(currentSignalGeoJson);
  setRoadSource(currentGeoJson);
  scheduleGridMeshRefresh();
  scheduleEditableOverlayElevation();
  if (pendingPayloadAfterStyle) {
    const payload = pendingPayloadAfterStyle;
    pendingPayloadAfterStyle = null;
    const installed = installPayloadData(payload);
    if (pendingPayloadLoadResolver) {
      const resolve = pendingPayloadLoadResolver;
      pendingPayloadLoadResolver = null;
      resolve(installed);
    }
  }
  if (pendingStyleRestore) {
    setSpotlightFeature(pendingStyleRestore);
  } else if (selectedFeature) {
    setSpotlightFeature(selectedFeature);
  }
  pendingStyleRestore = null;
}

function scheduleOverlayRestore(requestId = restoreRequestId) {
  const restore = () => restoreOverlayLayersAfterStyleChange(requestId);
  map.once("style.load", restore);
  map.once("idle", restore);
  setTimeout(restore, 250);
  setTimeout(restore, 750);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

let spotlightMapResizeFrame = null;

function scheduleSpotlightMapResize() {
  if (spotlightMapResizeFrame !== null) return;
  spotlightMapResizeFrame = window.requestAnimationFrame(() => {
    spotlightMapResizeFrame = null;
    map.resize();
  });
}

function setSpotlightWidth(width) {
  const maxWidth = Math.max(240, window.innerWidth - 80);
  const nextWidth = clamp(Number(width) || 300, 240, Math.min(720, maxWidth));
  spotlight.style.width = `${nextWidth}px`;
  localStorage.setItem("opendriveviewer_width", String(Math.round(nextWidth)));
  scheduleSpotlightMapResize();
}

function getSpotlightSide() {
  return ["left", "right"].includes(spotlight.dataset.side) ? spotlight.dataset.side : null;
}

function updateSpotlightSideControls(side) {
  spotlightDockLeft.setAttribute("aria-pressed", String(side === "left"));
  spotlightDockRight.setAttribute("aria-pressed", String(side === "right"));
}

function setSpotlightSide(side, persist = true) {
  const nextSide = side === "left" ? "left" : "right";
  spotlight.dataset.side = nextSide;
  updateSpotlightSideControls(nextSide);
  if (persist) {
    localStorage.setItem(SPOTLIGHT_SIDE_STORAGE_KEY, nextSide);
  }
  scheduleSpotlightMapResize();
}

function restoreSpotlightLayout() {
  const storedWidth = Number(localStorage.getItem("opendriveviewer_width"));
  if (Number.isFinite(storedWidth) && storedWidth > 0) {
    setSpotlightWidth(storedWidth);
  }
  const storedSide = localStorage.getItem(SPOTLIGHT_SIDE_STORAGE_KEY);
  setSpotlightSide(storedSide === "left" ? "left" : "right", false);
  // Older versions restored arbitrary drag coordinates that could reopen the
  // panel away from the selected sidebar. Side placement now uses its own key.
  localStorage.removeItem("opendriveviewer_left");
  localStorage.removeItem("opendriveviewer_top");
}

function setStatus(message, isError = false) {
  if (String(message || "").includes("Action instance already exists")) {
    return;
  }
  status.textContent = message;
  status.style.color = isError ? "#8a1f11" : "#1f2933";
  if (!isError && loadingOverlayCount > 0) setLoadingOverlayMessage(message);
  updateBasemapPosition();
}

function updateBasemapPosition() {
  const statusHeight = status.getBoundingClientRect().height || 0;
  basemapSelect.parentElement.style.bottom = `${Math.ceil(statusHeight + 24)}px`;
}

function setLoadingOverlayMessage(message) {
  if (loadingScreenText) loadingScreenText.textContent = message || "Loading...";
}

function showLoadingOverlay(message = "Loading...") {
  loadingOverlayCount += 1;
  setLoadingOverlayMessage(message);
  if (!loadingScreen) return;
  loadingScreen.classList.remove("loading-hidden");
  loadingScreen.setAttribute("aria-busy", "true");
}

function hideLoadingOverlay(force = false) {
  loadingOverlayCount = force ? 0 : Math.max(0, loadingOverlayCount - 1);
  if (loadingOverlayCount > 0 || !loadingScreen) return;
  loadingScreen.classList.add("loading-hidden");
  loadingScreen.setAttribute("aria-busy", "false");
}

function elapsedSeconds(startMs) {
  return Math.max(0, (performance.now() - startMs) / 1000);
}

function formatSeconds(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "0.00 seconds";
  return `${value.toFixed(value < 10 ? 2 : 1)} seconds`;
}

function formatFileSize(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "unknown size";
  const units = ["B", "KB", "MB", "GB"];
  let scaled = value;
  let unitIndex = 0;
  while (scaled >= 1024 && unitIndex < units.length - 1) {
    scaled /= 1024;
    unitIndex += 1;
  }
  const precision = unitIndex === 0 ? 0 : (scaled < 10 ? 2 : 1);
  return `${scaled.toFixed(precision)} ${units[unitIndex]}`;
}

function payloadFileSize(payload, fallbackBytes = 0) {
  const payloadBytes = Number(payload?.file_size_bytes);
  if (Number.isFinite(payloadBytes) && payloadBytes > 0) return payloadBytes;
  return fallbackBytes;
}

function loadSummary(payload, elapsed, fileSizeBytes) {
  return `Loaded ${currentFilename} (${formatFileSize(fileSizeBytes)}) in ${formatSeconds(elapsed)}: ${payload.lane_geojson.features.length} lanes, ${(payload.signal_geojson?.features.length || 0)} signals, and ${payload.geojson.features.length} editable roads.`;
}

function errorMessage(error) {
  if (!error) return "Unknown error";
  return error.stack || error.message || String(error);
}

function isBenignGeomanActionError(error) {
  const message = errorMessage(error);
  return message.includes("Action instance already exists");
}

window.addEventListener("error", (event) => {
  if (isBenignGeomanActionError(event.error || event.message)) {
    event.preventDefault();
    return;
  }
  setStatus(`Browser error: ${errorMessage(event.error || event.message)}`, true);
});
window.addEventListener("unhandledrejection", (event) => {
  if (isBenignGeomanActionError(event.reason)) {
    event.preventDefault();
    return;
  }
  setStatus(`Browser promise error: ${errorMessage(event.reason)}`, true);
});

const browserSessionId = (
  window.crypto && typeof window.crypto.randomUUID === "function"
) ? window.crypto.randomUUID() : `session_${Date.now()}_${Math.random().toString(16).slice(2)}`;
let browserCloseSent = false;

function postBrowserLifecycle(path, useBeacon = false) {
  const body = JSON.stringify({ session_id: browserSessionId });
  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(path, new Blob([body], { type: "application/json" }));
    return;
  }
  fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {});
}

function notifyBrowserClose() {
  if (browserCloseSent) return;
  browserCloseSent = true;
  postBrowserLifecycle("/api/browser-close", true);
}

postBrowserLifecycle("/api/browser-open");
window.addEventListener("pagehide", notifyBrowserClose);
window.addEventListener("beforeunload", notifyBrowserClose);

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    throw new Error(`Invalid JSON response from ${url}: ${errorMessage(error)}. First response text: ${text.slice(0, 240)}`);
  }
  if (!response.ok) {
    throw new Error(payload.error || response.statusText);
  }
  return payload;
}

function downloadText(filename, text, type = "application/xml") {
  const link = document.createElement("a");
  link.download = filename;
  link.href = URL.createObjectURL(new Blob([text], { type }));
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  }, 1000);
}

function fitToGeoJson(geojson) {
  const coords = geojson.features.flatMap((feature) => {
    if (feature.geometry?.type === "LineString") {
      return feature.geometry.coordinates;
    }
    if (feature.geometry?.type === "Polygon") {
      return feature.geometry.coordinates.flat();
    }
    return [];
  });
  if (coords.length === 0) return;
  const bounds = coords.reduce(
    (box, coord) => box.extend(coord),
    new maplibregl.LngLatBounds(coords[0], coords[0])
  );
  map.fitBounds(bounds, { padding: 60, duration: 500 });
  map.once("moveend", () => scheduleGridMeshRefresh());
  setTimeout(scheduleGridMeshRefresh, 650);
}

function emptyFeatureCollection() {
  return {
    type: "FeatureCollection",
    features: [],
  };
}

function addEditorGeoJsonSource(sourceId, data) {
  // Keep source maxzoom above the map max zoom. MapLibre 5.x can otherwise
  // retain an overscaled tile as if it had four children during fractional zoom.
  map.addSource(sourceId, {
    type: "geojson",
    data: data || emptyFeatureCollection(),
    maxzoom: MAPLIBRE_SAFE_SOURCE_MAXZOOM,
  });
}

// Feature lookup helpers always return the source object from the editable
// collections.  MapLibre click events hand us copies, and editing those
// copies would not change the data that is later saved.
function laneKeyFromProperties(properties) {
  if (!properties) return "";
  if (properties.lane_key) return String(properties.lane_key);
  return `${properties.road_id}/${Number(properties.lanesection_s0 || 0).toFixed(6)}/${properties.lane_id}`;
}

function findLaneFeature(roadId, laneSectionS0, laneId) {
  const section = Number(laneSectionS0);
  return currentLaneGeoJson.features.find((feature) => {
    const props = feature.properties || {};
    return (
      String(props.road_id) === String(roadId) &&
      String(props.lane_id) === String(laneId) &&
      Math.abs(Number(props.lanesection_s0 || 0) - section) < 1e-6
    );
  });
}

function findLaneFeatureByKey(laneKey) {
  return currentLaneGeoJson.features.find((feature) => {
    return laneKeyFromProperties(feature.properties) === String(laneKey);
  });
}

function findRoadFeatureById(roadId) {
  return currentGeoJson.features.find((feature) => {
    return String(feature.properties?.road_id || feature.id) === String(roadId);
  });
}

function findSignalFeatureByKey(signalKey) {
  return currentSignalGeoJson.features.find((feature) => {
    return String(feature.properties?.signal_key || feature.id) === String(signalKey);
  });
}

function findSignalObjectFeatureByKey(objectKey) {
  return currentSignalGeoJson.features.find((feature) => {
    return (
      String(feature.properties?.object_key || feature.id) === String(objectKey) ||
      String(feature.properties?.editor_id || "") === String(objectKey) ||
      String(feature.properties?.object_id || "") === String(objectKey)
    );
  });
}

function resolveSourceFeature(feature) {
  if (!feature) return null;
  if (feature.properties?.feature_type === "signal") {
    return findSignalFeatureByKey(feature.properties?.signal_key || feature.id) || feature;
  }
  if (["signal_object", "environment_object"].includes(feature.properties?.feature_type)) {
    return findSignalObjectFeatureByKey(feature.properties?.object_key || feature.id) || feature;
  }
  if (feature.geometry?.type === "Polygon") {
    const laneKey = laneKeyFromProperties(feature.properties);
    return findLaneFeatureByKey(laneKey) || feature;
  }
  if (feature.geometry?.type === "LineString") {
    return findRoadFeatureById(feature.properties?.road_id || feature.id) || feature;
  }
  return feature;
}

function propertyList(value) {
  if (Array.isArray(value)) return value;
  if (value === undefined || value === null || value === "") return [];
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed;
    } catch (_) {
      return [value];
    }
  }
  return [value];
}

function adjacentLaneFeatures(feature) {
  if (!feature) return [];
  const props = feature.properties || {};
  const adjacent = [];
  for (const laneKey of propertyList(props.predecessor_keys)) {
    const predecessor = findLaneFeatureByKey(laneKey);
    if (predecessor) adjacent.push({ ...predecessor, properties: { ...predecessor.properties, relation: "predecessor" } });
  }
  for (const laneKey of propertyList(props.successor_keys)) {
    const successor = findLaneFeatureByKey(laneKey);
    if (successor) adjacent.push({ ...successor, properties: { ...successor.properties, relation: "successor" } });
  }
  if (adjacent.length === 0 && props.predecessor !== undefined && Number(props.predecessor) !== 0) {
    const predecessor = findLaneFeature(props.road_id, props.lanesection_s0, props.predecessor);
    if (predecessor) adjacent.push({ ...predecessor, properties: { ...predecessor.properties, relation: "predecessor" } });
  }
  if (adjacent.length === 0 && props.successor !== undefined && Number(props.successor) !== 0) {
    const successor = findLaneFeature(props.road_id, props.lanesection_s0, props.successor);
    if (successor) adjacent.push({ ...successor, properties: { ...successor.properties, relation: "successor" } });
  }
  const seen = new Set();
  return adjacent.filter((item) => {
    const key = `${laneKeyFromProperties(item.properties)}:${item.properties?.relation}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Attribute editors store text in form fields, then convert the edited
// text back to the original value type before refreshing the map.
function attributeValueToText(value) {
  if (Array.isArray(value) || (value && typeof value === "object")) {
    return JSON.stringify(value);
  }
  if (value === undefined || value === null) return "";
  return String(value);
}

function parseAttributeValue(rawValue, field) {
  if (typeof rawValue === "boolean") return field.checked;
  if (typeof rawValue === "number") {
    const value = Number(field.value);
    return Number.isFinite(value) ? value : rawValue;
  }
  if (Array.isArray(rawValue) || (rawValue && typeof rawValue === "object")) {
    try {
      return JSON.parse(field.value);
    } catch (_) {
      return rawValue;
    }
  }
  return field.value;
}

// Geometry helpers work in lon/lat because that is what MapLibre draws.
// The Python server converts lon/lat back to OpenDRIVE x/y on save.
function localRect(lon, lat, heading, lengthM, widthM) {
  const halfLength = Math.max(0.2, Number(lengthM || 0.4) * 0.5);
  const halfWidth = Math.max(0.2, Number(widthM || 0.4) * 0.5);
  const latScale = 110540;
  const lonScale = Math.max(1e-9, 111320 * Math.cos((Number(lat) * Math.PI) / 180));
  const along = [Math.cos(heading), Math.sin(heading)];
  const across = [-Math.sin(heading), Math.cos(heading)];
  const toLonLat = (xMeters, yMeters) => [lon + xMeters / lonScale, lat + yMeters / latScale];
  return [
    toLonLat(along[0] * halfLength + across[0] * halfWidth, along[1] * halfLength + across[1] * halfWidth),
    toLonLat(along[0] * halfLength - across[0] * halfWidth, along[1] * halfLength - across[1] * halfWidth),
    toLonLat(-along[0] * halfLength - across[0] * halfWidth, -along[1] * halfLength - across[1] * halfWidth),
    toLonLat(-along[0] * halfLength + across[0] * halfWidth, -along[1] * halfLength + across[1] * halfWidth),
    toLonLat(along[0] * halfLength + across[0] * halfWidth, along[1] * halfLength + across[1] * halfWidth),
  ];
}

function meterBox(lon, lat, sizeM) {
  return localRect(lon, lat, 0, sizeM, sizeM);
}

function polygonCenter(feature) {
  const ring = feature.geometry?.coordinates?.[0] || [];
  const points = ring.length > 1 ? ring.slice(0, -1) : ring;
  if (points.length === 0) return null;
  const totals = points.reduce((acc, coord) => {
    return [acc[0] + Number(coord[0] || 0), acc[1] + Number(coord[1] || 0)];
  }, [0, 0]);
  return [totals[0] / points.length, totals[1] / points.length];
}

function translateCoordinates(coordinates, dLng, dLat) {
  if (!Array.isArray(coordinates)) return coordinates;
  if (typeof coordinates[0] === "number") {
    return [Number(coordinates[0]) + dLng, Number(coordinates[1]) + dLat];
  }
  return coordinates.map((item) => translateCoordinates(item, dLng, dLat));
}

function translateFeature(feature, dLng, dLat) {
  if (!feature?.geometry) return;
  feature.geometry = {
    ...feature.geometry,
    coordinates: translateCoordinates(feature.geometry.coordinates, dLng, dLat),
  };
  const center = feature.geometry.type === "Polygon" ? polygonCenter(feature) : null;
  if (center && ["signal", "signal_object", "environment_object"].includes(feature.properties?.feature_type)) {
    feature.properties.lon = center[0];
    feature.properties.lat = center[1];
  }
}

function markFeatureGeometryEdited(feature, kind = "translated") {
  if (!feature) return;
  feature.geometry_edited = true;
  feature.geometry_edit_kind = kind;
}

function cloneData(value) {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function selectedFeatureKey(feature = selectedFeature) {
  const props = feature?.properties || {};
  if (props.feature_type === "lane") return { type: "lane", key: laneKeyFromProperties(props) };
  if (props.feature_type === "signal") return { type: "signal", key: String(props.signal_key || feature.id) };
  if (props.feature_type === "signal_object") return { type: "signal_object", key: String(props.object_key || feature.id) };
  if (props.feature_type === "environment_object") return { type: "environment_object", key: String(props.object_key || feature.id) };
  if (props.feature_type === "road") return { type: "road", key: String(props.road_id || feature.id) };
  return null;
}

function findFeatureByUndoKey(ref) {
  if (!ref) return null;
  if (ref.type === "lane") return findLaneFeatureByKey(ref.key);
  if (ref.type === "signal") return findSignalFeatureByKey(ref.key);
  if (ref.type === "signal_object") return findSignalObjectFeatureByKey(ref.key);
  if (ref.type === "environment_object") return findSignalObjectFeatureByKey(ref.key);
  if (ref.type === "road") return findRoadFeatureById(ref.key);
  return null;
}

function snapshotEditableState() {
  return {
    lanes: cloneData(currentLaneGeoJson),
    signals: cloneData(currentSignalGeoJson),
    selected: selectedFeatureKey(),
  };
}

function restoreEditableState(snapshot) {
  if (!snapshot) return;
  currentLaneGeoJson = cloneData(snapshot.lanes || emptyFeatureCollection());
  currentSignalGeoJson = cloneData(snapshot.signals || emptyFeatureCollection());
  selectedFeature = findFeatureByUndoKey(snapshot.selected);
  updateSpotlightSummary(selectedFeature);
  renderAttributeEditor(selectedFeature);
  refreshFeatureSources();
}

function undoLastMovement() {
  const snapshot = undoStack.pop();
  if (!snapshot) {
    setStatus("No movement to undo.", true);
    return;
  }
  restoreEditableState(snapshot);
  setStatus("Undid last movement. Save to write the restored position to OpenDRIVE.");
}

// Dragging a lane near another lane endpoint updates predecessor and
// successor links.  It does not invent full OpenDRIVE lane geometry.
function metersBetween(a, b) {
  if (!a || !b) return Number.POSITIVE_INFINITY;
  const lat = ((Number(a[1]) || 0) + (Number(b[1]) || 0)) * 0.5;
  const dx = (Number(a[0]) - Number(b[0])) * 111320 * Math.cos((lat * Math.PI) / 180);
  const dy = (Number(a[1]) - Number(b[1])) * 110540;
  return Math.hypot(dx, dy);
}

function metersPerDegree(lat) {
  return {
    lon: Math.max(1e-9, 111320 * Math.cos((Number(lat) * Math.PI) / 180)),
    lat: 110540,
  };
}

function estimateLaneWidth(feature) {
  const stored = Number(feature?.properties?.width);
  if (Number.isFinite(stored) && stored > 0) return stored;
  const ring = feature?.geometry?.coordinates?.[0] || [];
  const points = ring.length > 1 ? ring.slice(0, -1) : ring;
  if (points.length < 4) return null;
  const half = Math.floor(points.length / 2);
  const outer = points.slice(0, half);
  const inner = points.slice(half).reverse();
  const widths = outer
    .map((point, index) => metersBetween(point, inner[index]))
    .filter((width) => Number.isFinite(width) && width > 0.1)
    .sort((a, b) => a - b);
  return widths.length ? widths[Math.floor(widths.length / 2)] : null;
}

function updateGlobalLaneWidthFromNetwork() {
  const measured = currentLaneGeoJson.features
    .map(estimateLaneWidth)
    .filter((width) => Number.isFinite(width) && width > 0.1)
    .sort((a, b) => a - b);
  const typicalDrivingWidths = currentLaneGeoJson.features
    .filter((feature) => feature.properties?.lane_type === "driving")
    .map(estimateLaneWidth)
    .filter((width) => Number.isFinite(width) && width >= 1.5 && width <= 6.0)
    .sort((a, b) => a - b);
  const widths = typicalDrivingWidths.length ? typicalDrivingWidths : measured;
  const nextWidth = widths.length ? widths[Math.floor(widths.length / 2)] : currentLaneWidth;
  currentLaneWidth = Math.max(0.2, Number(nextWidth) || 3.5);
  globalLaneWidthInput.value = currentLaneWidth.toFixed(2);
}

function laneCenterline(feature) {
  if (feature?.geometry?.type === "LineString") return feature.geometry.coordinates || [];
  const ring = feature?.geometry?.coordinates?.[0] || [];
  const points = ring.length > 1 ? ring.slice(0, -1) : ring;
  if (points.length < 4) return [];
  const half = Math.floor(points.length / 2);
  const outer = points.slice(0, half);
  const inner = points.slice(half).reverse();
  return outer.map((point, index) => {
    const other = inner[index] || point;
    return [(Number(point[0]) + Number(other[0])) * 0.5, (Number(point[1]) + Number(other[1])) * 0.5];
  });
}

function lineToLanePolygon(lineCoordinates, widthMeters = currentLaneWidth) {
  const coordinates = (lineCoordinates || []).filter((coord) => Array.isArray(coord) && coord.length >= 2);
  if (coordinates.length < 2) return null;
  const halfWidth = Math.max(0.1, Number(widthMeters) * 0.5 || 1.75);
  const anchorLat = coordinates.reduce((sum, coord) => sum + Number(coord[1] || 0), 0) / coordinates.length;
  const scale = metersPerDegree(anchorLat);
  const origin = coordinates[0];
  const xy = coordinates.map((coord) => [
    (Number(coord[0]) - Number(origin[0])) * scale.lon,
    (Number(coord[1]) - Number(origin[1])) * scale.lat,
  ]);
  const normals = xy.map((point, index) => {
    const prev = xy[Math.max(0, index - 1)];
    const next = xy[Math.min(xy.length - 1, index + 1)];
    const dx = next[0] - prev[0];
    const dy = next[1] - prev[1];
    const length = Math.hypot(dx, dy) || 1;
    return [-dy / length, dx / length];
  });
  const toLonLat = (point, normal, sign) => [
    Number(origin[0]) + (point[0] + normal[0] * halfWidth * sign) / scale.lon,
    Number(origin[1]) + (point[1] + normal[1] * halfWidth * sign) / scale.lat,
  ];
  const left = xy.map((point, index) => toLonLat(point, normals[index], 1));
  const right = xy.map((point, index) => toLonLat(point, normals[index], -1));
  const ring = [...left, ...right.reverse()];
  ring.push(ring[0]);
  return {
    type: "Polygon",
    coordinates: [ring],
  };
}

function rebuildLaneGeometry(feature, widthMeters = currentLaneWidth) {
  const centerline = laneCenterline(feature);
  const geometry = lineToLanePolygon(centerline, widthMeters);
  if (geometry) feature.geometry = geometry;
}

function applyGlobalLaneWidth() {
  const width = Number(globalLaneWidthInput.value);
  if (!Number.isFinite(width) || width <= 0) {
    setStatus("Enter a positive lane width in meters.", true);
    return;
  }
  currentLaneWidth = width;
  for (const lane of currentLaneGeoJson.features) {
    if (lane.properties?.feature_type !== "lane") continue;
    lane.properties.width = width;
    rebuildLaneGeometry(lane, width);
  }
  refreshFeatureSources();
  if (selectedFeature?.properties?.feature_type === "lane") {
    renderAttributeEditor(selectedFeature);
  }
  setStatus(`Updated all lane widths to ${width.toFixed(2)} m. Save to write lane width records.`);
}

function laneEndpoints(feature) {
  const ring = feature?.geometry?.coordinates?.[0] || [];
  const points = ring.length > 1 ? ring.slice(0, -1) : ring;
  if (points.length < 4) return null;
  const half = Math.floor(points.length / 2);
  const midpoint = (a, b) => [(Number(a[0]) + Number(b[0])) * 0.5, (Number(a[1]) + Number(b[1])) * 0.5];
  return {
    start: midpoint(points[0], points[points.length - 1]),
    end: midpoint(points[Math.max(0, half - 1)], points[Math.min(points.length - 1, half)]),
  };
}

function laneLinkPayload(feature) {
  return {
    id: Number(feature.properties?.lane_id || 0),
    key: laneKeyFromProperties(feature.properties),
  };
}

function setLaneConnection(fromFeature, toFeature) {
  const from = laneLinkPayload(fromFeature);
  const to = laneLinkPayload(toFeature);
  if (!from.id || !to.id || from.key === to.key) return;
  fromFeature.properties.successor = to.id;
  fromFeature.properties.successor_keys = [to.key];
  toFeature.properties.predecessor = from.id;
  toFeature.properties.predecessor_keys = [from.key];
}

function autoConnectDraggedLane(feature, thresholdMeters = 2.5) {
  if (feature?.properties?.feature_type !== "lane") return false;
  const draggedEnds = laneEndpoints(feature);
  if (!draggedEnds) return false;
  let best = null;
  for (const candidate of currentLaneGeoJson.features) {
    if (candidate === feature || candidate.properties?.feature_type !== "lane") continue;
    if (String(candidate.properties?.road_id) !== String(feature.properties?.road_id)) continue;
    const candidateEnds = laneEndpoints(candidate);
    if (!candidateEnds) continue;
    const checks = [
      { distance: metersBetween(draggedEnds.start, candidateEnds.end), kind: "candidate_to_dragged", candidate },
      { distance: metersBetween(draggedEnds.end, candidateEnds.start), kind: "dragged_to_candidate", candidate },
    ];
    for (const check of checks) {
      if (!best || check.distance < best.distance) best = check;
    }
  }
  if (!best || best.distance > thresholdMeters) return false;
  if (best.kind === "candidate_to_dragged") {
    setLaneConnection(best.candidate, feature);
  } else {
    setLaneConnection(feature, best.candidate);
  }
  setStatus(`Connected lanes within ${best.distance.toFixed(2)} m. Save to write predecessor/successor links.`);
  return true;
}

function updateSignalDerivedMapProperties(feature) {
  if (!["signal", "signal_object", "environment_object"].includes(feature.properties?.feature_type)) return;
  const props = feature.properties;
  const base = Math.max(0, Number(props.zOffset ?? props.z ?? 0) || 0);
  const height = Math.max(1, Number(props.height) || 1);
  props.extrusion_base = base;
  props.extrusion_height = base + height;
  if (props.feature_type === "environment_object" && !props.object_color) {
    props.object_color = environmentColorForType(props.environment_type || props.type || props.name);
  }

  const center = polygonCenter(feature);
  if (center && props.feature_type === "signal") {
    feature.geometry.coordinates = [meterBox(center[0], center[1], Math.max(Number(props.width) || 0.6, 0.6))];
  } else if (center && props.feature_type === "signal_object") {
    const length = Math.max(Number(props.length) || Number(props.radius) * 2 || 0.4, 0.4);
    const width = Math.max(Number(props.width) || Number(props.radius) * 2 || 0.4, 0.4);
    feature.geometry.coordinates = [localRect(center[0], center[1], Number(props.map_heading) || 0, length, width)];
  } else if (center && props.feature_type === "environment_object") {
    props.lon = center[0];
    props.lat = center[1];
  }
}

// When ids change, every related key must change too.  Otherwise the map
// would display the new id while save/highlight still referenced the old id.
function replaceArrayValue(value, oldValue, newValue) {
  const items = propertyList(value);
  return items.map((item) => String(item) === String(oldValue) ? newValue : item);
}

function refreshLaneIdentity(feature, oldProps = {}) {
  if (feature.properties?.feature_type !== "lane") return;
  const props = feature.properties;
  const oldKey = oldProps.lane_key || laneKeyFromProperties(oldProps);
  const newKey = `${props.road_id}/${Number(props.lanesection_s0 || 0).toFixed(6)}/${props.lane_id}`;
  const oldLaneId = oldProps.lane_id;
  props.lane_key = newKey;
  feature.id = props.editor_id || newKey;

  for (const lane of currentLaneGeoJson.features) {
    const laneProps = lane.properties || {};
    if (oldKey && laneProps.predecessor_keys !== undefined) {
      laneProps.predecessor_keys = replaceArrayValue(laneProps.predecessor_keys, oldKey, newKey);
    }
    if (oldKey && laneProps.successor_keys !== undefined) {
      laneProps.successor_keys = replaceArrayValue(laneProps.successor_keys, oldKey, newKey);
    }
    if (
      oldLaneId !== undefined &&
      String(laneProps.road_id) === String(props.road_id) &&
      String(laneProps.predecessor) === String(oldLaneId)
    ) {
      laneProps.predecessor = props.lane_id;
    }
    if (
      oldLaneId !== undefined &&
      String(laneProps.road_id) === String(props.road_id) &&
      String(laneProps.successor) === String(oldLaneId)
    ) {
      laneProps.successor = props.lane_id;
    }
  }
}

function cascadeRoadIdentity(feature, oldProps = {}) {
  if (feature.properties?.feature_type !== "road") return;
  const props = feature.properties;
  const oldRoadId = oldProps.road_id || oldProps.id || feature.id;
  const newRoadId = props.road_id || feature.id;
  feature.id = newRoadId;
  props.road_id = newRoadId;

  for (const lane of currentLaneGeoJson.features) {
    if (String(lane.properties?.road_id) !== String(oldRoadId)) continue;
    lane.properties.road_id = newRoadId;
    if (props.name !== undefined) lane.properties.road_name = props.name;
    if (props.junction !== undefined) lane.properties.junction = props.junction;
    refreshLaneIdentity(lane, { ...lane.properties, road_id: oldRoadId });
  }
  for (const signal of currentSignalGeoJson.features) {
    const signalProps = signal.properties || {};
    if (String(signalProps.road_id) !== String(oldRoadId)) continue;
    signalProps.road_id = newRoadId;
    if (props.name !== undefined) signalProps.road_name = props.name;
    if (signalProps.feature_type === "signal") {
      signalProps.signal_key = `${newRoadId}/${signalProps.signal_id}`;
      signal.id = signalProps.signal_key;
    } else if (["signal_object", "environment_object"].includes(signalProps.feature_type)) {
      signalProps.object_key = `${newRoadId}/${signalProps.object_id}`;
      signal.id = signalProps.editor_id || signalProps.object_key;
    }
  }
}

function cascadeSignalIdentity(feature) {
  const props = feature.properties || {};
  if (props.feature_type === "signal") {
    props.signal_key = `${props.road_id}/${props.signal_id}`;
    feature.id = props.signal_key;
  } else if (["signal_object", "environment_object"].includes(props.feature_type)) {
    props.object_key = `${props.road_id}/${props.object_id}`;
    feature.id = props.editor_id || props.object_key;
  }
}

function applyAttributeEdit(feature, key, nextValue, oldProps) {
  feature.properties[key] = nextValue;
  if (feature.properties.feature_type === "road") {
    cascadeRoadIdentity(feature, oldProps);
  } else if (feature.properties.feature_type === "lane") {
    refreshLaneIdentity(feature, oldProps);
    if (key === "width") {
      currentLaneWidth = Math.max(0.2, Number(nextValue) || currentLaneWidth);
      globalLaneWidthInput.value = currentLaneWidth.toFixed(2);
      rebuildLaneGeometry(feature, currentLaneWidth);
    }
  } else if (["signal", "signal_object", "environment_object"].includes(feature.properties.feature_type)) {
    if (feature.properties.feature_type === "environment_object" && ["environment_type", "type", "name"].includes(key)) {
      feature.properties.object_color = environmentColorForType(nextValue);
    }
    cascadeSignalIdentity(feature);
    updateSignalDerivedMapProperties(feature);
  }
}

// Creation and deletion operate on the in-memory GeoJSON first.  The XML
// file is written only when the user clicks Save.
function shiftedPolygon(feature, dx = 0.000015, dy = 0.000015) {
  if (feature.geometry?.type !== "Polygon") return feature.geometry;
  return {
    type: "Polygon",
    coordinates: feature.geometry.coordinates.map((ring) => {
      return ring.map((coord) => [Number(coord[0]) + dx, Number(coord[1]) + dy]);
    }),
  };
}

function nextLaneId(props) {
  const sign = Number(props.lane_id) < 0 ? -1 : 1;
  const section = Number(props.lanesection_s0 || 0);
  const ids = currentLaneGeoJson.features
    .map((feature) => feature.properties || {})
    .filter((item) => {
      return (
        String(item.road_id) === String(props.road_id) &&
        Math.abs(Number(item.lanesection_s0 || 0) - section) < 1e-6 &&
        Math.sign(Number(item.lane_id || 0)) === sign
      );
    })
    .map((item) => Math.abs(Number(item.lane_id || 0)));
  return sign * (Math.max(0, ...ids) + 1);
}

function generatedEditorId(prefix) {
  generatedFeatureCounter += 1;
  return `${prefix}_${Date.now()}_${generatedFeatureCounter}`;
}

function nearestLaneForGeometry(geometry) {
  const coordinates = geometry?.type === "LineString" ? geometry.coordinates : laneCenterline({ geometry });
  if (!coordinates || coordinates.length === 0) return null;
  const probes = [coordinates[0], coordinates[coordinates.length - 1], coordinates[Math.floor(coordinates.length / 2)]];
  let best = null;
  for (const lane of currentLaneGeoJson.features) {
    const center = polygonCenter(lane);
    const endpoints = laneEndpoints(lane);
    const candidates = [center, endpoints?.start, endpoints?.end].filter(Boolean);
    for (const probe of probes) {
      for (const candidate of candidates) {
        const distance = metersBetween(probe, candidate);
        if (!best || distance < best.distance) best = { lane, distance };
      }
    }
  }
  return best?.lane || null;
}

function defaultLaneContext(geometry) {
  const selectedLane = selectedFeature?.properties?.feature_type === "lane" ? selectedFeature : null;
  const nearbyLane = selectedLane || nearestLaneForGeometry(geometry);
  const selectedRoad = selectedFeature?.properties?.feature_type === "road" ? selectedFeature : null;
  if (nearbyLane) return { ...nearbyLane.properties };
  if (selectedRoad) {
    return {
      road_id: selectedRoad.properties?.road_id || selectedRoad.id,
      road_name: selectedRoad.properties?.name || "",
      junction: selectedRoad.properties?.junction ?? "-1",
      lane_id: -1,
      lane_type: "driving",
      level: false,
      lanesection_s0: 0,
    };
  }
  const firstLane = currentLaneGeoJson.features.find((feature) => feature.properties?.feature_type === "lane");
  return firstLane ? { ...firstLane.properties } : null;
}

function addLaneFeatureFromGeometry(geometry, source = "maplibre-gl-geo-editor") {
  const context = defaultLaneContext(geometry);
  if (!context?.road_id) {
    setStatus("Open a network or select a road/lane before adding lane geometry.", true);
    return null;
  }
  const laneId = nextLaneId(context);
  const laneWidth = Math.max(0.2, Number(context.width) || currentLaneWidth);
  const geometryPrefix = geometry.type === "LineString" ? "odr" : "odr_polygon";
  const generatedId = generatedEditorId(geometryPrefix);
  const props = {
    ...context,
    feature_type: "lane",
    editor_id: generatedId,
    generated_from: geometry.type,
    lane_id: laneId,
    lane_key: `${context.road_id}/${Number(context.lanesection_s0 || 0).toFixed(6)}/${laneId}`,
    lane_type: context.lane_type || "driving",
    level: context.level ?? false,
    predecessor: 0,
    successor: 0,
    predecessor_keys: [],
    successor_keys: [],
    width: laneWidth,
    source,
  };
  const laneGeometry = geometry.type === "LineString"
    ? lineToLanePolygon(geometry.coordinates, laneWidth)
    : geometry;
  if (!laneGeometry) {
    setStatus("Draw at least two points before creating a lane.", true);
    return null;
  }
  const feature = {
    type: "Feature",
    id: generatedId,
    properties: props,
    geometry: laneGeometry,
  };
  if (geometry.type === "Polygon") {
    rebuildLaneGeometry(feature, laneWidth);
  }
  currentLaneGeoJson.features.push(feature);
  const connected = autoConnectDraggedLane(feature, Math.max(2.5, currentLaneWidth));
  loadIntoEditor(currentGeoJson);
  setSpotlightFeature(feature);
  refreshFeatureSources();
  setStatus(
    `Added lane ${laneId} on road ${props.road_id}${connected ? " and connected nearby endpoints" : ""}. Save to write it to OpenDRIVE.`
  );
  return feature;
}

function addLaneFromSelection() {
  const base = selectedFeature?.properties?.feature_type === "lane" ? selectedFeature : null;
  if (!base) {
    setStatus("Select a lane before adding a lane.", true);
    return;
  }
  const props = { ...base.properties };
  const generatedId = generatedEditorId("odr_button_lane");
  props.editor_id = generatedId;
  props.generated_from = "Add Lane";
  props.lane_id = nextLaneId(props);
  props.lane_key = `${props.road_id}/${Number(props.lanesection_s0 || 0).toFixed(6)}/${props.lane_id}`;
  props.predecessor = 0;
  props.successor = 0;
  props.predecessor_keys = [];
  props.successor_keys = [];
  props.width = currentLaneWidth;
  props.source = "maplibre-gl-geo-editor";
  const feature = {
    ...base,
    id: generatedId,
    properties: props,
    geometry: shiftedPolygon(base),
  };
  rebuildLaneGeometry(feature, currentLaneWidth);
  currentLaneGeoJson.features.push(feature);
  autoConnectDraggedLane(feature, Math.max(2.5, currentLaneWidth));
  setSpotlightFeature(feature);
  refreshFeatureSources();
  setStatus(`Added lane ${props.lane_id} on road ${props.road_id}. Save to write it to OpenDRIVE.`);
}

function removeFeatureFromCollection(collection, predicate) {
  const before = collection.features.length;
  collection.features = collection.features.filter((feature) => !predicate(feature));
  return collection.features.length !== before;
}

function removeArrayValue(value, deletedValue) {
  const items = propertyList(value).filter((item) => String(item) !== String(deletedValue));
  if (Array.isArray(value)) return items;
  return items.length > 0 ? items : [];
}

function clearDeletedLaneReferences(deletedProps) {
  const deletedKey = laneKeyFromProperties(deletedProps);
  const deletedLaneId = deletedProps.lane_id;
  let changed = 0;
  for (const lane of currentLaneGeoJson.features) {
    const props = lane.properties || {};
    if (deletedKey && props.predecessor_keys !== undefined) {
      const next = removeArrayValue(props.predecessor_keys, deletedKey);
      if (JSON.stringify(next) !== JSON.stringify(propertyList(props.predecessor_keys))) {
        props.predecessor_keys = next;
        changed += 1;
      }
    }
    if (deletedKey && props.successor_keys !== undefined) {
      const next = removeArrayValue(props.successor_keys, deletedKey);
      if (JSON.stringify(next) !== JSON.stringify(propertyList(props.successor_keys))) {
        props.successor_keys = next;
        changed += 1;
      }
    }
    const sameRoad = String(props.road_id) === String(deletedProps.road_id);
    if (sameRoad && String(props.predecessor) === String(deletedLaneId)) {
      props.predecessor = 0;
      changed += 1;
    }
    if (sameRoad && String(props.successor) === String(deletedLaneId)) {
      props.successor = 0;
      changed += 1;
    }
  }
  if (copiedLaneLink && String(copiedLaneLink.lane_key) === String(deletedKey)) {
    copiedLaneLink = null;
  }
  return changed;
}

function signalObjectMatches(feature, key) {
  const props = feature.properties || {};
  return (
    String(props.object_key || feature.id) === String(key) ||
    String(props.editor_id || "") === String(key) ||
    String(props.object_id || "") === String(key)
  );
}

function deleteSelectedFeature() {
  const feature = selectedFeature;
  const props = feature?.properties || {};
  let removed = false;
  let updatedLinks = 0;
  if (props.feature_type === "lane") {
    const key = laneKeyFromProperties(props);
    updatedLinks = clearDeletedLaneReferences(props);
    removed = removeFeatureFromCollection(currentLaneGeoJson, (item) => laneKeyFromProperties(item.properties) === key);
  } else if (props.feature_type === "road") {
    const roadId = props.road_id || feature.id;
    removed = removeFeatureFromCollection(currentGeoJson, (item) => String(item.properties?.road_id || item.id) === String(roadId));
    removeFeatureFromCollection(currentLaneGeoJson, (item) => String(item.properties?.road_id) === String(roadId));
    removeFeatureFromCollection(currentSignalGeoJson, (item) => String(item.properties?.road_id) === String(roadId));
  } else if (props.feature_type === "signal") {
    const key = props.signal_key || feature.id;
    removed = removeFeatureFromCollection(currentSignalGeoJson, (item) => String(item.properties?.signal_key || item.id) === String(key));
  } else if (props.feature_type === "signal_object") {
    const key = props.object_key || props.editor_id || props.object_id || feature.id;
    removed = removeFeatureFromCollection(currentSignalGeoJson, (item) => signalObjectMatches(item, key));
  } else if (props.feature_type === "environment_object") {
    const key = props.object_key || props.editor_id || props.object_id || feature.id;
    removed = removeFeatureFromCollection(currentSignalGeoJson, (item) => signalObjectMatches(item, key));
  }
  if (!removed) {
    setStatus("Select a road, lane, signal, post, mast arm, or environment object before deleting.", true);
    return;
  }
  loadIntoEditor(currentGeoJson);
  setSpotlightFeature(null);
  refreshFeatureSources();
  setStatus(
    updatedLinks > 0
      ? `Deleted selected feature and cleared ${updatedLinks} lane link reference(s). Save to write the deletion to OpenDRIVE.`
      : "Deleted selected feature. Save to write the deletion to OpenDRIVE."
  );
}

function copySelectedLaneLink() {
  if (selectedFeature?.properties?.feature_type !== "lane") {
    setStatus("Select a lane to copy its lane key.", true);
    return;
  }
  const laneKey = laneKeyFromProperties(selectedFeature.properties);
  copiedLaneLink = { lane_id: Number(selectedFeature.properties.lane_id), lane_key: laneKey };
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(laneKey).catch(() => {});
  }
  setStatus(`Copied selected lane key: ${laneKey}. Paste it into predecessor_keys or successor_keys in the editable fields.`);
}

function draggableFeatureFromEvent(event) {
  const feature = resolveSourceFeature(event.features?.[0]);
  if (!feature || feature.geometry?.type !== "Polygon") return null;
  if (!["lane", "signal", "signal_object", "environment_object"].includes(feature.properties?.feature_type)) return null;
  return feature;
}

// Direct map dragging is intentionally simple: move the selected polygon,
// keep an undo snapshot, and let save project the final lon/lat to s/t.
function startFeatureDrag(event) {
  const feature = draggableFeatureFromEvent(event);
  if (!feature) return;
  event.preventDefault();
  map.dragPan.disable();
  map.getCanvas().style.cursor = "grabbing";
  dragState = {
    feature,
    before: snapshotEditableState(),
    moved: false,
    lastLngLat: event.lngLat,
  };
}

function moveFeatureDrag(event) {
  if (!dragState) return;
  const dLng = event.lngLat.lng - dragState.lastLngLat.lng;
  const dLat = event.lngLat.lat - dragState.lastLngLat.lat;
  if (Math.abs(dLng) > 0 || Math.abs(dLat) > 0) dragState.moved = true;
  translateFeature(dragState.feature, dLng, dLat);
  dragState.lastLngLat = event.lngLat;
  refreshFeatureSources();
}

function endFeatureDrag() {
  if (!dragState) return;
  const feature = dragState.feature;
  const before = dragState.before;
  const moved = dragState.moved;
  dragState = null;
  map.dragPan.enable();
  map.getCanvas().style.cursor = "";
  if (moved) {
    undoStack.push(before);
    if (undoStack.length > 50) undoStack.shift();
    markFeatureGeometryEdited(feature);
  }
  const connected = autoConnectDraggedLane(feature);
  updateSignalDerivedMapProperties(feature);
  if (selectedFeature === feature) {
    updateSpotlightSummary(feature);
    renderAttributeEditor(feature);
  }
  refreshFeatureSources();
  if (!connected && feature.properties?.feature_type === "lane") {
    setStatus("Moved lane. No nearby lane endpoint was close enough to auto-connect.");
  } else if (feature.properties?.feature_type !== "lane") {
    setStatus("Moved object. Save to write its updated position to OpenDRIVE.");
  }
}

function selectedPlacement() {
  const feature = selectedFeature;
  const props = feature?.properties || {};
  if (!feature) return null;
  const center = feature.geometry?.type === "Polygon" ? polygonCenter(feature) : null;
  const lineCoords = feature.geometry?.type === "LineString" ? feature.geometry.coordinates : null;
  const coord = center || (lineCoords && lineCoords[Math.floor(lineCoords.length / 2)]);
  if (!coord) return null;
  return {
    lon: coord[0],
    lat: coord[1],
    road_id: props.road_id || props.id || props.road_id,
    s: Number(props.s ?? props.lanesection_s0 ?? 0),
    t: Number(props.t ?? 0),
  };
}

function polygonDimensionsMeters(geometry) {
  const ring = geometry?.coordinates?.[0] || [];
  const points = ring.length > 1 ? ring.slice(0, -1) : ring;
  if (points.length === 0) return { length: 5, width: 5 };
  const lons = points.map((coord) => Number(coord[0]) || 0);
  const lats = points.map((coord) => Number(coord[1]) || 0);
  const lat = lats.reduce((sum, value) => sum + value, 0) / lats.length;
  const scale = metersPerDegree(lat);
  return {
    length: Math.max(0.5, (Math.max(...lons) - Math.min(...lons)) * scale.lon),
    width: Math.max(0.5, (Math.max(...lats) - Math.min(...lats)) * scale.lat),
  };
}

function environmentColorForType(type) {
  const normalized = String(type || "").toLowerCase();
  if (normalized.includes("tree")) return "#16784f";
  if (normalized.includes("apartment")) return "#667085";
  if (normalized.includes("building")) return "#8a6f4d";
  if (normalized.includes("parking")) return "#475467";
  if (normalized.includes("park")) return "#2b8f5e";
  return "#2e90fa";
}

function defaultPolygonEnvironment(dimensions) {
  const footprint = Math.max(Number(dimensions.length) || 0, Number(dimensions.width) || 0);
  if (footprint >= 22) {
    return { name: "Apartment", type: "apartment", color: environmentColorForType("apartment"), height: Math.min(40, footprint * 0.9) };
  }
  if (footprint <= 4) {
    return { name: "Tree", type: "tree", color: environmentColorForType("tree"), height: 10 };
  }
  return { name: "Building", type: "building", color: environmentColorForType("building"), height: Math.max(6, Math.min(28, footprint * 0.8 || 8)) };
}

function normalizedPolygonGeometry(geometry) {
  const polygonCoordinates = geometry?.type === "MultiPolygon"
    ? geometry.coordinates?.[0]
    : geometry?.coordinates;
  if (!["Polygon", "MultiPolygon"].includes(geometry?.type)) return null;
  const ring = (polygonCoordinates?.[0] || [])
    .filter((coord) => Array.isArray(coord) && coord.length >= 2)
    .map((coord) => [Number(coord[0]), Number(coord[1])])
    .filter((coord) => Number.isFinite(coord[0]) && Number.isFinite(coord[1]));
  if (ring.length < 3) return null;
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) {
    ring.push([...first]);
  }
  return {
    type: "Polygon",
    coordinates: [ring],
  };
}

function editorFeatureKey(feature) {
  const geometry = feature?.geometry || {};
  return `${feature?.id || ""}:${geometry.type || ""}:${JSON.stringify(geometry.coordinates || [])}`;
}

function addEnvironmentObjectFromPolygon(geometry) {
  geometry = normalizedPolygonGeometry(geometry);
  if (!geometry) {
    setStatus("Draw a valid polygon before creating an environment object.", true);
    return null;
  }
  const context = defaultLaneContext(geometry);
  if (!context?.road_id) {
    setStatus("Open a network or select a road/lane before adding environment geometry.", true);
    return null;
  }
  const center = polygonCenter({ geometry });
  if (!center) {
    setStatus("Draw a closed polygon before creating an environment object.", true);
    return null;
  }
  const generatedId = generatedEditorId("odr_polygon_environment");
  const dimensions = polygonDimensionsMeters(geometry);
  const environment = defaultPolygonEnvironment(dimensions);
  const props = {
    feature_type: "environment_object",
    editor_id: generatedId,
    generated_from: "Polygon",
    object_key: `${context.road_id}/${generatedId}`,
    object_id: generatedId,
    road_id: context.road_id,
    road_name: context.road_name || "",
    name: environment.name,
    environment_type: environment.type,
    lon: center[0],
    lat: center[1],
    s: Number(context.lanesection_s0 || 0),
    t: 0,
    zOffset: 0,
    length: dimensions.length,
    width: dimensions.width,
    radius: 0,
    height: environment.height,
    visual_scale: 1,
    object_color: environment.color,
    hdg: 0,
    map_heading: 0,
    pitch: 0,
    roll: 0,
    orientation: "+",
    type: environment.type,
    subtype: "",
    dynamic: false,
    source: "maplibre-gl-geo-editor",
  };
  props.extrusion_base = props.zOffset;
  props.extrusion_height = props.zOffset + props.height;
  const feature = {
    type: "Feature",
    id: generatedId,
    properties: props,
    geometry: cloneData(geometry),
  };
  currentSignalGeoJson.features.push(feature);
  loadIntoEditor(currentGeoJson);
  setSpotlightFeature(feature);
  refreshFeatureSources();
  setStatus(`Added environment object ${generatedId}. Edit name/type/height in OpenDrive 3D Viewer, then save to write it to OpenDRIVE.`);
  return feature;
}

function defaultObjectContext(geometry) {
  const context = defaultLaneContext(geometry);
  if (context?.road_id) return context;
  const lane = currentLaneGeoJson.features[0];
  if (lane?.properties?.road_id) return { ...lane.properties };
  const road = currentGeoJson.features[0];
  if (road?.properties?.road_id || road?.id) {
    return {
      road_id: road.properties?.road_id || road.id,
      road_name: road.properties?.name || "",
      lanesection_s0: 0,
    };
  }
  return null;
}

function addObjectDefinitionAtLngLat(definition, lngLat) {
  const pointGeometry = { type: "Point", coordinates: [lngLat.lng, lngLat.lat] };
  const context = defaultObjectContext(pointGeometry);
  if (!context?.road_id) {
    setStatus("Open a network or select a road/lane before placing a 3D object.", true);
    return null;
  }
  if (definition.signal_detail_kind) {
    addSignalDetail(definition.signal_detail_kind, {
      lon: lngLat.lng,
      lat: lngLat.lat,
      road_id: context.road_id,
      s: Number(context.lanesection_s0 || 0),
      t: 0,
    });
    return selectedFeature;
  }
  const generatedId = generatedEditorId(`odr_${definition.id}`);
  const props = {
    feature_type: "environment_object",
    editor_id: generatedId,
    generated_from: "Object Palette",
    object_key: `${context.road_id}/${generatedId}`,
    object_id: generatedId,
    object_role: "city_transportation",
    road_id: context.road_id,
    road_name: context.road_name || "",
    name: definition.name,
    environment_type: definition.type,
    lon: lngLat.lng,
    lat: lngLat.lat,
    s: Number(context.lanesection_s0 || 0),
    t: 0,
    zOffset: Number(definition.zOffset || 0),
    length: Number(definition.length || 1),
    width: Number(definition.width || 1),
    radius: 0,
    height: Number(definition.height || 1),
    visual_scale: Number(definition.visual_scale || 1),
    object_color: definition.object_color || environmentColorForType(definition.type),
    hdg: 0,
    map_heading: 0,
    pitch: 0,
    roll: 0,
    orientation: "+",
    type: definition.type,
    subtype: "",
    dynamic: false,
    source: "maplibre-gl-geo-editor",
  };
  props.extrusion_base = props.zOffset;
  props.extrusion_height = props.zOffset + props.height;
  const feature = {
    type: "Feature",
    id: generatedId,
    properties: props,
    geometry: {
      type: "Polygon",
      coordinates: [localRect(lngLat.lng, lngLat.lat, 0, props.length, props.width)],
    },
  };
  currentSignalGeoJson.features.push(feature);
  setSpotlightFeature(feature);
  refreshFeatureSources();
  setStatus(`Added ${definition.label}. Save to write it to OpenDRIVE.`);
  return feature;
}

function renderObjectPalette() {
  objectPaletteGrid.replaceChildren();
  for (const definition of objectDefinitions) {
    const button = document.createElement("button");
    button.type = "button";
    button.title = definition.label;
    button.setAttribute("aria-label", definition.label);
    button.className = armedObjectDefinition?.id === definition.id ? "active" : "";
    button.innerHTML = `<i class="fa ${definition.icon}" aria-hidden="true"></i>`;
    button.style.color = definition.object_color || "#111827";
    button.addEventListener("click", () => {
      armedObjectDefinition = definition;
      renderObjectPalette();
      setStatus(`Click the map to place ${definition.label}.`);
    });
    objectPaletteGrid.appendChild(button);
  }
}

function setObjectPaletteOpen(open, anchorElement = null) {
  objectPalette.classList.toggle("open", open);
  if (open && anchorElement) {
    const mainViewRect = mainView.getBoundingClientRect();
    const rect = anchorElement.getBoundingClientRect();
    const left = rect.left - mainViewRect.left - 260;
    const top = rect.top - mainViewRect.top;
    objectPalette.style.left = `${Math.max(8, Math.min(mainViewRect.width - 280, left))}px`;
    objectPalette.style.top = `${Math.max(8, Math.min(mainViewRect.height - 260, top))}px`;
    objectPalette.style.right = "auto";
  }
}

function maybeSelectToolElement(target) {
  const button = target.closest?.("button, [role='button'], .maplibregl-ctrl button, .maplibregl-ctrl-group button");
  if (!button) return null;
  if (!button.closest(".maplibregl-ctrl, .maplibregl-ctrl-group")) return null;
  const label = `${button.title || ""} ${button.getAttribute("aria-label") || ""} ${button.textContent || ""} ${button.className || ""}`.toLowerCase();
  return label.includes("select") ? button : null;
}

function hideGeoEditorToolbarButtons() {
  const hiddenTools = ["copy", "split", "simplify", "undo", "redo"];
  for (const button of document.querySelectorAll(".geo-editor-toolbar button")) {
    const label = `${button.title || ""} ${button.getAttribute("aria-label") || ""} ${button.textContent || ""} ${button.className || ""}`.toLowerCase();
    if (hiddenTools.some((tool) => label.includes(tool))) {
      button.style.display = "none";
    }
  }
}

function handleEditorCreatedFeature(feature) {
  if (!feature?.geometry) return false;
  if (feature.properties?.feature_type) return false;
  const key = editorFeatureKey(feature);
  if (processedEditorFeatureKeys.has(key)) return true;
  if (currentLaneGeoJson.features.length > 0 && feature.geometry.type === "LineString") {
    processedEditorFeatureKeys.add(key);
    addLaneFeatureFromGeometry(feature.geometry);
    return true;
  }
  if (
    currentLaneGeoJson.features.length > 0 &&
    ["Polygon", "MultiPolygon"].includes(feature.geometry.type)
  ) {
    processedEditorFeatureKeys.add(key);
    addEnvironmentObjectFromPolygon(feature.geometry);
    return true;
  }
  if (["Polygon", "MultiPolygon"].includes(feature.geometry.type)) {
    processedEditorFeatureKeys.add(key);
    setStatus("Open an OpenDRIVE network before adding environment polygon geometry.", true);
    loadIntoEditor(currentGeoJson);
    return true;
  }
  return false;
}

function extractEditorFeature(event) {
  return event?.feature || event?.features?.[0] || event?.geojson || event?.detail?.feature || null;
}

function processEditorGeneratedFeatures() {
  if (!geoEditor || typeof geoEditor.getAllFeatureCollection !== "function") return false;
  const collection = geoEditor.getAllFeatureCollection();
  const features = collection?.features || [];
  let handled = false;
  for (const feature of features) {
    if (handleEditorCreatedFeature(feature)) handled = true;
  }
  if (handled) loadIntoEditor(currentGeoJson);
  return handled;
}

function armSignalDetailPlacement(kind) {
  pendingSignalDetailKind = kind;
  const label = kind === "mastarm" ? "mast arm" : kind;
  setStatus(`Click a lane to place the ${label}.`);
}

function nearestMastArmPlacement(placement, thresholdMeters = 8) {
  let best = null;
  for (const feature of currentSignalGeoJson.features) {
    const props = feature.properties || {};
    if (props.feature_type !== "signal_object" || props.object_role !== "mastarm") continue;
    if (String(props.road_id) !== String(placement.road_id)) continue;
    const center = polygonCenter(feature);
    if (!center) continue;
    const distance = metersBetween([placement.lon, placement.lat], center);
    if (distance > thresholdMeters) continue;
    if (!best || distance < best.distance) {
      best = { feature, props, center, distance };
    }
  }
  if (!best) return null;
  return {
    ...placement,
    lon: best.center[0],
    lat: best.center[1],
    mastarm_zOffset: Number(best.props.zOffset || 0),
    mastarm_height: Number(best.props.height || 0),
  };
}

function addSignalDetail(kind, placementOverride = null) {
  const placement = placementOverride || selectedPlacement();
  if (!placement?.road_id) {
    setStatus("Click a lane before adding signal detail.", true);
    return;
  }
  const id = `new_${kind}_${Date.now()}`;
  if (kind === "signal") {
    const mastArmPlacement = nearestMastArmPlacement(placement) || placement;
    const signalHeight = 1;
    const mastArmCenterZ = Number.isFinite(mastArmPlacement.mastarm_zOffset)
      ? mastArmPlacement.mastarm_zOffset + Math.max(0, Number(mastArmPlacement.mastarm_height || 0)) * 0.5
      : 8.6 + 1.3 * 0.5;
    const signalZOffset = Math.max(0, mastArmCenterZ - signalHeight * 0.5);
    const props = {
      feature_type: "signal",
      signal_key: `${placement.road_id}/${id}`,
      signal_id: id,
      road_id: placement.road_id,
      name: "User_Signal_Head",
      s: placement.s,
      t: placement.t,
      zOffset: signalZOffset,
      value: -1,
      height: signalHeight,
      width: 0.6,
      hOffset: 0,
      pitch: 0,
      roll: 0,
      orientation: "+",
      country: "OpenDRIVE",
      type: "1000001",
      subtype: "-1",
      unit: "",
      text: "",
      dynamic: true,
      source: "maplibre-gl-geo-editor",
    };
    props.extrusion_base = props.zOffset;
    props.extrusion_height = props.zOffset + props.height;
    const feature = {
      type: "Feature",
      id: props.signal_key,
      properties: props,
      geometry: { type: "Polygon", coordinates: [meterBox(mastArmPlacement.lon, mastArmPlacement.lat, props.width)] },
    };
    currentSignalGeoJson.features.push(feature);
    setSpotlightFeature(feature);
  } else {
    const isMastArm = kind === "mastarm";
    const props = {
      feature_type: "signal_object",
      object_role: isMastArm ? "mastarm" : "post",
      object_key: `${placement.road_id}/${id}`,
      object_id: id,
      road_id: placement.road_id,
      name: isMastArm ? "Signal_MastArm_15ft" : "Signal_Post_30ft",
      s: placement.s,
      t: placement.t,
      zOffset: isMastArm ? 8.6 : 0,
      length: isMastArm ? 0.25 : 0.55,
      width: isMastArm ? 4.7 : 0.55,
      radius: 0,
      height: isMastArm ? 1.3 : 9.7,
      hdg: 0,
      map_heading: 0,
      pitch: 0,
      roll: 0,
      orientation: "+",
      type: "-1",
      subtype: "",
      dynamic: false,
      source: "maplibre-gl-geo-editor",
    };
    props.extrusion_base = props.zOffset;
    props.extrusion_height = props.zOffset + props.height;
    const feature = {
      type: "Feature",
      id: props.object_key,
      properties: props,
      geometry: { type: "Polygon", coordinates: [localRect(placement.lon, placement.lat, 0, props.length, props.width)] },
    };
    currentSignalGeoJson.features.push(feature);
    setSpotlightFeature(feature);
  }
  refreshFeatureSources();
  setStatus(`Added ${kind}. Save to write it to OpenDRIVE.`);
}

// Push current in-memory data into MapLibre sources after edits, undo,
// save reloads, or basemap style changes.
function refreshFeatureSources() {
  if (map.getSource("opendrive-lanes")) {
    map.getSource("opendrive-lanes").setData(currentLaneGeoJson);
  }
  refreshLaneDirectionSource();
  if (map.getSource("opendrive-signals")) {
    map.getSource("opendrive-signals").setData(currentSignalGeoJson);
  }
  if (map.getSource("opendrive-roads")) {
    map.getSource("opendrive-roads").setData(currentGeoJson);
  }
  if (selectedFeature) {
    setLaneNetworkHighlight(selectedFeature);
    const source = map.getSource("opendrive-spotlight");
    if (source) {
      source.setData({
        type: "FeatureCollection",
        features: [selectedFeature],
      });
    }
  }
}

function renderAttributeEditor(feature) {
  attributeFields.replaceChildren();
  if (!feature || !feature.properties) {
    const empty = document.createElement("span");
    empty.textContent = "No selected data";
    empty.style.color = "#667085";
    attributeFields.appendChild(empty);
    return;
  }

  for (const key of Object.keys(feature.properties).sort()) {
    const value = feature.properties[key];
    const row = document.createElement("div");
    row.className = "attribute-row";
    const label = document.createElement("label");
    label.textContent = key;
    label.htmlFor = `attr_${key}`;

    let field = null;
    if (typeof value === "boolean") {
      field = document.createElement("input");
      field.type = "checkbox";
      field.checked = value;
    } else if (typeof value === "number") {
      field = document.createElement("input");
      field.type = "number";
      field.step = "any";
      field.value = String(value);
    } else if (Array.isArray(value) || (value && typeof value === "object")) {
      field = document.createElement("textarea");
      field.value = attributeValueToText(value);
    } else {
      field = document.createElement("input");
      field.type = "text";
      field.value = attributeValueToText(value);
    }

    field.id = `attr_${key}`;
    field.dataset.attribute = key;
    field.addEventListener("change", () => {
      const current = feature.properties[key];
      const oldProps = { ...feature.properties };
      const scrollTop = attributeFields.scrollTop;
      applyAttributeEdit(feature, key, parseAttributeValue(current, field), oldProps);
      selectedFeature = resolveSourceFeature(feature);
      updateSpotlightSummary(selectedFeature);
      renderAttributeEditor(selectedFeature);
      attributeFields.scrollTop = scrollTop;
      refreshFeatureSources();
    });
    row.appendChild(label);
    row.appendChild(field);
    attributeFields.appendChild(row);
  }
}

// The panel previously had a duplicate top summary.  Keep this no-op so
// older event flow can still call it without special cases.
function updateSpotlightSummary(feature) {
}

// Only the selected lane and its actual predecessor/successor lanes are
// highlighted.  Nearby or same-road lanes are not highlighted by default.
function setLaneNetworkHighlight(feature) {
  const selectedSource = map.getSource("opendrive-lane-selected");
  const adjacentSource = map.getSource("opendrive-lane-adjacent");
  if (!feature || feature.geometry?.type !== "Polygon" || feature.properties?.feature_type !== "lane") {
    if (selectedSource) selectedSource.setData(emptyFeatureCollection());
    if (adjacentSource) adjacentSource.setData(emptyFeatureCollection());
    return;
  }
  if (selectedSource) {
    selectedSource.setData({
      type: "FeatureCollection",
      features: [feature],
    });
  }
  if (adjacentSource) {
    adjacentSource.setData({
      type: "FeatureCollection",
      features: adjacentLaneFeatures(feature),
    });
  }
}

function setSpotlightFeature(feature) {
  feature = resolveSourceFeature(feature);
  selectedFeature = feature;
  const source = map.getSource("opendrive-spotlight");
  if (!feature || !["LineString", "Polygon"].includes(feature.geometry?.type)) {
    if (source) source.setData(emptyFeatureCollection());
    updateSpotlightSummary(null);
    renderAttributeEditor(null);
    setLaneNetworkHighlight(null);
    return;
  }

  updateSpotlightSummary(feature);
  renderAttributeEditor(feature);
  if (source) {
    source.setData({
      type: "FeatureCollection",
      features: [feature],
    });
  }
  setLaneNetworkHighlight(feature);
}

function featureIdentity(feature) {
  const ref = selectedFeatureKey(resolveSourceFeature(feature));
  return ref ? `${ref.type}:${ref.key}` : "";
}

function selectOrToggleFeature(feature) {
  const resolved = resolveSourceFeature(feature);
  if (!resolved) {
    setSpotlightFeature(null);
    return;
  }
  if (selectedFeature && featureIdentity(selectedFeature) === featureIdentity(resolved)) {
    setSpotlightFeature(null);
    setStatus("Selection cleared.");
    return;
  }
  setSpotlightFeature(resolved);
}

function topObjectFeatureAtPoint(point) {
  const features = map.queryRenderedFeatures(point, {
    layers: ["opendrive-signal-hitbox"],
  });
  return features.find((feature) => {
    return ["environment_object", "signal_object", "signal"].includes(feature.properties?.feature_type);
  }) || features[0] || null;
}

// One click selects, mouse drag moves.  Registering once avoids duplicate
// handlers after reloads or style changes.
function registerSpotlightEvents() {
  if (spotlightEventsRegistered) return;
  spotlightEventsRegistered = true;
  map.on("mousemove", moveFeatureDrag);
  map.on("mouseup", endFeatureDrag);
  map.on("mouseleave", endFeatureDrag);
  map.on("mousemove", "opendrive-lanes", (event) => {
    if (dragState) return;
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "opendrive-lanes", () => {
    if (dragState) return;
    map.getCanvas().style.cursor = "";
  });
  map.on("mousedown", "opendrive-lanes", startFeatureDrag);
  map.on("click", "opendrive-lanes", (event) => {
    event.preventDefault();
    if (dragState) return;
    const lane = resolveSourceFeature(event.features?.[0]);
    if (lane?.properties?.feature_type === "lane") {
      const props = lane.properties || {};
      const placement = {
        lon: event.lngLat.lng,
        lat: event.lngLat.lat,
        road_id: props.road_id,
        s: Number(props.s ?? props.lanesection_s0 ?? 0),
        t: Number(props.t ?? 0),
        lane_key: laneKeyFromProperties(props),
      };
      if (pendingSignalDetailKind) {
        const kind = pendingSignalDetailKind;
        pendingSignalDetailKind = null;
        selectOrToggleFeature(lane);
        addSignalDetail(kind, placement);
        return;
      }
    }
    selectOrToggleFeature(lane || event.features?.[0]);
  });
  map.on("mousemove", "opendrive-roads", (event) => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "opendrive-roads", () => {
    map.getCanvas().style.cursor = "";
  });
  map.on("click", "opendrive-roads", (event) => {
    event.preventDefault();
    selectOrToggleFeature(event.features?.[0]);
  });
  map.on("mousemove", "opendrive-signal-hitbox", () => {
    if (dragState) return;
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "opendrive-signal-hitbox", () => {
    if (dragState) return;
    map.getCanvas().style.cursor = "";
  });
  map.on("mousedown", "opendrive-signal-hitbox", startFeatureDrag);
  map.on("click", "opendrive-signal-hitbox", (event) => {
    event.preventDefault();
    if (dragState) return;
    selectOrToggleFeature(topObjectFeatureAtPoint(event.point) || event.features?.[0]);
  });
  map.on("click", (event) => {
    if (!armedObjectDefinition) return;
    if (event.originalEvent?.target?.closest?.(".maplibregl-ctrl, .maplibregl-ctrl-group, #object_palette")) return;
    event.preventDefault();
    addObjectDefinitionAtLngLat(armedObjectDefinition, event.lngLat);
    armedObjectDefinition = null;
    renderObjectPalette();
    setObjectPaletteOpen(false);
  });
}

function refreshLaneDirectionSource() {
  if (map.getSource("opendrive-lane-directions")) {
    map.getSource("opendrive-lane-directions").setData(laneDirectionGeoJson(currentLaneGeoJson));
  }
}

function updateLaneArrowControls() {
  toggleLaneArrowsButton.textContent = laneArrowsVisible ? "Hide Lane Arrows" : "Show Lane Arrows";
  if (map.getLayer("opendrive-lane-direction-arrows")) {
    map.setLayoutProperty(
      "opendrive-lane-direction-arrows",
      "visibility",
      laneArrowsVisible ? "visible" : "none"
    );
  }
}

function applyLaneArrowSize() {
  laneArrowSize = Math.max(0.2, Math.min(3, Number(laneArrowSizeInput.value) || 1));
  laneArrowSizeInput.value = laneArrowSize.toFixed(1);
  refreshLaneDirectionSource();
}

function toggleLaneArrows() {
  laneArrowsVisible = !laneArrowsVisible;
  updateLaneArrowControls();
}

function registerLaneSelectionEvents() {
  if (laneSelectionEventsRegistered) return;
  laneSelectionEventsRegistered = true;
}

// The visible network is lane-first.  Road centerlines stay available for
// editing/save support but are hidden so the lane layer carries the map.
function setLaneSource(geojson) {
  currentLaneGeoJson = geojson || emptyFeatureCollection();
  updateGlobalLaneWidthFromNetwork();
  if (map.getSource("opendrive-lanes")) {
    map.getSource("opendrive-lanes").setData(currentLaneGeoJson);
    refreshLaneDirectionSource();
    return;
  }

  addEditorGeoJsonSource("opendrive-lanes", currentLaneGeoJson);
  map.addLayer({
    id: "opendrive-lanes",
    type: "fill",
    source: "opendrive-lanes",
    paint: {
      "fill-color": [
        "case",
        ["==", ["get", "lane_type"], "driving"], "#2e90fa",
        ["==", ["get", "lane_type"], "sidewalk"], "#12b76a",
        ["==", ["get", "lane_type"], "biking"], "#f79009",
        "#667085",
      ],
      "fill-opacity": [
        "case",
        ["boolean", ["get", "level"], false], 0.46,
        0.34,
      ],
    },
  });
  map.addLayer({
    id: "opendrive-lane-borders",
    type: "line",
    source: "opendrive-lanes",
    paint: {
      "line-color": "#111827",
      "line-width": 1.2,
      "line-opacity": 0.72,
    },
  });
  addEditorGeoJsonSource("opendrive-lane-directions", laneDirectionGeoJson(currentLaneGeoJson));
  map.addLayer({
    id: "opendrive-lane-direction-arrows",
    type: "fill",
    source: "opendrive-lane-directions",
    layout: {
      visibility: laneArrowsVisible ? "visible" : "none",
    },
    paint: {
      "fill-color": "#101828",
      "fill-opacity": 0.88,
      "fill-outline-color": "#ffffff",
    },
  });
  updateLaneArrowControls();
  addEditorGeoJsonSource("opendrive-lane-adjacent", emptyFeatureCollection());
  map.addLayer({
    id: "opendrive-lane-adjacent",
    type: "fill",
    source: "opendrive-lane-adjacent",
    paint: {
      "fill-color": [
        "case",
        ["==", ["get", "relation"], "predecessor"], "#7a5af8",
        ["==", ["get", "relation"], "successor"], "#f79009",
        "#f79009",
      ],
      "fill-opacity": 0.62,
    },
  });
  map.addLayer({
    id: "opendrive-lane-adjacent-outline",
    type: "line",
    source: "opendrive-lane-adjacent",
    paint: {
      "line-color": [
        "case",
        ["==", ["get", "relation"], "predecessor"], "#5925dc",
        ["==", ["get", "relation"], "successor"], "#b54708",
        "#b54708",
      ],
      "line-width": 3,
    },
  });
  addEditorGeoJsonSource("opendrive-lane-selected", emptyFeatureCollection());
  map.addLayer({
    id: "opendrive-lane-selected",
    type: "fill",
    source: "opendrive-lane-selected",
    paint: {
      "fill-color": "#f04438",
      "fill-opacity": 0.68,
    },
  });
  map.addLayer({
    id: "opendrive-lane-selected-outline",
    type: "line",
    source: "opendrive-lane-selected",
    paint: {
      "line-color": "#b42318",
      "line-width": 4,
    },
  });
  registerLaneSelectionEvents();
}

function setSignalSource(geojson) {
  currentSignalGeoJson = geojson || emptyFeatureCollection();
  if (map.getSource("opendrive-signals")) {
    map.getSource("opendrive-signals").setData(currentSignalGeoJson);
    return;
  }

  addEditorGeoJsonSource("opendrive-signals", currentSignalGeoJson);
  map.addLayer({
    id: "opendrive-signal-hitbox",
    type: "fill",
    source: "opendrive-signals",
    paint: {
      "fill-color": [
        "case",
        ["has", "object_color"], ["get", "object_color"],
        ["==", ["get", "feature_type"], "environment_object"], "#8a6f4d",
        "#000000",
      ],
      "fill-opacity": [
        "case",
        ["==", ["get", "feature_type"], "environment_object"], 0.16,
        0.01,
      ],
    },
  });
  map.addLayer({
    id: "opendrive-signals",
    type: "fill-extrusion",
    source: "opendrive-signals",
    paint: {
      "fill-extrusion-color": [
        "case",
        ["has", "object_color"], ["get", "object_color"],
        ["==", ["get", "feature_type"], "environment_object"], "#8a6f4d",
        ["==", ["get", "object_role"], "mastarm"], "#475467",
        ["==", ["get", "object_role"], "post"], "#344054",
        ["==", ["get", "dynamic"], true], "#d92d20",
        "#fdb022",
      ],
      "fill-extrusion-height": ["coalesce", ["get", "extrusion_height"], 2],
      "fill-extrusion-base": ["coalesce", ["get", "extrusion_base"], 0],
      "fill-extrusion-opacity": 0.86,
    },
  });
  map.addLayer({
    id: "opendrive-signal-labels",
    type: "symbol",
    source: "opendrive-signals",
    filter: [
      "all",
      ["!=", ["to-string", ["coalesce", ["get", "text"], ""]], ""],
      ["!=", ["downcase", ["to-string", ["coalesce", ["get", "text"], ""]]], "none"],
    ],
    layout: {
      "text-field": ["to-string", ["get", "text"]],
      "text-size": 11,
      "text-offset": [0, 1.2],
      "text-anchor": "top",
      "text-allow-overlap": false,
    },
    paint: {
      "text-color": "#111827",
      "text-halo-color": "#ffffff",
      "text-halo-width": 1.25,
    },
  });
}

function setRoadSource(geojson) {
  currentGeoJson = geojson;
  if (map.getSource("opendrive-roads")) {
    map.getSource("opendrive-roads").setData(geojson);
  } else {
    addEditorGeoJsonSource("opendrive-roads", geojson);
    map.addLayer({
      id: "opendrive-road-casing",
      type: "line",
      source: "opendrive-roads",
      layout: {
        visibility: "none",
      },
      paint: {
        "line-color": "#243447",
        "line-width": 7,
        "line-opacity": 0.55,
      },
    });
    map.addLayer({
      id: "opendrive-roads",
      type: "line",
      source: "opendrive-roads",
      layout: {
        visibility: "none",
      },
      paint: {
        "line-color": "#f2b705",
        "line-width": 3,
      },
    });
    addEditorGeoJsonSource("opendrive-spotlight", emptyFeatureCollection());
    map.addLayer({
      id: "opendrive-spotlight-glow",
      type: "line",
      source: "opendrive-spotlight",
      paint: {
        "line-color": "#f04438",
        "line-width": 12,
        "line-opacity": 0.28,
      },
    });
    map.addLayer({
      id: "opendrive-spotlight",
      type: "line",
      source: "opendrive-spotlight",
      paint: {
        "line-color": "#f04438",
        "line-width": 5,
      },
    });
    registerSpotlightEvents();
  }
}

// Loading means replacing every collection from the Python API response.
// This is also used after save so ids, links, and derived geometry match
// the OpenDRIVE file that was just written.
function loadIntoEditor(geojson) {
  setRoadSource(geojson);
  if (!geoEditor) return;

  geoEditorSyncPending = true;
  const token = ++geoEditorSyncToken;
  const syncRoadsIntoEditor = () => {
    if (token !== geoEditorSyncToken || !geoEditor) return;
    try {
      geoEditor.loadGeoJson(geojson);
    } catch (error) {
      console.warn("maplibre-gl-geo-editor could not load road GeoJSON", error);
    } finally {
      if (token === geoEditorSyncToken) geoEditorSyncPending = false;
    }
  };

  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(syncRoadsIntoEditor, { timeout: 1200 });
  } else {
    setTimeout(syncRoadsIntoEditor, 0);
  }
}

function installPayloadData(payload) {
  try {
    setLaneSource(payload.lane_geojson || emptyFeatureCollection());
    setSignalSource(payload.signal_geojson || emptyFeatureCollection());
    loadIntoEditor(payload.geojson || emptyFeatureCollection());
    scheduleGridMeshRefresh();
    fitToGeoJson(
      (payload.lane_geojson && payload.lane_geojson.features.length > 0)
        ? payload.lane_geojson
        : ((payload.signal_geojson && payload.signal_geojson.features.length > 0)
          ? payload.signal_geojson
          : payload.geojson)
    );
    return true;
  } catch (error) {
    console.error(error);
    setStatus(`Failed to draw ${payload?.filename || "OpenDRIVE network"}: ${errorMessage(error)}`, true);
    return false;
  }
}

function loadPayload(payload) {
  currentFilename = payload.filename || "network.xodr";
  restoreRequestId += 1;
  selectedFeature = null;
  undoStack = [];
  renderAttributeEditor(null);
  updateSpotlightSummary(null);
  setLaneNetworkHighlight(null);
  const basemapChanged = applyDefaultBasemapForPayload(payload);
  if (basemapChanged) {
    pendingPayloadAfterStyle = payload;
    return new Promise((resolve) => {
      pendingPayloadLoadResolver = resolve;
    });
  }
  return Promise.resolve(installPayloadData(payload));
}

function editorFeatureCollection() {
  if (!geoEditorSyncPending && geoEditor && typeof geoEditor.getAllFeatureCollection === "function") {
    const collection = geoEditor.getAllFeatureCollection();
    return {
      ...collection,
      features: (collection.features || []).filter((feature) => {
        return feature.properties?.feature_type === "road";
      }),
    };
  }
  return currentGeoJson;
}

function commitAttributeEditorEdits() {
  if (!selectedFeature?.properties) return;
  let sourceFeature = resolveSourceFeature(selectedFeature);
  if (!sourceFeature?.properties) return;
  const fields = attributeFields.querySelectorAll("[data-attribute]");
  for (const field of fields) {
    const key = field.dataset.attribute;
    if (!key || !(key in sourceFeature.properties)) continue;
    const current = sourceFeature.properties[key];
    const nextValue = parseAttributeValue(current, field);
    if (attributeValueToText(current) === attributeValueToText(nextValue)) continue;
    const oldProps = { ...sourceFeature.properties };
    applyAttributeEdit(sourceFeature, key, nextValue, oldProps);
    sourceFeature = resolveSourceFeature(sourceFeature) || sourceFeature;
  }
  selectedFeature = sourceFeature;
}

function syncBeforeSave() {
  commitAttributeEditorEdits();
  processEditorGeneratedFeatures();
  refreshFeatureSources();
  return {
    geojson: cloneData(editorFeatureCollection()),
    lane_geojson: cloneData(currentLaneGeoJson),
    signal_geojson: cloneData(currentSignalGeoJson),
  };
}

async function loadNetwork() {
  const startedAt = performance.now();
  showLoadingOverlay("Loading OpenDRIVE network...");
  setStatus("Loading OpenDRIVE network...");
  try {
    const payload = await requestJson("/api/network");
    const installed = await loadPayload(payload);
    if (installed) setStatus(loadSummary(payload, elapsedSeconds(startedAt), payloadFileSize(payload)));
  } finally {
    hideLoadingOverlay();
  }
}

async function openXodrFile(file) {
  if (!file) return;
  const startedAt = performance.now();
  showLoadingOverlay(`Reading ${file.name} (${formatFileSize(file.size)})...`);
  try {
    setStatus(`Reading ${file.name} (${formatFileSize(file.size)})...`);
    const text = await file.text();
    setStatus(`Loading ${file.name} into OpenDRIVE map...`);
    const payload = await requestJson("/api/load-xodr", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, xodr: text }),
    });
    const installed = await loadPayload(payload);
    if (installed) setStatus(loadSummary(payload, elapsedSeconds(startedAt), payloadFileSize(payload, file.size)));
  } catch (error) {
    console.error(error);
    setStatus(`Failed to load ${file.name}: ${errorMessage(error)}`, true);
  } finally {
    hideLoadingOverlay();
  }
}

// Save sends all editable collections.  The server decides which fields
// can safely be written to OpenDRIVE XML and returns a refreshed payload.
async function saveEditedXodr() {
  showLoadingOverlay("Saving edited OpenDRIVE network...");
  setStatus("Saving edited OpenDRIVE network...");
  try {
    const savePayload = syncBeforeSave();
    const payload = await requestJson("/api/save-xodr", {
      method: "POST",
      body: JSON.stringify(savePayload),
    });
    currentFilename = payload.saved_filename || `edited_${currentFilename}`;
    await loadPayload(payload);
    downloadText(currentFilename, payload.xodr);
    setStatus(`Saved ${currentFilename} from ${payload.geojson.features.length} edited roads and refreshed ${payload.lane_geojson.features.length} lanes plus ${(payload.signal_geojson?.features.length || 0)} signals.`);
  } finally {
    hideLoadingOverlay();
  }
}

// Small console/debug API kept for developers and old demos.
window.OpenDriveViewer = {
  map,
  get editor() {
    return geoEditor;
  },
  get filename() {
    return currentFilename;
  },
  getGeoJson: editorFeatureCollection,
  getLaneGeoJson: () => currentLaneGeoJson,
  getSignalGeoJson: () => currentSignalGeoJson,
  loadNetwork,
  openXodrFile,
  saveEditedXodr,
  fit: () => fitToGeoJson(editorFeatureCollection()),
  spotlightRoad: (roadId) => {
    const feature = currentLaneGeoJson.features.find((item) => {
      return String(item.properties?.road_id || item.id) === String(roadId);
    }) || editorFeatureCollection().features.find((item) => {
      return String(item.properties?.road_id || item.id) === String(roadId);
    });
    setSpotlightFeature(feature);
    if (feature) {
      fitToGeoJson({
        type: "FeatureCollection",
        features: [feature],
      });
    }
  },
  spotlightLane: (roadId, laneId) => {
    const feature = currentLaneGeoJson.features.find((item) => {
      return (
        String(item.properties?.road_id) === String(roadId) &&
        String(item.properties?.lane_id) === String(laneId)
      );
    });
    setSpotlightFeature(feature);
    if (feature) {
      fitToGeoJson({
        type: "FeatureCollection",
        features: [feature],
      });
    }
  },
  highlightLaneNetwork: (roadId, laneId) => {
    window.OpenDriveViewer.spotlightLane(roadId, laneId);
  },
  spotlightSignal: (roadId, signalId) => {
    const feature = currentSignalGeoJson.features.find((item) => {
      return (
        String(item.properties?.road_id) === String(roadId) &&
        String(item.properties?.signal_id) === String(signalId)
      );
    });
    setSpotlightFeature(feature);
    if (feature) {
      fitToGeoJson({
        type: "FeatureCollection",
        features: [feature],
      });
    }
  },
  spotlightSignalObject: (roadId, objectId) => {
    const feature = currentSignalGeoJson.features.find((item) => {
      return (
        String(item.properties?.road_id) === String(roadId) &&
        String(item.properties?.object_id) === String(objectId)
      );
    });
    setSpotlightFeature(feature);
    if (feature) {
      fitToGeoJson({
        type: "FeatureCollection",
        features: [feature],
      });
    }
  },
  clearSpotlight: () => setSpotlightFeature(null),
};

map.on("load", () => {
  const startGeoEditor = () => {
    if (geoEditorStarted || !geoman || !initialNetworkLoaded || !map.isStyleLoaded()) return;
    geoEditorStarted = true;
    geoEditor = new GeoEditor({
      position: "top-right",
      toolbarOrientation: "vertical",
      columns: 2,
      drawModes: ["line", "polygon"],
      editModes: ["select", "copy", "split", "simplify", "lasso"],
      fileModes: [],
      fitBoundsOnLoad: false,
      enableAttributeEditing: true,
      attributePanelPosition: "right",
      attributePanelWidth: 320,
      attributePanelTitle: "OpenDRIVE Road",
      attributeSchema: {
        line: [
          { name: "road_id", label: "Road ID", type: "string", required: true },
          { name: "name", label: "Name", type: "string" },
          { name: "junction", label: "Junction", type: "string" },
        ],
        polygon: [
          { name: "road_id", label: "Road ID", type: "string", required: true },
          { name: "lane_id", label: "Lane ID", type: "number", required: true },
          { name: "lane_type", label: "Lane Type", type: "string" },
        ],
      },
      onFeatureCreate: (feature) => {
        if (handleEditorCreatedFeature(feature)) return;
        const generatedId = generatedEditorId("odr_line_road");
        feature.properties = {
          ...(feature.properties || {}),
          feature_type: "road",
          editor_id: generatedId,
          generated_from: feature.geometry?.type || "LineString",
          road_id: feature.properties?.road_id || generatedId,
          source: "maplibre-gl-geo-editor",
        };
        feature.id = generatedId;
        setRoadSource(editorFeatureCollection());
      },
      onFeatureEdit: () => {
        if (processEditorGeneratedFeatures()) return;
        setRoadSource(editorFeatureCollection());
      },
      onFeatureDelete: () => setRoadSource(editorFeatureCollection()),
      onGeoJsonLoad: (result) => {
        if (result?.features) {
          const editorFeatures = result.features || [];
          const generatedFeature = editorFeatures.find((feature) => {
            return !feature.properties?.feature_type && ["LineString", "Polygon", "MultiPolygon"].includes(feature.geometry?.type);
          });
          if (generatedFeature && handleEditorCreatedFeature(generatedFeature)) {
            loadIntoEditor(currentGeoJson);
            return;
          }
          setRoadSource({
            type: "FeatureCollection",
            features: editorFeatures,
          });
        }
      },
    });
    geoEditor.setGeoman(geoman);
    map.addControl(geoEditor, "top-right");
    scheduleEditableOverlayElevation();
    hideGeoEditorToolbarButtons();
    setTimeout(hideGeoEditorToolbarButtons, 250);
    setTimeout(hideGeoEditorToolbarButtons, 1000);
    for (const eventName of ["gm:drawstart", "gm:create", "gm:drawend", "gm:editend", "gm:update"]) {
      map.on(eventName, (event) => {
        if (eventName === "gm:drawstart") setGeoEditorLiveDrawActive(true);
        if (eventName === "gm:create" || eventName === "gm:drawend") {
          setTimeout(() => setGeoEditorLiveDrawActive(false), 500);
        }
        scheduleEditableOverlayElevation();
        const feature = extractEditorFeature(event);
        if (feature && handleEditorCreatedFeature(feature)) {
          loadIntoEditor(currentGeoJson);
          return;
        }
        processEditorGeneratedFeatures();
      });
    }
    loadIntoEditor(currentGeoJson);
  };

  const startGeoEditorWhenStyleReady = () => {
    if (!initialNetworkLoaded) return;
    if (!map.isStyleLoaded()) {
      map.once("style.load", startGeoEditorWhenStyleReady);
      return;
    }
    if (!geoman) {
      geoman = new Geoman(map, {});
      setTimeout(startGeoEditor, 0);
      return;
    }
    startGeoEditor();
  };

  map.on("style.load", () => {
    scheduleGridMeshRefresh();
    if (
      currentLaneGeoJson.features.length > 0 ||
      currentSignalGeoJson.features.length > 0 ||
      currentGeoJson.features.length > 0
    ) {
      restoreOverlayLayersAfterStyleChange();
    }
    setTimeout(syncGeoEditorToCurrentStyle, 0);
    setTimeout(startGeoEditorWhenStyleReady, 0);
  });
  map.on("click", () => {
    if (geoEditorLiveDrawActive) scheduleEditableOverlayElevation();
  });
  map.on("mousemove", () => {
    if (geoEditorLiveDrawActive) scheduleEditableOverlayElevation();
  });
  map.on("gm:loaded", startGeoEditor);
  loadNetwork()
    .then(() => {
      initialNetworkLoaded = true;
      startGeoEditorWhenStyleReady();
    })
    .catch((error) => {
      initialNetworkLoaded = true;
      setStatus(error.message, true);
      startGeoEditorWhenStyleReady();
    });
});

fileInput.addEventListener("change", () => {
  openXodrFile(fileInput.files[0]).catch((error) => setStatus(error.message, true));
  fileInput.value = "";
});
window.addEventListener("resize", updateBasemapPosition);
saveButton.addEventListener("click", () => {
  saveEditedXodr().catch((error) => setStatus(error.message, true));
});
fitButton.addEventListener("click", () => fitToGeoJson(editorFeatureCollection()));
reloadButton.addEventListener("click", () => {
  loadNetwork().catch((error) => setStatus(error.message, true));
});
addLaneButton.addEventListener("click", addLaneFromSelection);
deleteFeatureButton.addEventListener("click", deleteSelectedFeature);
copyLaneLinkButton.addEventListener("click", copySelectedLaneLink);
addSignalButton.addEventListener("click", () => armSignalDetailPlacement("signal"));
addPostButton.addEventListener("click", () => armSignalDetailPlacement("post"));
addMastArmButton.addEventListener("click", () => armSignalDetailPlacement("mastarm"));
undoMoveButton.addEventListener("click", undoLastMovement);
globalLaneWidthInput.addEventListener("input", applyGlobalLaneWidth);
globalLaneWidthInput.addEventListener("change", applyGlobalLaneWidth);
laneArrowSizeInput.addEventListener("input", applyLaneArrowSize);
laneArrowSizeInput.addEventListener("change", applyLaneArrowSize);
toggleLaneArrowsButton.addEventListener("click", toggleLaneArrows);
basemapSelect.addEventListener("change", () => changeBasemap(basemapSelect.value));
basemapFallbackNoticeClose.addEventListener("click", hideBasemapFallbackNotice);
spotlightToggle.addEventListener("click", () => {
  const collapsed = spotlight.classList.toggle("collapsed");
  spotlightToggle.textContent = collapsed ? "+" : "-";
  spotlightToggle.title = collapsed ? "Unfold panel" : "Fold panel";
  spotlightToggle.setAttribute("aria-label", spotlightToggle.title);
  scheduleSpotlightMapResize();
});
spotlightDockLeft.addEventListener("click", () => setSpotlightSide("left"));
spotlightDockRight.addEventListener("click", () => setSpotlightSide("right"));
function startRightResize(event) {
  if (getSpotlightSide() !== "left") return;
  event.preventDefault();
  event.stopPropagation();
  const rect = spotlight.getBoundingClientRect();
  const startX = event.clientX;
  const startWidth = rect.width;
  spotlightResizeHandleRight.setPointerCapture(event.pointerId);

  const onPointerMove = (moveEvent) => {
    const nextWidth = startWidth + moveEvent.clientX - startX;
    setSpotlightWidth(nextWidth);
  };
  const onPointerUp = () => {
    spotlightResizeHandleRight.removeEventListener("pointermove", onPointerMove);
    spotlightResizeHandleRight.removeEventListener("pointerup", onPointerUp);
    spotlightResizeHandleRight.removeEventListener("pointercancel", onPointerUp);
  };
  spotlightResizeHandleRight.addEventListener("pointermove", onPointerMove);
  spotlightResizeHandleRight.addEventListener("pointerup", onPointerUp);
  spotlightResizeHandleRight.addEventListener("pointercancel", onPointerUp);
}

function startLeftResize(event) {
  if (getSpotlightSide() !== "right") return;
  event.preventDefault();
  event.stopPropagation();
  const rect = spotlight.getBoundingClientRect();
  const startX = event.clientX;
  const startWidth = rect.width;
  spotlightResizeHandleLeft.setPointerCapture(event.pointerId);

  const onPointerMove = (moveEvent) => {
    const dx = moveEvent.clientX - startX;
    setSpotlightWidth(startWidth - dx);
  };
  const onPointerUp = () => {
    spotlightResizeHandleLeft.removeEventListener("pointermove", onPointerMove);
    spotlightResizeHandleLeft.removeEventListener("pointerup", onPointerUp);
    spotlightResizeHandleLeft.removeEventListener("pointercancel", onPointerUp);
  };
  spotlightResizeHandleLeft.addEventListener("pointermove", onPointerMove);
  spotlightResizeHandleLeft.addEventListener("pointerup", onPointerUp);
  spotlightResizeHandleLeft.addEventListener("pointercancel", onPointerUp);
}

spotlightResizeHandleRight.addEventListener("pointerdown", startRightResize);
spotlightResizeHandleLeft.addEventListener("pointerdown", startLeftResize);
window.addEventListener("resize", () => {
  if (!spotlight.classList.contains("collapsed")) {
    setSpotlightWidth(spotlight.getBoundingClientRect().width);
  }
  scheduleSpotlightMapResize();
});
window.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
    event.preventDefault();
    undoLastMovement();
    return;
  }
  if (event.key === "Delete" || event.key === "Backspace") {
    const target = event.target;
    const isEditingText = target?.closest?.("input, textarea, select, [contenteditable='true']");
    if (isEditingText) return;
    event.preventDefault();
    deleteSelectedFeature();
  }
});
restoreSpotlightLayout();
updateBasemapPosition();
updateLaneArrowControls();
renderObjectPalette();
copyLaneLinkButton.textContent = "Copy Selected Lane Key";
document.addEventListener("click", (event) => {
  const selectTool = maybeSelectToolElement(event.target);
  if (selectTool) {
    renderObjectPalette();
    setObjectPaletteOpen(!objectPalette.classList.contains("open"), selectTool);
    return;
  }
  if (!event.target.closest?.("#object_palette") && !event.target.closest?.(".maplibregl-ctrl, .maplibregl-ctrl-group")) {
    setObjectPaletteOpen(false);
  }
});
