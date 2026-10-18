// The phone's viewport: the safe areas, the part of the screen the keyboard covers, and whether the visitor is typing.
// The keyboard is `layout height − visual viewport height − its offset` (iOS keeps the layout still and slides the visual
// viewport over it; Android with `interactive-widget=resizes-content` shrinks the layout itself and this is 0). It is
// published as `--kb` for the sheet's `bottom`; «typing» (the field has focus) puts the sheet on its short form.

import { isPhone } from './dom.js';

const root = document.documentElement;
const KEYBOARD_MIN = 80; // less than this is a browser bar, not a keyboard
let probe = null;
let keyboard = 0;
let typing = false;
let hooks = { onTyping: () => {}, onResize: () => {} };

// the screen's real height above the keyboard
export const availableHeight = () => window.innerHeight - keyboard;
export const keyboardHeight = () => keyboard;
export const isTyping = () => typing;

// `env(safe-area-inset-top)` read back in px: never a constant
export function safeTop() {
  return probe ? probe.getBoundingClientRect().height : 0;
}

function measure() {
  const vv = window.visualViewport;
  if (!vv) return 0;
  const covered = Math.round(window.innerHeight - vv.height - vv.offsetTop);
  return covered >= KEYBOARD_MIN ? covered : 0;
}

function update() {
  const next = measure();
  if (next !== keyboard) {
    keyboard = next;
    root.style.setProperty('--kb', `${keyboard}px`);
  }
  hooks.onResize();
}

function setTyping(on) {
  if (on === typing) return;
  typing = on;
  document.body.classList.toggle('typing', on);
  hooks.onTyping(on);
}

// onTyping(on): the field got or lost the focus; onResize(): the screen or the keyboard changed size
export function initViewport({ onTyping, onResize }) {
  hooks = { onTyping, onResize };
  probe = document.createElement('div');
  probe.className = 'safe-probe';
  probe.setAttribute('aria-hidden', 'true');
  document.body.append(probe);
  const vv = window.visualViewport;
  if (vv) {
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
  }
  window.addEventListener('resize', update);

  const form = document.getElementById('composer');
  const field = document.getElementById('composer-input');
  form.addEventListener('focusin', (e) => e.target === field && isPhone() && setTyping(true));
  form.addEventListener('focusout', (e) => {
    if (!form.contains(e.relatedTarget)) setTyping(false);
  });
  // a tap beside the field, the chips and the place's row puts the keyboard away
  document.addEventListener('pointerdown', (e) => {
    if (typing && !e.target.closest('#composer, #sheet-mini')) document.activeElement?.blur();
  }, true);
  update();
}
