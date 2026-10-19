// The places of an answer and the «Вы здесь» origin as HTML markers: numbered pins (the selected one filled with the
// accent, the others outlined), a status dot on every pin, the name of the selected (or hovered) place beside it,
// and a card at the pointer. Labels are placed so that none covers another or the origin's.

import * as maplibregl from '../vendor/maplibre-gl-6.14.0/maplibre-gl.mjs';
import { h, icon } from './dom.js';
import { walkText } from './map-leg.js';
import { hideTip, moveTip, showTip } from './map-tip.js';

const STATES = new Set(['open', 'closing_soon', 'closed', 'unknown']);
const STATUS_ICON = { open: 'open', closing_soon: 'open', closed: 'closed', unknown: 'unknown' };
const LABEL_GAP = 4; // px kept free between two labels
const EDGE_GAP = 6;

let map = null;
let changed = () => {};
let hoverHandler = null;
let places = []; // [{...place, id, marker, el}], in answer order
let selId = null;
let pendingId = null; // selectPlace() before the places of that answer arrived
let hotId = null;
let you = null; // {marker, el, latlon}

export function initPins(m, onChange) {
  map = m;
  changed = onChange;
}

export function onHover(fn) {
  hoverHandler = fn;
}

const stateOf = (place) => (STATES.has(place.state) ? place.state : 'unknown');
const byId = (id) => places.find((p) => p.id === id) || null;

function clear() {
  for (const p of places) p.marker.remove();
  places = [];
  hotId = null;
  hideTip();
}

function tipNodes(p) {
  const state = stateOf(p);
  const walk = walkText(p.leg);
  return [
    h('b', { text: p.name }),
    h('div', { class: 'tip-row' }, h('span', { class: `tip-state ${state}` }, h('i', { class: `dot ${state}` }), icon(STATUS_ICON[state]), p.stateText || '')),
    walk || p.kind ? h('div', { class: 'tip-row mono' }, walk, walk && p.kind ? ' · ' : '', p.kind ? h('span', { class: 'tip-kind', text: p.kind }) : '') : null,
  ];
}

function hoverFromPointer(id) {
  if (hotId === id) return;
  hotId = id;
  if (hoverHandler) hoverHandler(id);
  paint();
  changed();
}

function build(p, i, onSelect) {
  const el = h(
    'button',
    {
      type: 'button',
      class: p.n == null ? 'mk extra' : 'mk',
      'aria-label': `${p.n == null ? '' : `${p.n}. `}${p.name}${p.stateText ? `, ${p.stateText}` : ''}`,
      dataset: { i: String(i), id: p.id },
    },
    h('span', { class: 'mk-dot', text: p.n == null ? '' : String(p.n) }),
    h('span', { class: `mk-state ${stateOf(p)}` }),
    h('span', { class: 'mk-label', text: p.name }),
  );
  el.addEventListener('click', (e) => {
    e.stopPropagation();
    selectPlace(p.id);
    if (onSelect) onSelect(i);
  });
  el.addEventListener('pointerenter', (e) => {
    if (e.pointerType !== 'mouse' || !places.some((q) => q.el === el)) return; // a pin that is gone shows no card
    showTip(e, tipNodes(p));
    hoverFromPointer(p.id);
  });
  el.addEventListener('pointermove', (e) => e.pointerType === 'mouse' && moveTip(e));
  el.addEventListener('pointerleave', (e) => {
    if (e.pointerType !== 'mouse') return;
    hideTip();
    if (hotId === p.id) hoverFromPointer(null);
  });
  el.addEventListener('focus', () => el.matches(':focus-visible') && hoverFromPointer(p.id));
  el.addEventListener('blur', () => hotId === p.id && hoverFromPointer(null));
  return el;
}

