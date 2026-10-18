// Weather on the map, from measured data only (GET /api/conditions, read from the server's background-refreshed weather):
//  • the SKY: one full-map gradient above the basemap's canvas (and below the pins and labels), tinted by the computed
//    position of the sun (night, dawn, golden hour, dusk, day), greyer under an overcast report, hazier under an НМУ
//    notice or the station's smoke / haze;
//  • the WIND: thin streaks drifting in the measured direction at a speed proportional to the measured speed, one
//    vector for the whole map (no field lines: there is one station);
//  • PRECIPITATION: snow or rain particles only while the airport report says it is falling.
// No data means no effect; a one-line provenance says what is drawn from where. A toggle («Эффекты») remembers the visitor's
// choice in localStorage `anyq.fx`; prefers-reduced-motion starts it off. Nothing is drawn over the offline basemap, and the
// animation stops while the tab is hidden or a phone's sheet covers the map. The loop allocates nothing: typed arrays, one
// path per batch, ~30 frames a second.

import { api } from './api.js';
import { h, icon, isPhone } from './dom.js';
import { onLang, tr } from './i18n.js';

const KEY = 'anyq.fx';
const POLL_MS = 5 * 60 * 1000; // the server refreshes every 10 minutes; the sun moves ~1° in five
const RETRY_MS = 30 * 1000; // no value yet (the server has just started) or the request failed
const STALE_MS = 20 * 60 * 1000; // a value this old is not shown: nothing is better than an old sky
const FRAME_MS = 32;
const CAP_DESKTOP = 120;
const CAP_PHONE = 60;
const PX_PER_MS = 13; // px/s of drift per m/s of measured wind
const MAX_DPR = 2;
const TAU = Math.PI * 2;
const LEVEL_SHARE = [0.3, 0.55, 0.8]; // of the particle cap, per intensity (light, moderate, heavy)

// ---------------------------------------------------------------- the sky

// [altitude of the sun, top rgba, bottom rgba] — the gradient is multiplied over the map, so white is «no change»
const SKY_MORNING = [
  [-14, [6, 12, 44, 0.64], [14, 22, 58, 0.58]],
  [-6, [92, 84, 150, 0.24], [236, 140, 130, 0.13]],
  [-0.8, [255, 160, 120, 0.18], [255, 205, 150, 0.09]],
  [6, [255, 190, 110, 0.12], [255, 220, 160, 0.06]],
  [14, [200, 225, 250, 0.05], [255, 255, 255, 0]],
];
const SKY_EVENING = [
  [-14, [6, 12, 44, 0.64], [14, 22, 58, 0.58]],
  [-6, [120, 80, 140, 0.26], [245, 130, 90, 0.14]],
  [-0.8, [255, 140, 80, 0.2], [255, 190, 120, 0.1]],
  [6, [255, 190, 110, 0.12], [255, 220, 160, 0.06]],
  [14, [200, 225, 250, 0.05], [255, 255, 255, 0]],
];
const GREY = [196, 202, 210];
const BEIGE = [196, 176, 146];
const INK_DAY = [65, 92, 130];
const INK_NIGHT = [222, 232, 255];

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const lerp = (a, b, t) => a + (b - a) * t;
const mixRgb = (p, q, t) => [lerp(p[0], q[0], t), lerp(p[1], q[1], t), lerp(p[2], q[2], t)];
const rgba = (c, a) => `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${a.toFixed(3)})`;

function skyAt(altitude, morning) {
  const stops = morning ? SKY_MORNING : SKY_EVENING;
  if (altitude <= stops[0][0]) return [stops[0][1], stops[0][2]];
  for (let i = 1; i < stops.length; i += 1) {
    if (altitude > stops[i][0]) continue;
    const [a0, t0, b0] = stops[i - 1];
    const [a1, t1, b1] = stops[i];
    const k = (altitude - a0) / (a1 - a0);
    return [t0.map((v, n) => lerp(v, t1[n], k)), b0.map((v, n) => lerp(v, b1[n], k))];
  }
  const last = stops[stops.length - 1];
  return [last[1], last[2]];
}

