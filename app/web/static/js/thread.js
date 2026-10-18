// One turn of the conversation on the page: the user's bubble and what came back (a `Turn` of walks.dialog plus the
// page's extras). The latest turn is open, earlier ones fold into their places as mini rows. The user's bubble shows at
// once, then the steps of the work while the answer is being made; a shown set of cards is never swapped for another.
// The answer to a follow-up about a place is a sentence and that place's card, in the thread under the folded answer.

import { altRow, miniRow, primaryCard, qaCard } from './cards.js';
import { sourceLinks } from './details.js';
import { h, icon } from './dom.js';
import { metres } from './fmt.js';
import { tr } from './i18n.js';

const STEP = { parse: 'step_parse', search: 'step_search', write: 'step_write', route: 'step_route' };

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

// «Сегодня рядом»: the afisha's events with their source links, under the cards, never above them.
function eventsBlock(events) {
  if (!events || !events.items.length) return null;
  return h(
    'section',
    { class: 'events', 'aria-label': events.heading },
    h('h4', { class: 'events-head' }, icon('flag'), events.heading),
    h('ul', {}, events.items.map((e) =>
      h('li', {},
        h('p', { class: 'event-title' }, h('b', { class: 'when', text: e.when }), ' ', e.title),
        h('p', { class: 'fine' },
          [e.venue, metres(e.distance_m), e.price].filter(Boolean).join(' · '), ' · ', ...sourceLinks([e.source])))),
    ),
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

// One place is the main card: the selected one (the first until another is chosen), the others are the rows under it.
function placesBlock(turn, ctx) {
  const places = turn.places;
  const byId = new Map(places.map((p, i) => [p.id, { place: p, n: i + 1 }]));
  const lead = places.find((p) => p.id === ctx.sel) || places[0];
  const others = places.filter((p) => p !== lead);
  const parts = [primaryCard(lead, cardOpts(ctx, byId.get(lead.id).n))];
  if (turn.route && turn.route.kind === 'plan') parts.push(routeLine(turn, byId));
  for (const notice of turn.notices || []) parts.push(noticeLine(notice)); // under the card, never pushing it down
  if (turn.route && turn.route.lighting) parts.push(h('p', { class: 'note lighting' }, icon('info'), turn.route.lighting));
  if (others.length) {
    parts.push(
      h('div', { class: 'sub' }, h('span', { class: 'lbl', text: tr('more_options', { n: others.length }) })),
      h('div', { class: 'alts' }, others.map((p) => altRow(p, cardOpts(ctx, byId.get(p.id).n)))),
    );
  }
  if (turn.route && turn.route.kind === 'plan') parts.push(routeBlock(turn, byId));
  return parts;
}

// ctx: {turnId, at, origin, sel, numberOf(id), walkOf(id) (the way the map shows to a place, or null), profileOn, onProfile, onSelect(id), onHover(id|null), onDetails(id),
//       onChip(chip), onRemember(chip, btn)}
export function renderAnswer(resp, ctx) {
  const turn = resp.turn;
  const places = turn.places || [];
  const answered = turn.kind === 'place_answer' && turn.answers && turn.answers.length > 0; // the answers say it
  const parts = [];
  if (!answered) parts.push(h('p', { class: 'reply', text: turn.reply }));
  if (!answered && turn.notice) parts.push(h('p', { class: 'reply-note', text: turn.notice })); // what the time rule dropped, plainly
  if (answered) parts.push(...placeAnswer(turn, ctx));
  else if (places.length) parts.push(...placesBlock(turn, ctx));
  else for (const notice of turn.notices || []) parts.push(noticeLine(notice));
  parts.push(eventsBlock(turn.events));
  const chips = (turn.chips || []).map((c) => chipButton(c, ctx.onChip));
  const remember = (resp.remember || []).map((c) =>
    h('button', { type: 'button', class: 'chip remember', onclick: (e) => ctx.onRemember(c, e.currentTarget) }, c.label));
  if (chips.length || remember.length) parts.push(h('div', { class: 'chips' }, chips, remember));
  return h('div', { class: 'answer' }, parts);
}

// an earlier answer folded: what was said and one row per place; a row opens it again
export function renderFolded(item, ctx) {
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

// The steps the core reported so far (walks.dialog on_stage): done ones ticked, the current one with the dots.
export function renderThinking(id, stages) {
  const known = stages.filter((s) => STEP[s]);
  const dots = h('span', { class: 'dots', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'));
  if (!known.length) return h('div', { class: 'thinking', id, role: 'status' }, dots);
  return h(
    'ol',
    { class: 'thinking steps', id, role: 'status' },
    known.map((s, i) => (i === known.length - 1
      ? h('li', { class: 'now' }, dots, tr(STEP[s]))
      : h('li', { class: 'done' }, icon('check'), tr(STEP[s])))),
  );
}
