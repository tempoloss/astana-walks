"""The phone's part of scripts/ui_tour.py: fingers, a keyboard and an audit of the touch targets.

A finger is a real touch sent over the DevTools protocol (the sheet reacts to touch and pointer events, not to the
mouse Playwright clicks with), the keyboard is the visual viewport shrunk by the keyboard's height (what iOS does and
what the page reads in viewport.js), and the audit reads every control on the screen: size with its invisible
extension, overlap with another control, a control cut by the edge of the sheet, text running out of its box.
"""

from __future__ import annotations

from playwright.sync_api import CDPSession, Page

# Installed before the page's scripts: the page's visual viewport, shrunk by `window.__keyboard(px)` to what a keyboard of
# that height leaves (the real viewport's own events still pass through).
KEYBOARD_INIT = """
(() => {
  const real = window.visualViewport;
  const vv = new EventTarget();
  let covered = 0;
  for (const type of ['resize', 'scroll']) real.addEventListener(type, () => vv.dispatchEvent(new Event(type)));
  Object.defineProperties(vv, {
    height: { get: () => real.height - covered },
    width: { get: () => real.width },
    offsetTop: { get: () => real.offsetTop },
    offsetLeft: { get: () => real.offsetLeft },
    scale: { get: () => real.scale },
  });
  Object.defineProperty(window, 'visualViewport', { value: vv, configurable: true });
  window.__keyboard = (px) => { covered = px; vv.dispatchEvent(new Event('resize')); };
})();
"""

SHEET = """() => {
  const panel = document.getElementById('view-assistant');
  const box = panel.getBoundingClientRect();
  const scroll = document.getElementById('thread-scroll');
  return {
    pos: ['peek', 'half', 'full'].find((n) => panel.classList.contains('pos-' + n)) || null,
    typing: panel.classList.contains('kbd'),
    locked: panel.classList.contains('locked'),
    top: box.top,
    bottom: box.bottom,
    composerTop: document.getElementById('composer').getBoundingClientRect().top,
    scrollTop: scroll.scrollTop,
    height: innerHeight,
  };
}"""

AUDIT = """() => {
  const TARGETS = 'a[href], button, textarea, select, summary, input:not([type=hidden])';
  const shown = (el) => {
    if (el.closest('[hidden]')) return false;
    const css = getComputedStyle(el);
    if (css.visibility === 'hidden' || css.display === 'none' || Number(css.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  // the control and its invisible extension (a ::after laid over it)
  const reach = (el) => {
    const own = el.tagName === 'INPUT' && el.closest('label') ? el.closest('label') : el;
    const r = own.getBoundingClientRect();
    let [l, t, rr, b] = [r.left, r.top, r.right, r.bottom];
    const ext = getComputedStyle(own, '::after');
    if (ext.content !== 'none' && ext.position === 'absolute' && ext.display !== 'none') {
      const w = parseFloat(ext.width) || 0;
      const h = parseFloat(ext.height) || 0;
      const pl = parseFloat(ext.left);
      const pt = parseFloat(ext.top);
      const m = ext.transform && ext.transform !== 'none' ? new DOMMatrix(ext.transform) : new DOMMatrix();
      const x0 = Number.isFinite(pl) ? r.left + pl + m.e : r.left + r.width / 2 - w / 2;
      const y0 = Number.isFinite(pt) ? r.top + pt + m.f : r.top + r.height / 2 - h / 2;
      [l, t, rr, b] = [Math.min(l, x0), Math.min(t, y0), Math.max(rr, x0 + w), Math.max(b, y0 + h)];
    }
    return { l, t, r: rr, b, w: rr - l, h: b - t };
  };
  const name = (el) => (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/).join('.') : '') || el.tagName;
  const label = (el) => (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 24);
  const out = { small: [], overlap: [], cut: [], clipped: [] };
  const panel = document.getElementById('view-assistant');
  const full = panel.classList.contains('pos-full') || panel.classList.contains('locked');
  const items = [];
  const modal = document.querySelector('#menu:not([hidden])'); // an open menu is all there is to touch
  for (const el of document.querySelectorAll(TARGETS)) {
    if (!shown(el) || el.classList.contains('skip') || (modal && !modal.contains(el))) continue;
    const r = el.getBoundingClientRect();
    const scroller = el.closest('.scroll');
    if (scroller && !full && scroller.closest('#view-assistant') && !scroller.closest('[hidden]')) { // a control the sheet's edge cuts in two
      const c = scroller.getBoundingClientRect();
      if (r.top >= c.top - 1 && r.top < c.bottom && r.bottom > c.bottom + 1) out.cut.push(name(el) + ' «' + label(el) + '»');
    }
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), innerWidth - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, 1), innerHeight - 1);
    const top = document.elementFromPoint(cx, cy);
    if (!top || !(top === el || el.contains(top) || top.contains(el) || (el.tagName === 'INPUT' && top.closest('label') === el.closest('label')))) continue; // under the sheet or off its list
    const e = reach(el);
    // what a finger can hit of a control in the sheet's list ends at the list's edge (the list clips it)
    const box = scroller && scroller.closest('#view-assistant') ? scroller.getBoundingClientRect() : null;
    const hit = box ? { ...e, t: Math.max(e.t, box.top), b: Math.min(e.b, box.bottom) } : e;
    if (e.w < 43.5 || e.h < 43.5) out.small.push(name(el) + ' ' + Math.round(e.w) + 'x' + Math.round(e.h) + ' «' + label(el) + '»');
    if (box && full && (r.top < box.top - 1 || r.bottom > box.bottom + 1)) continue; // mid-scroll at the list's edge: not a resting place
    items.push({ el, e: hit, n: name(el) });
  }
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const a = items[i];
      const b = items[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const bar = (el) => el.closest('.details-view .acts');
      if ((bar(a.el) && !bar(b.el) && b.el.closest('.details-view')) || (bar(b.el) && !bar(a.el) && a.el.closest('.details-view'))) continue; // a list scrolls under the pinned bar
      const ox = Math.min(a.e.r, b.e.r) - Math.max(a.e.l, b.e.l);
      const oy = Math.min(a.e.b, b.e.b) - Math.max(a.e.t, b.e.t);
      if (ox > 1 && oy > 1) out.overlap.push(a.n + ' × ' + b.n + ' (' + Math.round(ox) + 'x' + Math.round(oy) + ')');
    }
  }
  for (const el of document.querySelectorAll('#view-assistant *, #plate *, #sheet-mini *, .map-note, .map-attr')) {
    if (!shown(el) || el.closest('svg') || el.closest('.chips, .quick') || el.closest('.scroll') && el.closest('.scroll').closest('[hidden]')) continue;
    const css = getComputedStyle(el);
    if (css.overflow === 'hidden' && el.scrollWidth > el.clientWidth + 1 && css.textOverflow !== 'ellipsis' && !el.children.length && el.textContent.trim()) {
      out.clipped.push(name(el) + ' ' + el.scrollWidth + '>' + el.clientWidth + ' «' + el.textContent.trim().slice(0, 30) + '»');
    }
  }
  return out;
}"""

