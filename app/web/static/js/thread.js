// One turn of the conversation on the page: the user's bubble and what came back (a `Turn` of walks.dialog plus the
// page's extras). The latest turn is open, earlier ones fold into their places as mini rows. The user's bubble shows at
// once; while the answer is being made the page waits quietly for 300 ms, then shows the steps the core reports above
// the shape of the answer to come; a shown set of cards is never swapped for another.
// The answer to a follow-up about a place is a sentence and that place's card, in the thread under the folded answer.

import { altRow, miniRow, primaryCard, qaCard } from './cards.js';
import { sourceLinks } from './details.js';
import { h, icon, isPhone } from './dom.js';
import { metres } from './fmt.js';
import { currentLang, tr, withLang } from './i18n.js';

const STEP = { parse: 'step_parse', search: 'step_search', hours: 'step_hours', write: 'step_write', route: 'step_route' };

// The steps in the order the core entered them. A step entered again (the model read the message otherwise and the
// places are searched anew) drops the ones after it: the list never shows more as done than is done.
function stepsSoFar(stages) {
  const seq = [];
  for (const s of stages) {
    if (!STEP[s]) continue;
    const at = seq.indexOf(s);
    if (at >= 0) seq.length = at;
    seq.push(s);
  }
  return seq;
}

// The route as one line of words, in walking order: «Старт → 4 мин → 1 Degirmen → 6 мин → 2 Фаттуш» (a plan only).
function routeLine(turn, byId) {
  const r = turn.route;
  if (!r || !r.stops.length) return null;
  const parts = [h('span', { class: 'stop you', text: tr('rt_start') })];
  r.stops.forEach((id, i) => {
    const hit = byId.get(id);
    parts.push(
      h('span', { class: 'arrow', 'aria-hidden': 'true', text: ' → ' }),
      h('span', { class: 'leg', text: tr('min_short', { n: r.legs_min[i] }) }),
      h('span', { class: 'arrow', 'aria-hidden': 'true', text: ' → ' }),
      h('span', { class: 'stop' }, hit ? h('b', { class: 'n', text: String(hit.n) }) : null, hit ? ` ${hit.place.name}` : id),
    );
  });
  return h('p', { class: 'route-line' }, icon('route'), h('span', {}, parts));
}

// One line from an official or live source («Штормовое предупреждение: …», «Последний автобус № 10 …»): the words and
// the link they stand on; whose observation it is stays in the tooltip.
function noticeLine(notice) {
  const body = h('span', { class: 'notice-body', title: notice.detail || null }, notice.text, notice.source ? [' · ', ...sourceLinks([notice.source])] : null);
  return h('p', { class: `note notice ${notice.kind}` }, icon(notice.kind === 'weather' ? 'cloud' : 'route'), body);
}

// «2 события», «2 іс-шара», «2 events»: the plural form of the language
function eventsCount(n) {
  const rule = new Intl.PluralRules(currentLang()).select(n);
  return tr(`ev_n_${['one', 'few', 'many'].includes(rule) ? rule : 'other'}`, { n });
}

// «Сегодня рядом: 2 события ›»: one line that opens onto the afisha's events with their source links, under the cards,
// never above them. It is open from the start when the events are the answer (the question was about them).
function eventsBlock(events, open) {
  if (!events || !events.items.length) return null;
  const items = events.items.map((e) =>
    h('li', {},
      h('p', { class: 'event-title' }, h('b', { class: 'when', text: e.when }), ' ', e.title),
      h('p', { class: 'fine' },
        [e.venue, metres(e.distance_m), e.price].filter(Boolean).join(' · '), ' · ', ...sourceLinks([e.source]))));
  return h(
    'details',
    { class: 'events', open },
    h('summary', {},
      icon('flag'),
      h('span', { class: 'events-head', text: `${events.heading}: ${eventsCount(events.items.length)}` }),
      h('span', { class: 'chev' }, icon('chevron'))),
    h('ul', {}, items),
    events.note ? h('p', { class: 'fine events-note', text: events.note }) : null,
  );
}

