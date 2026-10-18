// The address field: «Кенесары 40», «хан шатыр», «Mangilik Yel» -> up to five points of Astana from GET /api/geocode, each
// with its kind (дом / улица / место) and district. Recent picks (the last three, this browser only) show while the
// field is empty. Keyboard: arrows, Enter, Esc (clears the field first). An empty answer is never a dead end: the
// message says what to try, and the caller keeps «Моё местоположение» and «Выбрать на карте» beside the field.

import { h, icon } from './dom.js';
import { currentLang, onLang, tr } from './i18n.js';

const RECENT_KEY = 'anyq.recent-where';
const RECENT_MAX = 3;
const MIN_CHARS = 2;
const DEBOUNCE_MS = 180;
const HITS = 5;

export function recents() {
  try {
    const saved = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    return (Array.isArray(saved) ? saved : [])
      .filter((r) => r && typeof r.label === 'string' && Number.isFinite(r.lat) && Number.isFinite(r.lon))
      .slice(0, RECENT_MAX);
  } catch {
    return [];
  }
}

function remember(hit) {
  const same = (r) => r.label === hit.label && Math.abs(r.lat - hit.lat) < 1e-4 && Math.abs(r.lon - hit.lon) < 1e-4;
  const next = [hit, ...recents().filter((r) => !same(r))].slice(0, RECENT_MAX);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
}

async function lookup(q, signal) {
  const params = new URLSearchParams({ q, lang: currentLang() });
  const res = await fetch(`/api/geocode?${params}`, { signal, cache: 'no-store' });
  if (!res.ok) throw new Error(`geocode ${res.status}`);
  return (await res.json()).results.slice(0, HITS);
}

// the house under a point, for a short address of a point picked on the map or found by the device; null if none
export async function addressAt(lat, lon) {
  try {
    const params = new URLSearchParams({ lat, lon, lang: currentLang() });
    const res = await fetch(`/api/geocode?${params}`, { cache: 'no-store' });
    if (!res.ok) return null;
    const [hit] = (await res.json()).results;
    return hit ? hit.label : null;
  } catch {
    return null;
  }
}

// id: a prefix for the element ids; onPick(hit) with {label, kind, lat, lon, district}
export function addressSearch({ id, onPick, label = 'adr_label' }) {
  let hits = [];
  let active = -1;
  let timer = 0;
  let ctl = null;
  let seq = 0;
  let failed = false;

  const input = h('input', {
    id: `${id}-q`,
    class: 'addr-input',
    type: 'text',
    role: 'combobox',
    inputmode: 'search',
    enterkeyhint: 'search',
    autocomplete: 'off',
    autocapitalize: 'off',
    autocorrect: 'off',
    spellcheck: 'false',
    maxlength: '100',
    'aria-autocomplete': 'list',
    'aria-expanded': 'false',
    'aria-controls': `${id}-list`,
  });
  const clear = h('button', { type: 'button', class: 'addr-clear', hidden: true, onclick: () => { reset(); input.focus(); } }, icon('close'));
  const field = h('div', { class: 'addr-field' }, icon('search'), input, clear);
  const list = h('ul', { class: 'addr-list', id: `${id}-list`, role: 'listbox', hidden: true });
  const msg = h('p', { class: 'addr-msg', role: 'status', hidden: true });
  const el = h('div', { class: 'addr' }, field, list, msg);

  const text = () => input.value.trim();

  function setActive(i) {
    active = i;
    const rows = list.querySelectorAll('.addr-row');
    rows.forEach((row, n) => row.setAttribute('aria-selected', String(n === i)));
    if (i >= 0 && rows[i]) {
      input.setAttribute('aria-activedescendant', rows[i].id);
      rows[i].scrollIntoView({ block: 'nearest' });
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function row(hit, i, withKind) {
    const sub = [hit.district].filter(Boolean).join(' · ');
    return h('li', {
      class: 'addr-row',
      id: `${id}-o${i}`,
      role: 'option',
      'aria-selected': 'false',
      onclick: () => choose(hit),
    },
    icon('pin'),
    h('span', { class: 'addr-main' }, h('span', { class: 'addr-label', text: hit.label }), sub ? h('span', { class: 'addr-sub', text: sub }) : null),
    withKind && hit.kind ? h('span', { class: 'addr-kind', text: tr(`adr_${hit.kind}`) }) : null);
  }

  function paint() {
    const q = text();
    clear.hidden = !q;
    const shown = q.length >= MIN_CHARS ? hits : recents();
    const asked = q.length >= MIN_CHARS;
    list.replaceChildren();
    if (!asked && shown.length) list.append(h('li', { class: 'addr-head', role: 'presentation', text: tr('adr_recent') }));
    shown.forEach((hit, i) => list.append(row(hit, i, asked)));
    list.hidden = !shown.length;
    input.setAttribute('aria-expanded', String(!list.hidden));
    const note = failed ? 'adr_fail' : asked && !shown.length && !el.classList.contains('busy') ? 'adr_none' : '';
    msg.hidden = !note;
    msg.replaceChildren(...(note ? [icon('info'), h('span', { text: tr(note) })] : []));
    setActive(-1);
  }

  async function run() {
    const q = text();
    if (q.length < MIN_CHARS) return;
    ctl?.abort();
    ctl = new AbortController();
    const mine = (seq += 1);
    el.classList.add('busy');
    try {
      const found = await lookup(q, ctl.signal);
      if (mine !== seq) return;
      hits = found;
      failed = false;
    } catch (err) {
      if (err.name === 'AbortError' || mine !== seq) return;
      hits = [];
      failed = true;
    }
    el.classList.remove('busy');
    paint();
  }

  function choose(hit) {
    remember(hit);
    reset();
    onPick(hit);
  }

  function reset() {
    clearTimeout(timer);
    ctl?.abort();
    seq += 1;
    input.value = '';
    hits = [];
    failed = false;
    el.classList.remove('busy');
    paint();
  }

  input.addEventListener('input', () => {
    clearTimeout(timer);
    failed = false;
    if (text().length < MIN_CHARS) {
      ctl?.abort();
      seq += 1;
      hits = [];
      el.classList.remove('busy');
      paint();
      return;
    }
    el.classList.add('busy');
    clear.hidden = false;
    timer = setTimeout(run, DEBOUNCE_MS);
  });

  input.addEventListener('keydown', async (e) => {
    const rows = list.querySelectorAll('.addr-row').length;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!rows) return;
      e.preventDefault();
      setActive((active + (e.key === 'ArrowDown' ? 1 : -1) + rows) % rows);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (text().length < MIN_CHARS && !rows) return;
      if (el.classList.contains('busy')) {
        clearTimeout(timer);
        await run();
      }
      const shown = text().length >= MIN_CHARS ? hits : recents();
      const hit = shown[active >= 0 ? active : 0];
      if (hit) choose(hit);
    } else if (e.key === 'Escape' && text()) {
      e.preventDefault();
      e.stopPropagation(); // a dialog around the field would close on the same key
      reset();
    }
  });

  const words = () => {
    input.placeholder = tr('adr_ph');
    input.setAttribute('aria-label', tr(label));
    clear.setAttribute('aria-label', tr('adr_clear'));
  };
  words();
  paint();
  onLang(() => {
    words();
    if (text().length >= MIN_CHARS) run();
    else paint();
  });
  return { el, input, focus: () => input.focus({ preventScroll: true }), reset };
}