// places: [{id, lat, lon, n, name, state, stateText, kind, primary, leg}]; onSelect(index) when a pin is clicked. A place
// outside the answer's 1+2 (asked about by name) has n: null: a pin with a dot instead of a number.
export function setPlaces(list, onSelect) {
  if (!map) return;
  clear();
  places = list.map((p, i) => {
    const el = build(p, i, onSelect);
    const marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([p.lon, p.lat]).addTo(map);
    return { ...p, marker, el };
  });
  const chosen = byId(pendingId) || places.find((p) => p.primary) || places[0] || null;
  pendingId = null;
  selId = chosen ? chosen.id : null;
  paint();
  changed();
}

function paint() {
  places.forEach((p, i) => {
    p.el.classList.toggle('primary', Boolean(p.primary));
    p.el.classList.toggle('sel', p.id === selId);
    p.el.classList.toggle('hot', p.id === hotId);
    if (p.id === selId) p.el.setAttribute('aria-current', 'true');
    else p.el.removeAttribute('aria-current');
    p.marker.getElement().style.zIndex = p.id === hotId ? '4' : p.id === selId ? '3' : String(places.length - i);
  });
}

export function selectPlace(id) {
  if (!byId(id)) {
    pendingId = id;
    return;
  }
  pendingId = null;
  if (selId === id) return;
  selId = id;
  paint();
  changed();
}

// A row of the answer under the pointer: the same hover state as the pin's own, without the card.
export function hoverPlace(id) {
  const next = id != null && byId(id) ? id : null;
  if (hotId === next) return;
  hotId = next;
  paint();
  changed();
}

// legacy: the index of the pin to emphasise while the pointer is on its card; -1 clears.
export function highlight(index) {
  hoverPlace(places[index] ? places[index].id : null);
}

export const selected = () => byId(selId);
export const hot = () => byId(hotId);
export const youPoint = () => (you ? you.latlon : null);

export function setYou(latlon, label) {
  if (!map) return;
  if (!you) {
    const el = h('div', { class: 'you', role: 'img' }, h('span', { class: 'you-dot' }), h('span', { class: 'you-label' }));
    you = { el, latlon, marker: new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([latlon[1], latlon[0]]).addTo(map) };
    you.marker.getElement().style.zIndex = '1'; // above the saved places (0), under the pins of an answer
  }
  you.latlon = latlon;
  you.marker.setLngLat([latlon[1], latlon[0]]);
  you.el.setAttribute('aria-label', label);
  you.el.title = label;
  you.el.querySelector('.you-label').textContent = label;
  changed();
}

const overlaps = (a, b) =>
  a.left < b.right + LABEL_GAP && a.right > b.left - LABEL_GAP && a.top < b.bottom + LABEL_GAP && a.bottom > b.top - LABEL_GAP;

// A label shows on the right of its pin and flips to the left where the right is under the interface or off the map.
// Returns false when it meets a box in `taken` (the label is then hidden); otherwise it takes its place there.
function placeLabel(label, taken, free) {
  label.classList.remove('off', 'flip');
  let box = label.getBoundingClientRect();
  if (box.right > free.right - EDGE_GAP) {
    label.classList.add('flip');
    const flipped = label.getBoundingClientRect();
    if (flipped.left >= free.left + EDGE_GAP) box = flipped;
    else label.classList.remove('flip');
  }
  const hit = taken.some((t) => overlaps(box, t));
  label.classList.toggle('off', hit);
  if (!hit) taken.push(box);
  return !hit;
}

// `free` is the part of the map's box not under the interface: {left, right} in client x. Returns the boxes now in use
// (pins, labels, the origin) so that the route's minutes can keep clear of them.
export function layoutLabels(free) {
  const taken = places.map((p) => p.el.querySelector('.mk-dot').getBoundingClientRect());
  if (you) taken.push(you.el.querySelector('.you-dot').getBoundingClientRect());
  const shown = [byId(hotId), byId(selId)].filter((p, i, all) => p && all.indexOf(p) === i);
  for (const p of shown) placeLabel(p.el.querySelector('.mk-label'), taken, free);
  if (you) placeLabel(you.el.querySelector('.you-label'), taken, free);
  return taken;
}
