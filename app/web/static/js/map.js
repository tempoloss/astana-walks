// The map: MapLibre over the OpenFreeMap «positron» style recoloured to the page's tokens (map-style.js), our own pins,
// route and «Город» layers on top (map-pins.js, map-route.js, map-layers.js). Without the network (the style does not
// load in a few seconds, its tiles keep failing, or the stand is offline) the map is a neutral background with the
// district outlines served by our own server: the route and the pins are our GeoJSON and HTML markers, so they are
// drawn either way.
//
// Camera rules: every fit keeps the part of the map under the interface clear (`setChromePadding`) plus a margin;
// choosing a place never moves the camera; only an explicit fit() or flyTo() does.

import * as maplibregl from '../vendor/maplibre-gl-6.14.0/maplibre-gl.mjs';
import * as controls from './map-controls.js';
import { currentLang, onLang } from './i18n.js';
import { addCityLayers, setCells as drawCells, setReports as drawReports, showDistricts } from './map-layers.js';
import * as pins from './map-pins.js';
import { addRouteLayers, drawRoute, initRoute, placePills } from './map-route.js';
import { attributionLines as attribution, localStyle, onlineStyle, relabel, TILE_SOURCE } from './map-style.js';
import { initTip } from './map-tip.js';
import * as weatherFx from './map-weather.js';

const MARGIN = 32; // px kept clear around what a fit shows, on top of the interface's own padding
const MIN_FREE = 96; // a fit never squeezes the free area below this, whatever the interface says
const FIT_MAX_ZOOM = 16.2;
const TILE_ERRORS_MAX = 3; // failed tiles, with none loaded, after which the basemap is given up
const TILE_PATIENCE_MS = 8000;
const REFRAME_MS = 240;
const MIN_ZOOM = 9; // the whole map box fits a laptop's screen at this zoom (MapLibre keeps the box in view by itself)

// Astana itself: a point outside this box is not «here» (the device's position, a place picked on the map).
const ASTANA = { south: 50.98, north: 51.3, west: 71.2, east: 71.7 };
// The map shows the city and its surroundings, about 2.5 times the city's width and height, so a walk or a trip can be
// followed past the last block: a pan stops at this box.
const MAP_BOUNDS = { south: 50.74, north: 51.54, west: 70.83, east: 72.08 };

let map = null;
let loaded = null;
let basemap = 'none';
let pickHandler = null;
let basemapHandler = null;
let chrome = { top: 0, right: 0, bottom: 0, left: 0 };
let plan = []; // legs of a multi-stop turn; empty = the route to the selected place
let drawn = '';
let framing = null; // the last explicit fit/flyTo, kept while the user has not moved the map since
let reframing = 0;

export const onHover = pins.onHover;
export const setYou = pins.setYou;
export const setPlaces = pins.setPlaces;
export const selectPlace = pins.selectPlace;
export const hoverPlace = pins.hoverPlace;
export const highlight = pins.highlight;
export const setMarks = controls.setMarks;
export const onPress = controls.onPress;
export const setLocateLabel = controls.setLocateLabel;
export const setLocateBusy = controls.setLocateBusy;

export function addLocate(onClick, label) {
  if (map) {
    controls.addLocate(map, onClick, label);
    weatherFx.addToggle();
  }
}

export const inAstana = (lat, lon) => lat >= ASTANA.south && lat <= ASTANA.north && lon >= ASTANA.west && lon <= ASTANA.east;

export const basemapKind = () => basemap;

export function onBasemapChange(fn) {
  basemapHandler = fn;
}

export function attributionLines(lang) {
  return attribution(lang || currentLang(), basemap);
}

// ---------------------------------------------------------------- what is drawn

// Everything that depends on the selection, the hover, the origin or the plan, redrawn when one of them changes.
function refresh() {
  if (!map) return;
  loaded.then(() => {
    const state = { plan, origin: pins.youPoint(), selected: pins.selected(), hot: pins.hot() };
    const key = JSON.stringify([plan, state.origin, state.selected && [state.selected.id, state.selected.leg], state.hot && [state.hot.id, state.hot.leg]]);
    if (key !== drawn) {
      drawn = key;
      drawRoute(state);
    }
    settle();
  });
}

let settling = false;
function settle() {
  if (settling) return;
  settling = true;
  requestAnimationFrame(() => {
    settling = false;
    layout();
  });
}

function layout() {
  if (!map) return;
  const box = map.getContainer().getBoundingClientRect();
  placePills(pins.layoutLabels({ left: box.left + chrome.left, right: box.right - chrome.right }));
}

export async function setRoute(legs) {
  if (!map) return;
  plan = legs || [];
  refresh();
  await loaded;
}

export async function setCells(geojson, colorOf) {
  if (!map) return;
  await loaded;
  drawCells(geojson, colorOf);
}

// points: [{lat, lon, color, title}]
export async function setReports(points) {
  if (!map) return;
  await loaded;
  drawReports(points);
}

// ---------------------------------------------------------------- the basemap's life

function setBasemap(kind) {
  if (basemap === kind) return;
  basemap = kind;
  weatherFx.setBasemapKind(kind);
  loaded.then(() => showDistricts(kind === 'offline'));
  if (basemapHandler) basemapHandler(kind);
}

