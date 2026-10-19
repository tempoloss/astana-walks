// The bottom sheet of the phone: three positions — peek, half, full — whose heights the caller measures from the content
// (`fit.targets()`). The handle taps through them (peek → half → full → half); a finger drags the handle or the body, and
// the sheet settles on the position nearest to where its speed would carry it. In «full» the list scrolls and a pull down
// from its top takes the sheet down; in the two others the whole sheet is a handle. While the visitor types, the sheet is
// its short form (the handle, the place's line, the field). From 761px the panel is docked beside the map: none of this applies.

import { isPhone } from './dom.js';

const ORDER = ['peek', 'half', 'full'];
const NEXT = { peek: 'half', half: 'full', full: 'half' };
const START_PX = 6; // a finger moves this far before it is a drag, and more up or down than sideways
const RESISTANCE = 0.25; // beyond peek and full the sheet follows the finger this much
const THROW_MS = 160; // the speed (px/ms) carries the sheet this long
const QUIET_MS = 60; // the click that ends a drag is not a tap

// fit: {targets() → {peek, half, full} px, align()}; onChange(name) after every move to a position
export function makeSheet(panel, { fit, onChange, onBack, initial = 'half' }) {
  const handle = panel.querySelector('.sheet-handle');
  const scroll = panel.querySelector('.scroll');
  let heights = { peek: 0, half: 0, full: 0 };
  let current = initial;
  let locked = false; // a place's details: «full» only
  let typing = false;
  let drag = null;
  let quiet = false;

  const live = () => isPhone() && !panel.hidden;
  const measured = () => panel.getBoundingClientRect().height;

  function place(name) {
    current = name;
    for (const n of ORDER) panel.classList.toggle(`pos-${n}`, n === name);
    panel.style.height = `${Math.round(heights[name])}px`;
    if (name !== 'full') fit.align();
    onChange && onChange(name);
  }

  function clear() {
    panel.style.height = '';
    for (const n of ORDER) panel.classList.remove(`pos-${n}`);
    panel.classList.remove('kbd', 'dragging');
    onChange && onChange(current);
  }

  const sheet = {
    snap(name) {
      if (!live() || typing) return;
      heights = fit.targets();
      place(locked ? 'full' : name);
    },
    // content or screen changed: measure again and stay where the sheet is
    refresh() {
      if (!live()) {
        clear();
        return;
      }
      if (drag) return;
      heights = fit.targets();
      if (typing) {
        onChange && onChange(current);
        return;
      }
      place(locked ? 'full' : current);
    },
    // a place's details: the sheet is full and does not move until it is let go
    lock(on, to = 'half') {
      locked = on;
      panel.classList.toggle('locked', on);
      if (!live()) return;
      heights = fit.targets();
      place(on ? 'full' : to);
    },
    // the visitor types: the short form of the sheet; done: back to half
    keyboard(on) {
      if (on === typing) return;
      typing = on;
      panel.classList.toggle('kbd', on);
      if (!live()) return;
      if (on) {
        panel.style.height = '';
        onChange && onChange('peek');
      } else {
        heights = fit.targets();
        place(locked ? 'full' : 'half');
      }
    },
    get state() {
      return current;
    },
    get typing() {
      return typing;
    },
    // the height the sheet has, or is about to have: the camera keeps clear of it
    height() {
      if (!live()) return 0;
      return typing ? measured() : Math.round(heights[current]);
    },
  };

  // ---- the drag: pointer events on the handle and the body, touch events for a pull from the top of a scrolled list

  function begin(y) {
    drag = { y0: y, h0: measured(), y, t: performance.now(), v: 0, h: measured(), moved: false };
  }

  function follow(y) {
    if (!drag.moved) {
      drag.moved = true;
      panel.classList.add('dragging');
    }
    const now = performance.now();
    const speed = (drag.y - y) / Math.max(1, now - drag.t); // up is positive
    drag.v = drag.v * 0.5 + speed * 0.5;
    drag.y = y;
    drag.t = now;
    let h = drag.h0 + drag.y0 - y;
    if (h > heights.full) h = heights.full + (h - heights.full) * RESISTANCE;
    else if (h < heights.peek) h = heights.peek - (heights.peek - h) * RESISTANCE;
    drag.h = h;
    panel.style.height = `${Math.round(h)}px`;
  }

  function release(cancelled) {
    const was = drag;
    drag = null;
    if (!was || !was.moved) return;
    panel.classList.remove('dragging');
    quiet = true;
    setTimeout(() => {
      quiet = false;
    }, QUIET_MS);
    const target = cancelled ? was.h0 : was.h + was.v * THROW_MS;
    const nearest = ORDER.reduce((a, b) => (Math.abs(heights[b] - target) < Math.abs(heights[a] - target) ? b : a));
    place(nearest);
  }

  panel.addEventListener('pointerdown', (e) => {
    if (!live() || locked || typing || e.button > 0) return;
    if (e.target.closest('.composer')) return; // the field and its buttons never drag the sheet
    if (current === 'full' && !e.target.closest('.sheet-handle')) return; // the list scrolls
    heights = fit.targets();
    drag = { id: e.pointerId, x0: e.clientX, probe: true, y0: e.clientY };
  });

  panel.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (drag.probe) {
      const dy = e.clientY - drag.y0;
      const dx = e.clientX - drag.x0;
      if (Math.abs(dy) < START_PX && Math.abs(dx) < START_PX) return;
      if (Math.abs(dy) <= Math.abs(dx)) {
        drag = null;
        return;
      }
      const id = drag.id;
      const y0 = drag.y0;
      begin(y0);
      drag.id = id;
      panel.setPointerCapture(id);
    }
    follow(e.clientY);
  });
  panel.addEventListener('pointerup', (e) => drag && e.pointerId === drag.id && release(false));
  panel.addEventListener('pointercancel', (e) => drag && e.pointerId === drag.id && release(true));

  // a pull down from the top of the scrolled list takes the sheet down; any other move scrolls the list
  let pull = null;
  scroll.addEventListener('touchstart', (e) => {
    pull = null;
    if (!live() || locked || current !== 'full' || e.touches.length !== 1 || scroll.scrollTop > 0) return;
    pull = { x: e.touches[0].clientX, y: e.touches[0].clientY, on: false };
  }, { passive: true });
  scroll.addEventListener('touchmove', (e) => {
    if (!pull) return;
    const t = e.touches[0];
    if (!pull.on) {
      const dy = t.clientY - pull.y;
      const dx = t.clientX - pull.x;
      if (dy < -START_PX || scroll.scrollTop > 0) {
        pull = null;
        return;
      }
      if (dy < START_PX || dy <= Math.abs(dx)) return;
      pull.on = true;
      heights = fit.targets();
      begin(pull.y);
    }
    e.preventDefault();
    follow(t.clientY);
  }, { passive: false });
  const letGo = (cancelled) => () => {
    if (pull && pull.on) release(cancelled);
    pull = null;
  };
  scroll.addEventListener('touchend', letGo(false));
  scroll.addEventListener('touchcancel', letGo(true));

  // the height changes over a transition: a list aligned at its start was held back by the taller box of that moment
  // (the browser keeps a scroll position within what the box could scroll), so it is placed once more when the box is final
  panel.addEventListener('transitionend', (e) => {
    if (e.target === panel && e.propertyName === 'height' && !drag && !typing && current !== 'full') fit.align();
  });

  // a wheel or a trackpad over a half-open sheet opens it (a finger drags it; a mouse has no finger): the rest of the
  // answer is one scroll away, never only behind the handle
  panel.addEventListener('wheel', (e) => {
    if (!live() || locked || typing || quiet || current === 'full' || e.deltaY < 4 || e.target.closest('.composer')) return;
    heights = fit.targets();
    place('full');
    e.preventDefault();
  }, { passive: false });

  // the click that ends a drag is not a press on whatever lies under the finger
  panel.addEventListener('click', (e) => {
    if (quiet) {
      e.stopPropagation();
      e.preventDefault();
    }
  }, true);

  handle.addEventListener('click', () => {
    if (!live() || quiet) return;
    if (locked) {
      onBack && onBack();
      return;
    }
    if (typing) return;
    heights = fit.targets();
    let next = NEXT[current];
    if (Math.abs(heights[next] - heights[current]) < 4) next = NEXT[next]; // a short answer has one height for peek and half
    place(next);
  });

  return sheet;
}