// the two gradient colours for the sun's altitude, the cloud cover (0..100 or null) and the haze flag
function skyColours(sun, cloud, haze) {
  let [top, bottom] = skyAt(sun.altitude, sun.morning);
  const k = cloud == null ? 0 : clamp((cloud - 30) / 70, 0, 1);
  const tint = (c, grey, hazeAlpha) => {
    let [r, g, b, a] = c;
    [r, g, b] = mixRgb([r, g, b], GREY, 0.55 * k);
    a += grey * k;
    if (haze) {
      [r, g, b] = mixRgb([r, g, b], BEIGE, 0.5);
      a += hazeAlpha;
    }
    return [r, g, b, Math.min(a, 0.6)];
  };
  top = tint(top, 0.08, 0.1);
  bottom = tint(bottom, 0.1, 0.14);
  return [rgba(top, top[3]), rgba(bottom, bottom[3])];
}

// ---------------------------------------------------------------- the particles

const fx = {
  userOn: true,
  open: false, // the popover
  online: false, // the basemap is the online one
  data: null,
  fetchedAt: 0,
  timer: 0,
  sheetFull: false,
  map: null,
  sky: null,
  cv: null,
  ctx: null,
  w: 0,
  h: 0,
  dpr: 1,
  raf: 0,
  last: 0,
  t: 0,
  seeded: '',
  // wind
  nW: 0,
  wSpeed: 0, // px/s
  wLen: 12,
  wGust: 0,
  wTravel: 0, // radians, screen direction of travel
  wDx: 0,
  wDy: 0,
  // precipitation
  nP: 0,
  kind: '',
  level: 0,
  // colours
  streakLo: '',
  streakHi: '',
  rain: '',
  edge: '',
  // typed pools, sized for the largest cap
  sx: new Float32Array(CAP_DESKTOP),
  sy: new Float32Array(CAP_DESKTOP),
  sv: new Float32Array(CAP_DESKTOP),
  sl: new Float32Array(CAP_DESKTOP),
  sph: new Float32Array(CAP_DESKTOP),
  sdx: new Float32Array(CAP_DESKTOP),
  sdy: new Float32Array(CAP_DESKTOP),
  px: new Float32Array(CAP_DESKTOP),
  py: new Float32Array(CAP_DESKTOP),
  pv: new Float32Array(CAP_DESKTOP),
  pr: new Float32Array(CAP_DESKTOP),
  pph: new Float32Array(CAP_DESKTOP),
};
const uis = [];

const cap = () => (isPhone() ? CAP_PHONE : CAP_DESKTOP);

function seedWind() {
  const base = fx.wTravel;
  for (let i = 0; i < fx.nW; i += 1) {
    fx.sx[i] = Math.random() * fx.w;
    fx.sy[i] = Math.random() * fx.h;
    fx.sv[i] = 0.85 + Math.random() * 0.3;
    fx.sl[i] = 0.6 + Math.random() * 0.8;
    fx.sph[i] = Math.random() * TAU;
    const a = base + (Math.random() - 0.5) * 0.12; // a few degrees of noise around the one measured direction
    fx.sdx[i] = Math.cos(a);
    fx.sdy[i] = Math.sin(a);
  }
}

function seedPrecip() {
  const snow = fx.kind === 'snow';
  for (let i = 0; i < fx.nP; i += 1) {
    fx.px[i] = Math.random() * fx.w;
    fx.py[i] = Math.random() * fx.h;
    fx.pph[i] = Math.random() * TAU;
    if (snow) {
      fx.pr[i] = 1.1 + Math.random() * 1.6;
      fx.pv[i] = (20 + Math.random() * 26) * (0.8 + 0.12 * fx.level);
    } else {
      fx.pr[i] = 9 + Math.random() * 8; // the streak's length
      fx.pv[i] = 380 + Math.random() * 200;
    }
  }
}

