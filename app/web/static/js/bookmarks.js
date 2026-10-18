// «Мои места»: Дом, Работа, Учёба or a name of one's own, kept in this browser only (localStorage `anyq.bookmarks`), shown
// on the map as small icons, and sent with every request (`bookmarks` of POST /api/turn: used for that request alone,
// never kept by the server). Their list lives in «Память» (places-panel.js); a place is added or changed in one sheet
// (kind, name, where) opened from there, from a long press (or a right click) on the map, or from a hint. A deleted
// place can be brought back from the notice that says it is gone: no confirm dialogs.

import { addressAt, addressSearch } from './address.js';
import { h, icon, isPhone } from './dom.js';
import { onLang, tr } from './i18n.js';
import * as mapView from './map.js';
import { toast } from './toast.js';

const KEY = 'anyq.bookmarks';
export const MAX = 10;
const NAME_MAX = 40;
const ADDR_MAX = 80;
export const KINDS = ['home', 'work', 'study', 'other'];
export const KIND_ICON = { home: 'home', work: 'work', study: 'study', other: 'star' };

const round = (x) => Math.round(x * 1000) / 1000; // ~100 m, like every point that leaves the page

// ctx: {where() -> {lat, lon, label?, preset?}, whereName() -> text, setWhere(where, {fly}), locate(onFound, report), pick(hint, onPoint, onCancel), picking()}
let ctx;
let items = load();
// the place being added or changed: {index, kind, name, touched, lat, lon, addr, errors: {name, where}, status}
let draft = null;
let moving = false; // the controls that set the point are open (always, while there is no point)
let leaving = false; // the sheet is closed on purpose to tap the map
let memoryWasOpen = false;
let openMemory = () => {};
let search = null; // the address field of the sheet, made once and kept
let setBox = null; // the node that holds it and the two buttons beside it: it outlives every redraw of the sheet
const listeners = new Set();

const $ = (id) => document.getElementById(id);
const kindName = (kind) => tr(`bm_kind_${kind}`);

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '[]');
    return (Array.isArray(saved) ? saved : [])
      .filter((b) => b && typeof b.name === 'string' && KINDS.includes(b.kind) && Number.isFinite(b.lat) && Number.isFinite(b.lon))
      .slice(0, MAX)
      .map((b) => ({
        name: b.name.slice(0, NAME_MAX),
        kind: b.kind,
        lat: round(b.lat),
        lon: round(b.lon),
        addr: typeof b.addr === 'string' ? b.addr.slice(0, ADDR_MAX) : '',
      }));
  } catch {
    return [];
  }
}

function persist() {
  localStorage.setItem(KEY, JSON.stringify(items));
  mapView.setMarks(items, onMarkTap);
  for (const fn of listeners) fn();
}

// what a request carries
export function forRequest() {
  return items.map((b) => ({ name: b.name, kind: b.kind, lat: b.lat, lon: b.lon }));
}

export function all() {
  return items;
}

export const isFull = () => items.length >= MAX;
export const hasHome = () => items.some((b) => b.kind === 'home');

// fn() after every change of the list
export function onChange(fn) {
  listeners.add(fn);
}

export function setMemoryOpener(fn) {
  openMemory = fn;
}

export function useAsStart(b) {
  ctx.setWhere({ preset: null, lat: b.lat, lon: b.lon, label: b.name });
}

// a place removed, with a notice that brings it back to where it was
export function removeAt(index) {
  const [gone] = items.splice(index, 1);
  if (!gone) return;
  persist();
  toast({
    text: tr('bm_deleted', { name: gone.name }),
    action: {
      label: tr('bm_undo'),
      run: () => {
        items.splice(Math.min(index, items.length), 0, gone);
        persist();
      },
    },
  });
}

// ---------------------------------------------------------------- the menu at a point of the map

function hideMenu() {
  $('map-menu').hidden = true;
}

