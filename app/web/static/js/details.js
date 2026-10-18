// Everything the page knows about one place, grouped by what the person is doing: now (status, today's hours with their
// source and date), getting there (the way, the nearest stop), about the place (why, what to do, price), contacts, and the
// sources behind it all, folded; then «Были здесь?» and the marks. On a desktop it is the panel's details view; on a
// phone the same list fills the sheet. Nothing here decides what a place is: every word comes from the turn, every link
// is built from its fields.

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

// «Источник часов: OpenStreetMap · данные на 17.10.2026»: whose hours the status rests on, with the page they came from.
// Nothing when there are none: the status already says «часы неизвестны», it is not said twice.
export function hoursSource(place) {
  const hrs = place.hours;
  if (!hrs.source) return [];
  const parts = [tr('status_from'), ' ', ...sourceLinks([hrs.source])];
  if (hrs.data_date) parts.push(` · ${tr('data_on_date', { date: isoDate(hrs.data_date) })}`);
  return parts;
}

// the date and the owner of a piece of data, after it: «реестр музеев e-museum.kz · данные на 17.10.2026»
function provenance(source, date) {
  const parts = [];
  if (source) parts.push(...sourceLinks([source]));
  if (date) parts.push(`${parts.length ? ' · ' : ''}${tr('data_on_date', { date: isoDate(date) })}`);
  return parts;
}

// «Вход: 1000 тг. · реестр музеев e-museum.kz · данные на 17.10.2026»: the place's own wording, never turned into a
// number, whose it is and when it was read
export function priceParts(place) {
  const price = place.price;
  if (!price) return null;
  const meta = provenance(price.source, price.date);
  return [`${tr('d_price')}: ${price.text}`, meta.length ? [' · ', ...meta] : ''];
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

// ---------------------------------------------------------------- the groups

function walkWords(place) {
  const w = place.walk;
  const how = w.method === 'valhalla' ? tr('walk_street') : tr(w.method === 'straight' ? 'walk_straight' : 'walk_estimate');
  return `${minutes(w.minutes, w.method)} · ${metres(w.distance_m)} · ${how}`;
}

// a line of a group: a small icon, then the value; a line that holds a link is marked (a phone gives it room to tap)
function line(iconName, ...value) {
  const el = h('div', { class: 'd-line' }, iconName ? icon(iconName) : null, h('div', {}, ...value));
  if (el.querySelector('a')) el.classList.add('has-link');
  return el;
}

function muted(...value) {
  const el = h('div', { class: 'd-muted' }, ...value);
  if (el.querySelector('a')) el.classList.add('has-link');
  return el;
}

function group(title, ...kids) {
  const body = kids.flat().filter(Boolean);
  return body.length ? h('section', { class: 'd-sec' }, h('h3', { text: title }), ...body) : null;
}

// «Сейчас»: the state, the day, the reason it is unknown when there is one, and whose hours these are
function nowGroup(place, strip, status) {
  const hrs = place.hours;
  // unknown: the reason from the data when it has one (the site lists hours without days, a holiday), else the card's
  // own line about it, else one short ask; said here once, not again under «О месте»
  let note = hrs.note;
  if (hrs.state === 'unknown' && !hrs.issue) note = place.note || (hrs.raw ? hrs.note : tr('hours_check'));
  return group(
    tr('d_sec_now'),
    h('div', { class: 'd-status' }, status),
    strip,
    note ? muted(note) : null,
    hoursSource(place).length ? muted(...hoursSource(place)) : null,
  );
}

function wayGroup(place) {
  const stop = place.stop;
  return group(
    tr('d_sec_way'),
    line('walk', walkWords(place)),
    stop ? line('route', stop.text, stop.source ? [' · ', ...sourceLinks([stop.source])] : '') : null,
    place.lrt_hint ? line('route', place.lrt_hint) : null,
  );
}

function aboutGroup(place) {
  const price = place.price;
  const meta = price ? provenance(price.source, price.date) : [];
  const people = place.people && place.people.text ? `${tr('d_people')}: ${place.people.text}${place.people.demo ? ` (${tr('demo_word')})` : ''}` : '';
  return group(
    tr('d_sec_about'),
    place.why ? h('p', { class: 'd-text', text: place.why }) : null,
    place.what_to_do
      ? h('p', { class: 'd-text' }, place.ai_idea ? [h('span', { class: 'tag' }, tr('ai_idea')), ' '] : null, place.what_to_do)
      : null,
    place.note && place.hours.state !== 'unknown' ? h('p', { class: 'd-text', text: place.note }) : null,
    price ? h('div', {}, `${tr('d_price')}: ${price.text}`) : null,
    meta.length ? muted(...meta) : null,
    place.stay_min ? muted(`${tr('d_stay')}: ${tr('stay_min', { n: place.stay_min })}`) : null,
    people ? muted(people) : null,
  );
}

function contactsGroup(place) {
  const tel = place.phone && telHref(place.phone);
  const site = place.website && siteHref(place.website);
  return group(
    tr('d_sec_contacts'),
    place.address ? line('pin', place.address) : null,
    place.phone ? line('phone', tel ? h('a', { href: tel, text: place.phone }) : place.phone) : null,
    site ? line('globe', link(site, String(place.website).replace(/^https?:\/\//, '').replace(/\/$/, ''))) : null,
  );
}

// «Источники», folded: the pages the data came from, the schedule as the source writes it, the day it was read
function sourcesGroup(place) {
  const raw = place.hours.raw;
  const rows = [
    place.sources.length ? muted(...sourceLinks(place.sources)) : null,
    raw ? muted(`${tr('d_hours_raw')}: ${raw}`) : null,
    place.data_date ? muted(tr('data_on_date', { date: isoDate(place.data_date) })) : null,
  ].filter(Boolean);
  if (!rows.length) return null;
  return h('details', { class: 'd-sec d-src' }, h('summary', {}, tr('d_sources'), h('span', { class: 'chev' }, icon('chevron'))), h('div', { class: 'd-src-list' }, rows));
}

// strip: the day strip (null with no schedule), status: the status element; cards.js builds both and passes them in
export function detailSections(place, strip, status) {
  return [nowGroup(place, strip, status), wayGroup(place), aboutGroup(place), contactsGroup(place), sourcesGroup(place)].filter(Boolean);
}

// the blocks that ask the visitor for something
export function askBlocks(place, opts) {
  return [reportBlock(place), marksBlock(place), opts.profileOn ? mineBlock(place, opts.onProfile) : null];
}
