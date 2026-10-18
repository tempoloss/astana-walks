// Numbers and times as the page says them. Minutes, metres and clock times are shown in the mono face (`.num-m`).

import { currentLang, tr } from './i18n.js';

const locale = () => (currentLang() === 'en' ? 'en' : 'ru');

export function metres(m) {
  if (m >= 1000) {
    return `${(m / 1000).toLocaleString(locale(), { maximumFractionDigits: 1 })} ${tr('km_short')}`;
  }
  return `${m} ${tr('col_m')}`;
}

// «4 мин», «≈ 4 мин» when the way is not a measured street route (a straight-line estimate)
export function minutes(n, method) {
  return `${method && method !== 'valhalla' ? '≈ ' : ''}${tr('min_short', { n })}`;
}

export function hhmm(hours) {
  const h = Math.floor(hours);
  const m = Math.round((hours - h) * 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function isoDate(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split('-');
  return d && m && y ? `${d}.${m}.${y}` : String(iso);
}

const WEEKDAYS = {
  ru: ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'],
  kk: ['жк', 'дс', 'сс', 'ср', 'бс', 'жм', 'сб'],
  en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
};

// «пн 14:00» from the answer's own moment ({time, date})
export function dayAndTime(at) {
  if (!at) return '';
  const [y, m, d] = at.date.split('-').map(Number);
  const day = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${WEEKDAYS[currentLang()][day]} ${at.time}`;
}

export function percent(x) {
  return `${Math.round(x)}${currentLang() === 'en' ? '' : '\u00a0'}%`;
}

export function count(n) {
  return Number(n).toLocaleString(locale());
}

// the status of a place as the map and the card colour it: open / closing_soon / closed / unknown
export function stateOf(place) {
  const hrs = place.hours;
  return hrs.state === 'open' && hrs.soon ? 'closing_soon' : hrs.state;
}
