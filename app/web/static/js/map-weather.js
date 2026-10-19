// Weather on the map, from measured data only (GET /api/conditions, read from the server's background-refreshed weather):
//  • the SKY: one full-map gradient above the basemap's canvas (and below the pins and labels), tinted by the computed
//    position of the sun (night, dawn, golden hour, dusk, day), greyer under an overcast report, hazier under an НМУ
//    notice or the station's smoke / haze;
//  • the WIND: fine particles carried along the ONE measured vector (direction and speed of the airport report) with a
//    small smooth noise per particle, each leaving a soft tapering trail: the look of windy.com / earth.nullschool, but no
//    field: one station says nothing about how the wind varies over the city. A trail is the particle's last positions,
//    drawn thinner and fainter with age (a faded-bitmap trail leaves 8-bit residue: a faint permanent haze);
//  • PRECIPITATION: snow or rain particles only while the airport report says it is falling.
// No data means no effect. The button «Эффекты» opens the weather card (weather-panel.js); the switch in it keeps the
// visitor's choice in localStorage `anyq.fx`; prefers-reduced-motion starts it off. Nothing is drawn over the offline
// basemap, and the animation stops while the tab is hidden or a phone's sheet covers the map. The loop allocates nothing:
// typed arrays and one path per batch, ~30 frames a second.

import { api } from './api.js';
import { h, isPhone } from './dom.js';
import { closePanel, initPanel, makeButton, renderPanel } from './weather-panel.js';

const KEY = 'anyq.fx';
const POLL_MS = 5 * 60 * 1000; // the server refreshes every 10 minutes; the sun moves ~1° in five
const RETRY_MS = 30 * 1000; // no value yet (the server has just started) or the request failed
const STALE_MS = 15 * 60 * 1000; // a value this old is not shown: nothing is better than an old sky
const PRECIP_FRESH_MS = 11 * 60 * 1000; // what falls is only drawn from an answer this young (the server refreshes every 10 min)
const FRAME_MS = 32;
const FRAME_S = FRAME_MS / 1000;
const CAP_DESKTOP = 120;
const CAP_PHONE = 60;
const PX_PER_MS = 14; // px/s of drift per m/s of measured wind
const CALM_MS = 0.5; // below this nothing moves: a light air does not push particles across a city
const MAX_PIXELS = 1.8e6; // backing store of the precipitation canvas: a retina phone fits, a retina laptop is drawn coarser
const WIND_PIXELS = 0.9e6; // the wind's: hairlines need no retina, and a canvas redrawn every frame costs by its pixels
const TAU = Math.PI * 2;
const LEVEL_SHARE = [0.3, 0.55, 0.8]; // of the particle cap, per intensity (light, moderate, heavy)
const TURN = 0.5; // rad: how far a particle's heading wanders around the measured one: wisps that curl, not straight slants
const TURN_RATE = 1.8; // rad/s of that wander
const HIST = 24; // positions kept per particle: the longest trail, in frames
const BUCKETS = 5; // a trail is drawn in this many steps, from its faint tail to its head
const BUCKET_ALPHA = [0.1, 0.24, 0.45, 0.72, 1]; // of the trail's strongest strength
const BUCKET_WIDTH = [0.6, 0.7, 0.85, 1, 1.1]; // of its width

// ---------------------------------------------------------------- the sky

// [altitude of the sun, top rgba, bottom rgba]: the gradient is multiplied over the map, so white is «no change»
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
const INK_DAY = [71, 85, 105]; // a desaturated slate: readable on the light basemap without shouting
const INK_NIGHT = [162, 176, 210]; // after dark: a muted blue-grey, never white (white streaks on a dark map read as rain or snow)

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

// ---------------------------------------------------------------- the state

