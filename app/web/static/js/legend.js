// The legend plate at the bottom left of the map: what the lines, pins and status marks mean, the honest share of places
// whose hours are known, and — always on screen — whose map this is (the lines come from the map module).
// Open where the map needs explaining (the first screen, no base map), folded to one line under an answer.

import { h, icon, isPhone } from './dom.js';
import { count, percent } from './fmt.js';
import { currentLang, tr } from './i18n.js';
import { updateChrome } from './chrome.js';
import * as mapView from './map.js';

const open = {}; // the visitor's choice per situation
const STATUS = [['open', 'lg_open', 'open'], ['closing_soon', 'lg_soon', 'clock'], ['closed', 'lg_closed', 'closed']];

let app = null;
let situation = () => 'answer';

const key = () => situation();
// open where the map needs explaining; a phone's one line is closed until it is asked (the sheet needs the room)
const isOpen = () => (key() in open ? open[key()] : !isPhone() && (key() === 'first' || key() === 'offline'));

function attribution() {
  const lines = mapView.attributionLines(currentLang());
  return h('span', { class: 'lg-attr' }, lines.flatMap((l, i) => [
    i ? h('span', { class: 'dot', text: ' · ' }) : '',
    l.href ? h('a', { href: l.href, target: '_blank', rel: 'noopener noreferrer', text: l.text }) : h('span', { text: l.text }),
  ]));
}

const swatch = (cls, text) => h('span', {}, h('i', { class: cls }), text);

function body() {
  const rows = h('div', { class: 'lg-rows' },
    h('div', { class: 'lg-r' }, swatch('sw-line', tr('lg_walk')), swatch('sw-dash', tr('lg_straight'))),
    h('div', { class: 'lg-r' }, STATUS.map(([state, text, glyph]) => h('span', { class: `st ${state}` }, icon(glyph), tr(text)))),
    h('div', { class: 'lg-r' }, swatch('sw-unk', tr('lg_unknown'))),
    h('div', { class: 'lg-r' },
      swatch('sw-me', tr('you_marker')),
      h('span', {}, h('i', { class: 'sw-pin sel', text: '1' }), tr('lg_sel')),
      h('span', {}, h('i', { class: 'sw-pin', text: '2' }), tr('lg_other'))),
  );
  const cov = app.coverage;
  const honest = cov
    ? h('div', { class: 'lg-honest' }, h('i', { class: 'sw-unk' }), h('span', { text: tr('lg_honest', { p: percent(cov.hours), n: count(cov.places) }) }))
    : null;
  return [rows, honest, h('div', { class: 'lg-foot' }, attribution())];
}

// beside the map on a laptop; the last thing of the sheet's list on a phone (the map's credits as links, the legend)
function home(el) {
  const to = isPhone() ? document.getElementById('thread-scroll') : document.querySelector('main');
  if (el.parentElement !== to) to.append(el);
}

export function renderLegend() {
  const el = document.getElementById('legend');
  home(el);
  const city = key() === 'city' || key() === 'data';
  if (city) {
    el.classList.add('closed', 'flat');
    el.replaceChildren(h('div', { class: 'lg-head static' }, attribution()));
    return;
  }
  const expanded = isOpen();
  el.classList.remove('flat');
  el.classList.toggle('closed', !expanded);
  const toggle = h(
    'button',
    { type: 'button', class: 'lg-toggle', 'aria-expanded': String(expanded), 'aria-label': tr('legend_title'), title: tr('legend_title') },
    icon('chevron'),
    h('span', { class: 'ttl', text: tr('legend_title') }),
  );
  toggle.addEventListener('click', () => {
    open[key()] = !isOpen();
    renderLegend();
  });
  const head = h('div', { class: 'lg-head' }, toggle, expanded ? null : h('span', { class: 'at' }, h('span', { class: 'bullet', text: '· ' }), attribution()));
  el.replaceChildren(head, h('div', { class: 'lg-body' }, h('div', { class: 'lg-in' }, expanded ? body() : null)));
  updateChrome(); // the legend's final height is what the map keeps clear
}

// whereAmI(): 'first' | 'answer' | 'offline' | 'city' | 'data'
export function initLegend(ctx, whereAmI) {
  matchMedia('(max-width: 760px)').addEventListener('change', renderLegend);
  app = ctx;
  situation = whereAmI;
}
