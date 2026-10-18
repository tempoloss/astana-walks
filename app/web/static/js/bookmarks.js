// «Мои места»: Дом, Работа, Учёба or a name of one's own, kept in this browser only (localStorage `anyq.bookmarks`), shown
// on the map as small icons, offered as starting points under «Вы здесь · Изменить», and sent with every request
// (`bookmarks` of POST /api/turn: used for that request alone, never kept by the server). A place is added by a long
// press (or a right click) on the map, from «Моё местоположение», or from the list.

import { h, icon } from './dom.js';
import { onLang, tr } from './i18n.js';
import * as mapView from './map.js';

const KEY = 'anyq.bookmarks';
const MAX = 10;
const NAME_MAX = 40;
const KINDS = ['home', 'work', 'study', 'other'];
const KIND_ICON = { home: 'home', work: 'work', study: 'study', other: 'star' };

const round = (x) => Math.round(x * 1000) / 1000; // ~100 m, like every point that leaves the page

// ctx: {where() -> {lat, lon, label?}, whereName() -> text, setWhere(where, {fly}), locate(onFound, report), pick(hint, onPoint, onCancel), picking()}
let ctx;
let items = load();
let draft = null; // the place being added or edited: {index, kind, name, touched, lat, lon, here, note}
let onList = () => {};

const $ = (id) => document.getElementById(id);
const kindName = (kind) => tr(`bm_kind_${kind}`);

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '[]');
    return (Array.isArray(saved) ? saved : [])
      .filter((b) => b && typeof b.name === 'string' && KINDS.includes(b.kind) && Number.isFinite(b.lat) && Number.isFinite(b.lon))
      .slice(0, MAX)
      .map((b) => ({ name: b.name.slice(0, NAME_MAX), kind: b.kind, lat: round(b.lat), lon: round(b.lon) }));
  } catch {
    return [];
  }
}

function persist() {
  localStorage.setItem(KEY, JSON.stringify(items));
  mapView.setMarks(items, onMarkTap);
  onList();
}

// what a request carries
export function forRequest() {
  return items.map((b) => ({ name: b.name, kind: b.kind, lat: b.lat, lon: b.lon }));
}

export function all() {
  return items;
}

export const isFull = () => items.length >= MAX;

// ---------------------------------------------------------------- the menu at a point of the map

function hideMenu() {
  $('map-menu').hidden = true;
}

function showMenu(x, y, entries) {
  const menu = $('map-menu');
  menu.replaceChildren(...entries.map(({ label, glyph, run }) =>
    h('button', { type: 'button', role: 'menuitem', onclick: () => { hideMenu(); run(); } }, icon(glyph), h('span', { text: label }))));
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
    { label: tr('map_save_here'), glyph: 'plus', run: () => edit(null, point) },
  ]);
}

function onMarkTap(index, el) {
  const b = items[index];
  const box = el.getBoundingClientRect();
  showMenu(box.left + box.width / 2, box.top + box.height / 2, [
    { label: tr('bm_use', { name: b.name }), glyph: 'pin', run: () => useAsStart(b) },
    { label: tr('bm_edit', { name: b.name }), glyph: 'edit', run: () => edit(index) },
  ]);
}

export function useAsStart(b) {
  ctx.setWhere({ preset: null, lat: b.lat, lon: b.lon, label: b.name });
}

// ---------------------------------------------------------------- the list (inside «Где вы?»)

// box: the dialog's slot; onUse(b) when a place is chosen as the start
export function renderList(box, onUse) {
  const here = ctx.where();
  const add = isFull()
    ? h('p', { class: 'fine', text: tr('bm_full', { n: MAX }) })
    : h('button', { type: 'button', class: 'link bm-add', onclick: () => edit(null) }, icon('plus'), tr('bm_add'));
  const rows = items.map((b, i) =>
    h('div', { class: 'bm-row' },
      h('button', {
        type: 'button',
        class: 'bm-use',
        'aria-pressed': String(Math.abs(here.lat - b.lat) < 1e-6 && Math.abs(here.lon - b.lon) < 1e-6),
        onclick: () => onUse(b),
      }, icon(KIND_ICON[b.kind]), h('span', { class: 'bm-name', text: b.name })),
      h('button', { type: 'button', class: 'bm-edit', 'aria-label': tr('bm_edit', { name: b.name }), onclick: () => edit(i) }, icon('edit'))));
  box.replaceChildren(
    h('div', { class: 'bm-head' }, h('p', { class: 'label', text: tr('bm_title') }), add),
    items.length ? h('div', { class: 'bm-rows' }, rows) : h('p', { class: 'fine', text: tr('bm_empty') }),
  );
}

export function onListChange(fn) {
  onList = fn;
}

// ---------------------------------------------------------------- the editor

