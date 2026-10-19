// «Ассистент»: one input, the conversation and the map beside it. The dialogue state is the server's `DialogState`
// (walks.dialog), kept in this tab only (sessionStorage) and sent back with every message. The panel owns the
// conversation; the map shows the places of the latest search, the way to the selected one (or the plan's whole route),
// and the two stay in step: a row or a card selects its pin, a pin selects its row, hover goes both ways.

import { api } from './api.js';
import * as bookmarks from './bookmarks.js';
import { detailsView, statusEl } from './cards.js';
import { updateChrome } from './chrome.js';
import { h, icon, isPhone } from './dom.js';
import { count, dayAndTime, minutes, percent, stateOf } from './fmt.js';
import { currentLang, langFixed, onLang, setLang, tr, withLang } from './i18n.js';
import * as mapView from './map.js';
import { renderAnswer, renderError, renderFolded, renderThinking } from './thread.js';

const STORE = 'anyq.dialog';
const BUDGETS = [30, 60, 120];
const WAIT_SHAPE = 300; // ms before the skeleton of the answer shows
const WAIT_STEPS = 3000; // ms before the steps do
const COMPANY = ['solo', 'pair', 'kids'];
const WEATHER = ['now', 'frost', 'rain', 'smog'];

let app;
let sheet;
const listeners = new Set(); // told when the thread changes (plate, legend)
const S = {
  where: null, // {preset, lat, lon}
  dialog: null, // DialogState of the last answer
  at: null, // «23:00» of a scenario or of the user's override; null: now
  weather: 'now',
  budget: null,
  company: null,
  items: [], // [{id, text, status, resp, open, before, where}]
  seq: 0,
};
const ui = { sel: null, detail: null }; // what is selected / opened right now (not kept)

const $ = (id) => document.getElementById(id);

function save() {
  const items = S.items.filter((i) => i.status === 'done').slice(-8);
  sessionStorage.setItem(STORE, JSON.stringify({ ...S, items }));
}

function restore() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORE) || 'null');
    if (saved && saved.where) Object.assign(S, saved);
  } catch {
    sessionStorage.removeItem(STORE);
  }
}

function presetOf(id) {
  return app.config.presets.find((p) => p.id === id);
}

export function whereName() {
  if (S.where.label) return S.where.label;
  if (S.where.device) return tr('loc_device');
  const preset = S.where.preset && presetOf(S.where.preset);
  return preset ? preset.names[currentLang()] : tr('loc_point');
}

const GENERIC = ['eat', 'coffee', 'walk', 'kids', 'museum', 'evening'];

function genericAsks() {
  return GENERIC.map((id) => ({ id, label: tr(`sug_${id}`), text: tr(`sug_${id}_q`) }));
}

function changed() {
  for (const fn of listeners) fn();
}

export function onThread(fn) {
  listeners.add(fn);
}

export function hasThread() {
  return S.items.length > 0;
}

export function where() {
  return S.where;
}

// what the plate shows: the time of the next search
export function state() {
  return { at: S.at };
}

// ---------------------------------------------------------------- location

export function setWhere(where, { fly = true } = {}) {
  const before = S.where;
  S.where = where;
  showWhere();
  paintYou();
  updateChrome();
  // the answer on screen was measured from the old place: when the start moves (not when the page is only opening) the
  // last question is asked again from the new one, as it is for a new time, so the minutes and the route never disagree
  const moved = fly && before && lastDone() && (Math.abs(before.lat - where.lat) > 0.0004 || Math.abs(before.lon - where.lon) > 0.0004);
  if (fly && !moved) mapView.flyTo([where.lat, where.lon], 14.5);
  save();
  if (moved && !S.items.some((i) => i.status === 'pending')) redoLast();
}

// «Старт по умолчанию: Байтерек» while the place is one of the app's own (a preset), «Вы здесь: …» once it is the visitor's
function showWhere() {
  const preset = Boolean(S.where.preset);
  $('where-text').textContent = tr(preset ? 'loc_default' : 'loc_here', { name: whereName() });
  $('where-change').textContent = tr(preset ? 'loc_set' : 'loc_change');
}

// ---------------------------------------------------------------- the composer: options

