// One walking leg, origin -> place: {minutes, meters, method, shape}. method is the router's: 'valhalla' is a walked
// street line; 'straight' and 'estimate' are a faint dashed straight hint whose numbers carry «≈» (never a fake street).

import { fmtNumber } from './dom.js';
import { currentLang, tr } from './i18n.js';

export const isStreet = (leg) => Boolean(leg && leg.method === 'valhalla' && leg.shape && leg.shape.length > 1);

export function minutesText(leg) {
  if (!leg || leg.minutes == null) return '';
  return `${isStreet(leg) ? '' : '≈'}${tr('min_short', { n: leg.minutes })}`;
}

// «≈7 мин · 540 м»
export function walkText(leg) {
  if (!leg || leg.minutes == null) return '';
  const lang = currentLang();
  const metres = leg.meters == null ? '' : ` · ${fmtNumber(Math.round(leg.meters), lang)} ${lang === 'en' ? 'm' : 'м'}`;
  return `${minutesText(leg)}${metres}`;
}
