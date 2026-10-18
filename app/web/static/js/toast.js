// One plain notice at the corner of the screen: bottom-right on a laptop, at the top on a phone (see `.toasts`). An
// action («Вернуть») lives as long as the notice does. A notice with an error stays until it is dismissed.

import { h, icon } from './dom.js';
import { tr } from './i18n.js';

const SHOW_MS = 7000;
const LEAVE_MS = 160;
let box = null;
let shown = null; // one notice at a time: a new one replaces the last

// a modal dialog blocks the page behind it, so the notice rides inside the one that is open
function host() {
  if (!box) box = h('div', { class: 'toasts', role: 'region', 'aria-live': 'polite' });
  const parent = document.querySelector('dialog[open]') || document.body;
  if (box.parentNode !== parent) parent.append(box);
  return box;
}

// toast({text, action: {label, run}, error}) -> {close}
export function toast({ text, action = null, error = false }) {
  const el = h('div', { class: `toast${error ? ' error' : ''}`, role: error ? 'alert' : 'status' }, h('span', { class: 'toast-text', text }));
  let timer = 0;
  const close = () => {
    clearTimeout(timer);
    el.classList.add('out');
    setTimeout(() => el.remove(), LEAVE_MS);
  };
  shown?.remove();
  shown = el;
  if (action) {
    el.append(h('button', { type: 'button', class: 'toast-act', onclick: () => { close(); action.run(); } }, action.label));
  }
  if (error) el.append(h('button', { type: 'button', class: 'toast-x', 'aria-label': tr('close'), onclick: close }, icon('close')));
  else timer = setTimeout(close, SHOW_MS);
  host().append(el);
  return { close };
}