// what to ask next, as chips: the buttons under the last answer, or the examples of the first screen
function suggestions() {
  const last = lastDone();
  const chips = last ? last.resp.turn.chips || [] : [];
  if (chips.length) {
    const ctx = answerCtx(last);
    return chips.map((chip) =>
      h('button', { type: 'button', class: `chip small${chip.kind === 'reset' ? ' reset' : ''}`, onclick: () => ctx.onChip(chip) },
        chip.kind === 'reset' ? icon('refresh') : null, chip.label));
  }
  return genericAsks().map((s) => h('button', { type: 'button', class: 'chip small', title: s.text, onclick: () => send(s.text, { fresh: true }) }, s.label));
}

function quickRow() {
  const row = $('quick');
  row.replaceChildren();
  const group = (items, current, label, onPick) =>
    items.map((value) =>
      h('button', {
        type: 'button',
        class: 'chip small',
        'aria-pressed': String(current === value),
        onclick: () => onPick(current === value ? null : value),
      }, label(value)));
  // on a phone the ribbon above the keyboard starts with what to ask next; a laptop has those under the answer
  if (isPhone()) row.append(...suggestions(), h('span', { class: 'sep', 'aria-hidden': 'true' }));
  row.append(
    ...group(BUDGETS, S.budget, (m) => tr(`dur_${m}`), (v) => {
      S.budget = v;
      quickRow();
    }),
    h('span', { class: 'sep', 'aria-hidden': 'true' }),
    ...group(COMPANY, S.company, (c) => tr(`company_${c}`), (v) => {
      S.company = v;
      quickRow();
    }),
  );
  const custom = S.at !== null || S.weather !== 'now';
  row.append(
    h('span', { class: 'sep', 'aria-hidden': 'true' }),
    h('button', {
      type: 'button',
      class: 'chip small',
      'aria-pressed': String(custom),
      'aria-expanded': String(!$('when-panel').hidden),
      onclick: () => {
        $('when-panel').hidden = !$('when-panel').hidden;
        whenPanel();
        quickRow();
      },
    }, icon('cloud'), custom ? whenLabel() : tr('when_other')),
  );
  condBar();
  save();
}

function whenLabel() {
  const parts = [];
  if (S.at) parts.push(S.at);
  if (S.weather !== 'now') parts.push(tr(`wx_${S.weather}`));
  return parts.join(' · ') || tr('when_now');
}

// what is in force for the next answer, as one small pill each («23:00 ✕», «вдвоём ✕»): the conditions of the panel and
// of the ribbon stay on until they are changed, so they stay in sight, one tap from gone
function activeConditions() {
  const list = [];
  if (S.at) list.push([S.at, () => { S.at = null; changed(); }]);
  if (S.budget) list.push([tr(`dur_${S.budget}`), () => { S.budget = null; }]);
  if (S.company) list.push([tr(`company_${S.company}`), () => { S.company = null; }]);
  if (S.weather !== 'now') list.push([tr(`wx_${S.weather}`), () => { S.weather = 'now'; }]);
  return list;
}

function condBar() {
  const bar = $('cond-bar');
  if (!bar) return;
  const list = activeConditions();
  const was = bar.hidden;
  bar.replaceChildren(...list.map(([label, clear]) =>
    h('button', {
      type: 'button',
      class: 'cond-pill',
      title: tr('cond_clear'),
      'aria-label': `${label}: ${tr('cond_clear')}`,
      onclick: () => {
        clear();
        whenPanel();
        quickRow();
      },
    }, h('span', { text: label }), icon('close'))));
  bar.hidden = !list.length;
  if (was !== bar.hidden && sheet) sheet.refresh();
}

