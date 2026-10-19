// Boot: strings and the stand's mode from the server, the map, then the three views (Ассистент, Город, Данные) as
// hash routes over one page. The map stays mounted; the panel beside it changes.

import { api } from './api.js';
import * as assistant from './assistant.js';
import { initChrome, updateChrome } from './chrome.js';
import * as city from './city.js';
import * as data from './data.js';
import { initBookmarks } from './bookmarks.js';
import { setMarksOn } from './details.js';
import { h, icon } from './dom.js';
import { applyStatic, currentLang, initStrings, initialLang, onLang, setInitialLang, setLang, tr } from './i18n.js';
import { initLegend, renderLegend } from './legend.js';
import { initLocation, isPicking, locate, pick } from './location.js';
import * as mapView from './map.js';
import * as memory from './memory.js';
import { initPlate } from './plate.js';
import { answerFit, shareFit } from './sheet-fit.js';
import { makeSheet } from './sheet.js';
import { initViewport } from './viewport.js';
import { mountVibeChip } from './vibe-form.js';

const app = { config: null, coverage: null, memory, sheet: null, showMapNote: () => {} };
const sheets = [];
const VIEWS = { '': 'assistant', city: 'city', data: 'data' };
let view = null;

// The page's only notice: one plain line when the app really has no network (the server runs without it).
function banner() {
  const el = document.getElementById('banner');
  el.hidden = !app.config.mode.offline;
  if (el.hidden) return;
  el.replaceChildren(h('p', { class: 'banner-line' }, icon('offline'), h('span', { class: 'banner-text', text: tr('banner_offline') })));
}