// entries: [{label, glyph, run, danger?}]; what destroys comes last, apart
function showMenu(x, y, entries) {
  const menu = $('map-menu');
  menu.replaceChildren(...entries.map(({ label, glyph, run, danger }) =>
    h('button', { type: 'button', role: 'menuitem', class: danger ? 'danger' : null, onclick: () => { hideMenu(); run(); } }, icon(glyph), h('span', { text: label }))));
  menu.hidden = false;
  const box = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(x - box.width / 2, innerWidth - box.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(y + 14, innerHeight - box.height - 8))}px`;
  menu.querySelector('button').focus({ preventScroll: true });
}

function onPress([lat, lon], at) {
  if (ctx.picking()) return;
  const point = { lat: round(lat), lon: round(lon) };
  showMenu(at.x, at.y, [
    { label: tr('map_start_here'), glyph: 'pin', run: () => ctx.setWhere({ preset: null, ...point }, { fly: false }) },
    { label: tr('map_save_here'), glyph: 'plus', run: () => openPlace({ point }) },
  ]);
}

function onMarkTap(index, el) {
  const b = items[index];
  const box = el.getBoundingClientRect();
  showMenu(box.left + box.width / 2, box.top + box.height / 2, [
    { label: tr('bm_use', { name: b.name }), glyph: 'pin', run: () => useAsStart(b) },
    { label: tr('bm_edit', { name: b.name }), glyph: 'edit', run: () => openPlace({ index }) },
    { label: tr('bm_remove', { name: b.name }), glyph: 'trash', danger: true, run: () => removeAt(index) },
  ]);
}

// ---------------------------------------------------------------- the place sheet

function firstFreeKind() {
  return KINDS.find((k) => k !== 'other' && !items.some((b) => b.kind === k)) || 'other';
}

const defaultName = (kind) => (kind === 'other' ? '' : kindName(kind));

// openPlace({index}) changes a saved place; openPlace({point: {lat, lon}, kind}) adds one there; openPlace() adds one
// at the visitor's own start (never at the default one: that is not where they are)
export function openPlace({ index = null, point = null, kind = null } = {}) {
  if (index == null && isFull()) {
    toast({ text: tr('bm_full', { n: MAX }) });
    return;
  }
  const b = index == null ? null : items[index];
  if (b) {
    draft = { index, kind: b.kind, name: b.name, touched: true, lat: b.lat, lon: b.lon, addr: b.addr, errors: {}, status: '' };
  } else {
    const here = ctx.where();
    const start = point || (here.preset ? null : { lat: here.lat, lon: here.lon, addr: here.label || '' });
    const k = kind || firstFreeKind();
    draft = { index: null, kind: k, name: defaultName(k), touched: false, lat: start ? start.lat : null, lon: start ? start.lon : null, addr: start && start.addr ? start.addr : '', errors: {}, status: '' };
    if (start && !draft.addr) describe(draft.lat, draft.lon);
  }
  moving = draft.lat == null;
  search.reset();
  renderSheet();
  const dialog = $('bookmark');
  if (!dialog.open) dialog.showModal();
  if (!isPhone()) (moving ? search : { focus: () => $('bm-name').focus({ preventScroll: true }) }).focus();
}

// a short address for a point (the house under it), when the server knows one
async function describe(lat, lon) {
  const addr = await addressAt(lat, lon);
  if (addr && draft && draft.lat === lat && draft.lon === lon && !draft.addr) {
    draft.addr = addr.slice(0, ADDR_MAX);
    paintWhere();
  }
}

function setKind(kind) {
  if (!draft.touched || KINDS.some((k) => kindName(k) === draft.name)) {
    draft.name = defaultName(kind);
    draft.touched = false;
    $('bm-name').value = draft.name;
    draft.errors.name = '';
    paintErrors();
  }
  draft.kind = kind;
  paintKinds();
}

function setPoint(lat, lon, addr = '') {
  draft.lat = round(lat);
  draft.lon = round(lon);
  draft.addr = addr;
  draft.errors.where = '';
  draft.status = '';
  moving = false;
  paintWhere();
  if (!addr) describe(draft.lat, draft.lon);
}

function validName() {
  draft.errors.name = draft.name.trim() ? '' : tr('bm_name_empty');
  paintErrors();
  return !draft.errors.name;
}

function save() {
  const okName = validName();
  draft.errors.where = draft.lat == null ? tr('bm_where_empty') : '';
  paintErrors();
  if (!okName) {
    $('bm-name').focus({ preventScroll: true });
    return;
  }
  if (draft.errors.where) {
    moving = true;
    paintWhere();
    search.focus();
    return;
  }
  if (draft.index == null && isFull()) {
    toast({ text: tr('bm_full', { n: MAX }) });
    return;
  }
  const name = draft.name.trim().slice(0, NAME_MAX);
  const next = { name, kind: draft.kind, lat: draft.lat, lon: draft.lon, addr: draft.addr.slice(0, ADDR_MAX) };
  const added = draft.index == null;
  if (added) items.push(next);
  else items[draft.index] = next;
  persist();
  $('bookmark').close();
  toast({ text: tr(!added ? 'bm_updated' : next.kind === 'home' ? 'bm_saved_home' : 'bm_saved', { name }) });
}

function remove() {
  const index = draft.index;
  $('bookmark').close();
  removeAt(index);
}

function useMine() {
  ctx.locate((lat, lon) => setPoint(lat, lon), (text) => {
    draft.status = text;
    paintErrors();
  });
}

function pickPoint() {
  const name = draft.name.trim() || kindName(draft.kind);
  leaving = true;
  if ($('memory').open) {
    memoryWasOpen = true;
    $('memory').close(); // its backdrop would cover the map
  }
  $('bookmark').close();
  const back = () => {
    leaving = false;
    renderSheet();
    $('bookmark').showModal();
  };
  ctx.pick(tr('bm_pick_hint', { name }), (lat, lon) => {
    setPoint(lat, lon);
    back();
  }, back);
}

function afterClose() {
  if (leaving) return;
  draft = null;
  if (memoryWasOpen) {
    memoryWasOpen = false;
    openMemory();
  }
}

// ---------------------------------------------------------------- the sheet's parts

function paintKinds() {
  for (const btn of $('bm-kinds').children) btn.setAttribute('aria-pressed', String(btn.dataset.kind === draft.kind));
}

function paintErrors() {
  for (const [id, text] of [['bm-name-err', draft.errors.name], ['bm-where-err', draft.errors.where], ['bm-status', draft.status]]) {
    const el = $(id);
    el.replaceChildren(...(text ? [icon('info'), h('span', { text })] : []));
    el.hidden = !text;
  }
  $('bm-name').setAttribute('aria-invalid', String(Boolean(draft.errors.name)));
}

// the chosen point as one line with «Изменить», or the controls that set it
function paintWhere() {
  const set = draft.lat != null;
  const line = $('bm-where-line');
  line.hidden = !set;
  line.replaceChildren(...(set ? [
    icon('pin'),
    h('span', { class: 'ps-addr', text: draft.addr || tr('bm_addr_point') }),
    h('button', { type: 'button', class: 'link', id: 'bm-move', onclick: () => { moving = !moving; paintWhere(); if (moving) search.focus(); } }, tr('loc_change')),
  ] : []));
  setBox.hidden = set && !moving;
  $('bm-move')?.setAttribute('aria-expanded', String(moving));
}

function renderSheet() {
  const editing = draft.index != null;
  const form = $('bm-form');
  const nameInput = h('input', {
    id: 'bm-name',
    type: 'text',
    maxlength: NAME_MAX,
    autocomplete: 'off',
    placeholder: tr('bm_name_ph'),
    'aria-describedby': 'bm-name-err',
    oninput: (e) => {
      draft.name = e.target.value;
      draft.touched = true;
      if (draft.errors.name && draft.name.trim()) {
        draft.errors.name = '';
        paintErrors();
      }
    },
    onblur: validName,
  });
  nameInput.value = draft.name; // `value` as an attribute is only the default
  setBox.replaceChildren(
    search.el,
    h('div', { class: 'ps-actions' },
      h('button', { type: 'button', class: 'secondary', id: 'bm-mine', onclick: useMine }, icon('target'), tr('loc_mine')),
      h('button', { type: 'button', class: 'secondary', id: 'bm-pick', onclick: pickPoint }, icon('map'), tr('loc_pick_map'))),
  );
  form.replaceChildren(...[
    h('header', {},
      h('h2', { id: 'bm-title', text: tr(editing ? 'bm_edit_title' : 'bm_new_title') }),
      h('button', { type: 'button', class: 'ghost icon close', 'aria-label': tr('close'), onclick: () => $('bookmark').close() }, icon('close'))),
    h('div', { class: 'ps-kinds', id: 'bm-kinds', role: 'group', 'aria-label': tr('bm_title') }, KINDS.map((k) =>
      h('button', { type: 'button', class: 'chip bm-kind', dataset: { kind: k }, onclick: () => setKind(k) }, icon(KIND_ICON[k]), kindName(k)))),
    h('label', { class: 'ps-field' }, h('span', { class: 'ps-label', text: tr('bm_name') }), nameInput, h('p', { class: 'ps-err', id: 'bm-name-err', role: 'alert', hidden: true })),
    h('div', { class: 'ps-field', role: 'group', 'aria-labelledby': 'bm-where-label' },
      h('span', { class: 'ps-label', id: 'bm-where-label', text: tr('bm_where') }),
      h('div', { class: 'ps-where', id: 'bm-where-line' }),
      setBox,
      h('p', { class: 'ps-err', id: 'bm-where-err', role: 'alert', hidden: true }),
      h('p', { class: 'ps-err plain', id: 'bm-status', role: 'status', hidden: true })),
    h('div', { class: 'ps-foot' }, h('button', { type: 'submit', class: 'primary-btn', id: 'bm-save' }, tr('bm_save'))),
    editing
      ? h('div', { class: 'ps-danger' }, h('button', { type: 'button', class: 'secondary danger', id: 'bm-delete', onclick: remove }, icon('trash'), tr('bm_delete')))
      : null,
  ].filter(Boolean));
  paintKinds();
  paintErrors();
  paintWhere();
}

export function initBookmarks(context) {
  ctx = context;
  const dialog = $('bookmark');
  setBox = h('div', { class: 'ps-set', id: 'bm-where-set' });
  search = addressSearch({
    id: 'bm',
    onPick: (hit) => setPoint(hit.lat, hit.lon, hit.label),
  });
  $('bm-form').addEventListener('submit', (e) => {
    e.preventDefault();
    save();
  });
  dialog.addEventListener('close', afterClose);
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) dialog.close();
  });
  document.addEventListener('pointerdown', (e) => {
    if (!$('map-menu').hidden && !$('map-menu').contains(e.target)) hideMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideMenu();
  });
  mapView.onPress(onPress);
  mapView.setMarks(items, onMarkTap);
  onLang(() => {
    hideMenu();
    if (dialog.open && draft) renderSheet();
  });
}