function sizeCanvas() {
  if (!fx.cv) return;
  const box = fx.map.getContainer().getBoundingClientRect();
  fx.w = Math.max(Math.round(box.width), 1);
  fx.h = Math.max(Math.round(box.height), 1);
  fx.dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
  fx.cv.width = Math.round(fx.w * fx.dpr);
  fx.cv.height = Math.round(fx.h * fx.dpr);
  fx.ctx.setTransform(fx.dpr, 0, 0, fx.dpr, 0, 0);
  planParticles();
}

// how many streaks and drops, from the measured wind and what falls; seeded again when anything here changes
function planParticles() {
  const d = fx.data;
  const limit = cap();
  const wind = d && d.wind;
  const precip = d && d.precip;
  fx.nP = precip ? Math.round(limit * LEVEL_SHARE[clamp(precip.level, 1, 3) - 1]) : 0;
  fx.kind = precip ? precip.kind : '';
  fx.level = precip ? precip.level : 0;
  if (wind) {
    const speed = wind.speed_ms;
    const travel = ((wind.from_deg + 180) * Math.PI) / 180; // the wind blows from `from_deg`; north is up the screen
    fx.wTravel = Math.atan2(-Math.cos(travel), Math.sin(travel));
    fx.wDx = Math.cos(fx.wTravel);
    fx.wDy = Math.sin(fx.wTravel);
    fx.wSpeed = speed * PX_PER_MS;
    fx.wLen = clamp(10 + 2.2 * speed, 10, 34);
    fx.wGust = wind.gust_ms ? clamp((wind.gust_ms / speed - 1) * 0.5, 0.06, 0.35) : 0.06;
    fx.nW = Math.min(Math.round(limit * clamp(0.3 + speed / 14, 0.3, 1)), limit - fx.nP);
  } else {
    fx.nW = 0;
  }
  const signature = `${fx.nW} ${fx.nP} ${fx.kind} ${fx.level} ${fx.wTravel.toFixed(2)} ${fx.w} ${fx.h}`;
  if (signature === fx.seeded) return; // a poll that changed nothing does not make every particle jump
  fx.seeded = signature;
  seedWind();
  seedPrecip();
}

function frame(now) {
  fx.raf = requestAnimationFrame(frame);
  const elapsed = now - fx.last;
  if (elapsed < FRAME_MS) return;
  fx.last = now;
  const dt = Math.min(elapsed, 100) / 1000;
  fx.t += dt;
  fx.ctx.clearRect(0, 0, fx.w, fx.h);
  if (fx.nW) drawWind(dt);
  if (fx.nP) {
    if (fx.kind === 'snow') drawSnow(dt);
    else drawRain(dt);
  }
}

function drawWind(dt) {
  const { ctx, w, h, t } = fx;
  const gust = 1 + fx.wGust * (0.6 * Math.sin(t * 0.9) + 0.4 * Math.sin(t * 2.3 + 1));
  const m = fx.wLen * 1.4 + 4;
  ctx.lineWidth = 1;
  ctx.lineCap = 'round';
  for (let pass = 0; pass < 2; pass += 1) {
    ctx.strokeStyle = pass ? fx.streakHi : fx.streakLo;
    ctx.beginPath();
    for (let i = pass; i < fx.nW; i += 2) {
      const step = fx.wSpeed * fx.sv[i] * gust * dt;
      const dx = fx.sdx[i];
      const dy = fx.sdy[i];
      let x = fx.sx[i] + dx * step;
      let y = fx.sy[i] + dy * step;
      if (x > w + m || x < -m || y > h + m || y < -m) { // out on one side: back in on the other, at a new place across
        if (Math.abs(dx) >= Math.abs(dy)) {
          x = dx > 0 ? -m : w + m;
          y = Math.random() * h;
        } else {
          y = dy > 0 ? -m : h + m;
          x = Math.random() * w;
        }
      }
      fx.sx[i] = x;
      fx.sy[i] = y;
      const wob = Math.sin(t * 0.8 + fx.sph[i]) * 3; // a little noise across the drift
      const x0 = x - dy * wob;
      const y0 = y + dx * wob;
      const len = fx.wLen * fx.sl[i];
      ctx.moveTo(x0, y0);
      ctx.lineTo(x0 - dx * len, y0 - dy * len);
    }
    ctx.stroke();
  }
}

