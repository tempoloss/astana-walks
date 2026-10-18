// The UI strings come from the server (app/i18n.py: one (kk, ru, en) tuple per key), so the three languages stay in
// one table that the tests check. `tr(key, fields)` fills {fields} like Python's str.format.

const INDEX = { kk: 0, ru: 1, en: 2 };
const KEY = 'anyq.lang';
let table = {};
let lang = 'ru';
const listeners = new Set();

export function initStrings(strings) {
  table = strings;
}

// a returning visitor's own pick first, then the browser's language; a stand that only replays recorded answers starts
// in Russian instead: its recordings are Russian (one Kazakh), so an English browser would meet the template on every
// starter tile
export function initialLang({ followBrowser = true } = {}) {
  const saved = localStorage.getItem(KEY);
  if (saved in INDEX) return saved;
  if (!followBrowser) return 'ru';
  const nav = (navigator.language || '').slice(0, 2).toLowerCase();
  return nav in INDEX ? nav : 'ru';
}

export function currentLang() {
  return lang;
}

export function langFixed() {
  return localStorage.getItem(KEY) !== null;
}

export function tr(key, fields) {
  const entry = table[key];
  if (!entry) return key;
  const text = entry[INDEX[lang]];
  if (!fields) return text;
  return text.replace(/\{(\w+)\}/g, (all, name) => (name in fields ? String(fields[name]) : all));
}

export function setLang(next, { user = false } = {}) {
  if (!(next in INDEX)) return;
  if (user) localStorage.setItem(KEY, next);
  if (next === lang) return;
  lang = next;
  document.documentElement.lang = next;
  applyStatic();
  for (const fn of listeners) fn(next, { user });
}

export function onLang(fn) {
  listeners.add(fn);
}

export function applyStatic(root = document) {
  for (const el of root.querySelectorAll('[data-i18n]')) el.textContent = tr(el.dataset.i18n);
  for (const el of root.querySelectorAll('[data-i18n-placeholder]')) el.placeholder = tr(el.dataset.i18nPlaceholder);
  for (const el of root.querySelectorAll('[data-i18n-aria]')) el.setAttribute('aria-label', tr(el.dataset.i18nAria));
  for (const el of root.querySelectorAll('[data-lang]')) el.setAttribute('aria-pressed', String(el.dataset.lang === lang));
  for (const el of root.querySelectorAll('[data-lang-code]')) el.textContent = lang.toUpperCase();
}

export function setInitialLang(next) {
  lang = next in INDEX ? next : 'ru';
  document.documentElement.lang = lang;
  applyStatic();
}
