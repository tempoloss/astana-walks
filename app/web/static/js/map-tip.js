// The small card that follows the pointer over a pin, a report or a city cell. One element, text nodes only.

import { h } from './dom.js';

const GAP_X = 14;
const GAP_Y = 16;
const EDGE = 8;
let box = null;
let el = null;

export function initTip(map) {
  box = map.getContainer();
  el = h('div', { class: 'map-tip', role: 'tooltip' });
  box.append(el);
}

// `e` is any pointer event or {clientX, clientY}; `nodes` the content (text and elements, never HTML).
export function showTip(e, nodes) {
  if (!el) return;
  el.replaceChildren(...nodes);
  el.classList.add('on');
  moveTip(e);
}

export function moveTip(e) {
  if (!el || !el.classList.contains('on')) return;
  const r = box.getBoundingClientRect();
  const w = el.offsetWidth;
  const hh = el.offsetHeight;
  let x = e.clientX - r.left + GAP_X;
  let y = e.clientY - r.top + GAP_Y;
  if (x + w > r.width - EDGE) x = Math.max(EDGE, e.clientX - r.left - w - GAP_X);
  if (y + hh > r.height - EDGE) y = Math.max(EDGE, e.clientY - r.top - hh - GAP_Y);
  el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}

export function hideTip() {
  if (el) el.classList.remove('on');
}
