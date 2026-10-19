// «Где вы?»: an address (or a place's name), the device's location, or a tap on the map: nothing else. The map's own
// «Моё местоположение» button does the second. The point is rounded to ~100 m before it leaves the page (the server
// rounds it again and never stores it). A device outside Astana is not «here»: the starting point stays. Until the
// visitor says where they are, the start is the default one and the sheet and the composer say so.

import { addressSearch } from './address.js';
import { setMemoryOpener } from './bookmarks.js';
import { h, icon, isPhone } from './dom.js';
import { initHints } from './places-hints.js';
import { onLang, tr } from './i18n.js';
import * as mapView from './map.js';

const round = (x) => Math.round(x * 1000) / 1000;
const NOTE_MS = 6000;
let app;
let assistant;
let search;
let picking = false;
let noteTimer = 0;

const $ = (id) => document.getElementById(id);

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
    choose({ preset: null, lat, lon, device: true });
  }, (text) => {
    status.textContent = text;
  });
}

// ---------------------------------------------------------------- the sheet

// a start the visitor never set (the default one) says so, and asks where they are
function nudge() {
  const el = $('loc-nudge');
  const here = assistant.where();
  el.hidden = !here.preset;
  el.replaceChildren(...(here.preset ? [icon('info'), h('span', { text: tr('loc_default_note') })] : []));
}

function openDialog() {
  nudge();
  search.reset();
  $('loc-status').textContent = tr('loc_privacy');
  if (!$('location').open) $('location').showModal();
  if (!isPhone()) search.focus(); // on a phone the keyboard would cover the two buttons under the field
}

export const isPicking = () => picking;
export { flash };

export function initLocation(ctx, assistantModule) {
  app = ctx;
  assistant = assistantModule;
  app.openLocation = openDialog;
  setMemoryOpener(() => app.memory.open());
  const dialog = $('location');
  search = addressSearch({
    id: 'loc',
    onPick: (hit) => choose({ preset: null, lat: hit.lat, lon: hit.lon, label: hit.label }),
  });
  $('loc-addr').append(search.el);
  $('where-change').addEventListener('click', openDialog);
  $('loc-mine').prepend(icon('target'));
  $('loc-pick').prepend(icon('map'));
  $('loc-mine').addEventListener('click', mine);
  $('loc-pick').addEventListener('click', () => {
    dialog.close();
    pick(tr('loc_pick_hint'), (lat, lon) => assistant.setWhere({ preset: null, lat, lon }));
  });
  dialog.querySelector('.close').append(icon('close'));
  dialog.querySelector('.close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) dialog.close();
  });
  onLang(() => {
    if (dialog.open) {
      nudge();
      $('loc-status').textContent = tr('loc_privacy');
    }
    mapView.setLocateLabel(tr('loc_mine'));
  });
  // the map's own button (a laptop) and the top bar's (a phone): the device's place becomes the start, a plain line
  // says when it cannot
  const here = () => locate((lat, lon) => assistant.setWhere({ preset: null, lat, lon, device: true }), flash);
  mapView.addLocate(here, tr('loc_mine'));
  $('locate-bar').append(icon('target'));
  $('locate-bar').addEventListener('click', here);
  // a visitor who has already allowed the location needs no tap on the crosshair: the first search starts from them
  // (a visitor who has not is never asked on arrival: the dialog's button and the crosshair ask)
  if (assistant.where().preset && navigator.permissions) {
    navigator.permissions.query({ name: 'geolocation' }).then((perm) => {
      if (perm.state === 'granted' && assistant.where().preset) {
        locate((lat, lon) => assistant.setWhere({ preset: null, lat, lon, device: true }), () => {});
      }
    }).catch(() => {});
  }
  initHints(app, assistant);
}