// the weather (and, on a phone, the time of today: a desktop has the plate's time row) next to the input
function whenPanel() {
  const panel = $('when-panel');
  panel.replaceChildren();
  if (panel.hidden) return;
  const pick = (values, current, label, set) =>
    h('div', { class: 'chips' }, values.map((v) =>
      h('button', {
        type: 'button',
        class: 'chip small',
        'aria-pressed': String(current === v),
        onclick: () => {
          set(v);
          whenPanel();
          quickRow();
        },
      }, label(v))));
  const toggle = (get, set) => (v) => set(get() === v ? null : v); // a second tap on the picked choice lets it go
  const on = activeConditions();
  panel.append(
    on.length
      ? h('div', { class: 'cond-note' },
        h('span', { text: `${tr('cond_active')}: ${on.map(([label]) => label).join(' · ')}. ${tr('cond_panel_on')}` }),
        h('button', {
          type: 'button',
          class: 'link',
          onclick: () => {
            for (const [, clear] of on) clear();
            whenPanel();
            quickRow();
          },
        }, tr('cond_reset')))
      : null,
    h('div', { class: 'when-time' },
      h('p', { class: 'label', text: tr('when_time') }),
      pick(['now', '19:00', '23:00'], S.at || 'now', (v) => (v === 'now' ? tr('when_now') : tr('when_at', { t: v })), (v) => {
        S.at = v === 'now' ? null : v;
        changed();
      })),
    // the field's ribbon has the same two groups, but only while the keyboard is up: a phone gets them here too
    ...(isPhone()
      ? [
        h('p', { class: 'label', text: tr('when_budget') }),
        pick(BUDGETS, S.budget, (m) => tr(`dur_${m}`), toggle(() => S.budget, (v) => { S.budget = v; })),
        h('p', { class: 'label', text: tr('when_company') }),
        pick(COMPANY, S.company, (c) => tr(`company_${c}`), toggle(() => S.company, (v) => { S.company = v; })),
      ]
      : []),
    h('p', { class: 'label', text: tr('when_weather') }),
    pick(WEATHER, S.weather, (v) => tr(`wx_${v}`), (v) => {
      S.weather = v;
    }),
    h('p', { class: 'fine', text: tr('when_note') }),
  );
}

// ---------------------------------------------------------------- the map beside the answer

function lastDone() {
  for (let i = S.items.length - 1; i >= 0; i -= 1) if (S.items[i].status === 'done') return S.items[i];
  return null;
}

const placesOf = (item) => (item && item.resp && item.resp.turn.places) || [];

function lastSearch() {
  for (let i = S.items.length - 1; i >= 0; i -= 1) {
    const item = S.items[i];
    if (item.status === 'done' && item.resp.turn.kind !== 'place_answer' && placesOf(item).length) return item;
  }
  return null;
}

// The map shows the latest search; an answer about places that search already showed only selects one of them, and
// an answer about a place it did not show puts that place on the map.
function mapItem() {
  const last = lastDone();
  if (!last) return null;
  const turn = last.resp.turn;
  if (turn.kind === 'place_answer' && turn.places.length) {
    const base = lastSearch();
    if (base && turn.places.every((p) => placesOf(base).some((q) => q.id === p.id))) return base;
  }
  if (turn.places.length) return last;
  // a question back, thanks or goodbye take nothing off the map: the places of the last search stay where they were
  return ['clarify', 'thanks', 'bye'].includes(turn.kind) ? lastSearch() : null;
}

// the plan's legs, each from the point the previous one ended at: the marker for the first, the place's pin for the rest
function planLegs(item, places, origin) {
  const { route } = item.resp.turn;
  if (!route || route.kind !== 'plan' || route.stops.length < 2) return [];
  const shapes = item.resp.route_shape || [];
  const byId = new Map(places.map((p) => [p.id, p]));
  const legs = [];
  let prev = origin;
  route.stops.forEach((id, i) => {
    const p = byId.get(id);
    if (!p) return;
    const to = [p.lat, p.lon];
    const line = shapes[i] && shapes[i].length > 1 ? [prev, ...shapes[i], to] : null;
    legs.push({ from: prev, to, text: tr('min_short', { n: route.legs_min[i] }), shape: line });
    prev = to;
  });
  return legs;
}

function numberOf(id) {
  const item = mapItem();
  if (item && item.resp.turn.kind === 'place_answer') return null; // a place asked about by name has no number
  const i = placesOf(item).findIndex((p) => p.id === id);
  return i < 0 ? 1 : i + 1;
}

// an answer about a place says the way the search measured when the map shows that place from it
function walkOf(id) {
  const hit = placesOf(mapItem()).find((p) => p.id === id);
  return hit ? hit.walk : null;
}