// An online style whose tiles cannot be fetched is a blank page: after a few failures (or some patience) with no tile
// shown, the map falls back to the neutral background and the districts, and comes back if a tile arrives later.
function watchTiles() {
  let shown = false;
  let failed = 0;
  const giveUp = () => !shown && setBasemap('offline');
  map.on('sourcedata', (e) => {
    if (e.sourceId !== TILE_SOURCE || !e.tile) return;
    shown = true;
    setBasemap('online');
  });
  map.on('error', (e) => {
    if (e.sourceId === TILE_SOURCE && (failed += 1) >= TILE_ERRORS_MAX) giveUp();
  });
  setTimeout(giveUp, TILE_PATIENCE_MS);
}

export async function initMap(el, { center, offline, lang }) {
  const style = offline ? null : await onlineStyle(lang);
  basemap = style ? 'online' : 'offline';
  map = new maplibregl.Map({
    container: el,
    style: style || localStyle(),
    center: [center[1], center[0]],
    zoom: 14,
    minZoom: MIN_ZOOM,
    maxBounds: [[MAP_BOUNDS.west, MAP_BOUNDS.south], [MAP_BOUNDS.east, MAP_BOUNDS.north]],
    maxZoom: 18,
    dragRotate: false,
    touchPitch: false,
    pitchWithRotate: false,
    attributionControl: false, // the legend row names the sources (attributionLines)
    cooperativeGestures: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.touchZoomRotate.disableRotation();
  initTip(map);
  initRoute(map);
  pins.initPins(map, refresh);
  controls.initControls(map);
  weatherFx.initWeather(map, basemap);
  map.on('moveend', () => {
    const c = map.getCenter();
    el.dataset.cam = `${map.getZoom().toFixed(2)} ${c.lat.toFixed(4)} ${c.lng.toFixed(4)}`; // what the tour reads
  });
  // `style.load`, not `load`: `load` waits for every tile of the first view, and on a slow network the route would not
  // be drawn until then (the style, which is all the layers need, is ready at once)
  loaded = new Promise((resolve) => map.once('style.load', () => {
    const firstSymbol = map.getStyle().layers.find((l) => l.type === 'symbol');
    addCityLayers(map, firstSymbol && firstSymbol.id);
    addRouteLayers();
    resolve();
  }));
  if (style) watchTiles();
  onLang((next) => loaded.then(() => style && relabel(map, next)));
  map.on('click', (e) => pickHandler && pickHandler([e.lngLat.lat, e.lngLat.lng]));
  // a move with an originalEvent is the user's (drag, wheel, pinch, keys, zoom buttons): the shell's framing is over
  map.on('movestart', (e) => {
    if (e.originalEvent) framing = null;
  });
  map.on('move', settle);
  map.on('resize', settle);
  return basemap;
}

export function onPick(fn) {
  pickHandler = fn;
  if (map) map.getCanvas().style.cursor = fn ? 'crosshair' : '';
}

// ---------------------------------------------------------------- the camera

// `p` is what the interface covers, {top, right, bottom, left} px, set by the shell on every layout. A change (the
// legend opened, the panel resized) re-frames the last fit or flyTo, unless the user has moved the map since; a
// selection never moves the camera.
export function setChromePadding(p) {
  const next = { top: p.top || 0, right: p.right || 0, bottom: p.bottom || 0, left: p.left || 0 };
  const same = Object.keys(next).every((k) => next[k] === chrome[k]);
  chrome = next;
  settle();
  if (!same && framing && map) {
    cancelAnimationFrame(reframing);
    reframing = requestAnimationFrame(() => framing && frame(framing, REFRAME_MS));
  }
}

// Chrome plus margin, never leaving less than MIN_FREE of the map free in either direction.
function padding(override) {
  if (override) return override;
  const box = map.getContainer().getBoundingClientRect();
  const squeeze = (a, b, room) => {
    const over = a + b - Math.max(room - MIN_FREE, 0);
    return over > 0 ? [Math.max(a - (over * a) / (a + b), 0), Math.max(b - (over * b) / (a + b), 0)] : [a, b];
  };
  const [left, right] = squeeze(chrome.left + MARGIN, chrome.right + MARGIN, box.width);
  const [top, bottom] = squeeze(chrome.top + MARGIN, chrome.bottom + MARGIN, box.height);
  return { top, right, bottom, left };
}

// A camera move with a `padding` option keeps it as the map's own padding and a later fitBounds would add its padding
// on top (the fit then fails), so single points are centred with an `offset` and only fitBounds gets the padding.
const offsetOf = (p) => [(p.left - p.right) / 2, (p.top - p.bottom) / 2];
const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const ms = (n) => (still() ? 0 : n);

// One explicit camera move: {latlons} to show all of them, or {latlon, zoom} to centre one point.
function frame(view, duration) {
  const pad = padding(view.override);
  if (view.latlons && view.latlons.length > 1) {
    const lons = view.latlons.map((p) => p[1]);
    const lats = view.latlons.map((p) => p[0]);
    map.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: pad, maxZoom: FIT_MAX_ZOOM, duration: ms(duration) },
    );
    return;
  }
  const at = view.latlon || view.latlons[0];
  map.easeTo({ center: [at[1], at[0]], zoom: view.zoom || 15, offset: offsetOf(pad), duration: ms(duration) });
}

function move(view, duration) {
  cancelAnimationFrame(reframing);
  framing = view;
  frame(view, duration);
}

export function fit(latlons, override) {
  if (!map || !latlons.length) return;
  move({ latlons, override }, latlons.length === 1 ? 500 : 600);
}

export function flyTo(latlon, zoom = 14.5, override, duration = 600) {
  if (!map) return;
  move({ latlon, zoom, override }, duration);
}

export function resize() {
  if (map) map.resize();
}
