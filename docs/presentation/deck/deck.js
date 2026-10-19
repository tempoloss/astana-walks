// The Анық deck: 1920 x 1080 slides scaled to the window, keys, builds, and animations that are pure functions of time
// (the approach, the city map and the camera come from the demo video's stage: app/.local/video/demo-2010/stage).
//   slides.html            present: F fullscreen, → / Space / click next build or slide, ← back, Home / End
//   slides.html?print      every slide at its final frame, one per page (build.py makes deck.pdf from it)
//   slides.html?frame      build.py calls window.seek(i, t) to record a slide frame by frame
// window.GEO comes from data/geo.js (build.py): the places, the districts, the river and the live walk of slide 3.

const W = 1920, H = 1080;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const lerp = (a, b, k) => a + (b - a) * k;
const io = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
const inout2 = (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);
const out3 = (k) => 1 - Math.pow(1 - k, 3);
const lin = (k) => k;
const prog = (t, a, d) => clamp((t - a) / d);
const P = (t, a, d, f = io) => f(prog(t, a, d));
const TAU = 6.2832;
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
const fmtInt = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f');
const fmt1 = (x) => x.toFixed(1).replace('.', ',');
function rise(e, k, dy = 26) {
  const v = clamp(k);
  e.style.opacity = String(v);
  e.style.transform = v >= 1 ? '' : `translateY(${((1 - v) * dy).toFixed(1)}px)`;
}
function ringPath(rings, T = (x, y) => [x, y]) {
  const p = new Path2D();
  for (const ring of rings) {
    const [x0, y0] = T(...ring[0]);
    p.moveTo(x0, y0);
    for (const pt of ring.slice(1)) p.lineTo(...T(...pt));
    p.closePath();
  }
  return p;
}
// where an element sits inside its slide, in slide pixels (offsets are not scaled by the presenting transform)
function posIn(el, root) {
  let x = 0, y = 0;
  for (let e = el; e && e !== root; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; }
  return { x, y, w: el.offsetWidth, h: el.offsetHeight };
}

// the colours of the paper and of the night slides (style.css)
const C = {
  paper: '#F2EEE6', card: '#FBFAF7', ink: '#161B26', ink3: '#737885', rule: '#DCD4C6', red: '#D8432E',
  dot: '#A39A8B', water: '#AFC6D6', night: '#10141A', nightInk: '#EDE8DE',
};
// the sources of the places, in the order of figures.SOURCES and of the data slide's bar
const SRC = ['#EDE8DE', '#6F86A0', '#EA5A43', '#F2A384', '#F6D3C6'];

const ANIM = {};

