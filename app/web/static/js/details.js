// Everything the page knows about one place as a «label — value» table: the hours with their source and date, the way,
// the nearest stop, residents' marks, why, what to do, phone, site, price, sources; then «Были здесь?» and the marks.
// On a desktop it is the panel's details view; on a phone the same table sits in the card's «Подробнее» disclosure.
// Nothing here decides what a place is: every word comes from the turn, every link is built from its fields.

import { api } from './api.js';
import { h, icon } from './dom.js';
import { isoDate, metres, minutes } from './fmt.js';
import { tr } from './i18n.js';

const reported = new Set(); // poi ids marked from this tab: one report per place
let marksOn = true; // false: this stand saves no residents' marks, so no button invites one

export function setMarksOn(on) {
  marksOn = on;
}

function pointsPath(origin, place) {
  return encodeURIComponent(`${origin[1]},${origin[0]}|${place.lon},${place.lat}`);
}

export function deepLinks(place, origin) {
  return {
    gis: `https://2gis.kz/astana/directions/tab/pedestrian/points/${pointsPath(origin, place)}`,
    yandex: `https://yandex.kz/maps/?rtext=${origin[0]},${origin[1]}~${place.lat},${place.lon}&rtt=pd`,
  };
}

export function telHref(phone) {
  const first = String(phone).split(/[;,]/)[0];
  const digits = first.replace(/[^\d+]/g, '');
  return digits.length >= 6 ? `tel:${digits}` : null;
}

function siteHref(url) {
  const first = String(url).split(/[;\s]/)[0];
  if (/^https?:\/\//i.test(first)) return first;
  return /^[\w.-]+\.[a-z]{2,}/i.test(first) ? `https://${first}` : null;
}

export function link(href, text) {
  return h('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
}

export function sourceLinks(sources) {
  return sources.flatMap((s, i) => [i ? ', ' : '', s.url ? link(s.url, s.label) : s.label]);
}

// «Источник часов: OpenStreetMap · данные на 17.10.2026»: whose hours the status rests on, with the page they came from
export function hoursSource(place) {
  const hrs = place.hours;
  if (!hrs.source) return [tr('status_from_none')];
  const parts = [tr('status_from'), ' ', ...sourceLinks([hrs.source])];
  if (hrs.data_date) parts.push(` · ${tr('data_on_date', { date: isoDate(hrs.data_date) })}`);
  return parts;
}

// «Вход: 1000 тг. · реестр музеев e-museum.kz · данные на 17.10.2026»: the place's own wording, never turned into a
// number, whose it is and when it was read
export function priceValue(place) {
  const price = place.price;
  if (!price) return null;
  return [
    price.text,
    price.source ? [' · ', ...sourceLinks([price.source])] : '',
    price.date ? ` · ${tr('data_on_date', { date: isoDate(price.date) })}` : '',
  ];
}

export function priceParts(place) {
  const value = priceValue(place);
  return value && [`${tr('d_price')}: `, ...value];
}

// ---------------------------------------------------------------- «Были здесь?» and the marks

// «Всё верно» confirms what the card says right now; «Другие часы» needs hours to disagree with.
function reportOptions(place) {
  const s = place.hours.state;
  const opts = [];
  opts.push(s === 'open' ? ['report_closed', 'was_closed'] : ['report_open', 'was_open']);
  if (s === 'unknown') opts.push(['report_closed', 'was_closed']);
  if (place.hours.raw) opts.push(['report_other_hours', 'hours_differ']);
  if (s === 'open') opts.push(['report_ok', 'was_open']);
  if (s === 'closed') opts.push(['report_ok', 'was_closed']);
  return opts;
}

function reportBlock(place) {
  if (!marksOn) return h('p', { class: 'fine', text: tr('marks_off') });
  const status = h('p', { class: 'thanks', role: 'status' });
  const row = h('div', { class: 'chips' });
  const done = reported.has(place.id);
  for (const [key, signal] of reportOptions(place)) {
    const btn = h('button', { type: 'button', class: 'chip', disabled: done }, tr(key));
    btn.addEventListener('click', async () => {
      for (const b of row.querySelectorAll('button')) b.disabled = true;
      try {
        await api.report({ poi_id: place.id, signal });
        reported.add(place.id);
        btn.classList.add('done');
        btn.prepend(icon('check'));
        status.textContent = tr('report_thanks');
      } catch {
        status.textContent = tr('mark_fail');
        for (const b of row.querySelectorAll('button')) b.disabled = false;
      }
    });
    row.append(btn);
  }
  if (done) status.textContent = tr('report_done');
  return h('div', { class: 'report' }, h('p', { class: 'subhead', text: tr('report_q') }), row, status);
}

function marksBlock(place) {
  if (!marksOn) return null;
  const status = h('p', { class: 'thanks', role: 'status' });
  const row = h('div', { class: 'chips' });
  for (const signal of ['has_socket', 'has_wifi', 'quiet', 'noisy']) {
    const btn = h('button', { type: 'button', class: 'chip' }, tr(`sig_${signal}`));
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await api.report({ poi_id: place.id, signal });
        btn.prepend(icon('check'));
        status.textContent = tr('report_thanks');
      } catch {
        btn.disabled = false;
        status.textContent = tr('mark_fail');
      }
    });
    row.append(btn);
  }
  return h('div', { class: 'marks' }, h('p', { class: 'subhead', text: tr('marks_q') }), row, status);
}