const fx = {
  userOn: true,
  online: false, // the basemap is the online one
  data: null,
  fetchedAt: 0,
  timer: 0,
  sheetFull: false,
  map: null,
  sky: null,
  wcv: null, // the wind's canvas (faded each frame)
  wctx: null,
  pcv: null, // the precipitation's canvas (cleared each frame)
  pctx: null,
  w: 0,
  h: 0,
  raf: 0,
  last: 0,
  t: 0,
  seeded: '',
  // wind
  nW: 0,
  wSpeed: 0, // px/s
  wTravel: 0, // radians, screen direction of travel
  wDx: 0, // its cosine and sine
  wDy: 0,
  wWidth: 1.2,
  hist: 12, // frames a trail is long (of HIST), from the measured speed
  head: 0, // the ring index of the newest position, the same for every particle
  trail: new Array(BUCKETS).fill(''), // stroke styles of a trail's steps
  // precipitation
  nP: 0,
  kind: '',
  level: 0,
  rain: '',
  edge: '',
  // typed pools, sized for the largest cap
  x: new Float32Array(CAP_DESKTOP),
  y: new Float32Array(CAP_DESKTOP),
  hx: new Float32Array(CAP_DESKTOP * HIST), // the last positions of each particle, a ring of `hist` per particle
  hy: new Float32Array(CAP_DESKTOP * HIST),
  age: new Float32Array(CAP_DESKTOP),
  life: new Float32Array(CAP_DESKTOP),
  sv: new Float32Array(CAP_DESKTOP), // its own share of the wind speed
  ph: new Float32Array(CAP_DESKTOP), // phase of its heading wander
  len: new Uint8Array(CAP_DESKTOP), // how much of its trail it shows: it grows at birth and shrinks before it ends
  px: new Float32Array(CAP_DESKTOP),
  py: new Float32Array(CAP_DESKTOP),
  pv: new Float32Array(CAP_DESKTOP),
  pr: new Float32Array(CAP_DESKTOP),
  pph: new Float32Array(CAP_DESKTOP),
};

const cap = () => (isPhone() ? CAP_PHONE : CAP_DESKTOP);
const shown = () => fx.userOn && fx.online;

// ---------------------------------------------------------------- wind

function respawn(i, spread) {
  const x = Math.random() * fx.w;
  const y = Math.random() * fx.h;
  fx.x[i] = x;
  fx.y[i] = y;
  for (let k = 0; k < HIST; k += 1) {
    fx.hx[i * HIST + k] = x;
    fx.hy[i * HIST + k] = y;
  }
  fx.life[i] = 2.4 + Math.random() * 3.6;
  fx.age[i] = spread ? Math.random() * fx.life[i] : 0;
}

function seedWind() {
  fx.head = 0;
  for (let i = 0; i < fx.nW; i += 1) {
    respawn(i, true);
    fx.sv[i] = 0.8 + Math.random() * 0.4;
    fx.ph[i] = Math.random() * TAU;
    fx.len[i] = 2;
  }
  fx.wctx.clearRect(0, 0, fx.w, fx.h);
}

function stepWind(dt) {
  const { w, h, t, hist } = fx;
  fx.head = (fx.head + 1) % hist;
  for (let i = 0; i < fx.nW; i += 1) {
    fx.age[i] += dt;
    const u = fx.age[i] / fx.life[i];
    if (u >= 1 || fx.x[i] < -8 || fx.x[i] > w + 8 || fx.y[i] < -8 || fx.y[i] > h + 8) respawn(i, false);
    const ph = fx.ph[i];
    // a smooth wander of its own around the one measured heading: no two neighbours agree, so no field is implied
    const heading = fx.wTravel + TURN * (0.7 * Math.sin(t * TURN_RATE + ph) + 0.3 * Math.sin(t * TURN_RATE * 2.3 + ph * 1.7));
    const v = fx.wSpeed * fx.sv[i] * (1 + 0.1 * Math.sin(t * 0.7 + ph * 1.3));
    const x = fx.x[i] + Math.cos(heading) * v * dt;
    const y = fx.y[i] + Math.sin(heading) * v * dt;
    fx.x[i] = x;
    fx.y[i] = y;
    fx.hx[i * HIST + fx.head] = x;
    fx.hy[i * HIST + fx.head] = y;
    const env = u < 0.2 ? u / 0.2 : u > 0.7 ? (1 - u) / 0.3 : 1; // in at birth, out at the end of its life
    fx.len[i] = Math.max(2, Math.round(hist * env));
  }
}