// where the answer's way starts when that is not the person's own point (an answer «рядом с домом» is measured from
// the saved place): the turn's origin, when it lies away from the point the question was asked at; else null
function answerStart(item) {
  const o = item && item.resp && item.resp.turn && item.resp.turn.origin;
  const asked = item && item.where;
  if (!Array.isArray(o) || o.length !== 2 || !Number.isFinite(o[0]) || !Number.isFinite(o[1]) || (!o[0] && !o[1]) || !asked) return null;
  return Math.abs(o[0] - asked[0]) > 0.0012 || Math.abs(o[1] - asked[1]) > 0.0012 ? o : null;
}

function originOf(item) {
  return answerStart(item) || (item && item.where) || [S.where.lat, S.where.lon];
}

// the marker of the map: «Вы здесь» at the person's point, or at the start of the way of the answer on screen with
// «от «Дом»», so the line never begins at a point the minutes were not measured from
function paintYou() {
  const item = mapItem();
  const start = answerStart(item);
  const here = [S.where.lat, S.where.lon];
  const name = start && item.resp.state && item.resp.state.bookmark;
  mapView.setYou(start || here, start ? tr(name ? 'route_from' : 'route_from_start', { name }) : tr('you_marker'));
}

export function showOnMap({ fit = true } = {}) {
  const item = mapItem();
  const places = placesOf(item);
  const origin = originOf(item);
  paintYou();
  const legs = (item && item.resp.place_legs) || [];
  mapView.setPlaces(
    places.map((p, i) => ({
      id: p.id,
      lat: p.lat,
      lon: p.lon,
      n: item.resp.turn.kind === 'place_answer' ? null : i + 1,
      name: p.name,
      kind: p.kind,
      state: stateOf(p),
      stateText: p.hours.text,
      primary: i === 0 && item.resp.turn.kind !== 'place_answer',
      leg: legs[i] || null,
    })),
    (i) => select(places[i].id),
  );
  mapView.setRoute(item ? planLegs(item, places, origin) : []);
  if (!places.some((p) => p.id === ui.sel)) ui.sel = places.length ? places[0].id : null;
  mapView.selectPlace(ui.sel);
  updateChrome();
  if (fit && places.length) mapView.fit([origin, ...places.map((p) => [p.lat, p.lon])]);
}