function drawSnow(dt) {
  const { ctx, w, h, t } = fx;
  const drift = fx.nW ? fx.wDx * fx.wSpeed * 0.5 : 0; // flakes are carried by the measured wind, not slid
  for (let i = 0; i < fx.nP; i += 1) {
    let y = fx.py[i] + fx.pv[i] * dt;
    let x = fx.px[i] + (drift + Math.sin(t * 1.1 + fx.pph[i]) * 9) * dt;
    if (y > h + 4) {
      y = -4;
      x = Math.random() * w;
    }
    if (x > w + 4) x = -4;
    else if (x < -4) x = w + 4;
    fx.px[i] = x;
    fx.py[i] = y;
  }
  ctx.fillStyle = fx.edge; // a faint dark rim keeps white flakes readable on the pale map
  ctx.beginPath();
  for (let i = 0; i < fx.nP; i += 1) {
    const r = fx.pr[i] + 0.9;
    ctx.moveTo(fx.px[i] + r, fx.py[i]);
    ctx.arc(fx.px[i], fx.py[i], r, 0, TAU);
  }
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.94)';
  ctx.beginPath();
  for (let i = 0; i < fx.nP; i += 1) {
    ctx.moveTo(fx.px[i] + fx.pr[i], fx.py[i]);
    ctx.arc(fx.px[i], fx.py[i], fx.pr[i], 0, TAU);
  }
  ctx.fill();
}

function drawRain(dt) {
  const { ctx, w, h } = fx;
  const slant = fx.nW ? clamp((fx.wDx * fx.wSpeed) / 400, -0.35, 0.35) : 0; // sideways share of the fall
  ctx.strokeStyle = fx.rain;
  ctx.lineWidth = 1;
  ctx.lineCap = 'round';
  ctx.beginPath();
  for (let i = 0; i < fx.nP; i += 1) {
    const v = fx.pv[i] * dt;
    let y = fx.py[i] + v;
    let x = fx.px[i] + v * slant;
    if (y > h + 20 || x > w + 20 || x < -20) {
      y = -20;
      x = Math.random() * w;
    }
    fx.px[i] = x;
    fx.py[i] = y;
    ctx.moveTo(x, y);
    ctx.lineTo(x - fx.pr[i] * slant, y - fx.pr[i]);
  }
  ctx.stroke();
}

// ---------------------------------------------------------------- what is shown, and when

const shown = () => fx.userOn && fx.online;
const animating = () => shown() && !document.hidden && !fx.sheetFull && fx.cv && (fx.nW > 0 || fx.nP > 0);

function syncLoop() {
  if (animating()) {
    if (!fx.raf) {
      fx.last = 0;
      fx.raf = requestAnimationFrame(frame);
    }
  } else if (fx.raf) {
    cancelAnimationFrame(fx.raf);
    fx.raf = 0;
    if (fx.ctx) fx.ctx.clearRect(0, 0, fx.w, fx.h);
  }
}

function paint() {
  const d = fx.data;
  const on = shown() && !!d;
  fx.sky.classList.toggle('on', on);
  fx.cv.hidden = !on;
  if (!d) return;
  const [top, bottom] = skyColours(d.sun, d.sky ? d.sky.cloud_pct : null, !!d.air);
  fx.sky.style.setProperty('--fx-a', top);
  fx.sky.style.setProperty('--fx-b', bottom);
  const lum = clamp((d.sun.altitude + 11) / 5, 0, 1); // the streaks are dark on a lit map and light on a night one
  const ink = mixRgb(INK_NIGHT, INK_DAY, lum);
  fx.streakLo = rgba(ink, 0.2 + 0.1 * (1 - lum));
  fx.streakHi = rgba(ink, 0.34 + 0.12 * (1 - lum));
  fx.rain = rgba(ink, 0.45 + 0.1 * (1 - lum));
  fx.edge = rgba(INK_DAY, 0.3 * lum);
}

const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const skyBand = (pct) => (pct < 15 ? 0 : pct < 45 ? 1 : pct < 80 ? 2 : 3);