function drawWind(dt) {
  const ctx = fx.wctx;
  const { hist, head } = fx;
  stepWind(dt);
  ctx.clearRect(0, 0, fx.w, fx.h);
  ctx.lineCap = 'butt';
  ctx.lineJoin = 'round';
  // from the tail (the faintest, the thinnest) to the head: segment `a` joins the position `a` frames ago to the one before it
  for (let b = 0; b < BUCKETS; b += 1) {
    const from = Math.floor(((BUCKETS - 1 - b) * (hist - 1)) / BUCKETS); // the ages of this step, head side first
    const to = Math.floor(((BUCKETS - b) * (hist - 1)) / BUCKETS);
    if (to <= from) continue;
    ctx.strokeStyle = fx.trail[b];
    ctx.lineWidth = fx.wWidth * BUCKET_WIDTH[b];
    ctx.beginPath();
    for (let i = 0; i < fx.nW; i += 1) {
      const last = Math.min(to, fx.len[i] - 1);
      if (last <= from) continue;
      const base = i * HIST;
      const near = base + ((head - from + hist) % hist); // a step is one straight chord between its two ends
      const far = base + ((head - last + hist) % hist);
      ctx.moveTo(fx.hx[far], fx.hy[far]);
      ctx.lineTo(fx.hx[near], fx.hy[near]);
    }
    ctx.stroke();
  }
}

// ---------------------------------------------------------------- precipitation

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

function drawSnow(dt) {
  const { pctx: ctx, w, h, t } = fx;
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
  const { pctx: ctx, w, h } = fx;
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

// ---------------------------------------------------------------- the loop

function sizeCanvas() {
  if (!fx.wcv) return;
  const box = fx.map.getContainer().getBoundingClientRect();
  fx.w = Math.max(Math.round(box.width), 1);
  fx.h = Math.max(Math.round(box.height), 1);
  const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(MAX_PIXELS / (fx.w * fx.h))));
  const wind = Math.min(1, Math.sqrt(WIND_PIXELS / (fx.w * fx.h))); // trails are soft hairlines: drawn at css-pixel density or coarser
  for (const [cv, ctx, k] of [[fx.wcv, fx.wctx, wind], [fx.pcv, fx.pctx, dpr]]) {
    cv.width = Math.round(fx.w * k);
    cv.height = Math.round(fx.h * k);
    ctx.setTransform(k, 0, 0, k, 0, 0);
  }
  fx.seeded = '';
  planParticles();
}

// how many particles of each kind, from the measured wind and what falls; seeded again when anything here changes
function planParticles() {
  const d = fx.data;
  const limit = cap();
  const wind = d && shown() ? d.wind : null;
  const precip = d && shown() && Date.now() - fx.fetchedAt < PRECIP_FRESH_MS ? d.precip : null;
  fx.nP = precip ? Math.round(limit * LEVEL_SHARE[clamp(precip.level, 1, 3) - 1]) : 0;
  fx.kind = precip ? precip.kind : '';
  fx.level = precip ? precip.level : 0;
  fx.nW = 0;
  if (wind && wind.speed_ms >= CALM_MS) {
    const speed = wind.speed_ms;
    const travel = ((wind.from_deg + 180) * Math.PI) / 180; // the wind blows from `from_deg`; north is up the screen
    fx.wTravel = Math.atan2(-Math.cos(travel), Math.sin(travel));
    fx.wDx = Math.cos(fx.wTravel);
    fx.wDy = Math.sin(fx.wTravel);
    fx.wSpeed = speed * PX_PER_MS;
    const length = clamp(24 + 6 * speed, 24, 96); // px a trail reaches behind its head
    fx.hist = clamp(Math.ceil(length / (fx.wSpeed * FRAME_S)), 6, HIST);
    fx.wWidth = clamp(1 + speed * 0.03, 1, 1.4);
    fx.nW = Math.min(Math.round(limit * clamp(0.6 + speed / 40, 0.6, 0.9)), limit - fx.nP);
  }
  const signature = `${fx.nW} ${fx.nP} ${fx.kind} ${fx.level} ${fx.wTravel.toFixed(2)} ${fx.wSpeed.toFixed(0)} ${fx.hist} ${fx.w} ${fx.h}`;
  if (signature === fx.seeded) return; // a poll that changed nothing does not make every particle jump
  fx.seeded = signature;
  seedWind();
  seedPrecip();
  fx.pctx.clearRect(0, 0, fx.w, fx.h);
}

function frame(now) {
  fx.raf = requestAnimationFrame(frame);
  const elapsed = now - fx.last;
  if (elapsed < FRAME_MS) return;
  fx.last = now;
  const dt = Math.min(elapsed, 100) / 1000;
  fx.t += dt;
  if (fx.nW) drawWind(dt);
  if (fx.nP) {
    fx.pctx.clearRect(0, 0, fx.w, fx.h);
    if (fx.kind === 'snow') drawSnow(dt);
    else drawRain(dt);
  }
}

