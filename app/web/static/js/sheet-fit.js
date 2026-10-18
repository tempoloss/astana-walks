// The three heights of the phone's answer sheet, measured from what it shows (never a share of the screen):
//   peek  down to the status line of the main card (the name, whether it is open, the minutes)
//   half  the longest content boundary that still leaves the map its room, and never above the end of the main card:
//         the sheet is cut between a card and a row, never through one
//   full  from just under the status bar to the field
// The content of the latest turn starts the visible part; earlier turns are above it and come into view at «full».

import { availableHeight, safeTop } from './viewport.js';

const TOP_GAP = 4; // the scroll box's own top padding: the turn starts this far below the handle
const TAIL = 6; // room under the last visible line
const NOTE_GAP = 12; // a link in a line under the card keeps its 44px reach clear of the field below the sheet's list
const EDGE = 29; // from the bottom of the top bar to the free map
const MAP_FREE = 250; // the map keeps at least this much between the top bar and the sheet
const MIN_STEP = 60; // peek and half stay at least this much (and 2×) below full
const FULL_TOP = 8; // below the status bar
const HANDLE_HIT = 44; // the handle's hit area lies this far above the sheet: it never covers the top bar's buttons

const $ = (id) => document.getElementById(id);

export function answerFit(panel) {
  const scroll = panel.querySelector('.scroll');

  // vertical positions inside the scrolled content, whatever the scroll position is now
  const frame = () => {
    const origin = scroll.getBoundingClientRect().top - scroll.scrollTop;
    return {
      top: (el) => el.getBoundingClientRect().top - origin,
      bottom: (el) => el.getBoundingClientRect().bottom - origin,
    };
  };

  // {start: where the visible part begins, peek: the end of the least that makes sense, must: the end half never stops
  // short of (the main card), cuts: the further boundaries half may end at when the map still has its room}
  function blocks() {
    const { top, bottom } = frame();
    const turn = panel.querySelector('#thread > li:last-child');
    if (!turn) {
      const hello = $('hello');
      const intro = hello.querySelector(':scope > p:not(.label):not(.desk-only)') || hello.querySelector('h1');
      return { start: top(hello), peek: bottom(intro), must: bottom($('starters')), cuts: [] };
    }
    const start = top(turn);
    const chips = turn.querySelector('.answer > .chips');
    const card = turn.querySelector('.card.primary');
    if (card) {
      const rows = [...turn.querySelectorAll('.alt')];
      // the lines under the card (an official notice, the lighting of the way) are part of it: half never ends inside one
      const notes = [...turn.querySelectorAll('.answer > .note, .answer > .route-line')];
      const must = Math.max(bottom(card), ...notes.map((n) => bottom(n) + NOTE_GAP));
      return { start, peek: bottom(card.querySelector('.c-st')), must, core: bottom(card), cuts: [...rows, chips].filter(Boolean).map(bottom) };
    }
    const asked = [...turn.querySelectorAll('.qa-card')];
    if (asked.length) {
      return { start, peek: bottom(turn.querySelector('.qa')), must: bottom(asked[0]), cuts: [...asked.slice(1), chips].filter(Boolean).map(bottom) };
    }
    // no place to show (a question back, the afisha, an error, the waiting): the first block, then the afisha's line and
    // its events one by one, then all of it when it fits
    const lead = turn.querySelector('.answer > *, .thinking, .error-row') || turn;
    const events = [...turn.querySelectorAll('.answer > .events > summary, .answer > .events[open] li')].map(bottom);
    return { start, peek: bottom(lead), must: bottom(lead), cuts: [...events, bottom(turn)] };
  }

  // everything in the sheet but the scrolled part: the handle, the notice, the field
  function chrome() {
    let sum = 0;
    for (const el of panel.children) {
      if (el === scroll || el.hidden || getComputedStyle(el).display === 'none') continue;
      const css = getComputedStyle(el);
      sum += el.getBoundingClientRect().height + parseFloat(css.marginTop) + parseFloat(css.marginBottom);
    }
    return sum;
  }

  const barBottom = () => {
    let bottom = $('plate').getBoundingClientRect().bottom;
    const note = $('map-note');
    if (!note.hidden) bottom = Math.max(bottom, note.getBoundingClientRect().bottom);
    return bottom;
  };

  return {
    // heights in px for peek, half, full
    targets() {
      const b = blocks();
      const bar = chrome();
      const visible = (y) => y - b.start + TOP_GAP + TAIL;
      const peekV = visible(b.peek);
      const room = availableHeight() - barBottom() - EDGE - MAP_FREE - bar;
      const fitting = b.cuts.map(visible).filter((v) => v <= room);
      let halfV = Math.max(visible(b.must), ...fitting);
      const full = availableHeight() - safeTop() - FULL_TOP;
      const below = availableHeight() - barBottom() - HANDLE_HIT; // the tallest a non-full sheet may be
      if (bar + halfV > below) {
        // too tall for the top bar: end at the card (or a row) that still fits, never through the notice under it
        const clean = [b.core ?? b.must, ...b.cuts].map(visible).filter((v) => bar + v <= below);
        halfV = clean.length ? Math.max(...clean) : below - bar;
      }
      return { peek: Math.min(bar + peekV, full - 2 * MIN_STEP, below), half: Math.min(bar + halfV, full - MIN_STEP, below), full };
    },
    // peek and half show the latest turn from its top
    align() {
      scroll.scrollTop = Math.max(0, blocks().start - TOP_GAP);
    },
  };
}

// the sheets without a measured content (the city): shares of the screen
export function shareFit() {
  return {
    targets() {
      const full = availableHeight() - safeTop() - FULL_TOP;
      return { peek: Math.round(full * 0.3), half: Math.round(full * 0.55), full };
    },
    align() {},
  };
}
