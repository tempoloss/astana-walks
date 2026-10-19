// «Данные»: a dashboard of where the facts come from (a card per source with its licence and links), how complete
// they are (bar charts) and how honest the answers measured, and the credits the licences ask for.

import { api } from './api.js';
import { fmtNumber, h, icon } from './dom.js';
import { currentLang, onLang, tr } from './i18n.js';

let active = false;

const GROUPS = ['places', 'weather', 'moving', 'city'];
const CATEGORY_ROWS = 8; // the rest of the kinds of places sits behind «show all»
const URL_RE = /https?:\/\/[^\s,;)]+/g;

const n = (x) => fmtNumber(x, currentLang());
const pctText = (x) => `${n(x)}%`;

function link(url, label, cls = 'dd-link') {
  return h('a', { class: cls, href: url, target: '_blank', rel: 'noopener noreferrer' }, h('span', { text: label }), icon('external'));
}

const host = (url) => new URL(url).hostname.replace(/^www\./, '');

// 2026-10-16 .. 2026-10-17 -> «16–17.10.2026»
function dateRange(from, to) {
  if (!from) return '—';
  const [y1, m1, d1] = from.split('-');
  if (!to || to === from) return `${d1}.${m1}.${y1}`;
  const [y2, m2, d2] = to.split('-');
  if (y1 === y2 && m1 === m2) return `${d1}–${d2}.${m2}.${y2}`;
  return `${d1}.${m1}.${y1} – ${d2}.${m2}.${y2}`;
}

function tiles(d) {
  const cells = [
    [n(d.coverage.places), tr('dd_tile_places')],
    [pctText(d.coverage.hours), tr('dd_tile_hours')],
    [n(d.cards.length), tr('dd_tile_sources')],
    [dateRange(d.sources.date_from, d.sources.date_to), tr('dd_tile_dates'), 'date'],
  ];
  return h('div', { class: 'dd-tiles' },
    cells.map(([value, label, cls]) => h('div', { class: `dd-tile ${cls || ''}`.trim() }, h('b', { text: value }), h('span', { text: label }))));
}

function card(c, s) {
  const links = h('div', { class: 'dd-links' });
  if (c.licences.length) {
    links.append(h('div', { class: 'dd-row' }, h('span', { class: 'dd-key', text: tr('dd_licence') }),
      c.licences.map((l) => link(l.url, l.label))));
  }
  if (c.links.length) {
    links.append(h('div', { class: 'dd-row' }, h('span', { class: 'dd-key', text: tr('dd_source') }),
      c.links.map((url) => link(url, host(url)))));
  }
  return h('article', { class: 'dd-card' },
    h('header', {},
      h('h4', { text: tr(`ds_${c.id}`) }),
      c.count != null ? h('span', { class: 'dd-count' }, h('b', { text: n(c.count) }), ` ${tr(`dd_unit_${c.unit}`)}`) : null),
    h('p', { class: 'what', text: tr(`ds_${c.id}_what`, { d: n(s.official_domains) }) }),
    c.id === 'valhalla' ? h('p', { class: 'fine', text: tr('src_walk') }) : null,
    links.childElementCount ? links : null);
}

function sources(d) {
  return [
    h('p', { class: 'fine', text: tr('dd_sources_lead') }),
    GROUPS.map((group) => {
      const cards = d.cards.filter((c) => c.group === group);
      return cards.length ? h('div', { class: 'dd-group' },
        h('h3', { class: 'subhead', text: tr(`dd_g_${group}`) }),
        h('div', { class: 'dd-grid' }, cards.map((c) => card(c, d.sources)))) : null;
    }),
  ];
}

// one row of a bar chart: the label (with the number of places), the bar, the share
function bar(label, value, count) {
  const fill = h('div', { class: 'fill' });
  fill.style.width = `${Math.min(Math.max(value, 0), 100)}%`;
  return h('div', { class: 'bar' },
    h('span', { class: 'lab' }, label, count != null ? h('small', { text: n(count) }) : null),
    h('div', { class: 'track', 'aria-hidden': 'true' }, fill),
    h('span', { class: 'v', text: pctText(value) }));
}

