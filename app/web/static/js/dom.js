// DOM helpers. Text from the server or the user only ever enters the page as text nodes (never as HTML).

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, String(value));
  }
  append(el, kids);
  return el;
}

export function append(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false || kid === '') continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const PATHS = {
  send: ['M5 12h13', 'M13 6l6 6-6 6'],
  pin: ['M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z', 'M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z'],
  walk: ['M13 4.5a1.5 1.5 0 1 0 0-.01', 'M10 21l2-6 2.5 2.5V21', 'M7.5 12l3-3.5 3 1 2.5 3', 'M11 8.5l-1.5 6.5'],
  open: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M8 12.5l2.7 2.7L16.2 9.6'],
  closed: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M9 9l6 6', 'M15 9l-6 6'],
  unknown: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M9.6 9.4a2.5 2.5 0 1 1 3.4 2.4c-.6.3-1 .8-1 1.5v.6', 'M12 17h.01'],
  external: ['M14 4h6v6', 'M20 4l-9 9', 'M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'],
  phone: ['M21 16.5v3a2 2 0 0 1-2.2 2 19.5 19.5 0 0 1-8.5-3 19.2 19.2 0 0 1-6-6 19.5 19.5 0 0 1-3-8.5A2 2 0 0 1 3.3 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L7.3 9.8a16 16 0 0 0 6 6l1.2-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.6 1.7z'],
  globe: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M3 12h18', 'M12 3c2.5 2.5 3.6 5.6 3.6 9s-1.1 6.5-3.6 9c-2.5-2.5-3.6-5.6-3.6-9S9.5 5.5 12 3z'],
  chevron: ['M6 9l6 6 6-6'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'M21 21l-4.3-4.3'],
  close: ['M6 6l12 12', 'M18 6L6 18'],
  info: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 11v5', 'M12 8h.01'],
  spark: ['M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z', 'M19 15l.8 1.9 1.9.8-1.9.8L19 20.4l-.8-1.9-1.9-.8 1.9-.8z'],
  target: ['M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', 'M12 2v3', 'M12 19v3', 'M2 12h3', 'M19 12h3'],
  map: ['M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z', 'M9 4v14', 'M15 6v14'],
  route: ['M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', 'M18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', 'M6 15V9a3 3 0 0 1 3-3h1', 'M18 9v6a3 3 0 0 1-3 3h-1'],
  flag: ['M5 21V4', 'M5 4h11l-2 4 2 4H5'],
  wind: ['M3 8h10a3 3 0 1 0-3-3', 'M3 12h15a3 3 0 1 1-3 3', 'M3 16h7a2 2 0 1 1-2 2'],
  cloud: ['M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9H7z'],
  offline: ['M2 2l20 20', 'M8.5 16.5a5 5 0 0 1 7 0', 'M5 12.9a10 10 0 0 1 4.4-2.6', 'M19 12.9a10 10 0 0 0-2.5-1.8', 'M2 8.8a15 15 0 0 1 4.2-2.7', 'M22 8.8A15 15 0 0 0 10.7 5', 'M12 20h.01'],
  refresh: ['M3 12a9 9 0 1 0 2.6-6.4L3 8', 'M3 3v5h5'],
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  person: ['M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M4 21a8 8 0 0 1 16 0'],
  back: ['M15 5l-7 7 7 7'],
  next: ['M9 5l7 7-7 7'],
  moon: ['M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z'],
  clock: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 7v5l3 2'],
  home: ['M4 11l8-7 8 7', 'M6 10v10h12V10', 'M10 20v-5h4v5'],
  work: ['M4 8h16v11H4z', 'M9 8V5h6v3', 'M4 13h16'],
  study: ['M2 9l10-5 10 5-10 5z', 'M6 11.5V16c0 1.4 2.7 3 6 3s6-1.6 6-3v-4.5', 'M22 9v6'],
  star: ['M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.7l1-5.9L3.5 9.7l5.9-.8z'],
  plus: ['M12 5v14', 'M5 12h14'],
  edit: ['M4 20h4L19 9l-4-4L4 16z', 'M13.5 6.5l4 4'],
  trash: ['M4 7h16', 'M9 7V4h6v3', 'M6 7l1 13h10l1-13', 'M10 11v6', 'M14 11v6'],
  layers: ['M12 3l9 5-9 5-9-5z', 'M3 12.5l9 5 9-5', 'M3 16.5l9 5 9-5'],
};

export function icon(name, extraClass) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  if (extraClass) svg.setAttribute('class', extraClass);
  for (const d of PATHS[name] || []) {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    svg.append(path);
  }
  return svg;
}

export function isPhone() {
  return matchMedia('(max-width: 760px)').matches;
}

export function fmtNumber(n, lang) {
  return new Intl.NumberFormat(lang === 'en' ? 'en' : 'ru').format(n);
}

export function pct(x, lang) {
  return new Intl.NumberFormat(lang === 'en' ? 'en' : 'ru', { style: 'percent', maximumFractionDigits: 0 }).format(x);
}
