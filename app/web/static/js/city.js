// «Город»: the same data that feeds the assistant, for the city and the research centre. Three layers over the 500 m
// grid: where requests found no place (demand), where the data is thin (quality), what residents reported. Only
// aggregates; a group below k requests is never shown. The map shows the chosen layer.

import { api } from './api.js';
import { fmtNumber, h, icon, pct } from './dom.js';
import { currentLang, onLang, tr } from './i18n.js';
import * as mapView from './map.js';

const UNMET = ['#dfe3ea', '#c2c8d3', '#9aa2b2', '#6c7588', '#414a5e', '#161b26'];
const GOOD = ['#dfe3ea', '#aeb5c3', '#7c8597', '#4b5466', '#161b26'];
const NONE = '#ffffff';
const REPORT_COLOR = { closed: '#d1373a', differ: '#b7791f', open: '#1f9d55', other: '#8a919e' };
const ASTANA = [51.13, 71.43];

let app;
let tab = 'demand';
const Q = { source: null, k: null, category: null, bucket: null, metric: 'hours' };
let active = false;

function mix(a, b, t) {
  const pa = a.match(/\w\w/g).map((x) => parseInt(x, 16));
  const pb = b.match(/\w\w/g).map((x) => parseInt(x, 16));
  return `#${pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0')).join('')}`;
}

function ramp(t, stops) {
  const x = Math.min(Math.max(t, 0), 1) * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  return mix(stops[i], stops[i + 1], x - i);
}

const n = (x) => fmtNumber(x, currentLang());

function metric(value, label) {
  return h('div', { class: 'metric' }, h('b', { text: value }), h('span', { text: label }));
}

function table(columns, rows, numeric = []) {
  return h(
    'div',
    { class: 'table-wrap' },
    h('table', {},
      h('thead', {}, h('tr', {}, columns.map((c, i) => h('th', { class: numeric.includes(i) ? 'n' : null, text: c })))),
      h('tbody', {}, rows.map((r) => h('tr', {}, r.map((v, i) => h('td', { class: numeric.includes(i) ? 'n' : null, text: v })))))),
  );
}

function seg(options, current, onPick) {
  return h('div', { class: 'seg', role: 'group' }, options.map(([value, label]) =>
    h('button', { type: 'button', 'aria-pressed': String(value === current), onclick: () => onPick(value) }, label)));
}

function downloads(items) {
  return h('div', { class: 'downloads' }, items.map(([name, label, params]) =>
    h('a', { class: 'btn', href: api.exportUrl(name, params || {}), download: name }, label)));
}

function legend(stops, left, right) {
  const bar = h('i');
  bar.style.background = `linear-gradient(90deg, ${stops.join(', ')})`;
  return h('p', { class: 'ramp' }, left, bar, right);
}

// ---------------------------------------------------------------- demand