// «Ветер СЗ 9 м/с · снег · пасмурно · аэропорт, 17:30 · закат (расчёт)»: each effect's data, then where it is from
function provenance(d) {
  const parts = [];
  if (d.wind) parts.push(tr('fx_wind', { dir: tr(`fx_dir_${Math.round(d.wind.from_deg / 45) % 8}`), speed: Math.max(Math.round(d.wind.speed_ms), 1) }));
  if (d.precip) parts.push(tr(`fx_${d.precip.kind}_${clamp(d.precip.level, 1, 3)}`));
  if (d.sky) parts.push(tr(`fx_sky_${skyBand(d.sky.cloud_pct)}`));
  if (d.air) parts.push(tr(d.air.kind === 'nmu' ? 'fx_air_nmu' : 'fx_air_smog'));
  const station = [d.wind, d.sky, d.precip].find(Boolean);
  if (station) parts.push(station.source === 'metar' ? tr('fx_src_metar', { time: station.at }) : tr('fx_src_metno'));
  parts.push(tr(`fx_sun_${d.sun.phase}`));
  return capital(parts.join(' · '));
}

// the short fact on the button: the wind («СЗ 9 м/с»), or what falls when there is no wind; nothing when off or unknown
function factText(d) {
  if (d.wind) return tr('fx_fact', { dir: tr(`fx_dir_${Math.round(d.wind.from_deg / 45) % 8}`), speed: Math.max(Math.round(d.wind.speed_ms), 1) });
  return d.precip ? tr(`fx_${d.precip.kind}_${clamp(d.precip.level, 1, 3)}`) : '';
}

function renderUi() {
  const d = shown() ? fx.data : null;
  const text = d ? provenance(d) : '';
  const fact = d ? factText(d) : '';
  for (const ui of uis) {
    ui.root.hidden = !fx.online;
    ui.btn.classList.toggle('on', fx.userOn);
    ui.btn.setAttribute('aria-label', fact ? `${tr('fx_btn')}: ${fact}` : tr('fx_btn'));
    ui.btn.title = tr('fx_title');
    ui.fact.textContent = fact;
    ui.fact.hidden = !fact;
    ui.name.textContent = tr('fx_btn');
    ui.sw.setAttribute('aria-checked', String(fx.userOn));
    ui.line.textContent = text || tr('fx_title'); // «what is drawn, from what»; the plain promise while nothing is
  }
  if (!fx.online) setOpen(false);
}

function render() {
  paint();
  planParticles();
  renderUi();
  syncLoop();
}

// ---------------------------------------------------------------- the data

async function load() {
  clearTimeout(fx.timer);
  if (!shown()) return;
  let wait = RETRY_MS;
  try {
    const query = new URLSearchParams(location.search).get('fx'); // test scenarios, served only under WALKS_FX_FAKE=1
    const d = await api.conditions(query);
    fx.data = d;
    fx.fetchedAt = Date.now();
    if (d.known) wait = POLL_MS;
  } catch {
    if (fx.data && Date.now() - fx.fetchedAt > STALE_MS) fx.data = null;
  }
  render();
  fx.timer = setTimeout(load, wait);
}

function setUser(on, { store = false } = {}) {
  fx.userOn = on;
  if (store) {
    try {
      localStorage.setItem(KEY, on ? 'on' : 'off');
    } catch { /* private mode: the choice lasts for the session */ }
  }
  if (on) load();
  else clearTimeout(fx.timer);
  render();
}