function mineBlock(place, onProfile) {
  const row = h('div', { class: 'chips' });
  for (const [key, action] of [['profile_visit', 'visit'], ['profile_like', 'like']]) {
    const btn = h('button', { type: 'button', class: 'chip' }, tr(key));
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const ok = await onProfile({ action, poi_id: place.id });
      if (ok) btn.prepend(icon('check'));
      else btn.disabled = false;
    });
    row.append(btn);
  }
  return h('div', { class: 'mine' }, h('p', { class: 'subhead', text: tr('mine_q') }), row);
}

// ---------------------------------------------------------------- the table

function walkWords(place) {
  const w = place.walk;
  const how = w.method === 'valhalla' ? tr('walk_street') : tr(w.method === 'straight' ? 'walk_straight' : 'walk_estimate');
  return `${minutes(w.minutes, w.method)} · ${metres(w.distance_m)} · ${how}`;
}

// strip: the day strip element (cards.js builds it; passed in so this module needs no cards.js)
export function detailRows(place, strip) {
  const rows = [];
  const add = (label, ...value) => rows.push(h('dt', { text: label }), h('dd', {}, ...value));
  const hrs = place.hours;
  add(
    tr('d_hours'),
    h('div', { class: 'big' }, hrs.text),
    strip,
    hrs.raw ? h('div', { class: 'raw', text: hrs.raw }) : h('div', { class: 'muted', text: tr('d_hours_none') }),
    h('div', { class: 'muted' }, ...hoursSource(place)),
    hrs.note ? h('div', { class: 'issue', text: hrs.note }) : null,
  );
  add(tr('d_walk'), h('span', { class: 'mono', text: walkWords(place) }));
  if (place.stop) add(tr('d_stop'), place.stop.text, place.stop.source ? [' · ', ...sourceLinks([place.stop.source])] : '');
  if (place.lrt_hint) add(tr('d_transit'), place.lrt_hint);
  if (place.people && place.people.text) {
    add(tr('d_people'), place.people.text, place.people.demo ? ` (${tr('demo_word')})` : '');
  }
  if (place.why) add(tr('d_why'), place.why);
  if (place.what_to_do) {
    add(tr('d_todo'), place.ai_idea ? h('span', { class: 'tag ai' }, icon('spark'), tr('ai_idea')) : null, ' ', place.what_to_do);
  }
  if (place.note) add(tr('d_note'), place.note);
  if (place.address) add(tr('d_address'), place.address);
  const tel = place.phone && telHref(place.phone);
  if (place.phone) add(tr('d_phone'), tel ? h('a', { href: tel, class: 'mono', text: place.phone }) : place.phone);
  const site = place.website && siteHref(place.website);
  if (site) add(tr('d_website'), link(site, String(place.website).replace(/^https?:\/\//, '').replace(/\/$/, '')));
  const price = priceValue(place);
  if (price) add(tr('d_price'), ...price);
  if (place.stay_min) add(tr('d_stay'), tr('stay_min', { n: place.stay_min }));
  if (place.sources.length) add(tr('d_sources'), ...sourceLinks(place.sources));
  if (place.data_date) add(tr('d_date'), isoDate(place.data_date));
  return h('dl', { class: 'dl' }, rows);
}

// the blocks that ask the visitor for something
export function askBlocks(place, opts) {
  return [reportBlock(place), marksBlock(place), opts.profileOn ? mineBlock(place, opts.onProfile) : null];
}
