// The satellite layer: a switch on the map (a laptop: under the zoom buttons; a phone: a row of the menu, the top bar has
// no room left and a button on the map would cover a pin) that lays the
// Sentinel-2 cloudless 2016 imagery (CC BY 4.0, 10 m per pixel) under everything else. The tiles are our own server's
// (/tiles/s2/…, web/tiles.py: a disk cache over EOX), so the page's CSP does not change.
//
// ON: a raster layer right above the background, the basemap's area fills (land, water, parks, buildings) and its
// waterway lines hidden so the imagery shows, the roads white with a dark casing, the labels white with a dark halo; the
// route, the pins, the cells and «Вы здесь» are ours and sit above all of that untouched. OFF (the default): nothing
// of the style is touched, the map is exactly the basemap's. Every property this module changes is remembered and put
// back on the way out. The choice is kept in localStorage `anyq.sat`.

import { h, icon } from './dom.js';
import { onLang, tr } from './i18n.js';
import { TILE_SOURCE } from './map-style.js';

const KEY = 'anyq.sat';
const ID = 'satellite'; // the overview: the map's box, z13 and overzoomed above it
const DETAIL = 'satellite-detail'; // the city's z14-15 tiles above it
const HD = 'satellite-hd'; // Esri World Imagery through our server (/tiles/esri), above both, when a key is configured
const HD_TILES = '/tiles/esri/{z}/{x}/{y}.jpg';
const HD_MAX_ZOOM = 18;
const TILES = '/tiles/s2/{z}/{x}/{y}.jpg';
const OVERVIEW_MAX_ZOOM = 13; // the server serves z14-15 for the city box only: elsewhere MapLibre overzooms z13, blurry but never blank
const DETAIL_MIN_ZOOM = 14;
const DETAIL_MAX_ZOOM = 15; // the server serves nothing above it; MapLibre overzooms the z15 tiles
const INK = '11, 18, 32';
const ROAD = '#ffffff';
const CASING = `rgba(${INK}, 0.4)`;
const LABEL = '#ffffff';
const HALO = `rgba(${INK}, 0.88)`;

let map = null;
let bounds = null; // [west, south, east, north] of the map's box: the overview's tiles
let cityBounds = null; // the same of the city box: the detail tiles
let on = false;
let hd = false; // the server says an Esri key is configured (/api/config satellite_hd)
let ready = false; // the style has loaded: layers can be added
let changed = []; // [[method, id, property, value before]]: what to put back
let onChange = () => {};
const buttons = [];
let menuRow = null; // a phone's: the last row of the menu (index.html)

const stored = () => {
  try {
    return localStorage.getItem(KEY) === 'on';
  } catch {
    return false; // no storage: the default
  }
};

export const isOn = () => on;
// what the credits and the camera's room ask for: false | 'eox' | 'hd'
export const mode = () => (on ? (hd ? 'hd' : 'eox') : false);

// What the style does to one basemap layer over imagery: {layout, paint} to set, or null to leave it.
function overImagery({ id, type }) {
  const hide = { layout: { visibility: 'none' } };
  if (type === 'fill') return hide;
  if (type === 'line') {
    if (/waterway|aeroway/.test(id)) return hide;
    if (/casing/.test(id)) return { paint: { 'line-color': CASING } };
    if (/boundary/.test(id)) return { paint: { 'line-color': ROAD, 'line-opacity': 0.5 } };
    if (id === 'districts-line') return { paint: { 'line-color': ROAD, 'line-opacity': 0.55 } };
    // the main streets stay bright, the minor ones and the paths recede so the imagery is still what is looked at
    return { paint: { 'line-color': ROAD, 'line-opacity': /major|motorway/.test(id) ? 0.95 : /path|pier/.test(id) ? 0.45 : 0.72 } };
  }
  if (type === 'symbol') return { paint: { 'text-color': LABEL, 'text-halo-color': HALO, 'text-halo-width': 1.6, 'text-halo-blur': 0.4 } };
  return null;
}

function remember(method, id, property) {
  if (changed.some((c) => c[0] === method && c[1] === id && c[2] === property)) return;
  const get = method === 'layout' ? map.getLayoutProperty(id, property) : map.getPaintProperty(id, property);
  changed.push([method, id, property, get]);
}

// Only the basemap's own layers: the route, the pins, the cells and the reports stay as they are.
function restyle() {
  for (const layer of map.getStyle().layers) {
    if (layer.source !== TILE_SOURCE && layer.source !== 'districts') continue;
    if (map.getLayoutProperty(layer.id, 'visibility') === 'none' && !changed.some((c) => c[1] === layer.id)) continue; // hidden anyway
    const set = overImagery(layer);
    if (!set) continue;
    for (const [property, value] of Object.entries(set.layout || {})) {
      remember('layout', layer.id, property);
      map.setLayoutProperty(layer.id, property, value);
    }
    for (const [property, value] of Object.entries(set.paint || {})) {
      remember('paint', layer.id, property);
      map.setPaintProperty(layer.id, property, value);
    }
  }
}

