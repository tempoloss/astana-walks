// The outline icons of the weather card: one stroke width, drawn like the page's own icons (dom.js `icon`), kept here so the
// card does not grow the shared table. `kind` is MET Norway's symbol reduced by the server (walks.metno.symbol_kind), or
// «arrow» (points up; the card rotates it to where the wind blows), «moon» (a clear night), «wind».

const CLOUD = 'M7 17a4 4 0 0 1-.5-8A6 6 0 0 1 18 8a4.5 4.5 0 0 1-.5 9H7z';
const SUN_RAYS = ['M12 2v2', 'M12 20v2', 'M4.9 4.9l1.4 1.4', 'M17.7 17.7l1.4 1.4', 'M2 12h2', 'M20 12h2', 'M4.9 19.1l1.4-1.4', 'M17.7 6.3l1.4-1.4'];

const PATHS = {
  clear: ['M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', ...SUN_RAYS],
  partly: ['M8 3v1.5', 'M3.2 5.2l1.1 1.1', 'M2 10h1.5', 'M12.8 5.2l-1.1 1.1', 'M9 15.5a4 4 0 0 1-.4-8', 'M10 21a3.5 3.5 0 0 1-.4-7A5 5 0 0 1 19 12.5a4 4 0 0 1-.5 8.5H10z'],
  moon: ['M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z'],
  cloud: [CLOUD],
  fog: ['M4 8h16', 'M6 12h12', 'M4 16h16', 'M8 20h8'],
  rain: ['M7 14a4 4 0 0 1-.5-8A6 6 0 0 1 18 5a4.5 4.5 0 0 1-.5 9H7z', 'M8 17l-1 3', 'M12 17l-1 3', 'M16 17l-1 3'],
  sleet: ['M7 14a4 4 0 0 1-.5-8A6 6 0 0 1 18 5a4.5 4.5 0 0 1-.5 9H7z', 'M8 17l-1 3', 'M16 17l-1 3', 'M12 18h.01', 'M12 21h.01'],
  snow: ['M7 14a4 4 0 0 1-.5-8A6 6 0 0 1 18 5a4.5 4.5 0 0 1-.5 9H7z', 'M8 18h.01', 'M12 18h.01', 'M16 18h.01', 'M10 21h.01', 'M14 21h.01'],
  thunder: ['M7 14a4 4 0 0 1-.5-8A6 6 0 0 1 18 5a4.5 4.5 0 0 1-.5 9H7z', 'M12.5 14l-2.5 3.5h3L11 21'],
  arrow: ['M12 20V5', 'M6 11l6-6 6 6'],
  wind: ['M3 8h10a3 3 0 1 0-3-3', 'M3 12h15a3 3 0 1 1-3 3', 'M3 16h7a2 2 0 1 1-2 2'],
  close: ['M6 6l12 12', 'M18 6L6 18'],
};

export function wxIcon(kind, extraClass) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  if (extraClass) svg.setAttribute('class', extraClass);
  for (const d of PATHS[kind] || []) {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    svg.append(path);
  }
  return svg;
}