function chart(title, rows, limit, cls = '') {
  const shown = limit ? rows.slice(0, limit) : rows;
  const rest = limit ? rows.slice(limit) : [];
  return h('div', { class: `dd-chart ${cls}`.trim() },
    h('h3', { class: 'subhead', text: title }),
    h('div', { class: 'bars' }, shown.map((r) => bar(r.label, r.hours, r.places))),
    rest.length ? h('details', { class: 'disclosure' },
      h('summary', {}, tr('dd_show_all', { n: n(rows.length) }), icon('chevron')),
      h('div', { class: 'bars' }, rest.map((r) => bar(r.label, r.hours, r.places)))) : null);
}

function coverage(c) {
  return [
    h('p', { text: tr('cov_lead', { n: n(c.places) }) }),
    h('div', { class: 'dd-charts' },
      h('div', { class: 'dd-chart' },
        h('h3', { class: 'subhead', text: tr('dd_cov_fields') }),
        h('div', { class: 'bars' },
          bar(tr('cov_hours'), c.hours),
          bar(tr('cov_hours_osm'), c.hours_osm),
          bar(tr('cov_hours_site'), c.hours_site),
          bar(tr('cov_phone'), c.phone),
          bar(tr('cov_website'), c.website),
          bar(tr('cov_address'), c.address),
          bar(tr('cov_description'), c.description))),
      c.districts.length ? chart(tr('dd_cov_dist'), c.districts) : null,
      chart(tr('dd_cov_cats'), c.categories, CATEGORY_ROWS, 'wide')),
    h('p', { class: 'fine', text: tr('cov_note') }),
  ];
}

function honesty(e) {
  if (!e.main) return h('p', { class: 'fine', text: tr('hon_missing') });
  const m = e.main;
  const fresh = e.holdout3 || m;
  return [
    h('p', { class: 'dd-hon', text: tr('dd_hon', {
      n: n(m.hallucinated_poi ?? 0),
      recs: n(m.recs_total ?? 0),
      p: n(m.honest_unknown_rate ?? 0),
      cases: n(fresh.cases ?? 0),
      all: n(fresh.case_all_ok_rate ?? 0),
    }) }),
    m.date ? h('p', { class: 'fine', text: tr('dd_hon_date', { date: m.date }) }) : null,
  ];
}

// «124 запроса», «124 сұраныс», «124 requests»: the plural form of the language
function requestsCount(count) {
  const rule = new Intl.PluralRules(currentLang()).select(count);
  return tr(`dd_req_${['one', 'few', 'many'].includes(rule) ? rule : 'other'}`, { n: n(count) });
}

// «Время ответа: медиана 2,1 с, 95 % быстрее 6,3 с» and how many logged answers it is based on (web.speed)
function speed(s) {
  if (!s || !s.requests) return h('p', { class: 'fine', text: tr('dd_speed_none') });
  return [
    h('p', { class: 'dd-speed', text: tr('dd_speed', { med: n(s.median_s), p95: n(s.p95_s) }) }),
    h('p', { class: 'fine', text: tr('dd_speed_n', { n: requestsCount(s.requests) }) }),
  ];
}

// the credits as the licences ask for them: one item per source, the addresses are links
function linkify(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(URL_RE)) {
    const url = m[0].replace(/[.:]+$/, '');
    out.push(text.slice(last, m.index), link(url, url.replace(/^https?:\/\//, ''), 'dd-inline'));
    last = m.index + url.length;
  }
  out.push(text.slice(last));
  return out;
}

function attribution() {
  return h('ul', { class: 'dd-attr' }, tr('footer').split(' · ').map((item) => h('li', {}, linkify(item))));
}

async function render() {
  const root = document.getElementById('data-root');
  root.replaceChildren(
    h('h1', { text: tr('data_title') }),
    h('p', { class: 'lead', text: tr('data_lead') }),
  );
  try {
    const d = await api.data(currentLang());
    if (!active) return;
    root.append(
      tiles(d),
      h('div', { class: 'section' }, h('h2', { text: tr('data_sources') }), sources(d)),
      h('div', { class: 'section' }, h('h2', { text: tr('data_coverage') }), coverage(d.coverage)),
      h('div', { class: 'section' }, h('h2', { text: tr('data_honesty') }), honesty(d.eval)),
      h('div', { class: 'section', id: 'data-speed' }, h('h2', { text: tr('data_speed') }), speed(d.speed)),
      h('div', { class: 'section' }, h('h2', { text: tr('data_attribution') }), attribution()),
    );
  } catch {
    root.append(h('p', { class: 'error-row', text: tr('city_load_fail') }));
  }
}

export function showData() {
  active = true;
  render();
}

export function hideData() {
  active = false;
}

export function initData() {
  onLang(() => active && render());
}