function restore() {
  for (const [method, id, property, value] of changed) {
    if (!map.getLayer(id)) continue;
    if (method === 'layout') map.setLayoutProperty(id, property, value ?? null);
    else map.setPaintProperty(id, property, value ?? null);
  }
  changed = [];
}

function addImagery() {
  const tiles = [`${location.origin}${TILES}`];
  if (!map.getSource(ID)) map.addSource(ID, { type: 'raster', tiles, tileSize: 256, maxzoom: OVERVIEW_MAX_ZOOM, bounds });
  if (!map.getSource(DETAIL)) {
    map.addSource(DETAIL, { type: 'raster', tiles, tileSize: 256, minzoom: DETAIL_MIN_ZOOM, maxzoom: DETAIL_MAX_ZOOM, bounds: cityBounds });
  }
  const layers = map.getStyle().layers;
  const above = layers[layers.findIndex((l) => l.type === 'background') + 1]; // right above the background
  if (!map.getLayer(ID)) map.addLayer({ id: ID, type: 'raster', source: ID }, above && above.id);
  if (!map.getLayer(DETAIL)) map.addLayer({ id: DETAIL, type: 'raster', source: DETAIL, minzoom: DETAIL_MIN_ZOOM }, above && above.id); // above the overview
  if (!hd) return;
  // Esri: where its tile is an empty 204 (outside the city at z14+, or Esri down) the EOX imagery under it shows through
  if (!map.getSource(HD)) {
    map.addSource(HD, { type: 'raster', tiles: [`${location.origin}${HD_TILES}`], tileSize: 256, minzoom: 0, maxzoom: HD_MAX_ZOOM, bounds });
  }
  if (!map.getLayer(HD)) map.addLayer({ id: HD, type: 'raster', source: HD }, above && above.id);
}

function removeImagery() {
  for (const id of [HD, DETAIL, ID]) {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
  }
}

// Idempotent: also called when the basemap falls back to the local style (its district layers join the style late).
export function apply() {
  if (!ready) return;
  if (on) {
    addImagery();
    restyle();
  } else {
    removeImagery();
    restore();
  }
  map.getContainer().dataset.sat = on ? 'on' : 'off'; // what the tour reads
}

function renderButtons() {
  for (const btn of buttons) {
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-pressed', String(on));
    btn.setAttribute('aria-label', tr('sat_btn'));
    btn.title = tr('sat_title');
  }
  if (menuRow) {
    menuRow.replaceChildren(icon('layers'), h('span', { text: tr('sat_btn') }), h('span', { class: 'sat-state' }, on ? icon('check') : null));
    menuRow.setAttribute('aria-pressed', String(on));
    menuRow.title = tr('sat_title');
  }
}

function setOn(next) {
  on = next;
  try {
    localStorage.setItem(KEY, on ? 'on' : 'off');
  } catch { /* private mode: the choice lasts for the session */ }
  renderButtons();
  apply();
  onChange();
}

function bind(btn) {
  btn.append(icon('layers'));
  btn.addEventListener('click', () => setOn(!on));
  buttons.push(btn);
  renderButtons();
  return btn;
}

// the map's own corner (a laptop; the stylesheet hides it on a phone)
function cornerButton() {
  const btn = bind(h('button', { type: 'button', class: 'sat-btn' }));
  return h('div', { class: 'maplibregl-ctrl sat-wrap' }, h('div', { class: 'maplibregl-ctrl-group sat-group' }, btn));
}

class SatControl {
  onAdd() {
    this.el = cornerButton();
    return this.el;
  }

  onRemove() {
    this.el.remove();
  }
}

// the button joins the corner's buttons below the weather one (map.addLocate)
export function addToggle() {
  map.addControl(new SatControl(), 'top-right');
}

// map.js calls it once the style has loaded: a choice kept from the last visit is drawn from the first frame
export function styleReady() {
  ready = true;
  apply();
}

// `box`, `city`: the map's box and the city box {south, north, west, east}; `change()` runs after a switch (the legend's credits follow it)
export function initSatellite(m, box, city, hdAvailable, change) {
  map = m;
  hd = hdAvailable;
  // an empty 204 is not an image: MapLibre reports it as an error of the source, expected here and not a console error
  map.on('error', (e) => {
    if (!String(e.sourceId || '').startsWith('satellite')) console.error(e.error || e);
  });
  bounds = [box.west, box.south, box.east, box.north];
  cityBounds = [city.west, city.south, city.east, city.north];
  onChange = change;
  on = stored();
  menuRow = document.getElementById('sat-menu');
  if (menuRow) menuRow.addEventListener('click', () => setOn(!on));
  renderButtons();
  onLang(renderButtons);
}
