// The weather card behind the «Эффекты» button: the measured conditions of /api/conditions, each block with its source and
// its time, and the switch of the map effects at the bottom. A block the server has no data for is left out (never «ясно»
// for unknown); with nothing at all the card says so in one sentence. A popover under the button on a laptop, a small sheet
// on a phone; it closes on a tap outside and on Esc.
//
// Owner's UI rules applied (local://uiux-rules.md): 728/729/736 one type scale, the temperature set larger than the rest and
// body text smaller; 455/693 sentence case, no all-caps labels, tabular numerals of the main font; 732/733 a 4 px unit and one
// side margin; 692/695 a shadow only on the popover itself, hairlines instead of boxes; 711/737 one accent, spent on the
// switch and the selected state; 694 a missing block is simply absent, a missing value a dash; 700/707 hit areas of 44 px
// from padding, nothing behind hover; 688 outline icons of one stroke; 709/724 enter 200 ms ease-out, no blocking.

import { h, isPhone } from './dom.js';
import { currentLang, onLang, tr } from './i18n.js';
import { wxIcon } from './weather-icons.js';

const MINUS = '\u2212';
const MIN_SPEED = 0.95; // m/s below this is written with a decimal («0,4»), never rounded up to «1»
const OPEN_ID = 'wx-panel';

const buttons = []; // {btn, fact}
let panel = null;
let body = null;
let sw = null;
let title = null;
let closeBtn = null;
let opener = null;
let isOpen = false;
let onSwitch = () => {};
let state = { data: null, effectsOn: true, online: false };

// ---------------------------------------------------------------- formatting

const decimal = (s) => (currentLang() === 'en' ? s : s.replace('.', ','));
const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const band = (pct) => (pct < 15 ? 0 : pct < 45 ? 1 : pct < 80 ? 2 : 3);
const level = (n) => Math.min(3, Math.max(1, n));

export function fmtTemp(t) {
  const r = Math.round(t);
  return `${r < 0 ? MINUS : ''}${Math.abs(r)}°`;
}

export function fmtSpeed(v) {
  return v >= MIN_SPEED ? String(Math.round(v)) : decimal(v.toFixed(1));
}

function fmtDistance(m) {
  if (m >= 9999) return tr('fx_vis_max');
  if (m >= 1000) return tr('fx_vis_km', { v: decimal(String(Math.round(m / 100) / 10)) });
  return tr('fx_vis_m', { v: Math.round(m / 10) * 10 });
}

const dirWord = (deg) => tr(`fx_dir_${Math.round(deg / 45) % 8}`);

const SOURCES = {
  metar: (b) => tr('fx_src_metar', { time: b.at }),
  'met-no': () => tr('fx_src_metno'),
  kazhydromet: () => tr('fx_src_kaz'),
  'open-meteo': () => tr('fx_src_openmeteo'),
};
const source = (b) => (SOURCES[b.source] || (() => ''))(b);

// the face of the button: a small icon of the sky and the temperature («☀ +3°»); the wind is in the card. What falls
// now outranks the sky; a clear sky is a moon after dark; with no sky and no temperature the neutral wind icon stays
export function buttonFace(d) {
  const sign = (t) => (Math.round(t) > 0 ? '+' : '') + fmtTemp(t);
  const text = d.temp ? sign(d.temp.temp_c) : '';
  let ic = 'wind';
  if (d.precip) ic = d.precip.kind;
  else if (d.sky) {
    const b = band(d.sky.cloud_pct);
    ic = b === 0 ? (d.sun.altitude < -0.83 ? 'moon' : 'clear') : b === 1 ? 'partly' : 'cloud';
  }
  return { ic, text };
}

// ---------------------------------------------------------------- the blocks

const meta = (text) => (text ? h('p', { class: 'wx-meta', text }) : null);

function block(cls, ...kids) {
  return h('section', { class: `wx-blk ${cls}` }, ...kids);
}

function nowBlock(d) {
  const { temp, sky, precip } = d;
  if (!temp && !sky && !precip) return null;
  const words = [sky && tr(`fx_sky_${band(sky.cloud_pct)}`), precip && tr(`fx_${precip.kind}_${level(precip.level)}`)].filter(Boolean);
  const feels = temp && temp.feels_c != null && temp.feels_c !== temp.temp_c ? tr('fx_feels', { t: fmtTemp(temp.feels_c) }) : '';
  return block(
    'wx-now',
    temp && h('p', { class: 'wx-temp-row' }, h('span', { class: 'wx-temp', text: fmtTemp(temp.temp_c) }), feels && h('span', { class: 'wx-feels', text: feels })),
    words.length ? h('p', { class: 'wx-val', text: capital(words.join(' · ')) }) : null,
    meta(source(temp || sky || precip)),
  );
}