function mapNote() {
  const el = document.getElementById('map-note');
  if (mapView.basemapKind() === 'offline') {
    el.replaceChildren(icon('offline'), tr('map_offline_note'));
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

// where the legend stands: it is open where the map needs explaining
function situation() {
  if (view === 'city' || view === 'data') return view;
  if (mapView.basemapKind() === 'offline') return 'offline';
  return assistant.hasThread() ? 'answer' : 'first';
}

function route() {
  const key = location.hash.replace(/^#\/?/, '');
  const next = VIEWS[key] || 'assistant';
  if (next === view) return;
  if (view === 'city') city.hideCity();
  if (view === 'data') data.hideData();
  view = next;
  document.body.dataset.view = next;
  document.getElementById('view-assistant').hidden = next !== 'assistant';
  document.getElementById('view-city').hidden = next !== 'city';
  document.getElementById('view-data').hidden = next !== 'data';
  for (const a of document.querySelectorAll('[data-view]')) {
    if (a.dataset.view === next) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  setMenu(false);
  renderLegend();
  for (const sheet of sheets) sheet.refresh();
  updateChrome();
  if (next === 'assistant') {
    const last = assistant.where();
    if (last && assistant.hasThread()) assistant.showOnMap();
    else if (last) mapView.flyTo([last.lat, last.lon], 14.5);
  }
  if (next === 'city') city.showCity();
  if (next === 'data') data.showData();
  requestAnimationFrame(() => mapView.resize());
}

// the phone's menu: opened over the sheet (the bar lies under a full sheet otherwise)
function setMenu(open) {
  document.getElementById('menu').hidden = !open;
  document.querySelector('.menu-open').setAttribute('aria-expanded', String(open));
  if (open) setLangMenu(false);
  raisePlate();
}

// the language menu: the globe with the current code, three full names behind it
function setLangMenu(open) {
  document.getElementById('lang-pop').hidden = !open;
  document.getElementById('lang-btn').setAttribute('aria-expanded', String(open));
  if (open) setMenu(false);
  raisePlate();
}

// a menu open over a full sheet is above it
function raisePlate() {
  const open = !document.getElementById('menu').hidden || !document.getElementById('lang-pop').hidden;
  document.getElementById('plate').classList.toggle('menu-on', open);
}

function header() {
  const langBtn = document.getElementById('lang-btn');
  const langPop = document.getElementById('lang-pop');
  langBtn.querySelector('.lang-globe').append(icon('globe'));
  langBtn.addEventListener('click', () => setLangMenu(langPop.hidden));
  for (const btn of document.querySelectorAll('[data-lang]')) {
    btn.addEventListener('click', () => {
      setLang(btn.dataset.lang, { user: true });
      setLangMenu(false);
      langBtn.focus();
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !langPop.hidden) {
      setLangMenu(false);
      langBtn.focus();
    }
  });
  const menuBtn = document.querySelector('.menu-open');
  const menu = document.getElementById('menu');
  menuBtn.append(icon('menu'));
  menuBtn.addEventListener('click', () => setMenu(menu.hidden));
  menu.addEventListener('click', () => setMenu(false));
  document.addEventListener('click', (e) => {
    if (!menu.hidden && !menu.contains(e.target) && !menuBtn.contains(e.target)) setMenu(false);
    if (!langPop.hidden && !langPop.contains(e.target) && !langBtn.contains(e.target)) setLangMenu(false);
  });
}

async function boot() {
  const [config, strings] = await Promise.all([api.config(), api.strings()]);
  app.config = config;
  setMarksOn(config.marks !== false);
  initStrings(strings);
  setInitialLang(initialLang({ followBrowser: !config.mode.replay_only }));
  header();
  banner();
  const start = config.presets.find((p) => p.id === config.start);
  const panelA = document.getElementById('view-assistant');
  const sheetA = makeSheet(panelA, { fit: answerFit(panelA), onChange: updateChrome, onBack: assistant.closeDetails });
  const panelC = document.getElementById('view-city');
  const sheetC = makeSheet(panelC, { fit: shareFit(), onChange: updateChrome });
  sheets.push(sheetA, sheetC);
  app.sheet = sheetA;
  app.showMapNote = mapNote;
  initChrome({ 'view-assistant': sheetA, 'view-city': sheetC });
  initViewport({
    onTyping: (on) => {
      sheetA.keyboard(on);
      updateChrome();
    },
    onResize: () => {
      for (const sheet of sheets) sheet.refresh();
      updateChrome();
    },
  });
  // the content of the sheet changes height by itself (fonts, a notice, the field's rows): the positions follow it
  const content = new ResizeObserver(() => sheetA.refresh());
  for (const id of ['thread', 'hello', 'composer', 'banner']) content.observe(document.getElementById(id));
  initLegend(app, situation);
  await mapView.initMap(document.getElementById('map'), {
    center: [start.lat, start.lon],
    offline: config.mode.offline,
    lang: currentLang(),
    hd: config.satellite_hd,
  });
  mapNote();
  await memory.initMemory();
  assistant.initAssistant(app, sheetA);
  mountVibeChip(memory, (text) => assistant.send(text, { fresh: true }));
  initPlate(app, assistant);
  initLocation(app, assistant);
  initBookmarks({
    where: assistant.where,
    whereName: assistant.whereName,
    setWhere: assistant.setWhere,
    locate,
    pick,
    picking: isPicking,
  });
  city.initCity(app);
  data.initData();
  assistant.onThread(renderLegend);
  mapView.onBasemapChange(() => {
    mapNote();
    renderLegend();
  });
  onLang(() => {
    banner();
    mapNote();
    renderLegend();
  });
  window.addEventListener('hashchange', route);
  route();
  applyStatic();
  document.body.dataset.ready = '1';
  // the share of places with hours is the legend's honest line; it arrives after the page is usable
  api.data(currentLang()).then((d) => {
    app.coverage = d.coverage;
    renderLegend();
  }).catch(() => {});
}

boot().catch(() => {
  document.body.replaceChildren(h('p', { class: 'error-row', text: 'Анық: сервер недоступен / server unavailable' }));
});