function initialChoice() {
  let saved = null;
  try {
    saved = localStorage.getItem(KEY);
  } catch { /* no storage: the default */ }
  if (saved === 'on' || saved === 'off') return saved === 'on';
  return !matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// ---------------------------------------------------------------- the controls

// two faces of one switch, each a small button (icon, and the wind when it is known) that opens a popover with the on/off
// switch and the full provenance line: on a laptop under the map's own buttons, on a phone in the top bar. Nothing stays
// on the map itself, so no pin is ever covered by it.
function buildUi(kind) {
  const fact = h('span', { class: 'fx-fact', hidden: true });
  const btn = h('button', { type: 'button', class: kind === 'ctrl' ? 'fx-btn' : 'fx-top', 'aria-haspopup': 'dialog', 'aria-expanded': 'false', onclick: () => setOpen(!fx.open) }, icon('wind'), fact);
  const name = h('span', { class: 'fx-name' });
  const sw = h('button', { type: 'button', class: 'fx-switch', role: 'switch', 'aria-checked': 'true', onclick: () => setUser(!fx.userOn, { store: true }) }, name, h('span', { class: 'fx-track', 'aria-hidden': 'true' }));
  const line = h('p', { class: 'fx-line' });
  const pop = h('div', { class: 'fx-pop', role: 'dialog', hidden: true }, sw, line);
  const root = kind === 'ctrl'
    ? h('div', { class: 'maplibregl-ctrl fx-wrap', hidden: true }, h('div', { class: 'maplibregl-ctrl-group fx-group' }, btn), pop)
    : h('div', { class: 'fx-menu', hidden: true }, btn, pop);
  const ui = { root, btn, fact, name, sw, line, pop };
  uis.push(ui);
  return ui;
}

function setOpen(open) {
  fx.open = open;
  for (const ui of uis) {
    ui.pop.hidden = !open;
    ui.btn.setAttribute('aria-expanded', String(open));
  }
}

class FxControl {
  onAdd() {
    this.el = buildUi('ctrl').root;
    return this.el;
  }

  onRemove() {
    this.el.remove();
  }
}

// a phone's sheet at «full» covers the map: the loop rests (the class is the sheet's own, sheet.js)
function watchSheets() {
  const panels = ['view-assistant', 'view-city'].map((id) => document.getElementById(id));
  const read = () => {
    fx.sheetFull = isPhone() && panels.some((p) => p && !p.hidden && p.classList.contains('pos-full'));
    if (fx.sheetFull) setOpen(false); // the sheet covers the bar: a popover left open would hang over it
    syncLoop();
  };
  const observer = new MutationObserver(read);
  for (const p of panels) if (p) observer.observe(p, { attributes: true, attributeFilter: ['class', 'hidden'] });
  window.addEventListener('resize', read);
  read();
}

// `online`: the basemap is the real one; over the offline fallback there is no map to put weather on
export function setBasemapKind(kind) {
  fx.online = kind === 'online';
  if (!fx.map) return;
  if (fx.online) load();
  else clearTimeout(fx.timer);
  render();
}

// the button joins the corner's buttons below the location button, which the shell adds later (map.addLocate)
export function addToggle() {
  fx.map.addControl(new FxControl(), 'top-right');
  renderUi();
}

export function initWeather(map, kind) {
  fx.map = map;
  fx.userOn = initialChoice();
  const canvas = map.getCanvas();
  fx.sky = h('div', { class: 'fx-sky', 'aria-hidden': 'true' });
  fx.cv = h('canvas', { class: 'fx-canvas', 'aria-hidden': 'true', hidden: true });
  fx.ctx = fx.cv.getContext('2d', { alpha: true });
  const phone = buildUi('phone');
  const tools = document.querySelector('.top-tools');
  if (tools) tools.prepend(phone.root);
  canvas.after(fx.sky, fx.cv); // above the basemap's canvas, below the pins and labels (they are added later)
  document.addEventListener('pointerdown', (e) => {
    if (fx.open && !uis.some((ui) => ui.root.contains(e.target))) setOpen(false);
  }, true);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && fx.open) {
      setOpen(false);
      for (const ui of uis) if (ui.root.contains(document.activeElement)) ui.btn.focus();
    }
  });
  new ResizeObserver(sizeCanvas).observe(map.getContainer());
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && shown() && Date.now() - fx.fetchedAt > POLL_MS) load();
    syncLoop();
  });
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
    let saved = null;
    try {
      saved = localStorage.getItem(KEY);
    } catch { /* no storage */ }
    if (e.matches && saved !== 'on') setUser(false);
  });
  onLang(renderUi);
  watchSheets();
  sizeCanvas();
  setBasemapKind(kind);
}