function routeBlock(turn, byId) {
  const r = turn.route;
  if (!r || !r.stops.length) return null;
  const steps = [h('li', { class: 'stop you', text: tr('rt_you') })];
  r.stops.forEach((id, i) => {
    const place = byId.get(id);
    steps.push(h('li', { class: 'leg', text: tr('rt_walk', { n: r.legs_min[i] }) }));
    steps.push(
      h('li', { class: 'stop' }, `${place ? place.n : i + 1} · ${place ? place.place.name : id} `,
        h('span', { class: 'stay', text: tr('rt_stay', { n: r.stay_min[i] }) })),
    );
  });
  steps.push(h('li', { class: 'leg', text: tr('rt_walk', { n: r.return_min }) }));
  steps.push(h('li', { class: 'stop you', text: tr('rt_back') }));
  const summary = h(
    'summary',
    {},
    h('span', { class: 'route-sum' },
      h('strong', { text: tr('rt_head', { total: r.total_min, budget: r.budget_min }) }),
      h('span', { class: r.fits ? 'fits' : 'over', text: tr(r.fits ? 'rt_fits' : 'rt_over') })),
    icon('chevron'),
  );
  return h('details', { class: 'disclosure route' }, summary, h('ol', { class: 'timeline' }, steps));
}

function chipButton(chip, onSend) {
  const cls = chip.kind === 'reset' ? 'chip reset' : 'chip';
  return h('button', { type: 'button', class: cls, dataset: { send: chip.send }, onclick: () => onSend(chip) }, chip.kind === 'reset' ? icon('refresh') : null, chip.label);
}

function cardOpts(ctx, n) {
  return {
    n,
    turnId: ctx.turnId,
    at: ctx.at,
    origin: ctx.origin,
    sel: ctx.sel,
    profileOn: ctx.profileOn,
    onProfile: ctx.onProfile,
    onSelect: ctx.onSelect,
    onHover: ctx.onHover,
    onDetails: ctx.onDetails,
  };
}

// the sentence that answers a question about a place, its source link, and the card of that place
function placeAnswer(turn, ctx) {
  const rows = (turn.answers || []).map((a) =>
    h('div', { class: `qa-row${a.known ? '' : ' unknown'}` },
      h('p', { class: 'qa-a', text: a.text }),
      a.source && a.source.url ? h('p', { class: 'fine' }, `${tr('qa_source')} `, ...sourceLinks([a.source])) : null));
  const cards = [];
  const seen = new Set();
  for (const a of turn.answers || []) {
    const place = (turn.places || []).find((p) => p.id === a.place_id);
    if (!place || seen.has(place.id)) continue;
    seen.add(place.id);
    cards.push(qaCard({ ...place, walk: ctx.walkOf(place.id) || place.walk }, cardOpts(ctx, ctx.numberOf(place.id))));
  }
  return [h('div', { class: 'qa' }, rows), ...cards];
}

// «Ещё 7 мест рядом — по расстоянию»: the plural form of the language, then the order the rows are in
function morePlacesLabel(n, order) {
  const rule = new Intl.PluralRules(currentLang()).select(n);
  const text = tr(`more_places_${['one', 'few', 'many'].includes(rule) ? rule : 'other'}`, { n });
  return order ? `${text} — ${tr(`more_order_${order}`)}` : text;
}

// One place is the main card: the selected one (the first until another is chosen), the others are the rows under it.
// Under them one button opens the further places of the same wish (`turn.more`, ranked, no text of the model): they are
// rows like the others, numbered on from the answer's own places, and a tap on one makes it the main card.
// `chipsRow`: on a phone the follow-up chips come right under the card, before the rows, so they are never behind the field.
function placesBlock(turn, ctx, chipsRow) {
  const more = turn.more || [];
  const places = ctx.moreOpen ? [...turn.places, ...more] : turn.places;
  const byId = new Map(places.map((p, i) => [p.id, { place: p, n: i + 1 }]));
  const lead = places.find((p) => p.id === ctx.sel) || turn.places[0];
  const others = turn.places.filter((p) => p !== lead);
  const parts = [primaryCard(lead, cardOpts(ctx, byId.get(lead.id).n))];
  if (turn.route && turn.route.kind === 'plan') parts.push(routeLine(turn, byId));
  for (const notice of turn.notices || []) parts.push(noticeLine(notice)); // under the card, never pushing it down
  if (turn.route && turn.route.lighting) parts.push(h('p', { class: 'note lighting' }, icon('info'), turn.route.lighting));
  if (chipsRow && isPhone()) parts.push(chipsRow);
  if (others.length) {
    parts.push(
      h('div', { class: 'sub' }, h('span', { class: 'lbl', text: tr('more_options', { n: others.length }) }), isPhone() ? icon('chevron') : null),
      h('div', { class: 'alts' }, others.map((p) => altRow(p, cardOpts(ctx, byId.get(p.id).n)))),
    );
  }
  if (more.length) {
    const open = Boolean(ctx.moreOpen);
    parts.push(h('button', { type: 'button', class: 'more-places', 'aria-expanded': String(open), onclick: () => ctx.onMore(!open) },
      h('span', { text: open ? tr('more_places_less') : morePlacesLabel(more.length, turn.more_order) }), icon('chevron')));
    if (open) parts.push(h('div', { class: 'alts more' }, more.filter((p) => p !== lead).map((p) => altRow(p, cardOpts(ctx, byId.get(p.id).n)))));
  }
  if (turn.route && turn.route.kind === 'plan') parts.push(routeBlock(turn, byId));
  return parts;
}