function windBlock(w) {
  const arrow = wxIcon('arrow', 'wx-arrow');
  arrow.style.transform = `rotate(${(w.from_deg + 180) % 360}deg)`; // the arrow shows where the wind blows to
  return block(
    'wx-half',
    h('h3', { class: 'wx-h', text: tr('fx_wind_title') }),
    h('p', { class: 'wx-val' }, arrow, h('span', { text: tr('fx_fact', { dir: dirWord(w.from_deg), speed: fmtSpeed(w.speed_ms) }) })),
    w.gust_ms && w.gust_ms > w.speed_ms ? h('p', { class: 'wx-sub', text: tr('fx_gust', { v: fmtSpeed(w.gust_ms) }) }) : null,
    meta(source(w)),
  );
}

function visBlock(v) {
  return block('wx-half', h('h3', { class: 'wx-h', text: tr('fx_vis_title') }), h('p', { class: 'wx-val', text: fmtDistance(v.m) }), meta(source(v)));
}

// «fog at night and in the morning», written in the visitor's language from the codes of the notice (the server names the
// phenomenon and the part of the day in its Russian text); '' when the notice names no phenomenon we know
function noticeTitle(n) {
  if (!n.phenomena || !n.phenomena.length) return '';
  const and = ` ${tr('fx_and')} `;
  const ph = n.phenomena.map((c) => tr(`fx_ph_${c}`)).join(', ');
  const when = (n.periods || []).map((c) => tr(`fx_per_${c}`)).join(and);
  return capital(when ? tr('fx_notice_fmt', { ph, when }) : ph);
}

// the Kazhydromet notice: its phenomenon as a title in the answer language, the link to the notice and how long it holds;
// the notice's own Russian words only behind a disclosure, and only when the page is not Russian itself. A notice of a
// phenomenon we do not know is just «Kazhydromet notice» and the link.
function noticeBlock(n) {
  const link = h('a', { class: 'wx-link', href: n.url, target: '_blank', rel: 'noopener noreferrer', text: tr('fx_src_kaz') });
  const title = noticeTitle(n);
  const orig = title && n.text && currentLang() !== 'ru'
    ? h('details', { class: 'wx-orig' }, h('summary', { text: tr('fx_notice_text') }), h('p', { lang: 'ru', text: capital(n.text) }))
    : null;
  return block(
    '',
    h('h3', { class: 'wx-h', text: tr('fx_notice_title') }),
    title ? h('p', { class: 'wx-val', text: title }) : null,
    h('p', { class: 'wx-meta' }, link, n.until ? ` · ${tr('fx_until', { t: n.until })}` : ''),
    orig,
  );
}

function airBlock(d) {
  const { air, pm25 } = d;
  if (!air && !pm25) return null;
  const lines = [];
  if (air && air.kind === 'nmu') {
    lines.push(h('p', { class: 'wx-val' }, h('a', { class: 'wx-link', href: air.url, target: '_blank', rel: 'noopener noreferrer', text: tr('fx_air_nmu') })), meta(source(air)));
  } else if (air) {
    lines.push(h('p', { class: 'wx-val', text: capital(tr('fx_air_smog')) }), meta(source(air)));
  }
  if (pm25) lines.push(h('p', { class: 'wx-val', text: tr('fx_pm25', { v: pm25.value }) }), meta(source(pm25)));
  return block('', h('h3', { class: 'wx-h', text: tr('fx_air_title') }), ...lines);
}

function hourCell(it) {
  const wet = it.precip_mm != null && it.precip_mm >= 0.1;
  const glyph = it.sym ? wxIcon(it.sym, 'wx-sym') : h('span', { class: 'wx-sym', text: '–' });
  if (it.sym) {
    glyph.setAttribute('role', 'img');
    glyph.setAttribute('aria-label', tr(`fx_sym_${it.sym}`));
    glyph.removeAttribute('aria-hidden');
  }
  return h('li', { class: 'wx-hr' }, h('span', { class: 'wx-hr-at', text: it.at }), glyph, h('span', { class: 'wx-hr-t', text: fmtTemp(it.temp_c) }), h('span', { class: 'wx-hr-mm', text: wet ? tr('fx_mm', { v: decimal(it.precip_mm.toFixed(1)) }) : '' }));
}

function hoursBlock(hrs) {
  return block('', h('h3', { class: 'wx-h', text: tr('fx_hours_title') }), h('ul', { class: 'wx-hours' }, ...hrs.items.map(hourCell)), meta(source(hrs)));
}

function sunBlock(s) {
  return block('', h('p', { class: 'wx-val', text: tr('fx_sun_times', { rise: s.rise, set: s.set }) }), meta(tr('fx_src_calc')));
}

