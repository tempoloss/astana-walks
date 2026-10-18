// Two nudges toward «Мои места», never in the way:
//   * once, under the first answer of a visitor who has marked nothing: «Отметьте дом или работу …» (a flag in
//     localStorage keeps it from coming back);
//   * under an answer about food, coffee or a bar late at night, while no «Дом» is saved: «Отметить дом — подскажу
//     места по пути» (the core understands «по пути домой» only when it knows where home is).
// Both are added to the answer the page has just drawn, from the thread's change hook.

import { all, hasHome, openPlace } from './bookmarks.js';
import { h, icon } from './dom.js';
import { tr } from './i18n.js';

const SEEN = 'anyq.places-hint';
const NIGHT_FROM = 22;
const NIGHT_TO = 5;
const FOOD = /поесть|поем|еда|еды|голод|ужин|перекус|кофе|кофейн|кафе|ресторан|выпить|(?:^|\s)бар(?:$|[\s.,!?])|паб|тамақ|ас іш|кофе|ішке|food|\beat|hungry|dinner|coffee|\bbar\b|drink/i;

// the hour of the request: the plate's «в 23:00», else now in Astana (UTC+5)
function hourOf(at) {
  const m = /^(\d{1,2}):/.exec(at || '');
  if (m) return Number(m[1]);
  return Number(new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hourCycle: 'h23', timeZone: 'Etc/GMT-5' }).format(new Date()));
}

const lateNight = (at) => {
  const hour = hourOf(at);
  return hour >= NIGHT_FROM || hour < NIGHT_TO;
};

function chipsOf(answer) {
  let chips = answer.querySelector(':scope > .chips');
  if (!chips) {
    chips = h('div', { class: 'chips' });
    answer.append(chips);
  }
  return chips;
}

export function initHints(app, assistant) {
  assistant.onThread(() => {
    const turn = document.querySelector('#thread > li.turn:last-child');
    if (!turn || !turn.querySelector('.answer') || turn.querySelector('.places-hint, .mark-home') || hasHome()) return;
    const asked = turn.querySelector('.u')?.textContent || '';
    if (lateNight(assistant.state().at) && FOOD.test(asked)) {
      chipsOf(turn.querySelector('.answer')).append(h('button', { type: 'button', class: 'chip mark-home', onclick: () => openPlace({ kind: 'home' }) }, icon('home'), tr('chip_mark_home')));
    } else if (!localStorage.getItem(SEEN) && !all().length) {
      localStorage.setItem(SEEN, '1');
      turn.querySelector('.answer').append(h('p', { class: 'places-hint' }, icon('info'),
        h('span', { text: tr('hint_places') }),
        h('button', { type: 'button', class: 'link', onclick: () => openPlace() }, tr('hint_places_btn'))));
    }
  });
}