// ctx: {turnId, at, origin, sel, numberOf(id), walkOf(id) (the way the map shows to a place, or null), profileOn, onProfile, onSelect(id), onHover(id|null), onDetails(id),
//       onChip(chip), onRemember(chip, btn)}
export function renderAnswer(resp, ctx) {
  return withLang(resp.turn.lang, () => drawAnswer(resp, ctx));
}

function drawAnswer(resp, ctx) {
  const turn = resp.turn;
  const places = turn.places || [];
  const answered = turn.kind === 'place_answer' && turn.answers && turn.answers.length > 0; // the answers say it
  const parts = [];
  if (!answered) parts.push(h('p', { class: 'reply', text: turn.reply }));
  if (!answered && turn.notice) parts.push(h('p', { class: 'reply-note', text: turn.notice })); // what the time rule dropped, plainly
  const chips = (turn.chips || []).map((c) => chipButton(c, ctx.onChip));
  const remember = (resp.remember || []).map((c) =>
    h('button', { type: 'button', class: 'chip remember', onclick: (e) => ctx.onRemember(c, e.currentTarget) }, c.label));
  const chipsRow = chips.length || remember.length ? h('div', { class: 'chips' }, chips, remember) : null;
  if (answered) parts.push(...placeAnswer(turn, ctx));
  else if (places.length) parts.push(...placesBlock(turn, ctx, chipsRow));
  else for (const notice of turn.notices || []) parts.push(noticeLine(notice));
  const events = turn.events;
  parts.push(eventsBlock(events, Boolean(events) && (!places.length || events.items.length > 2)));
  if (chipsRow && !parts.includes(chipsRow)) parts.push(chipsRow);
  return h('div', { class: 'answer' }, parts);
}

// an earlier answer folded: what was said and one row per place; a row opens it again
export function renderFolded(item, ctx) {
  return withLang(item.resp && item.resp.turn && item.resp.turn.lang, () => drawFolded(item, ctx));
}

function drawFolded(item, ctx) {
  const turn = item.resp && item.resp.turn;
  const places = turn && turn.kind !== 'place_answer' && turn.places ? turn.places : [];
  const parts = [];
  if (turn && turn.reply) parts.push(h('p', { class: 'reply small', text: turn.reply }));
  if (places.length) {
    parts.push(h('div', { class: 'mini' }, places.map((p, i) => miniRow(p, { n: i + 1, onOpen: ctx.onOpen }))));
  } else {
    parts.push(h('button', { type: 'button', class: 'lnk', onclick: ctx.onOpen }, tr('turn_open')));
  }
  return h('div', { class: 'folded' }, parts);
}

export function renderError(onRetry) {
  return h(
    'div',
    { class: 'error-row', role: 'alert' },
    h('span', { text: tr('error_send') }),
    h('button', { type: 'button', class: 'secondary', onclick: onRetry }, icon('refresh'), tr('retry')),
  );
}

// the shape of the answer to come: two lines of the lead and one card, resting (nothing moves but a slow pulse)
function skeleton() {
  const bar = (cls) => h('i', { class: cls });
  return h('div', { class: 'skel', 'aria-hidden': 'true' },
    h('div', { class: 'skel-lead' }, bar(), bar()),
    h('div', { class: 'skel-card' }, bar('t'), bar('s'), bar('b'), h('div', { class: 'skel-btns' }, bar(), bar())));
}

// The wait for an answer. phase 0: the first 300 ms, nothing (a quick answer never flashes a placeholder); phase 1: the
// steps the core reported so far (walks.pipeline on_stage), the done ones ticked, the current one marked, above the shape
// of the answer. Never a spinner alone.
export function renderThinking(id, stages, phase = 0) {
  const known = stepsSoFar(stages);
  const box = h('div', { class: 'thinking', id, role: 'status' });
  if (phase < 1) return box;
  if (known.length) {
    box.setAttribute('aria-label', tr(STEP[known[known.length - 1]]));
    box.append(h(
      'ol',
      { class: 'steps' },
      known.map((s, i) => (i === known.length - 1
        ? h('li', { class: 'now', 'aria-current': 'step' }, tr(STEP[s]))
        : h('li', { class: 'done' }, icon('check'), tr(STEP[s])))),
    ));
  }
  box.append(skeleton());
  return box;
}
