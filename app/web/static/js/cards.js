// The place as the panel shows it: the main card (status, the day's hours, why, the source of the hours, the way out),
// an alternative as one compact row, a mini row of a folded answer, and the card under an answer about a place.
// Every word comes from the turn (walks.dialog `Place`); nothing here decides what a place is.

import { h, icon, isPhone } from './dom.js';
import { askBlocks, deepLinks, detailSections, hoursSource, priceParts, sourceLinks, telHref } from './details.js';
import { dayAndTime, hhmm, metres, minutes, stateOf } from './fmt.js';
import { tr } from './i18n.js';

const STATE_ICON = { open: 'open', closing_soon: 'clock', closed: 'closed' };

// an icon and the words of the turn; hours that are unknown are plain muted words, nothing more
export function statusEl(place) {
  const state = stateOf(place);
  if (state === 'unknown') return h('span', { class: 'st unknown' }, place.hours.text);
  return h('span', { class: `st ${state}` }, icon(STATE_ICON[state]), place.hours.text);
}

const nowHour = (at) => {
  const [hh, mm] = (at ? at.time : '00:00').split(':').map(Number);
  return hh + mm / 60;
};

// «сегодня» / «завтра» / «пн»: the day the answer is about (`at.day` days ahead of today), never «today» for tomorrow
function dayWord(at) {
  if (!at || !at.day) return tr('h_today');
  return at.day === 1 ? tr('h_tomorrow') : dayAndTime(at).split(' ')[0];
}

// the day as a strip: open spans, a tick at the moment of the answer; with no schedule there is no strip at all
export function hoursStrip(place, at) {
  const spans = place.hours.today;
  if (spans == null || place.hours.state === 'unknown') return null;
  const now = h('b', { style: `left:${(nowHour(at) / 24) * 100}%`, 'aria-hidden': 'true' });
  const bar = h('div', { class: 'hbar' },
    spans.map(([open, close]) => h('i', { style: `left:${(open / 24) * 100}%;width:${((close - open) / 24) * 100}%` })), spans.length ? now : null);
  const closed = at && at.day ? `${dayWord(at)} ${tr('h_closed_word')}` : tr('h_today_closed');
  const today = spans.length ? spans.map(([o, c]) => `${hhmm(o)}–${hhmm(c)}`).join(', ') : closed;
  return h('div', { class: 'strip' }, bar,
    h('div', { class: 'hcap' }, h('span', { text: spans.length ? `${dayWord(at)} ${today}` : today }), h('span', { text: `${at && at.day ? dayWord(at) : tr('h_now')} ${at ? at.time : ''}` })));
}

function walkTail(place) {
  const w = place.walk;
  return `${metres(w.distance_m)}${w.method === 'valhalla' ? '' : ` · ${tr(w.method === 'straight' ? 'walk_straight' : 'walk_estimate')}`}`;
}

function num(n) {
  return h('span', { class: n > 9 ? 'num long' : 'num', text: String(n) });
}

function out(href, label, primary) {
  return h('a', { class: `btn${primary ? ' pri' : ''}`, href, target: '_blank', rel: 'noopener noreferrer' }, icon('external'), label);
}

// the way into a place's details: the arrow at the end of its title row (the rows of the other places have the same one)
function moreButton(place, onDetails) {
  return h('button', { type: 'button', class: 'more-b card-more', 'aria-label': tr('details'), title: tr('details'), onclick: () => onDetails(place.id) }, icon('next'));
}

// the source of the hours on a card: whose they are and when they were read; no source, no line (the status says it)
function sourceLine(place) {
  const source = hoursSource(place);
  return source.length ? h('div', { class: 'c-src' }, h('span', { class: 'src' }, ...source)) : null;
}

// a row or a card is the place's handle on the page: it is hovered with its pin and selected with it
function wire(el, place, o) {
  el.dataset.pid = place.id;
  if (o.sel === place.id) el.classList.add('sel');
  // pointer events, like the map's pins: a jump from a row to a pin must run leave-then-enter in one order for both
  el.addEventListener('pointerenter', (e) => e.pointerType === 'mouse' && o.onHover(place.id));
  el.addEventListener('pointerleave', (e) => e.pointerType === 'mouse' && o.onHover(null));
  el.addEventListener('click', (e) => {
    if (e.target.closest('button, a, summary, details')) return;
    // the main card is already the chosen place: a tap on it on a phone opens its details
    if (isPhone() && el.classList.contains('primary') && o.sel === place.id) o.onDetails(place.id);
    else o.onSelect(place.id);
  });
  return el;
}

// a long reason: three lines, «ещё» opens the rest (the phone's card shows two; the whole text is in the details)
function whyBlock(text) {
  const p = h('p', { class: 'why clamp', text });
  const [moreText, lessText] = [tr('why_more'), tr('why_less')]; // in the answer's language, whenever it is tapped
  const more = h('button', { type: 'button', class: 'link why-more', hidden: true, 'aria-expanded': 'false' }, moreText);
  more.addEventListener('click', () => {
    const open = p.classList.toggle('clamp') === false;
    more.textContent = open ? lessText : moreText;
    more.setAttribute('aria-expanded', String(open));
  });
  new ResizeObserver(() => {
    if (p.classList.contains('clamp')) more.hidden = p.scrollHeight <= p.clientHeight + 1;
  }).observe(p);
  return h('div', { class: 'why-wrap' }, p, more);
}