function demandBody(d) {
  if (!d.sources.length) return [h('p', { class: 'fine', text: tr('city_no_log') })];
  const out = [];
  if (d.sources.length > 1) {
    out.push(seg(d.sources.map((s) => [s, tr(`city_src_${s}`)]), d.source, (s) => {
      Q.source = s;
      Q.k = null;
      load();
    }));
  }
  if (d.simulated) {
    const meta = d.meta && d.meta.seed != null ? ` ${tr('city_sim_meta', { seed: d.meta.seed, n: d.meta.n, date: d.meta.date })}` : '';
    out.push(h('p', { class: 'warn', text: tr('city_sim_banner') + meta }));
  }
  if (d.empty) {
    out.push(h('p', { class: 'fine', text: tr('city_log_empty') }));
    return out;
  }
  const t = d.totals;
  const cat = h('select', { 'aria-label': tr('city_category') },
    h('option', { value: '', text: tr('city_all') }),
    d.categories.map((c) => h('option', { value: c.id, selected: c.id === d.category, text: c.label })));
  cat.addEventListener('change', () => {
    Q.category = cat.value || null;
    load();
  });
  const bucket = h('select', { 'aria-label': tr('city_bucket') },
    h('option', { value: '', text: tr('city_all') }),
    d.buckets.map((b) => h('option', { value: b.id, selected: b.id === d.bucket, text: b.label })));
  bucket.addEventListener('change', () => {
    Q.bucket = bucket.value || null;
    load();
  });
  const step = (delta) => {
    Q.k = Math.min(Math.max(d.k + delta, d.k_min), d.k_max);
    load();
  };
  const stepper = h('span', { class: 'stepper' },
    h('button', { type: 'button', 'aria-label': tr('city_k_less'), disabled: d.k <= d.k_min, onclick: () => step(-1) }, '−'),
    h('output', { text: String(d.k) }),
    h('button', { type: 'button', 'aria-label': tr('city_k_more'), disabled: d.k >= d.k_max, onclick: () => step(1) }, '+'));
  out.push(
    h('div', { class: 'filters' },
      h('label', {}, tr('city_category'), cat),
      h('label', {}, tr('city_bucket'), bucket),
      h('label', {}, tr('city_k', { min: d.k_min }), stepper)),
    h('div', { class: 'metrics' },
      metric(n(t.requests), tr('city_m_requests')),
      metric(n(t.no_place), tr('city_m_no_place')),
      metric(n(t.hours_unknown), tr('city_m_hours_unknown')),
      metric(n(t.cells_shown), tr('city_m_cells_shown')),
      metric(n(t.cells_hidden), tr('city_m_cells_hidden', { k: d.k }))),
    legend(UNMET, tr('city_legend_few'), tr('city_legend_many')),
    h('p', { class: 'fine', text: tr('city_k_why', { k: d.k }) }),
    h('p', { class: 'fine', text: tr('city_demand_note', { k: d.k }) + (t.cells_hidden ? ` ${tr('city_hidden_note', { n: n(t.requests_hidden) })}` : '') }),
  );
  if (d.top.length) {
    out.push(
      h('h2', { text: tr('city_top_title') }),
      table(
        [tr('city_col_district'), tr('city_col_category'), tr('city_col_bucket'), tr('city_col_requests'), tr('city_col_no_place'), tr('city_col_share')],
        d.top.map((r) => [r.district, r.category, r.bucket, n(r.requests), n(r.no_place), pct(r.share, currentLang())]),
        [3, 4, 5],
      ),
    );
  }
  if (d.merged.requests) out.push(h('p', { class: 'fine', text: tr('city_merged', { n: n(d.merged.requests), g: n(d.merged.groups), k: d.k }) }));
  out.push(
    h('h2', { text: tr('city_actions_title') }),
    d.simulated ? h('p', { class: 'fine', text: tr('city_actions_sim') }) : null,
    d.actions.length
      ? h('ol', { class: 'acts' }, d.actions.map((a) => h('li', { text: tr('city_act_supply', { district: a.district, n: n(a.count), of: n(a.of), cat: a.category }) })))
      : h('p', { class: 'fine', text: tr('city_actions_none', { k: d.k }) }),
    h('p', { class: 'fine', text: tr('city_padded', { n: n(t.padded), of: n(t.requests) }) }),
    h('details', { class: 'disclosure' }, h('summary', {}, tr('city_how_title'), icon('chevron')),
      h('div', { class: 'lines' }, ['city_how_1', 'city_how_2', 'city_how_3', 'city_how_4', 'city_how_5'].map((key) => h('p', { text: tr(key, { k: d.k }) })))),
    h('h2', { text: tr('city_export_title') }),
    downloads([
      ['demand.csv', tr('city_dl_demand_csv'), { source: d.source, k: d.k }],
      ['demand.geojson', tr('city_dl_demand_geojson'), { source: d.source, k: d.k }],
    ]),
  );
  return out;
}

// ---------------------------------------------------------------- data quality