const animating = () => shown() && !document.hidden && !fx.sheetFull && fx.wcv && (fx.nW > 0 || fx.nP > 0);

function clearCanvases() {
  if (!fx.wctx) return;
  fx.wctx.clearRect(0, 0, fx.w, fx.h);
  fx.pctx.clearRect(0, 0, fx.w, fx.h);
}

function syncLoop() {
  if (animating()) {
    if (!fx.raf) {
      fx.last = 0;
      fx.raf = requestAnimationFrame(frame);
    }
  } else if (fx.raf) {
    cancelAnimationFrame(fx.raf);
    fx.raf = 0;
    clearCanvases();
  }
}

// ---------------------------------------------------------------- what is shown

function paint() {
  const d = fx.data;
  const on = shown() && !!d && d.known;
  fx.sky.classList.toggle('on', on);
  fx.wcv.hidden = fx.pcv.hidden = !on;
  if (!d || !d.known) return;
  const [top, bottom] = skyColours(d.sun, d.sky ? d.sky.cloud_pct : null, !!d.air);
  fx.sky.style.setProperty('--fx-a', top);
  fx.sky.style.setProperty('--fx-b', bottom);
  const lum = clamp((d.sun.altitude + 11) / 5, 0, 1); // the trails are slate on a lit map and pale on a night one
  const ink = mixRgb(INK_NIGHT, INK_DAY, lum);
  const alpha = 0.42 - 0.12 * (1 - lum); // and fainter by night: wind is air, not weather
  for (let b = 0; b < BUCKETS; b += 1) fx.trail[b] = rgba(ink, alpha * BUCKET_ALPHA[b]);
  fx.rain = rgba(ink, 0.45 + 0.1 * (1 - lum));
  fx.edge = rgba(INK_DAY, 0.3 * lum);
}

function renderUi() {
  renderPanel({ data: fx.data, effectsOn: fx.userOn, online: fx.online });
}

function render() {
  paint();
  planParticles();
  renderUi();
  syncLoop();
}

// ---------------------------------------------------------------- the data

// the card needs the numbers also while the effects are off, so the data is read whenever the basemap is the real one
async function load() {
  clearTimeout(fx.timer);
  if (!fx.online) return;
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

class FxControl {
  onAdd() {
    this.el = makeButton('ctrl');
    return this.el;
  }

  onRemove() {
    this.el.remove();
  }
}

// a phone's sheet at «full» covers the map: the loop rests and the card goes (the class is the sheet's own, sheet.js)
function watchSheets() {
  const panels = ['view-assistant', 'view-city'].map((id) => document.getElementById(id));
  const read = () => {
    fx.sheetFull = isPhone() && panels.some((p) => p && !p.hidden && p.classList.contains('pos-full'));
    if (fx.sheetFull) closePanel();
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
  else {
    clearTimeout(fx.timer);
    closePanel();
  }
  render();
}

// the button joins the corner's buttons below the location button, which the shell adds later (map.addLocate)
export function addToggle() {
  fx.map.addControl(new FxControl(), 'top-right');
}

export function initWeather(map, kind) {
  fx.map = map;
  fx.userOn = initialChoice();
  const canvas = map.getCanvas();
  fx.sky = h('div', { class: 'fx-sky', 'aria-hidden': 'true' });
  fx.wcv = h('canvas', { class: 'fx-canvas', 'aria-hidden': 'true', hidden: true });
  fx.pcv = h('canvas', { class: 'fx-canvas', 'aria-hidden': 'true', hidden: true });
  fx.wctx = fx.wcv.getContext('2d', { alpha: true });
  fx.pctx = fx.pcv.getContext('2d', { alpha: true });
  initPanel({ onToggle: () => setUser(!fx.userOn, { store: true }) });
  const tools = document.querySelector('.top-tools');
  if (tools) tools.prepend(makeButton('top'));
  canvas.after(fx.sky, fx.wcv, fx.pcv); // above the basemap's canvas, below the pins and labels (they are added later)
  new ResizeObserver(sizeCanvas).observe(map.getContainer());
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && fx.online && Date.now() - fx.fetchedAt > POLL_MS) load();
    syncLoop();
  });
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
    let saved = null;
    try {
      saved = localStorage.getItem(KEY);
    } catch { /* no storage */ }
    if (e.matches && saved !== 'on') setUser(false);
  });
  watchSheets();
  sizeCanvas();
  setBasemapKind(kind);
}