// ---- the city map of the video (stage/engine.js: CityMap, zoomCam) on paper: the places, the districts, the river,
// one street line, numbered places and «Вы здесь»
// a zoom between two cameras {x, y, z} that keeps the motion even in scale: log zoom, the centre travels with 1/z
function zoomCam(c0, c1, k) {
  const z = Math.exp(lerp(Math.log(c0.z), Math.log(c1.z), k));
  if (Math.abs(c0.z - c1.z) < 1e-6) return { x: lerp(c0.x, c1.x, k), y: lerp(c0.y, c1.y, k), z };
  const s = (1 / z - 1 / c1.z) / (1 / c0.z - 1 / c1.z);
  return { x: c1.x + (c0.x - c1.x) * s, y: c1.y + (c0.y - c1.y) * s, z };
}
function polyLen(pts) {
  const acc = [0];
  for (let i = 1; i < pts.length; i++) acc.push(acc[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return acc;
}

class CityMap {
  constructor(cv) {
    cv.width = W; cv.height = H;
    this.g = cv.getContext('2d');
    this.pts = GEO.places;
    this.rivers = GEO.river.map((rv) => ({ p: new Path2D(rv.d), w: rv.w }));
    this.dists = GEO.districts.map((d) => ringPath(d.rings));
  }

  label(text, x, y, side, dark) {
    const g = this.g;
    g.font = "600 24px 'IBM Plex Sans'"; g.textBaseline = 'middle';
    const w = g.measureText(text).width;
    const bx = side === 'l' ? x - w - 20 : x, by = y - 21;
    g.fillStyle = dark ? C.ink : C.card;
    g.fillRect(bx, by, w + 20, 42);
    if (!dark) { g.strokeStyle = '#CBC3B5'; g.lineWidth = 1.5; g.strokeRect(bx + 0.5, by + 0.5, w + 19, 41); }
    g.fillStyle = dark ? C.card : C.ink; g.textAlign = 'left';
    g.fillText(text, bx + 10, y + 1);
  }

  // cam {x, y, z}: the frame point at the screen centre and the zoom; o: {line, k, pins: [{x, y, k, n, label, side}], here, veil}
  draw(cam, o) {
    const g = this.g, z = cam.z;
    const sx = (x) => 960 + (x - cam.x) * z, sy = (y) => 540 + (y - cam.y) * z;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalAlpha = 1;
    g.fillStyle = C.paper;
    g.fillRect(0, 0, W, H);
    g.setTransform(z, 0, 0, z, 960 - cam.x * z, 540 - cam.y * z);
    g.strokeStyle = C.rule; g.lineWidth = 1.4 / z; g.lineJoin = 'round';
    for (const p of this.dists) g.stroke(p);
    g.strokeStyle = C.water; g.lineCap = 'round';
    const rw = Math.min(1 + (z - 1) * 0.55, 16);
    for (const rv of this.rivers) { g.lineWidth = rv.w * rw / z; g.stroke(rv.p); }
    const rr = 2.5 * Math.pow(z, 0.34) / z;
    const x0 = cam.x - 980 / z, x1 = cam.x + 980 / z, y0 = cam.y - 560 / z, y1 = cam.y + 560 / z;
    g.fillStyle = C.dot; g.globalAlpha = 0.85;
    for (const [x, y] of this.pts) {
      if (x < x0 || x > x1 || y < y0 || y > y1) continue;
      g.beginPath(); g.arc(x, y, rr, 0, TAU); g.fill();
    }
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalAlpha = 1;
    if (o.line && o.k > 0) {
      const acc = o.acc || (o.acc = polyLen(o.line));
      const L = acc[acc.length - 1] * clamp(o.k);
      g.beginPath();
      g.moveTo(sx(o.line[0][0]), sy(o.line[0][1]));
      for (let i = 1; i < o.line.length; i++) {
        if (acc[i] <= L) { g.lineTo(sx(o.line[i][0]), sy(o.line[i][1])); continue; }
        const f = (L - acc[i - 1]) / (acc[i] - acc[i - 1] || 1);
        g.lineTo(sx(lerp(o.line[i - 1][0], o.line[i][0], f)), sy(lerp(o.line[i - 1][1], o.line[i][1], f)));
        break;
      }
      g.lineCap = 'round'; g.lineJoin = 'round';
      g.strokeStyle = C.paper; g.lineWidth = 15; g.stroke();
      g.strokeStyle = C.red; g.lineWidth = 7; g.stroke();
    }
    for (const pn of o.pins || []) {
      const k = clamp(pn.k);
      if (k <= 0) continue;
      const px = sx(pn.x), py = sy(pn.y), r = 18;
      g.globalAlpha = k;
      g.fillStyle = C.red;
      g.beginPath(); g.arc(px, py, r * (0.6 + 0.4 * out3(k)), 0, TAU); g.fill();
      g.strokeStyle = C.card; g.lineWidth = 3; g.stroke();
      g.fillStyle = '#fff'; g.font = "700 19px 'IBM Plex Sans'"; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(String(pn.n), px, py + 1);
      this.label(pn.label, pn.side === 'l' ? px - r - 10 : px + r + 10, py, pn.side, false);
    }
    const h = o.here;
    if (h && h.k > 0) {
      const px = sx(h.x), py = sy(h.y);
      g.globalAlpha = clamp(h.k);
      const pulse = (h.t % 1.6) / 1.6;
      g.strokeStyle = `rgba(22,27,38,${(0.55 * (1 - pulse)).toFixed(3)})`; g.lineWidth = 2;
      g.beginPath(); g.arc(px, py, 12 + 34 * pulse, 0, TAU); g.stroke();
      g.fillStyle = C.ink; g.strokeStyle = C.card; g.lineWidth = 4;
      g.beginPath(); g.arc(px, py, 11, 0, TAU); g.fill(); g.stroke();
      g.font = "700 20px 'IBM Plex Sans'";
      const w = g.measureText('Вы здесь').width;
      this.label('Вы здесь', px - (w + 20) / 2, py + 45, 'r', true);
    }
    if (o.veil > 0) {
      g.globalAlpha = clamp(o.veil);
      g.fillStyle = C.paper;
      g.fillRect(0, 0, W, H);
    }
    g.globalAlpha = 1;
  }
}

// 03: the live answer on the city map: the camera flies from the city to the street, the walk of the answer is drawn
// street by street, its places come up, then the camera settles where the stand's own screen of the same answer lands,
// so that the stand's route covers ours (GEO.take.match: the scale and the «Вы здесь» point of the stand's screenshot)
ANIM.demo = (root) => {
  const map = new CityMap(root.querySelector('canvas.route'));
  const T = GEO.take, shot = root.querySelector('.shot');
  const all = [T.start, ...T.places.map((p) => p.xy), ...T.line];
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  const bx0 = Math.min(...xs), bx1 = Math.max(...xs), by0 = Math.min(...ys), by1 = Math.max(...ys);
  const START = { x: 760, y: 430, z: 0.9 };
  const zs = Math.min(620 / (bx1 - bx0), 560 / (by1 - by0));
  const STREET = { x: (bx0 + bx1) / 2 - (1100 - 960) / zs, y: (by0 + by1) / 2 - (650 - 540) / zs, z: zs };
  // the screenshot's pixel of «Вы здесь» and its pixels per frame unit, scaled into the browser frame (measured once
  // the slide is on screen: offsets of a hidden slide are 0)
  const img = shot.querySelector('img');
  let MATCH = null;
  const match = () => {
    const at = posIn(img, root), k = at.w / T.match.width, z = T.match.scale * k;
    return { x: T.start[0] - (at.x + T.match.here[0] * k - 960) / z, y: T.start[1] - (at.y + T.match.here[1] * k - 540) / z, z };
  };
  const o = { line: T.line, k: 0, pins: [], here: null, veil: 0 };
  return {
    dur: 6.8,
    draw(t) {
      if (!MATCH && img.offsetWidth) MATCH = match();
      const gone = 1 - P(t, 5.1, 0.5, lin);
      o.k = P(t, 2.6, 1.5, inout2);
      o.here = { x: T.start[0], y: T.start[1], k: P(t, 0.3, 0.5, out3) * gone, t: Math.min(t, 6.4) };
      // the labels go left: the line comes into the first place from the right
      o.pins = T.places.map((p, i) => ({ x: p.xy[0], y: p.xy[1], n: i + 1, label: p.label, side: 'l',
        k: P(t, i === 0 ? 4.0 : 3.4, 0.45, out3) * gone }));
      o.veil = 0.9 * P(t, 5.6, 0.6);
      const cam = t < 4.4 || !MATCH ? zoomCam(START, STREET, P(t, 0.5, 2.3, inout2)) : zoomCam(STREET, MATCH, P(t, 4.4, 0.9, inout2));
      map.draw(cam, o);
      rise(shot, P(t, 5.1, 0.7, lin), 0);
    },
  };
};

// 05: the line under the place that says why it fits: ringed once the phone is up, then tied to its large copy
ANIM.ring = (root) => {
  const ring = root.querySelector('.ring'), line = root.querySelector('.lead-line');
  const call = root.querySelector('.call b');
  let geom = null;
  const place = () => {
    const r = posIn(ring, root), c = posIn(call, root);
    const x0 = c.x + c.w + 28, x1 = r.x - 14, y = r.y + r.h / 2;
    line.style.left = `${x0}px`; line.style.top = `${y - 1.5}px`; line.style.width = `${Math.max(0, x1 - x0)}px`;
    geom = true;
  };
  return {
    dur: 2.8,
    draw(t) {
      if (!geom) place();
      const k = P(t, 1.0, 0.5, out3);
      ring.style.opacity = String(k);
      ring.style.transform = `scale(${lerp(1.12, 1, k).toFixed(3)})`;
      line.style.transform = `scaleX(${P(t, 1.6, 0.6, out3).toFixed(3)})`;
    },
  };
};

// 06: one bar per test scenario, all 120 of them, and the share of honest answers counting up
ANIM.trust = (root) => {
  const box = root.querySelector('.cells');
  const n = +box.dataset.n;
  box.innerHTML = '<i></i>'.repeat(n);
  const cells = [...box.children];
  const pct = root.querySelector('[data-count]');
  const target = parseFloat(pct.dataset.count);
  return {
    dur: 2.8,
    draw(t) {
      cells.forEach((c, i) => { c.style.opacity = String(P(t, 0.6 + i * 0.012, 0.2, out3)); });
      pct.innerHTML = `${Math.round(target * P(t, 0.8, 1.4, lin))}<small>%</small>`;
    },
  };
};

// counters of the slide: every [data-int] runs from 0 to its value, one after another
function counters(root, t0, d, gap) {
  const els = [...root.querySelectorAll('[data-int]')].map((e) => ({ e, v: parseInt(e.dataset.int, 10) }));
  return (t) => els.forEach(({ e, v }, i) => { e.textContent = fmtInt(v * P(t, t0 + i * gap, d, out3)); });
}

// 07: the rounds and the tests counting up
ANIM.live = (root) => {
  const run = counters(root, 1.0, 1.2, 0.35);
  return { dur: 2.6, draw: run };
};

// 08: the first visible step of the answer: 0,0 → 0,3 s
ANIM.speed = (root) => {
  const big = root.querySelector('[data-count]');
  const target = parseFloat(big.dataset.count.replace(',', '.'));
  return {
    dur: 2.6,
    draw(t) { big.innerHTML = `${fmt1(target * P(t, 0.2, 0.9, lin))}<small>с</small>`; },
  };
};

// 09: the districts filled by how complete the data on their places are (the share with known hours), named
ANIM.city = (root) => {
  const cv = root.querySelector('canvas');
  const box = { w: cv.width, h: cv.height };
  const g = cv.getContext('2d');
  const D = GEO.full.districts;
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const d of D) for (const ring of d.rings) for (const [x, y] of ring) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const s = Math.min((box.w - 220) / (x1 - x0), (box.h - 60) / (y1 - y0));
  const ox = (box.w - (x1 - x0) * s) / 2 - x0 * s, oy = (box.h - (y1 - y0) * s) / 2 - y0 * s;
  const T = (x, y) => [ox + x * s, oy + y * s];
  const m = new DOMMatrix([s, 0, 0, s, ox, oy]);
  const water = GEO.full.river.map((rv) => { const p = new Path2D(); p.addPath(new Path2D(rv.d), m); return { p, w: rv.w }; });
  const host = cv.parentElement;
  const lo = Math.min(...D.map((d) => d.hours)), hi = Math.max(...D.map((d) => d.hours));
  const A = [0xE6, 0xDF, 0xD2], B = [0x46, 0x59, 0x7A];
  const ds = D.map((d, i) => {
    const lab = document.createElement('div');
    lab.className = 'd-lab';
    lab.textContent = d.name;
    const [lx, ly] = T(...d.label);
    lab.style.left = `${lx}px`; lab.style.top = `${ly}px`;
    host.append(lab);
    const leader = d.leader ? [lx, ly, ...T(...d.leader)] : null;
    // darker: the places of the district have more of their data (the share with known hours)
    const k = (d.hours - lo) / (hi - lo);
    const col = `rgb(${A.map((a, j) => Math.round(lerp(a, B[j], 0.15 + 0.85 * k))).join(',')})`;
    return { p: ringPath(d.rings, T), col, lab, leader, delay: 0.3 + i * 0.16 };
  });
  return {
    dur: 3.2,
    draw(t) {
      g.clearRect(0, 0, box.w, box.h);
      for (const { p, col, delay } of ds) {
        g.globalAlpha = P(t, delay, 0.7, out3);
        g.fillStyle = col;
        g.fill(p);
        g.strokeStyle = C.paper; g.lineWidth = 3; g.lineJoin = 'round';
        g.stroke(p);
      }
      g.globalAlpha = P(t, 0.6, 0.8);
      g.strokeStyle = '#7FA7C2'; g.lineCap = 'round'; g.lineJoin = 'round';
      for (const rv of water) { g.lineWidth = rv.w * 0.9; g.stroke(rv.p); }
      for (const { lab, leader, delay } of ds) {
        const k = P(t, delay + 0.8, 0.5, out3);
        rise(lab, k, 12);
        if (leader && k > 0) {
          g.globalAlpha = k;
          g.strokeStyle = C.ink3; g.lineWidth = 1.5;
          g.beginPath(); g.moveTo(leader[0], leader[1] + (leader[3] > leader[1] ? 18 : -18)); g.lineTo(leader[2], leader[3]); g.stroke();
          g.fillStyle = C.ink3;
          g.beginPath(); g.arc(leader[2], leader[3], 4, 0, TAU); g.fill();
        }
      }
      g.globalAlpha = 1;
    },
  };
};

// 10: the 4170 places open from the centre of the city, coloured by their source; the counter is the number of dots
// shown, the bar fills source by source with them
ANIM.data = (root) => {
  const cv = root.querySelector('canvas.dots');
  const g = cv.getContext('2d');
  const r = rng(20261019);
  const xs = GEO.places.map((p) => p[0]).sort((a, b) => a - b), ys = GEO.places.map((p) => p[1]).sort((a, b) => a - b);
  const q = (a, f) => a[Math.floor(f * (a.length - 1))];
  const bx0 = q(xs, 0.01), bx1 = q(xs, 0.99), by0 = q(ys, 0.01), by1 = q(ys, 0.99);
  const s = Math.min((cv.width - 80) / (bx1 - bx0), (cv.height - 80) / (by1 - by0));
  const ox = (cv.width - (bx1 - bx0) * s) / 2 - bx0 * s, oy = (cv.height - (by1 - by0) * s) / 2 - by0 * s;
  const cx = (bx0 + bx1) / 2, cy = (by0 + by1) / 2;
  const md = Math.hypot(bx1 - cx, by1 - cy);
  const pts = GEO.places.map(([x, y, src]) => ({ x: ox + x * s, y: oy + y * s, src,
    at: 0.2 + 2.3 * Math.pow(Math.min(1, Math.hypot(x - cx, y - cy) / md), 0.8) + r() * 0.25 }));
  pts.sort((a, b) => a.at - b.at);
  const total = pts.length, ats = pts.map((p) => p.at);
  const bySrc = SRC.map((_, i) => pts.filter((p) => p.src === i).map((p) => p.at));
  const upTo = (arr, t) => { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] <= t) lo = m + 1; else hi = m; } return lo; };
  const rivers = GEO.river.map((rv) => { const p = new Path2D(); p.addPath(new Path2D(rv.d), new DOMMatrix([s, 0, 0, s, ox, oy])); return { p, w: rv.w }; });
  const segs = [...root.querySelectorAll('.pb i')];
  for (const e of root.querySelectorAll('[data-src]')) e.style.background = SRC[+e.dataset.src];
  const num = root.querySelector('[data-int]');
  return {
    dur: 3.9,
    draw(t) {
      g.clearRect(0, 0, cv.width, cv.height);
      g.globalAlpha = 0.9 * P(t, 0, 0.8);
      g.strokeStyle = '#2A4257'; g.lineCap = 'round'; g.lineJoin = 'round';
      for (const rv of rivers) { g.lineWidth = rv.w * 1.3; g.stroke(rv.p); }
      for (const p of pts) {
        const a = P(t, p.at, 0.45, out3);
        if (a <= 0) break;
        g.globalAlpha = (p.src === 0 ? 0.78 : 0.95) * a;
        g.fillStyle = SRC[p.src];
        g.beginPath(); g.arc(p.x, p.y, (p.src === 0 ? 2.3 : 2.9) * (0.6 + 0.4 * a), 0, TAU); g.fill();
      }
      g.globalAlpha = 1;
      num.textContent = fmtInt(upTo(ats, t));
      let left = 0;
      segs.forEach((e, i) => {
        const w = (100 * upTo(bySrc[i], t)) / total;
        e.style.left = `${left}%`; e.style.width = `${w}%`;
        left += w;
      });
    },
  };
};