// why the hours are unknown, when the data has a reason (the website lists hours without days, the sources disagree)
function hoursIssue(place) {
  const hrs = place.hours;
  return hrs.state === 'unknown' && hrs.issue && hrs.note ? h('p', { class: 'c-note', text: hrs.note }) : null;
}

// o: {n, at, origin, sel, profileOn, onProfile, onSelect(id), onHover(id|null), onDetails(id)}
export function primaryCard(place, o) {
  const links = deepLinks(place, o.origin);
  const tel = place.phone && telHref(place.phone);
  const price = priceParts(place);
  const card = h(
    'article',
    { class: 'card primary', id: `place-${o.turnId}-${o.n}` },
    h('div', { class: 'c-top' },
      num(o.n),
      h('h3', { class: 'c-title' }, h('span', { class: 'c-name', text: place.name }), h('span', { class: 'c-kind', text: place.kind })),
      h('span', { class: 'c-min', text: minutes(place.walk.minutes, place.walk.method) }),
      moreButton(place, o.onDetails)),
    h('div', { class: 'c-st' }, statusEl(place), h('span', { class: 'm', text: walkTail(place) })),
    hoursStrip(place, o.at),
    hoursIssue(place),
    price ? h('p', { class: 'price' }, ...price) : null,
    place.signal
      ? h('p', { class: 'note signal' }, icon('info'), h('span', {}, place.signal.text, ' · ', ...sourceLinks([place.signal.source])))
      : null,
    place.caveat ? h('p', { class: 'c-note', text: place.caveat }) : null,
    place.vibe ? h('p', { class: 'c-vibe', text: place.vibe }) : null,
    place.why ? whyBlock(place.why) : null,
    sourceLine(place),
    h('div', { class: 'acts' },
      out(links.gis, tr('open_2gis'), true),
      out(links.yandex, tr('open_yandex_short')),
      tel ? h('a', { class: 'btn call', href: tel, 'aria-label': tr('call') }, icon('phone'), h('span', { class: 'call-lbl', text: tr('call') })) : null),
  );
  return wire(card, place, o);
}

// an alternative: name and kind, status and metres, minutes; the arrow opens its details
export function altRow(place, o) {
  const row = h(
    'div',
    { class: 'alt', id: `place-${o.turnId}-${o.n}` },
    num(o.n),
    h('span', { class: 'a-l1' }, h('span', { class: 'a-name', text: place.name }), h('span', { class: 'kd', text: place.kind })),
    h('span', { class: 'a-meta' }, statusEl(place), h('span', { class: 'm', text: walkTail(place) })),
    place.vibe ? h('span', { class: 'a-vibe', text: place.vibe }) : null,
    h('span', { class: 'a-end' },
      h('span', { class: 'a-min', text: minutes(place.walk.minutes, place.walk.method) }),
      h('button', { type: 'button', class: 'more-b', 'aria-label': tr('details'), onclick: () => o.onDetails(place.id) }, icon('next'))),
  );
  return wire(row, place, o);
}

// a folded answer keeps one line per place; a tap opens the answer
export function miniRow(place, o) {
  const row = h(
    'button',
    { type: 'button', class: 'mrow', 'aria-label': `${tr('turn_open')}: ${place.name}`, onclick: o.onOpen },
    num(o.n),
    h('span', { class: 'mn', text: place.name }),
    statusEl(place),
    h('span', { class: 'mm', text: minutes(place.walk.minutes, place.walk.method) }),
  );
  return row;
}

// the place a question was about, under the sentence that answers it
export function qaCard(place, o) {
  const card = h(
    'article',
    { class: 'qa-card', id: `place-${o.turnId}-qa` },
    h('div', { class: 'c-top' }, o.n ? num(o.n) : null, h('b', { text: place.name }), statusEl(place), moreButton(place, o.onDetails)),
    hoursStrip(place, o.at),
    sourceLine(place),
  );
  return wire(card, place, o);
}

// The details view of a place, grouped by what the person is doing (now, getting there, about, contacts, sources), the
// questions to the visitor, and the way out pinned at the bottom (with the way back on a phone).
// o: {n, at, origin, sel, profileOn, onProfile, onBack}
export function detailsView(place, o) {
  const links = deepLinks(place, o.origin);
  const tel = place.phone && telHref(place.phone);
  const name = h('div', { class: 'dname' }, o.n ? h('span', { class: `num${o.sel === place.id ? ' sel' : ''}`, text: String(o.n) }) : null, h('h2', { text: place.name }));
  return h(
    'div',
    { class: 'details-view' },
    h('div', { class: 'dhead' }, h('button', { type: 'button', class: 'backb', onclick: o.onBack }, icon('back'), tr('back_to_answer'))),
    name,
    h('div', { class: 'dsub', text: place.kind }),
    ...detailSections(place, hoursStrip(place, o.at), statusEl(place)),
    h('div', { class: 'asks' }, ...askBlocks(place, o)),
    h('div', { class: 'acts' },
      h('button', { type: 'button', class: 'btn back-b', 'aria-label': tr('back_to_answer'), onclick: o.onBack }, icon('back')),
      out(links.gis, tr('open_2gis'), true),
      out(links.yandex, tr('open_yandex_short')),
      tel ? h('a', { class: 'btn call', href: tel, 'aria-label': tr('call') }, icon('phone'), h('span', { class: 'call-lbl', text: tr('call') })) : null),
  );
}