// The layers behind the assistant's extra lines: the open OpenStreetMap notes about closures and opening hours as a
// queue to check (every one with its link), the road works, and how far the afisha reaches. «Данных нет» is said for a
// missing layer, never «нет».
function layersBlock(layers) {
  if (!layers) return [];
  const out = [h('h2', { text: tr('city_q_queue_title') })];
  const notes = layers.notes;
  if (!notes) {
    out.push(h('p', { class: 'fine', text: tr('city_q_layers_none') }));
  } else {
    out.push(
      h('p', { class: 'fine', text: tr('city_q_queue_lead') }),
      h('div', { class: 'metrics' },
        metric(n(notes.open_total), tr('city_q_notes_open')),
        layers.construction == null ? null : metric(n(layers.construction), tr('city_q_constr'))),
      notes.queue.length
        ? h('ul', { class: 'recent queue' }, notes.queue.map((item) =>
          h('li', {},
            h('span', { class: 'sig', text: tr(`city_q_note_${item.kind}`) }),
            h('span', { text: item.snippet || '—' }),
            h('span', { class: 'fine' },
              `${tr('city_q_note_date', { date: item.date || '—' })} · `,
              h('a', { href: item.url, target: '_blank', rel: 'noopener noreferrer', text: tr('city_q_note_open') })))))
        : h('p', { class: 'fine', text: tr('city_q_queue_none') }),
      h('p', { class: 'fine', text: `${notes.attribution}${notes.snapshot_date ? ` · ${notes.snapshot_date}` : ''}` }),
    );
  }
  const ev = layers.events;
  out.push(h('h2', { text: tr('city_q_events_title') }));
  if (!ev) {
    out.push(h('p', { class: 'fine', text: tr('city_q_events_none') }));
  } else {
    const sources = ev.sources.map((s) => `${s.label} (${n(s.count)})`).join(', ');
    const date = (ev.fetched_at || '').slice(0, 10) || '—';
    out.push(
      h('p', { class: 'fine', text: `${tr('city_q_events', { n: n(ev.total), located: n(ev.located), sources, date })}${ev.stale ? ` ${tr('city_q_events_stale')}` : ''}` }),
      h('p', { class: 'fine', text: tr('city_q_events_note') }),
    );
  }
  return out;
}

const NOTE_DOT = '#b7791f';

function noteDots(layers) {
  const queue = (layers && layers.notes && layers.notes.queue) || [];
  return queue.map((item) => ({ lat: item.lat, lon: item.lon, color: NOTE_DOT, title: `#${item.id} ${tr(`city_q_note_${item.kind}`)}` }));
}

function qualityBody(q) {
  const lang = currentLang();
  return [
    h('p', { class: 'fine', text: tr('city_quality_lead') }),
    h('div', { class: 'metrics' },
      metric(n(q.total), tr('city_q_places')),
      q.metrics.map((m) => metric(pct(q.shares[m], lang), tr(`city_q_${m}`)))),
    q.demo_marks ? h('p', { class: 'fine', text: tr('city_q_demo_marks') }) : null,
    seg(q.metrics.map((m) => [m, tr(`city_q_${m}`)]), q.metric, (m) => {
      Q.metric = m;
      load();
    }),
    legend(GOOD, tr('city_legend_low'), tr('city_legend_high')),
    h('h2', { text: tr('city_worst_title') }),
    table(
      [tr('city_col_category'), tr('city_col_places'), tr('city_col_with_hours'), tr('city_col_share')],
      q.worst.map((r) => [r.category, n(r.pois), n(r.with_hours), pct(r.share, lang)]),
      [1, 2, 3],
    ),
    h('h2', { text: tr('city_hours_actions_title') }),
    h('ol', { class: 'acts' }, q.actions.map((a) =>
      h('li', { text: tr('city_act_hours', { district: a.district, n: n(a.missing), cat: a.category, have: n(a.have), of: n(a.of) }) }))),
    h('p', { class: 'fine', text: tr('city_hours_actions_note') }),
    ...layersBlock(q.layers),
    h('h2', { text: tr('city_export_title') }),
    downloads([
      ['quality.csv', tr('city_dl_quality_csv')],
      ['quality.geojson', tr('city_dl_quality_geojson')],
    ]),
  ];
}

// ---------------------------------------------------------------- residents' reports