// ---------------------------------------------------------------- the runtime

const MODE = new URLSearchParams(location.search).has('print') ? 'print'
  : new URLSearchParams(location.search).has('frame') ? 'frame' : 'present';
const slides = [...document.querySelectorAll('section.slide')];
const ST = slides.map((s) => ({
  anim: null,
  auto: [...s.querySelectorAll('[data-at]')],
  steps: [...s.querySelectorAll('[data-step]')].sort((a, b) => a.dataset.step - b.dataset.step),
}));
const FINAL = 1e4;

function dur(i) {
  const st = ST[i];
  let d = st.anim ? st.anim.dur : 0;
  for (const e of st.auto) d = Math.max(d, +e.dataset.at + 0.7);
  st.steps.forEach((e, k) => { d = Math.max(d, stepAt(e, k) + 0.6); });
  return d;
}
const stepAt = (e, k) => (e.dataset.stepAt ? +e.dataset.stepAt : 0.6 + 0.55 * k);

// t: seconds since the slide opened; reveal[k]: when build k was shown (undefined: not yet)
function draw(i, t, reveal) {
  const st = ST[i];
  if (st.anim) st.anim.draw(t);
  for (const e of st.auto) rise(e, P(t, +e.dataset.at, 0.6, out3), +(e.dataset.dy || 26));
  st.steps.forEach((e, k) => rise(e, reveal[k] === undefined ? 0 : P(t, reveal[k], 0.55, out3), 34));
}

