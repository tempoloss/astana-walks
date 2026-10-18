// «Город»: the 500 m cells (filled with the colour the page gives each cell, a hairline between them, the cell under the
// pointer outlined in the accent), the residents' reports as dots, and the district outlines that stand in for the
// basemap when it cannot load. All of them sit under the basemap's labels.

import { h } from './dom.js';
import { ACCENT } from './map-route.js';
import { hideTip, moveTip, showTip } from './map-tip.js';
import { DISTRICT_LAYERS } from './map-style.js';

const EMPTY = { type: 'FeatureCollection', features: [] };
const HAIRLINE = 'rgba(16, 24, 40, 0.16)';
let map = null;
let beforeId;
let hovered = null;

function outline(id) {
  if (hovered !== null) map.setFeatureState({ source: 'cells', id: hovered }, { hl: false });
  hovered = id;
  if (id !== null) map.setFeatureState({ source: 'cells', id }, { hl: true });
}

export function addCityLayers(m, firstSymbol) {
  map = m;
  beforeId = firstSymbol;
  map.addSource('cells', { type: 'geojson', data: EMPTY, generateId: true });
  map.addSource('reports', { type: 'geojson', data: EMPTY });
  map.addLayer({ id: 'cells-fill', type: 'fill', source: 'cells', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.86 } }, beforeId);
  map.addLayer({ id: 'cells-line', type: 'line', source: 'cells', paint: { 'line-color': HAIRLINE, 'line-width': 0.6 } }, beforeId);
  map.addLayer({
    id: 'cells-hl',
    type: 'line',
    source: 'cells',
    paint: { 'line-color': ACCENT, 'line-width': 2.2, 'line-opacity': ['case', ['boolean', ['feature-state', 'hl'], false], 1, 0] },
  }, beforeId);
  map.addLayer({
    id: 'reports',
    type: 'circle',
    source: 'reports',
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 3, 14, 6, 17, 9],
      'circle-color': ['get', 'color'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
    },
  });
  map.on('mousemove', 'cells-fill', (e) => {
    const f = e.features && e.features[0];
    if (f) outline(f.id);
  });
  map.on('mouseleave', 'cells-fill', () => outline(null));
  map.on('mousemove', 'reports', (e) => {
    const f = e.features && e.features[0];
    if (!f) return;
    showTip(e.originalEvent, [h('b', { text: f.properties.title })]);
    moveTip(e.originalEvent);
  });
  map.on('mouseleave', 'reports', hideTip);
}

export function setCells(geojson, colorOf) {
  outline(null);
  const data = geojson
    ? { ...geojson, features: geojson.features.map((f) => ({ ...f, properties: { ...f.properties, color: colorOf(f.properties) } })) }
    : EMPTY;
  map.getSource('cells').setData(data);
}

// points: [{lat, lon, color, title}]
export function setReports(points) {
  hideTip();
  map.getSource('reports').setData({
    type: 'FeatureCollection',
    features: (points || []).map((p) => ({
      type: 'Feature',
      properties: { color: p.color, title: p.title },
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
    })),
  });
}

// The district outlines are in the local style from the start; with the basemap they are added only if it fails.
export function showDistricts(on) {
  if (on && !map.getSource('districts')) {
    map.addSource('districts', { type: 'geojson', data: '/api/districts' });
    for (const layer of DISTRICT_LAYERS) map.addLayer({ ...layer, layout: { visibility: 'none' } }, 'cells-fill');
  }
  for (const { id } of DISTRICT_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}
