// The walking line. Normally only origin -> the selected place (a faint dashed preview to the place under the pointer);
// for a multi-stop plan the ordered route. A street line is solid (white casing, accent line, width graded by zoom);
// a leg the router had no street line for is a straight, dashed hint. One minutes label sits on each drawn leg, slid
// along it to the first spot that covers no pin, no name and no «Вы здесь».

import * as maplibregl from '../vendor/maplibre-gl-6.14.0/maplibre-gl.mjs';
import { h } from './dom.js';
import { isStreet, minutesText } from './map-leg.js';

export const ACCENT = '#0f9d76';
const INK = '#161b26';
const EMPTY = { type: 'FeatureCollection', features: [] };
const grade = (a, b, c) => ['interpolate', ['linear'], ['zoom'], 11, a, 14, b, 17, c];
const MIN_LABEL_PX = 90; // a leg shorter than this on screen is too short to carry its minutes
const SLOTS = [0.5, 0.38, 0.62, 0.28, 0.72]; // where along the leg a label may sit
const GAP_PX = 4;

let map = null;
let pills = []; // [{el, marker, pts, from, to}]

export function initRoute(m) {
  map = m;
}

export function addRouteLayers() {
  map.addSource('route', { type: 'geojson', data: EMPTY });
  map.addSource('preview', { type: 'geojson', data: EMPTY });
  const round = { 'line-cap': 'round', 'line-join': 'round' };
  const street = ['==', ['get', 'kind'], 'street'];
  const straight = ['==', ['get', 'kind'], 'straight'];
  map.addLayer({
    id: 'preview-line',
    type: 'line',
    source: 'preview',
    layout: round,
    paint: { 'line-color': INK, 'line-opacity': 0.45, 'line-width': grade(1.4, 1.8, 2.6), 'line-dasharray': [1.2, 1.8] },
  });
  map.addLayer({ id: 'route-casing', type: 'line', source: 'route', filter: street, layout: round, paint: { 'line-color': '#ffffff', 'line-width': grade(3.5, 6, 11) } });
  map.addLayer({ id: 'route-line', type: 'line', source: 'route', filter: street, layout: round, paint: { 'line-color': ACCENT, 'line-width': grade(1.8, 3, 5.5) } });
  map.addLayer({ id: 'straight-casing', type: 'line', source: 'route', filter: straight, layout: round, paint: { 'line-color': '#ffffff', 'line-width': grade(3, 5, 7) } });
  map.addLayer({
    id: 'straight-line',
    type: 'line',
    source: 'route',
    filter: straight,
    layout: { 'line-cap': 'butt', 'line-join': 'round' },
    paint: { 'line-color': ACCENT, 'line-width': grade(1.6, 2.4, 3.2), 'line-dasharray': [2, 1.6] },
  });
}

const line = (pts, props) => ({
  type: 'Feature',
  properties: props,
  geometry: { type: 'LineString', coordinates: pts.map(([la, lo]) => [lo, la]) },
});

// plan legs, [{from, to, text, shape}] with the shape already running from `from` to `to`, become the same items as
// the leg of one place: {pts, street, text, from, to}
function planItems(legs) {
  return legs.map((l) => {
    const street = Boolean(l.shape && l.shape.length > 1);
    return { pts: street ? l.shape : [l.from, l.to], street, text: l.text, from: l.from, to: l.to };
  });
}

// the origin -> place leg; the router computed it from the origin rounded to ~100 m, so the ends are anchored on the
// true origin and the place's pin
function legItem(origin, place) {
  const street = isStreet(place.leg);
  const to = [place.lat, place.lon];
  return { pts: street ? [origin, ...place.leg.shape, to] : [origin, to], street, text: minutesText(place.leg), from: origin, to };
}

// plan: legs of a multi-stop turn or []; origin: [lat, lon] | null; selected, hot: places of the answer or null.
export function drawRoute({ plan, origin, selected, hot }) {
  let items = [];
  if (plan.length) items = planItems(plan);
  else if (origin && selected) items = [legItem(origin, selected)];
  map.getSource('route').setData(items.length ? { type: 'FeatureCollection', features: items.map((i) => line(i.pts, { kind: i.street ? 'street' : 'straight' })) } : EMPTY);
  const preview = !plan.length && origin && hot && hot !== selected && hot.leg ? legItem(origin, hot) : null;
  map.getSource('preview').setData(preview ? { type: 'FeatureCollection', features: [line(preview.pts, {})] } : EMPTY);
  for (const p of pills.splice(0)) p.marker.remove();
  items.forEach((it, i) => {
    if (!it.text) return;
    const el = h('div', { class: 'leg-label', text: it.text, dataset: { leg: String(i + 1) } });
    pills.push({ el, marker: new maplibregl.Marker({ element: el }).setLngLat(lonlat(along(it.pts, 0.5))).addTo(map), ...it });
  });
}

const lonlat = ([la, lo]) => [lo, la];

function along(pts, t) {
  const k = Math.cos((pts[0][0] * Math.PI) / 180);
  const seg = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], (p[1] - pts[i][1]) * k));
  let left = seg.reduce((a, b) => a + b, 0) * t;
  for (let i = 0; i < seg.length; i += 1) {
    if (left <= seg[i] || i === seg.length - 1) {
      const f = seg[i] ? Math.min(left / seg[i], 1) : 0;
      return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f];
    }
    left -= seg[i];
  }
  return pts[0];
}

const overlaps = (a, b) => a.left < b.right + GAP_PX && a.right > b.left - GAP_PX && a.top < b.bottom + GAP_PX && a.bottom > b.top - GAP_PX;

// `taken`: client-space boxes the labels must keep clear of (pins, their names, the origin and its label).
export function placePills(taken) {
  const used = [...taken];
  for (const pill of pills) {
    const a = map.project(lonlat(pill.from));
    const b = map.project(lonlat(pill.to));
    let placed = false;
    pill.el.classList.remove('off');
    if (Math.hypot(a.x - b.x, a.y - b.y) >= MIN_LABEL_PX) {
      for (const t of SLOTS) {
        pill.marker.setLngLat(lonlat(along(pill.pts, t)));
        const box = pill.el.getBoundingClientRect();
        if (!used.some((o) => overlaps(box, o))) {
          used.push(box);
          placed = true;
          break;
        }
      }
    }
    pill.el.classList.toggle('off', !placed);
  }
}