async function setup() {
  await document.fonts.ready;
  document.body.classList.add(MODE);
  slides.forEach((s, i) => {
    const name = s.dataset.anim;
    if (name && ANIM[name]) ST[i].anim = ANIM[name](s);
  });
  if (MODE === 'print') {
    slides.forEach((s, i) => draw(i, FINAL, ST[i].steps.map(() => 0)));
  } else if (MODE === 'frame') {
    window.slideDur = dur;
    window.animated = (i) => Boolean(ST[i].anim);
    window.seek = async (i, t) => {
      slides.forEach((s, k) => s.classList.toggle('on', k === i));
      draw(i, t, ST[i].steps.map((e, k) => stepAt(e, k)));
      await Promise.all([...slides[i].querySelectorAll('img')].map((im) => im.decode().catch(() => null)));
      return true;
    };
  } else {
    present();
  }
  window.READY = true;
}

function present() {
  const deck = document.getElementById('deck');
  const fit = () => {
    const k = Math.min(innerWidth / W, innerHeight / H);
    deck.style.transform = `translate(${(innerWidth - W * k) / 2}px, ${(innerHeight - H * k) / 2}px) scale(${k})`;
  };
  addEventListener('resize', fit);
  fit();
  let cur = 0, t0 = 0, reveal = [], shown = 0;
  const now = () => (performance.now() - t0) / 1000;
  const go = (i, final = false) => {
    cur = clamp(i, 0, slides.length - 1);
    slides.forEach((s, k) => s.classList.toggle('on', k === cur));
    t0 = performance.now() - (final ? FINAL * 1000 : 0);
    shown = final ? ST[cur].steps.length : 0;
    reveal = final ? ST[cur].steps.map(() => 0) : [];
    history.replaceState(null, '', `#${cur + 1}`);
    draw(cur, now(), reveal);
  };
  const next = () => {
    if (shown < ST[cur].steps.length) { reveal[shown++] = Math.max(now(), 0.2); return; }
    if (cur < slides.length - 1) go(cur + 1);
  };
  const back = () => { if (cur > 0) go(cur - 1, true); };
  addEventListener('keydown', (e) => {
    if (['ArrowRight', 'ArrowDown', ' ', 'PageDown', 'Enter'].includes(e.key)) { e.preventDefault(); next(); }
    else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].includes(e.key)) { e.preventDefault(); back(); }
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(slides.length - 1, true);
    else if (e.key === 'f' || e.key === 'F' || e.key === 'а' || e.key === 'А') {
      if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen();
    }
  });
  addEventListener('click', next);
  const start = parseInt(location.hash.slice(1), 10);
  go(Number.isFinite(start) ? start - 1 : 0, Number.isFinite(start) && start > 1);
  const tick = () => {
    const t = now();
    if (t < dur(cur) + 1 || reveal.some((r) => r !== undefined && t < r + 1)) draw(cur, t, reveal);
    requestAnimationFrame(tick);
  };
  draw(cur, now(), reveal);
  requestAnimationFrame(tick);
}

setup();
