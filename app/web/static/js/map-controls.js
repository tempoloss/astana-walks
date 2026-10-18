// What the visitor puts on the map besides the answer: their saved places as small round icons, a long press (or a right
// click) that asks what to do with a point, and the «Моё местоположение» button under the zoom buttons.

import * as maplibregl from '../vendor/maplibre-gl-6.14.0/maplibre-gl.mjs';
import { h, icon } from './dom.js';

const PRESS_MS = 550;
const PRESS_SLOP = 10; // px a finger may wander and still be a press
const DEBOUNCE_MS = 800; // a long press on Android fires `contextmenu` as well
const KIND_ICON = { home: 'home', work: 'work', study: 'study', other: 'star' };

let map = null;
let marks = [];
let pressHandler = null;
let locateBtn = null;

// map.js hands over its own control: the button is a MapLibre control so it stacks under the zoom buttons
class LocateControl {
  constructor(onClick, label) {
    this.onClick = onClick;
    this.label = label;
  }

  onAdd() {
    locateBtn = h('button', { type: 'button', class: 'locate', title: this.label, 'aria-label': this.label, onclick: this.onClick }, icon('target'));
    this.el = h('div', { class: 'maplibregl-ctrl maplibregl-ctrl-group locate-ctrl' }, locateBtn);
    return this.el;
  }

  onRemove() {
    this.el.remove();
    locateBtn = null;
  }
}

export function addLocate(m, onClick, label) {
  m.addControl(new LocateControl(onClick, label), 'top-right');
}

export function setLocateLabel(label) {
  if (!locateBtn) return;
  locateBtn.title = label;
  locateBtn.setAttribute('aria-label', label);
}

export function setLocateBusy(busy) {
  for (const btn of document.querySelectorAll('.locate, .locate-bar')) {
    btn.classList.toggle('busy', busy);
    btn.setAttribute('aria-busy', String(busy));
  }
}

// the saved places: [{name, kind, lat, lon}]; onPick(index, element) when one is tapped
export function setMarks(list, onPick) {
  if (!map) return;
  for (const m of marks) m.remove();
  marks = list.map((b, i) => {
    const el = h(
      'button',
      { type: 'button', class: `bm bm-${b.kind}`, title: b.name, 'aria-label': b.name },
      h('span', { class: 'bm-dot' }, icon(KIND_ICON[b.kind] || 'star')),
    );
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      onPick(i, el);
    });
    const marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([b.lon, b.lat]).addTo(map);
    marker.getElement().style.zIndex = '0'; // under the pins of an answer
    return marker;
  });
}

// fn([lat, lon], {x, y}) with the point's place in the page, or null to stop listening
export function onPress(fn) {
  pressHandler = fn;
}

export function initControls(m) {
  map = m;
  let timer = 0;
  let start = null;
  let last = 0;
  const cancel = () => {
    clearTimeout(timer);
    start = null;
  };
  const fire = (e) => {
    const target = e.originalEvent && e.originalEvent.target;
    if (!pressHandler || Date.now() - last < DEBOUNCE_MS || (target && target.closest && target.closest('.mk, .bm, .maplibregl-ctrl'))) return;
    last = Date.now();
    const box = map.getContainer().getBoundingClientRect();
    pressHandler([e.lngLat.lat, e.lngLat.lng], { x: box.left + e.point.x, y: box.top + e.point.y });
  };
  m.getContainer().addEventListener('contextmenu', (ev) => ev.preventDefault());
  map.on('contextmenu', (e) => {
    cancel();
    fire(e);
  });
  map.on('touchstart', (e) => {
    cancel();
    if (!e.points || e.points.length !== 1) return;
    start = e.point;
    timer = setTimeout(() => {
      start = null;
      fire(e);
    }, PRESS_MS);
  });
  map.on('touchmove', (e) => {
    if (start && e.point.dist(start) > PRESS_SLOP) cancel();
  });
  for (const type of ['touchend', 'touchcancel', 'movestart', 'zoomstart']) map.on(type, cancel);
}
