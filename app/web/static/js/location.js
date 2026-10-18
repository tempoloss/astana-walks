// «Где вы?»: one of the known places, one of «Мои места», the device's location, or a tap on the map; the map's own
// «Моё местоположение» button does the second-to-last. The point is rounded to ~100 m before it leaves the page (the
// server rounds it again and never stores it). A device outside Astana is not «here»: the starting point stays.

import { renderList as renderMarks, onListChange, useAsStart } from './bookmarks.js';
import { h, icon } from './dom.js';
import { currentLang, onLang, tr } from './i18n.js';
import * as mapView from './map.js';

const round = (x) => Math.round(x * 1000) / 1000;
const NOTE_MS = 6000;
let app;
let assistant;
let picking = false;
let noteTimer = 0;

const $ = (id) => document.getElementById(id);

function list() {
  const box = $('loc-list');
  box.replaceChildren(h('p', { class: 'label', text: tr('loc_places') }));
  const here = assistant.where();
  for (const p of app.config.presets) {
    box.append(
      h('button', {
        type: 'button',
        'aria-pressed': String(here.preset === p.id),
        onclick: () => choose({ preset: p.id, lat: p.lat, lon: p.lon }),
      }, icon('pin'), p.names[currentLang()]),
    );
  }
  renderMarks($('loc-marks'), (b) => {
    $('location').close();
    useAsStart(b);
  });
}

function choose(where) {
  $('location').close();
  assistant.setWhere({ ...where, lat: round(where.lat), lon: round(where.lon) });
}

// ---------------------------------------------------------------- notes on the map

function note(text) {
  const el = $('map-note');
  el.replaceChildren();
  if (!text) {
    el.hidden = true;
    return;
  }
  el.append(text, h('button', { type: 'button', class: 'link', onclick: () => stopPicking() }, tr('cancel')));
  el.hidden = false;
}

// one plain line on the map for a few seconds (a pick in progress keeps its own note)
function flash(text) {
  if (picking) return;
  const el = $('map-note');
  clearTimeout(noteTimer);
  el.replaceChildren(icon('info'), text);
  el.hidden = false;
  noteTimer = setTimeout(() => !picking && app.showMapNote(), NOTE_MS);
}

let cancelled = null;

function stopPicking({ aborted = true } = {}) {
  picking = false;
  mapView.onPick(null);
  note(null);
  app.showMapNote();
  const again = cancelled;
  cancelled = null;
  if (aborted && again) again();
}

// a tap on the map picks a point: onPoint(lat, lon); onCancel when the visitor gives up
export function pick(hint, onPoint, onCancel) {
  if (app.sheet) app.sheet.snap('peek');
  clearTimeout(noteTimer);
  picking = true;
  cancelled = onCancel || null;
  note(hint);
  mapView.onPick(([lat, lon]) => {
    stopPicking({ aborted: false });
    onPoint(round(lat), round(lon));
    if (app.sheet) app.sheet.snap('half');
  });
}

// ---------------------------------------------------------------- the device's location

// onFound(lat, lon) with a point inside Astana; report(text) says what happened when it did not (or while it waits)
export function locate(onFound, report) {
  if (!navigator.geolocation) {
    report(tr('loc_mine_fail'));
    return;
  }
  mapView.setLocateBusy(true);
  report(tr('loc_mine_wait'));
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      mapView.setLocateBusy(false);
      const lat = round(pos.coords.latitude);
      const lon = round(pos.coords.longitude);
      if (!mapView.inAstana(lat, lon)) {
        report(tr('loc_outside'));
        return;
      }
      report(tr('loc_found'));
      onFound(lat, lon);
    },
    (err) => {
      mapView.setLocateBusy(false);
      report(tr(err && err.code === 1 ? 'loc_denied' : 'loc_mine_fail'));
    },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
  );
}

function mine() {
  const status = $('loc-status');
  locate((lat, lon) => {
    status.textContent = tr('loc_privacy');
    choose({ preset: null, lat, lon });
  }, (text) => {
    status.textContent = text;
  });
}

function openDialog() {
  list();
  $('loc-status').textContent = tr('loc_privacy');
  if (!$('location').open) $('location').showModal();
}

export const isPicking = () => picking;
export { flash };

export function initLocation(ctx, assistantModule) {
  app = ctx;
  assistant = assistantModule;
  app.openLocation = openDialog;
  const dialog = $('location');
  $('where-change').addEventListener('click', openDialog);
  $('loc-mine').prepend(icon('target'));
  $('loc-pick').prepend(icon('map'));
  $('loc-mine').addEventListener('click', mine);
  $('loc-pick').addEventListener('click', () => {
    dialog.close();
    pick(tr('loc_pick_hint'), (lat, lon) => assistant.setWhere({ preset: null, lat, lon }));
  });
  dialog.querySelector('.close').append(icon('close'));
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) dialog.close();
  });
  onLang(() => {
    if (dialog.open) list();
    mapView.setLocateLabel(tr('loc_mine'));
  });
  onListChange(() => dialog.open && list());
  // the map's own button (a laptop) and the top bar's (a phone): the device's place becomes the start, a plain line
  // says when it cannot
  const here = () => locate((lat, lon) => assistant.setWhere({ preset: null, lat, lon }), flash);
  mapView.addLocate(here, tr('loc_mine'));
  $('locate-bar').append(icon('target'));
  $('locate-bar').addEventListener('click', here);
}