function blocks(d) {
  const pair = [d.wind && windBlock(d.wind), d.vis && visBlock(d.vis)].filter(Boolean);
  const out = [nowBlock(d), pair.length ? h('div', { class: 'wx-pair' }, ...pair) : null, d.notice && noticeBlock(d.notice), airBlock(d), d.hours && hoursBlock(d.hours)].filter(Boolean);
  if (!out.length) return [h('p', { class: 'wx-empty', text: tr('fx_none') })];
  return [...out, sunBlock(d.sun)];
}

// ---------------------------------------------------------------- the card and its buttons

function renderBody() {
  const d = state.data;
  body.replaceChildren(...(d && d.known ? blocks(d) : [h('p', { class: 'wx-empty', text: tr('fx_none') })]));
}

function renderStatic() {
  title.textContent = tr('fx_panel_title');
  closeBtn.setAttribute('aria-label', tr('close'));
  sw.firstChild.textContent = tr('fx_switch');
  sw.setAttribute('aria-checked', String(state.effectsOn));
  sw.parentElement.hidden = !state.online; // over the offline basemap the switch would do nothing
}

function renderButtons() {
  const d = state.online && state.data && state.data.known ? state.data : null;
  const face = d ? buttonFace(d) : { ic: 'wind', text: '' };
  for (const b of buttons) {
    if (b.shown !== face.ic) {
      b.ic.replaceChildren(wxIcon(face.ic));
      b.shown = face.ic;
    }
    b.btn.setAttribute('aria-label', face.text ? `${tr('fx_btn')}: ${face.text}` : tr('fx_btn'));
    b.btn.title = tr('fx_title');
    b.fact.textContent = face.text;
    b.fact.hidden = !face.text;
  }
}

function place() {
  if (isPhone() || !opener) {
    panel.style.top = panel.style.right = panel.style.maxHeight = '';
    return;
  }
  const r = opener.getBoundingClientRect();
  panel.style.top = `${Math.round(r.bottom + 8)}px`;
  panel.style.right = `${Math.max(Math.round(window.innerWidth - r.right), 8)}px`;
  panel.style.maxHeight = `${Math.max(window.innerHeight - r.bottom - 20, 240)}px`;
}

function setOpen(open, from) {
  if (open === isOpen) return;
  isOpen = open;
  panel.hidden = !open;
  for (const b of buttons) b.btn.setAttribute('aria-expanded', String(open && b.btn === from));
  if (open) {
    opener = from;
    renderStatic();
    renderBody();
    place();
    panel.focus({ preventScroll: true });
  } else {
    opener = null;
  }
}

export function closePanel() {
  setOpen(false);
}

// kind: 'ctrl' = the map's own corner (a laptop), 'top' = the top bar (a phone); the stylesheet shows one of them
export function makeButton(kind) {
  const fact = h('span', { class: 'fx-fact', hidden: true });
  const ic = h('span', { class: 'fx-ic' }, wxIcon('wind'));
  const btn = h('button', { type: 'button', class: kind === 'ctrl' ? 'fx-btn' : 'fx-top', 'aria-haspopup': 'dialog', 'aria-expanded': 'false', 'aria-controls': OPEN_ID }, ic, fact);
  btn.addEventListener('click', () => setOpen(!isOpen, btn));
  buttons.push({ btn, fact, ic, shown: 'wind' });
  renderButtons();
  return kind === 'ctrl' ? h('div', { class: 'maplibregl-ctrl fx-wrap' }, h('div', { class: 'maplibregl-ctrl-group fx-group' }, btn)) : btn;
}

export function renderPanel(next) {
  state = { ...state, ...next };
  renderButtons();
  if (isOpen) {
    renderStatic();
    renderBody();
  }
}

export function initPanel({ onToggle }) {
  onSwitch = onToggle;
  title = h('h2', { class: 'wx-title', id: 'wx-title' });
  closeBtn = h('button', { type: 'button', class: 'wx-close', onclick: () => setOpen(false) }, wxIcon('close'));
  sw = h('button', { type: 'button', class: 'wx-switch', role: 'switch', 'aria-checked': 'true', onclick: () => onSwitch() }, h('span'), h('span', { class: 'wx-track', 'aria-hidden': 'true' }));
  body = h('div', { class: 'wx-body' });
  panel = h('div', { class: 'wx-panel', id: OPEN_ID, role: 'dialog', 'aria-labelledby': 'wx-title', tabindex: '-1', hidden: true }, h('header', { class: 'wx-head' }, title, closeBtn), body, h('footer', { class: 'wx-foot' }, sw));
  document.body.append(panel);
  document.addEventListener(
    'pointerdown',
    (e) => {
      if (isOpen && !panel.contains(e.target) && !buttons.some((b) => b.btn.contains(e.target))) setOpen(false);
    },
    true,
  );
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !isOpen) return;
    const back = opener;
    setOpen(false);
    if (back) back.focus();
  });
  window.addEventListener('resize', () => isOpen && place());
  onLang(() => renderPanel({}));
  renderStatic();
}
