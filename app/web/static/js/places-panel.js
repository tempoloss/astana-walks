// «Мои места» at the top of «Память»: what the visitor marked (a kind's icon, the name, a short address), «Добавить место»,
// a tap on a row to change it (rename, move, delete are in that sheet), a trash button that deletes and offers «Вернуть».
// The places stay in this browser; the section says so in one line.

import { h, icon } from './dom.js';
import { tr } from './i18n.js';
import { KIND_ICON, MAX, all, isFull, onChange, openPlace, removeAt } from './bookmarks.js';

let current = null; // the section in the page now (memory.js draws a new one each time it renders)

function row(b, i) {
  return h('li', { class: 'pl-row', dataset: { kind: b.kind } },
    h('button', { type: 'button', class: 'pl-main', 'aria-label': tr('bm_edit', { name: b.name }), onclick: () => openPlace({ index: i }) },
      icon(KIND_ICON[b.kind]),
      h('span', { class: 'pl-text' }, h('span', { class: 'pl-name', text: b.name }), h('span', { class: 'pl-addr', text: b.addr || tr('bm_addr_point') }))),
    h('button', { type: 'button', class: 'pl-del', 'aria-label': tr('bm_remove', { name: b.name }), onclick: () => removeAt(i) }, icon('trash')));
}

function paint() {
  const places = all();
  const add = h('button', { type: 'button', class: places.length ? 'secondary pl-add' : 'primary-btn pl-add', id: 'pl-add', onclick: () => openPlace() }, icon('plus'), tr('bm_add'));
  current.replaceChildren(...[
    h('div', { class: 'pl-head' }, h('h3', { text: tr('bm_title') }), places.length && !isFull() ? add : null),
    places.length ? h('ul', { class: 'pl-list' }, places.map(row)) : h('p', { class: 'pl-empty', text: tr('bm_empty') }),
    places.length ? null : add,
    isFull() ? h('p', { class: 'fine', text: tr('bm_full', { n: MAX }) }) : null,
    h('p', { class: 'pl-note', text: tr('bm_privacy') }),
  ].filter(Boolean));
}

// the section for memory.js to put at the top of its panel; it follows the list while it is in the page
export function placesSection() {
  current = h('section', { class: 'pl', id: 'places', 'aria-label': tr('bm_title') });
  paint();
  return current;
}

onChange(() => current && current.isConnected && paint());