_sessions: dict[Page, CDPSession] = {}


def _cdp(page: Page) -> CDPSession:
    if page not in _sessions:
        _sessions[page] = page.context.new_cdp_session(page)
    return _sessions[page]


def tap(page: Page, x: float, y: float, hold_ms: int = 60) -> None:
    """One finger down and up on a point."""
    session = _cdp(page)
    session.send(
        "Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]}
    )
    page.wait_for_timeout(hold_ms)
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_timeout(350)


def centre(page: Page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"no box for {selector}"
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def tap_on(page: Page, selector: str) -> None:
    tap(page, *centre(page, selector))


def warm(page: Page) -> None:
    """A touch that is cancelled at once (no click anywhere): after a picture the browser's emulation loses the next one."""
    session = _cdp(page)
    session.send(
        "Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 1, "y": 1}]}
    )
    page.wait_for_timeout(30)
    session.send("Input.dispatchTouchEvent", {"type": "touchCancel", "touchPoints": []})
    page.wait_for_timeout(100)


def swipe(page: Page, x: float, y0: float, y1: float, steps: int = 8, step_ms: int = 16) -> None:
    """One finger from (x, y0) to (x, y1) in `steps` moves."""
    session = _cdp(page)
    session.send(
        "Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y0}]}
    )
    for i in range(1, steps + 1):
        page.wait_for_timeout(step_ms)
        y = y0 + (y1 - y0) * i / steps
        session.send(
            "Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]}
        )
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_timeout(450)


def keyboard(page: Page, px: int) -> None:
    """A keyboard of this height comes up (0: goes away)."""
    page.evaluate("px => window.__keyboard(px)", px)
    page.wait_for_timeout(500)


def sheet(page: Page) -> dict:
    return page.evaluate(SHEET)


def audit(page: Page) -> list[str]:
    """What is wrong with the controls on the screen now, one line each."""
    found = page.evaluate(AUDIT)
    labels = {
        "small": "target under 44 px",
        "overlap": "targets overlap",
        "cut": "control cut by the sheet's edge",
        "clipped": "text clipped",
    }
    return [f"{labels[kind]}: {line}" for kind, lines in found.items() for line in lines]