function reportsBody(r) {
  const kinds = Object.entries(r.counts).sort((a, b) => b[1] - a[1]);
  return [
    h('p', { class: 'fine', text: tr('city_reports_lead') }),
    h('div', { class: 'metrics' },
      metric(n(r.total), tr('city_r_total')),
      kinds.map(([sig, count]) => metric(n(count), r.labels[sig] || sig))),
    r.demo ? h('p', { class: 'fine', text: tr('city_r_demo', { n: n(r.demo) }) }) : null,
    h('p', { class: 'ramp' },
      ...[['closed', 'city_r_closed'], ['differ', 'city_r_differ'], ['open', 'city_r_open'], ['other', 'city_r_other']].flatMap(([k, key]) => {
        const dot = h('span', { class: 'report-dot' });
        dot.style.background = REPORT_COLOR[k];
        return [dot, tr(key)];
      })),
    h('h2', { text: tr('city_r_recent') }),
    r.recent.length
      ? h('ul', { class: 'recent' }, r.recent.map((e) =>
        h('li', {}, h('span', { class: 'sig', text: e.label }), h('span', { text: `${e.name} · ${e.kind}` }),
          h('span', { class: 'fine', text: `${e.date} · ${e.bucket}${e.demo ? ` · ${tr('demo_word')}` : ''}` }))))
      : h('p', { class: 'fine', text: tr('city_r_none') }),
  ];
}

function reportColor(p) {
  if (p.closed) return REPORT_COLOR.closed;
  if (p.differ) return REPORT_COLOR.differ;
  if (p.open) return REPORT_COLOR.open;
  return REPORT_COLOR.other;
}

// ---------------------------------------------------------------- page

async function load() {
  const body = document.getElementById('city-body');
  const lang = currentLang();
  body.setAttribute('aria-busy', 'true');
  try {
    if (tab === 'demand') {
      const d = await api.city('demand', { source: Q.source, k: Q.k, category: Q.category, bucket: Q.bucket, lang });
      Q.source = d.source || null;
      body.replaceChildren(...demandBody(d).filter(Boolean));
      mapView.setReports([]);
      await mapView.setCells(d.cells, (p) => (p.no_place ? ramp(p.t, UNMET) : NONE));
    } else if (tab === 'quality') {
      const q = await api.city('quality', { metric: Q.metric, lang });
      body.replaceChildren(...qualityBody(q).filter(Boolean));
      mapView.setReports(noteDots(q.layers));
      await mapView.setCells(q.cells, (p) => ramp(p.t, GOOD));
    } else {
      const r = await api.city('reports', { lang });
      body.replaceChildren(...reportsBody(r).filter(Boolean));
      await mapView.setCells(null);
      mapView.setReports(r.places.features.map((f) => ({
        lon: f.geometry.coordinates[0],
        lat: f.geometry.coordinates[1],
        color: reportColor(f.properties),
        title: `${f.properties.name}: ${f.properties.total}`,
      })));
    }
  } catch {
    body.replaceChildren(h('p', { class: 'error-row', text: tr('city_load_fail') }));
  } finally {
    body.removeAttribute('aria-busy');
  }
}

function frame() {
  const root = document.getElementById('city-scroll');
  root.replaceChildren(
    h('div', { class: 'section' },
      h('h1', { text: tr('city_title') }),
      h('p', { class: 'lead', text: tr('city_lead') }),
      seg([['demand', tr('city_tab_demand')], ['quality', tr('city_tab_quality')], ['reports', tr('city_tab_reports')]], tab, (t) => {
        tab = t;
        frame();
      })),
    h('div', { class: 'section', id: 'city-body' }),
  );
  load();
}

export function showCity() {
  active = true;
  mapView.setPlaces([]);
  mapView.setRoute([], []);
  mapView.flyTo(ASTANA, 11);
  frame();
}

export function hideCity() {
  active = false;
  mapView.setCells(null);
  mapView.setReports([]);
}

export function initCity(ctx) {
  app = ctx;
  onLang(() => active && frame());
}