// A row, a card or a pin selects its place: it becomes the main card (the one it replaces falls back to a row, the
// sheet keeps its position) and the way on the map changes, the camera does not move.
function select(id) {
  const same = ui.sel === id;
  ui.sel = id;
  mapView.selectPlace(id);
  if (same) return;
  render(); // the chosen place becomes the main card, the one it replaces falls back to a row
  const card = isPhone() ? null : document.querySelector(`#thread .card.primary[data-pid="${CSS.escape(id)}"]`);
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hover(id) {
  mapView.hoverPlace(id);
  for (const el of document.querySelectorAll('#thread [data-pid]')) el.classList.toggle('hot', el.dataset.pid === id);
}

function openDetails(id) {
  ui.detail = id;
  ui.sel = id;
  mapView.selectPlace(id);
  render();
  $('thread-scroll').scrollTop = 0;
  if (sheet) sheet.lock(true); // a phone: the sheet is full while a place is open
}

export function closeDetails() {
  ui.detail = null;
  if (sheet) sheet.lock(false);
  render();
}

// ---------------------------------------------------------------- the conversation

function answerCtx(item) {
  return {
    turnId: item.id,
    at: item.resp.at,
    origin: originOf(item),
    sel: ui.sel,
    numberOf,
    walkOf,
    profileOn: app.memory.on(),
    onProfile: (act) => app.memory.act(act),
    onSelect: (id) => select(id),
    onHover: hover,
    onDetails: openDetails,
    onChip: (chip) => (chip.kind === 'reset' ? newSearch() : send(chip.send)),
    onRemember: async (chip, btn) => {
      btn.disabled = true;
      const ok = await app.memory.act({ action: 'remember', key: chip.key });
      if (ok) btn.prepend(icon('check'));
      else btn.disabled = false;
    },
    onOpen: () => {
      item.open = true;
      render();
    },
  };
}

function findPlace(id) {
  for (const item of [mapItem(), ...S.items].filter(Boolean)) {
    const hit = placesOf(item).find((p) => p.id === id);
    if (hit) return { place: hit, item };
  }
  return null;
}

function detailsLi() {
  const found = findPlace(ui.detail);
  if (!found) {
    ui.detail = null;
    return null;
  }
  const { place, item } = found;
  const ctx = answerCtx(item);
  return withLang(item.resp.turn.lang, () => h('li', { class: 'turn' }, detailsView(place, {
    n: numberOf(place.id),
    at: item.resp.at,
    origin: ctx.origin,
    sel: ui.sel,
    profileOn: ctx.profileOn,
    onProfile: ctx.onProfile,
    onBack: closeDetails,
  })));
}

// «БАЙТЕРЕК · ПН 14:00»: where and when the answer is about
function contextLabel(item) {
  const preset = presetOf(S.where.preset);
  const name = item.where && preset && Math.abs(preset.lat - item.where[0]) < 0.002 ? preset.names[currentLang()] : whereName();
  return h('p', { class: 'lbl ctxl', text: `${name} · ${dayAndTime(item.resp && item.resp.at)}` });
}

// the phone's top bar says what was asked; a tap on it edits the question, the cross starts over
function queryPill() {
  const last = S.items[S.items.length - 1];
  $('qpill').hidden = !last;
  document.body.classList.toggle('has-thread', Boolean(last));
  if (!last) return;
  $('q-text').textContent = last.text;
  const done = lastDone();
  const reset = done && (done.resp.turn.chips || []).find((c) => c.kind === 'reset');
  $('q-new').setAttribute('aria-label', reset ? reset.label : tr('close'));
}

// while the visitor types the sheet is short: the place of the answer in one line stands for the whole card
function miniRow() {
  const box = $('sheet-mini');
  const found = ui.sel && findPlace(ui.sel);
  if (!found) {
    box.replaceChildren();
    box.hidden = true;
    return;
  }
  const { place } = found;
  const n = numberOf(place.id);
  box.replaceChildren(
    n ? h('span', { class: 'num sel', text: String(n) }) : null,
    h('span', { class: 'mn', text: place.name }),
    statusEl(place),
    h('span', { class: 'mm', text: minutes(place.walk.minutes, place.walk.method) }),
  );
  box.setAttribute('aria-label', place.name);
  box.hidden = false;
}

function render() {
  const thread = $('thread');
  thread.replaceChildren();
  $('hello').hidden = S.items.length > 0;
  $('composer').classList.toggle('has-thread', S.items.length > 0);
  $('view-assistant').classList.toggle('has-thread', S.items.length > 0);
  $('view-assistant').classList.toggle('on-details', Boolean(ui.detail));
  const view = ui.detail ? detailsLi() : null;
  if (view) {
    thread.append(view);
  } else {
    const last = S.items.length - 1;
    S.items.forEach((item, idx) => {
      const li = h('li', { class: `turn${item.status === 'pending' ? ' pending' : ''}`, id: `turn-${item.id}` });
      const folded = idx !== last && !item.open && item.status === 'done';
      if (idx === 0 && item.resp) li.append(contextLabel(item));
      li.append(h('p', { class: 'u', text: item.text }));
      if (folded) li.append(renderFolded(item, answerCtx(item)));
      else if (item.status === 'pending') li.append(renderThinking(`thinking-${item.id}`, item.stages || [], item.phase || 0));
      else if (item.status === 'error') li.append(renderError(() => send(item.text, { retry: item })));
      else li.append(renderAnswer(item.resp, answerCtx(item)));
      thread.append(li);
    });
  }
  queryPill();
  miniRow();
  if (isPhone()) quickRow();
  updateChrome();
  changed();
  if (sheet) sheet.refresh();
}

function scrollToTurn(item) {
  const li = document.getElementById(`turn-${item.id}`);
  if (!li) return;
  const box = $('thread-scroll');
  box.scrollTop = Math.max(li.offsetTop - box.offsetTop - 4, 0);
}

function payload(text, item) {
  return {
    text,
    lat: S.where.lat,
    lon: S.where.lon,
    lang: currentLang(),
    lang_fixed: langFixed(),
    at: S.at,
    weather: S.weather,
    budget_min: S.budget,
    company: S.company,
    state: item.before,
    profile_on: app.memory.on(),
    profile_id: app.memory.id(),
    bookmarks: bookmarks.forRequest(),
  };
}

export async function send(text, { retry = null, fresh = false } = {}) {
  const clean = String(text || '').trim();
  if (!clean) return;
  const item = retry || { id: `t${(S.seq += 1)}`, text: clean, status: 'pending', resp: null, open: false, where: [S.where.lat, S.where.lon] };
  item.status = 'pending';
  item.stages = [];
  item.phase = 0;
  if (ui.detail && sheet) sheet.lock(false);
  ui.detail = null;
  if (!retry) {
    item.before = fresh ? null : S.dialog;
    S.items.push(item);
  }
  $('composer-input').blur(); // the keyboard goes away; the sheet comes back to half with the answer
  render();
  scrollToTurn(item);
  setBusy(true);
  // the wait: nothing for 300 ms (a quick answer never flashes a placeholder), then the shape of the answer, after 3 s the steps
  const refresh = () => {
    const el = document.getElementById(`thinking-${item.id}`);
    if (el) el.replaceWith(renderThinking(`thinking-${item.id}`, item.stages, item.phase));
    if (sheet) sheet.refresh();
  };
  const timers = [[WAIT_SHAPE, 1], [WAIT_STEPS, 2]].map(([ms, phase]) =>
    setTimeout(() => {
      item.phase = phase;
      refresh();
    }, ms));
  const onStage = (stage) => {
    item.stages.push(stage);
    refresh();
  };
  try {
    const resp = await api.turn(payload(clean, item), onStage);
    item.resp = resp;
    item.status = 'done';
    S.dialog = resp.state;
    // the page takes the language of the visitor's first message (when they never picked one); later messages never flip
    // the interface under a thread already on screen: only the language button does
    const firstAnswer = !S.items.some((i) => i !== item && i.status === 'done');
    if (firstAnswer && !langFixed() && resp.turn.lang !== currentLang()) setLang(resp.turn.lang);
    ui.sel = resp.turn.places.length ? resp.turn.places[0].id : null;
    render();
    if (sheet) sheet.snap('half');
    showOnMap();
    requestAnimationFrame(() => scrollToTurn(item));
  } catch {
    item.status = 'error';
    render();
  } finally {
    setBusy(false);
    for (const t of timers) clearTimeout(t);
    save();
  }
}

function setBusy(busy) {
  document.querySelector('#composer .send').disabled = busy;
}

export function newSearch() {
  S.items = [];
  S.dialog = null;
  ui.sel = null;
  ui.detail = null;
  render();
  showOnMap({ fit: false });
  if (sheet) sheet.snap('half');
  mapView.flyTo([S.where.lat, S.where.lon], 14.5);
  save();
  if (!isPhone()) $('composer-input').focus(); // on a phone the keyboard would cover the examples
}

// the time row: the next search (and the answer on screen, asked again) is at this time of today; null: now
export function setAt(at) {
  S.at = at;
  whenPanel();
  quickRow();
  redoLast();
}

// the last question asked again, in the current language or at the current time: it replaces that answer
function redoLast() {
  const last = lastDone();
  if (!last) {
    changed();
    return;
  }
  S.items = S.items.filter((i) => i !== last);
  S.dialog = last.before;
  send(last.text);
}

// the first screen's chips: generic asks that keep the current place and time; «Мои места» opens the list of saved places
function suggestionChips() {
  const box = $('starters');
  box.replaceChildren(
    ...genericAsks().map((s) => h('button', { type: 'button', class: 'chip', title: s.text, dataset: { suggest: s.id }, onclick: () => send(s.text, { fresh: true }) }, s.label)),
    h('button', { type: 'button', class: 'chip marks-chip', id: 'hello-marks', onclick: () => app.memory.open() }, icon('home'), tr('bm_title')),
  );
}

// «В данных»: how much there is and how much of it has hours (the honest share, from /api/data)
export function renderFacts() {
  const box = $('facts');
  const cov = app.coverage;
  if (!cov) {
    box.replaceChildren();
    return;
  }
  box.replaceChildren(
    h('p', { class: 'lbl', text: tr('facts_in_data') }),
    h('p', { class: 'row' }, h('b', { class: 'tnum', text: count(cov.places) }), ` ${tr('facts_places', { n: '' }).trim()}`, ' · ', tr('facts_hours', { p: '' }).trim(), ' ', h('b', { class: 'tnum', text: percent(cov.hours) })),
    h('p', { class: 'cov', text: tr('facts_note') }),
  );
}

// The language selector: the last answer is asked again in the chosen language (it replaces that answer).
function relang(_lang, { user }) {
  suggestionChips();
  quickRow();
  whenPanel();
  renderFacts();
  if (S.where) {
    showWhere();
    paintYou();
  }
  const last = lastDone();
  if (!user || !last) {
    render();
    return;
  }
  redoLast();
}

function autosize(area) {
  area.style.height = 'auto';
  area.style.height = `${Math.min(area.scrollHeight, 200)}px`;
}

export function initAssistant(ctx, sheetCtl) {
  app = ctx;
  sheet = sheetCtl;
  restore();
  const start = presetOf(app.config.start);
  if (!S.where) S.where = { preset: start.id, lat: start.lat, lon: start.lon };
  const form = $('composer');
  const area = $('composer-input');
  form.insertBefore(h('div', { class: 'when-panel', id: 'when-panel', hidden: true }), form.querySelector('.ask'));
  form.insertBefore(h('div', { class: 'quick', id: 'quick' }), $('when-panel'));
  form.insertBefore(h('div', { class: 'cond', id: 'cond-bar', hidden: true, role: 'group', 'aria-label': tr('cond_active') }), form.querySelector('.where'));
  // a tap on a chip above the keyboard keeps the focus in the field: the ribbon is drawn again after the tap, and a
  // focused button that disappears would take the keyboard (and the short form of the sheet) away with it
  for (const id of ['quick', 'when-panel']) $(id).addEventListener('mousedown', (e) => e.target.closest('button') && e.preventDefault());
  $('composer').querySelector('.send').append(icon('send'));
  form.querySelector('.where-icon').append(icon('pin'));
  $('opts-toggle').addEventListener('click', () => {
    const open = form.classList.toggle('opts-open');
    $('opts-toggle').setAttribute('aria-expanded', String(open));
    if (isPhone()) { // the panel is the options: time, how long, company, weather
      $('when-panel').hidden = !open;
      whenPanel();
      quickRow();
      if (sheet) sheet.snap(open ? 'full' : 'half'); // the panel is tall: the list above it needs the whole sheet
    }
    updateChrome();
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = area.value;
    area.value = '';
    autosize(area);
    send(text);
  });
  area.addEventListener('input', () => autosize(area));
  area.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && ui.detail && !document.querySelector('dialog[open]')) closeDetails();
  });
  // «Ещё варианты (2) ˄» under the card on a phone: a tap opens the sheet to the rest of the list
  $('thread').addEventListener('click', (e) => {
    if (isPhone() && sheet && e.target.closest('.sub')) sheet.snap('full');
  });
  mapView.onHover((id) => {
    for (const el of document.querySelectorAll('#thread [data-pid]')) el.classList.toggle('hot', el.dataset.pid === id);
  });
  onLang(relang);
  suggestionChips();
  quickRow();
  setWhere(S.where, { fly: false });
  $('q-edit').querySelector('.q-icon').append(icon('search'));
  $('q-new').append(icon('close'));
  $('q-edit').addEventListener('click', () => {
    const asked = S.items[S.items.length - 1];
    if (!asked) return;
    area.value = asked.text;
    autosize(area);
    area.focus();
    area.select();
  });
  $('q-new').addEventListener('click', newSearch);
  $('sheet-mini').addEventListener('click', () => area.blur());
  matchMedia('(max-width: 760px)').addEventListener('change', render);
  const last = lastDone();
  if (last) ui.sel = last.resp.turn.places.length ? last.resp.turn.places[0].id : null;
  render();
  if (last) showOnMap();
  else mapView.flyTo([S.where.lat, S.where.lon], 14.5, undefined, 0);
}