function edit(index, point) {
  const b = index == null ? null : items[index];
  const here = ctx.where();
  draft = b
    ? { index, kind: b.kind, name: b.name, touched: true, lat: b.lat, lon: b.lon, here: false, note: '' }
    : { index: null, kind: 'home', name: '', touched: false, lat: point ? point.lat : here.lat, lon: point ? point.lon : here.lon, here: !point, note: '' };
  if (!b) draft.name = kindName(draft.kind);
  openEditor();
}

function openEditor() {
  renderEditor();
  const dialog = $('bookmark');
  if (!dialog.open) dialog.showModal();
}

function setKind(kind) {
  if (!draft.touched || KINDS.some((k) => kindName(k) === draft.name)) {
    draft.name = kind === 'other' ? '' : kindName(kind);
    draft.touched = false;
  }
  draft.kind = kind;
  renderEditor();
  $('bm-name').focus({ preventScroll: true });
}

function setPoint(lat, lon) {
  draft.lat = round(lat);
  draft.lon = round(lon);
  draft.here = false;
  draft.note = '';
  openEditor();
}

function save() {
  const name = draft.name.trim().slice(0, NAME_MAX);
  if (!name) {
    draft.note = tr('bm_name_empty');
    renderEditor();
    $('bm-name').focus({ preventScroll: true });
    return;
  }
  if (draft.index == null && isFull()) {
    draft.note = tr('bm_full', { n: MAX });
    renderEditor();
    return;
  }
  const next = { name, kind: draft.kind, lat: draft.lat, lon: draft.lon };
  if (draft.index == null) items.push(next);
  else items[draft.index] = next;
  persist();
  $('bookmark').close();
}

function remove() {
  items.splice(draft.index, 1);
  persist();
  $('bookmark').close();
}

function renderEditor() {
  const form = $('bm-form');
  const editing = draft.index != null;
  const keep = document.activeElement === $('bm-name') ? $('bm-name').selectionStart : null;
  form.replaceChildren(
    h('header', {},
      h('h2', { text: tr(editing ? 'bm_edit_title' : 'bm_add') }),
      h('button', { type: 'button', class: 'ghost icon close', 'aria-label': tr('close'), onclick: () => $('bookmark').close() }, icon('close'))),
    h('div', { class: 'bm-kinds', role: 'group' }, KINDS.map((k) =>
      h('button', { type: 'button', class: 'chip bm-kind', 'aria-pressed': String(draft.kind === k), dataset: { kind: k }, onclick: () => setKind(k) }, icon(KIND_ICON[k]), kindName(k)))),
    h('label', { class: 'bm-field' },
      h('span', { text: tr('bm_name') }),
      h('input', {
        id: 'bm-name',
        type: 'text',
        maxlength: NAME_MAX,
        autocomplete: 'off',
        value: draft.name,
        placeholder: tr('bm_name_ph'),
        oninput: (e) => {
          draft.name = e.target.value;
          draft.touched = true;
        },
      })),
    h('div', { class: 'bm-pos' },
      h('p', { class: 'bm-where' }, icon('pin'), h('span', { text: draft.here ? tr('bm_where_now', { name: ctx.whereName() }) : tr('bm_where_set') })),
      h('div', { class: 'loc-actions' },
        h('button', { type: 'button', class: 'secondary', id: 'bm-mine', onclick: useMine }, icon('target'), tr('loc_mine')),
        h('button', { type: 'button', class: 'secondary', id: 'bm-pick', onclick: pickPoint }, icon('map'), tr('loc_pick_map')))),
    h('p', { class: 'fine bm-note', role: 'status', text: draft.note }),
    h('div', { class: 'bm-actions' },
      editing ? h('button', { type: 'button', class: 'secondary danger', id: 'bm-delete', onclick: remove }, icon('trash'), tr('bm_delete')) : null,
      h('button', { type: 'submit', class: 'primary-btn', id: 'bm-save' }, tr('bm_save'))),
    h('p', { class: 'fine', text: tr('bm_privacy') }),
  );
  const input = $('bm-name');
  input.value = draft.name; // `value` as an attribute is only the default
  if (keep != null) input.setSelectionRange(keep, keep);
}

function useMine() {
  ctx.locate((lat, lon) => setPoint(lat, lon), (text) => {
    draft.note = text;
    if ($('bookmark').open) renderEditor();
  });
}

function pickPoint() {
  const reopen = () => openEditor();
  $('bookmark').close();
  ctx.pick(tr('bm_pick_hint', { name: draft.name.trim() || kindName(draft.kind) }), (lat, lon) => setPoint(lat, lon), reopen);
}

export function initBookmarks(context) {
  ctx = context;
  const dialog = $('bookmark');
  $('bm-form').addEventListener('submit', (e) => {
    e.preventDefault();
    save();
  });
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
    if (dialog.open && draft) renderEditor();
    onList();
  });
}
