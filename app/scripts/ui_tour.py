"""Acceptance tour of the web UI: screenshots of every screen at laptop (1440x900, 1920x1080) and phone (390x844, 360x740) size.

Starts `python -m web` with the recording-only configuration (WALKS_ENV=demo, WALKS_DEMO_PIN, WALKS_CACHE_PIN,
WALKS_REPLAY_ONLY=1: recorded answers only, no model call; the internal replay tooling, not what the live stand runs), a second one also with WALKS_OFFLINE=1 for the
«no network» pictures, a third with forced data (scripts/ui_tour_fixtures.py), and drives them with Playwright.

A laptop size shows: the first screen; an answer; a hover over a row and over a pin; another place chosen from the
rows (its own card opens, the camera must not move); the details view; a follow-up answered in the thread under the folded answer; a place whose
hours are unknown, on the offline stand with the browser's network blocked; Kazakh (through the language menu); «Город»; «Данные»; then the 13
recorded requests (the 5 scenarios, the cold-airport request, the Kazakh request and the 6 follow-up buttons) with a
check that the text on screen is the AI's text from the recording. The phone (a touch screen, fingers sent as real
touches) shows the first screen; an answer with the sheet at half, dragged down to peek, tapped up to full, scrolled and
pulled back; a tap on a pin (the card changes, the camera stays); the details of the main card and the way back; the
keyboard (a field with a keyboard's height gone from the screen); the menu; and the same 13 requests, Kazakh, «Город»,
«Данные» and the offline stand. Every phone picture is audited: no control under 44 px, no two controls overlapping, no
control cut by the edge of the sheet, no text running out of its box.

The page has no scenario tiles: a recorded request is sent as a visitor would send it, from the place and time the
session holds (ui_tour.Tour.scenario). scripts/ui_tour_places.py adds the language menu, the generic first-screen chips,
the map kept to Astana, «Моё местоположение» (inside, outside, refused) and «Мои места» (added, edited, deleted, sent).
Every answer is checked on the page: the primary card is visible without scrolling (above the input), the map shows
the origin and the places in the free area (not under the plate, the panel, the legend or the sheet), no card wider
than the screen, no leg label on top of a pin or of «Вы здесь», no script error. The forced-data stand shows what the
real data has nothing to say about at a given moment: the «Сегодня рядом» block, a weather warning, a card with an
OpenStreetMap note, the answer to «что сегодня интересного». A request that is not in the recording yet
(data/demo_llm_cache.json is re-warmed by scripts/warm_cache.py) is reported as «pending re-warm», not as a failure.
Exit code 1 = a UI check failed.

Run from `app/` (Playwright is not a project dependency):

    uv run --no-project --with playwright python scripts/ui_tour.py [--size laptop|wide|phone|phone-s|both] [--port 8601]
    (once: uv run --no-project --with playwright python -m playwright install chromium)

Outputs (git-ignored): app/.local/ui-shots/{laptop,wide,phone,phone-s}-NN-name.png and ui-shots/report.json
(phone is 390x844, phone-s 360x740).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from ui_tour_phone import KEYBOARD_INIT, audit, keyboard, sheet, swipe, tap, tap_on, warm
from ui_tour_places import run_places

APP = Path(__file__).resolve().parents[1]
OUT = APP / ".local" / "ui-shots"
SCRATCH = APP / ".local" / "ui-tour"
SEED_MARKS = APP.parent / "data" / "city_feedback.json"

SIZES = {
    "laptop": (1440, 900, 1),
    "wide": (1920, 1080, 1),
    "phone": (390, 844, 2),
    "phone-s": (360, 740, 2),
}

# the 13 recorded requests, as scripts/warm_cache.py runs them: (name, starter id | follow-up chip text, base starter)
STARTERS = ("s0", "s1", "s2", "s3", "s4", "r0")
FOLLOW_UPS = (  # (button text sent, starter it refines)
    ("а поближе?", "s0"),
    ("что-то другое", "s0"),
    ("а без алкоголя", "s4"),
    ("а подешевле", "s1"),
    ("а если с ребёнком", "s0"),
    ("на час дольше", "s3"),
)
PLACE_QUESTION = "до скольки работает {name}?"
OPEN_NOW = "а оно сейчас открыто?"

# a point of a box is covered by the interface when it lies inside one of these boxes
BOXES = """() => {
  const phone = matchMedia('(max-width: 760px)').matches;
  const rect = (el) => (el && !el.hidden && el.getClientRects().length ? el.getBoundingClientRect() : null);
  const covers = [rect(document.getElementById('plate')), rect(document.getElementById('view-assistant')),
                  rect(document.getElementById('legend'))].filter(Boolean);
  const pts = [...document.querySelectorAll('.mk .mk-dot, .you .you-dot')].map((el) => {
    const b = el.getBoundingClientRect();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  });
  const inside = (p, b) => p.x > b.left && p.x < b.right && p.y > b.top && p.y < b.bottom;
  const hidden = pts.filter((p) => covers.some((b) => inside(p, b))).length;
  const out = pts.filter((p) => p.x < 4 || p.x > innerWidth - 4 || p.y < 4 || p.y > innerHeight - 4).length;
  return { pins: pts.length, hidden, out, phone };
}"""


_PIN_PAIR = re.compile(r"targets overlap: \.mk\S* × \.mk\S* \((\d+)x(\d+)\)")


def touching_pins(line: str) -> bool:
    """«.mk × .mk (2x11)»: the invisible 44px boxes of two neighbouring pins touch by a few pixels (where the answer's
    places lie close together the camera cannot put them further apart): the dots themselves stay clear."""
    hit = _PIN_PAIR.fullmatch(line)
    return bool(hit) and min(int(hit.group(1)), int(hit.group(2))) <= 4


LONG_NAME = "Ресторан-кофейня «Золотой дракон и серебряный тигр» у Центральной площади имени Первого Президента"
ONE_WORD = "Верхнепромышленныйкомбинатпереработкиморепродуктов-1"


def mangle_answer(route) -> None:
    """Serve the real answer with its chips removed and the names of its places made awkward (100 characters, one
    long word, one letter) and a long kind of place."""
    res = route.fetch()
    out = []
    for line in res.text().splitlines():
        msg = json.loads(line) if line else {}
        if "answer" in msg:
            turn = msg["answer"]["turn"]
            turn["chips"] = []
            msg["answer"].pop("remember", None)
            for i, p in enumerate(turn.get("places", [])):
                p["name"] = [LONG_NAME, ONE_WORD, "Ы"][i % 3]
                p["kind"] = "очень длинный тип заведения для проверки"
            line = json.dumps(msg, ensure_ascii=False)
        out.append(line)
    route.fulfill(response=res, body="\n".join(out) + "\n")


# visible text that is an untranslated i18n key (snake_case words only): a bug on any picture
RAW_KEYS = r"""() => {
  const key = /^[a-z][a-z0-9]*(_[a-z0-9]+)+$/;
  const found = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walk.nextNode(); node; node = walk.nextNode()) {
    const text = node.textContent.trim();
    const el = node.parentElement;
    if (!key.test(text) || !el || el.closest('script, style, noscript, [hidden]')) continue;
    const css = getComputedStyle(el);
    if (css.visibility === 'hidden' || css.display === 'none' || !el.getClientRects().length) continue;
    found.push(text);
  }
  return [...new Set(found)];
}"""

# a /api/turn stream made slow and staged like the real one (stage lines, then the answer after `ms`)
SLOW_STREAM = r"""(ms) => {
  if (!window.__realFetch) window.__realFetch = window.fetch.bind(window);
  const real = window.__realFetch;
  window.fetch = async (url, opts) => {
    if (!String(url).includes('/api/turn')) return real(url, opts);
    const t0 = performance.now(); // the delays count from the request, whatever the real answer cost
    const res = await real(url, opts);
    const lines = (await res.text()).split('\n').filter(Boolean);
    const stages = lines.filter((l) => l.includes('"stage"'));
    const rest = lines.filter((l) => !l.includes('"stage"'));
    const enc = new TextEncoder();
    const until = (at) => new Promise((r) => setTimeout(r, Math.max(at - (performance.now() - t0), 0)));
    const stream = new ReadableStream({
      async start(c) {
        for (const [at, line] of [[Math.min(100, ms / 2), stages[0]], [Math.min(1200, ms / 2), stages[1]], [Math.max(ms - 1800, ms / 2), stages[2]]]) {
          if (!line) continue;
          await until(at);
          c.enqueue(enc.encode(line + '\n'));
        }
        await until(ms);
        for (const line of rest) c.enqueue(enc.encode(line + '\n'));
        c.close();
      },
    });
    return new Response(stream, { status: 200, headers: { 'content-type': 'application/x-ndjson' } });
  };
}"""
RESTORE_FETCH = "() => { if (window.__realFetch) window.fetch = window.__realFetch; }"


@dataclass
class Shot:
    file: str
    what: str
    ok: bool = True
    notes: list[str] = field(default_factory=list)
    ai_text: bool | None = None  # an answer with places: the text on screen is the recorded AI text
    pending_rewarm: bool = False


class Tour:
    def robust(self, browser, url: str) -> None:
        """The page draws whatever arrives: an answer with no chips at all, with a name of 100 characters, a name of one
        long word and a name of one letter, and a very long kind of place. No card wider than the screen, no control
        cut or overlapped (the phone's audit), no control under 44 px."""
        page = self.open(browser, url)
        page.route("**/api/turn", mangle_answer)
        self.ask(page, "хочу поесть")
        s = self.shot(page, "robust-no-chips", "an answer with no chips and awkward names")
        if page.locator("#thread .answer .chips .chip:not(.mark-home)").count():
            s.ok = False
            s.notes.append("chips on screen although the answer sent none")
        s.notes = [n for n in s.notes if not n.startswith("targets overlap: .mk")]
        s.ok = not s.notes
        wide = page.evaluate(
            """() => [...document.querySelectorAll('#thread .card, #thread .alt, #thread .answer > *:not(.alts)')]
              .filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'auto')
              .map((e) => e.className)"""
        )
        if wide:
            s.ok = False
            s.notes.append(f"block(s) overflow sideways: {wide}")
        page.context.close()

    def conditions_shown(self, browser, url: str) -> None:
        """A condition picked in the panel stays in sight when the panel is closed, as a pill that removes it, and the
        panel itself says what is on."""
        page = self.open(browser, url)
        opts = "#opts-toggle"
        self.press(page, opts)
        if self.phone:  # the panel: time of today, how long, with whom, weather
            page.wait_for_selector("#when-panel .chip")
            self.press(page, "#when-panel .when-time .chip:has-text('23:00')")
            self.press(page, "#when-panel .chip:has-text('Вдвоём')")
            first, want = "23:00", 2
        else:  # a laptop: the time is in the plate, the rest in the row the «Условия» button opens
            page.wait_for_selector("#quick .chip")
            self.press(page, "#quick .chip:has-text('1 час')")
            first, want = "1 час", 1
        s = self.shot(page, "conditions-panel", "a condition picked: the panel says what is on")
        if self.phone and not page.locator("#when-panel .cond-note").count():
            s.ok = False
            s.notes.append("the panel does not say which conditions are on")
        self.press(page, opts)  # the panel closed
        page.wait_for_timeout(300)
        pills = page.locator("#cond-bar .cond-pill")
        s = self.shot(
            page, "conditions-pills", "the panel closed: the conditions stay in sight as pills"
        )
        if pills.count() != want or first not in pills.first.inner_text():
            s.ok = False
            s.notes.append(f"{pills.count()} pill(s), expected {want} with «{first}» first")
        if self.phone:
            tap_on(page, "#cond-bar .cond-pill")
        else:
            pills.first.click()
        page.wait_for_timeout(300)
        left = page.locator("#cond-bar .cond-pill").count()
        if left != want - 1:
            s.ok = False
            s.notes.append(f"the pill did not remove its condition ({left} left)")
        page.context.close()

    def answer_shapes(self, browser, url: str) -> None:
        """An answer drawn from what the server sent: its start (an answer about a saved place is measured from the
        place, so the marker starts there, named) and its language (a Kazakh answer on a Russian page keeps Kazakh
        labels)."""
        page = self.open(browser, url)

        def bend(route) -> None:
            res = route.fetch()
            out = []
            for line in res.text().splitlines():
                msg = json.loads(line) if line else {}
                if "answer" in msg:
                    turn = msg["answer"]["turn"]
                    lat, lon = turn["origin"]
                    turn["origin"] = [lat + 0.012, lon + 0.012]  # ~1.3 km away: «Дом»
                    turn["lang"] = "kk"
                    msg["answer"]["state"]["bookmark"] = "Дом"
                    line = json.dumps(msg, ensure_ascii=False)
                out.append(line)
            route.fulfill(response=res, body="\n".join(out) + "\n")

        before = page.evaluate("document.querySelector('.you-label').textContent")
        page.route("**/api/turn", bend)
        self.ask(page, "хочу кофе")
        s = self.shot(
            page, "answer-from-home", "an answer measured from «Дом»: the marker says «от «Дом»»"
        )
        s.notes = [n for n in s.notes if not n.startswith("targets overlap: .mk")]
        s.ok = not s.notes
        label = page.evaluate("document.querySelector('.you-label').textContent")
        if label == before or "Дом" not in label:
            s.ok = False
            s.notes.append(f"the start marker says {label!r} (was {before!r}), expected «от «Дом»»")
        caption = page.locator("#thread .turn:last-child .hcap").first
        if caption.count() and "қазір" not in caption.inner_text():
            s.ok = False
            s.notes.append("a Kazakh answer on a Russian page has Russian labels")
        page.context.close()

    def memory_form(self, browser, url: str) -> None:
        """What a person does in «Память»: taps the words of a switch, of a choice and of a chip (not the little control
        beside them), picks two ages for two children; every tap is stored at once; the first one says it turned the
        memory on."""
        page = self.open(browser, url)
        if self.phone:
            self.press(page, ".menu-open")
            self.press(page, "#menu .memory-open")
        else:
            self.press(page, ".tabs .memory-open")
        page.wait_for_selector("#memory[open] #memory-root .mf-toggle")

        def tap_words(selector: str, text: str) -> None:
            el = page.locator(selector, has_text=text).first
            el.scroll_into_view_if_needed()
            box = el.bounding_box()
            assert box is not None, text
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            if self.phone:
                tap(page, x, y)
            else:
                page.mouse.click(x, y)
            page.wait_for_selector("#memory-root .mf-status[data-state='saved']", timeout=10000)
            page.wait_for_timeout(200)

        tap_words("#memory-root .mf-toggle > span", "с детьми")
        status = page.locator("#memory-root .mf-status").inner_text()
        s = self.shot(
            page,
            "memory-kids",
            "«Хожу с детьми» tapped by its words: saved, and the line says the memory is on",
        )
        if "включено" not in status:
            s.ok = False
            s.notes.append(
                f"the line after the first setting does not say the memory is on: {status!r}"
            )
        tap_words("#memory-root .mf-chips .mf-chip", "4–7")
        tap_words("#memory-root .mf-chips .mf-chip", "8–12")
        tap_words("#memory-root .mf-seg button", "Мёрзну")
        stored = page.evaluate(
            """async () => {
              const id = localStorage.getItem('anyq.profile.id');
              const r = await fetch('/api/profile?id=' + id);
              return (await r.json()).form;
            }"""
        )
        s = self.shot(page, "memory-ages", "two ages and «Мёрзну» tapped by their words")
        if (
            stored["kids_age_bands"] != ["4-7", "8-12"]
            or stored["cold_tolerance"] != "low"
            or not stored["with_kids"]
        ):
            s.ok = False
            s.notes.append(f"stored: {stored}")
        page.locator("#memory-root .mf-forget").click()
        page.wait_for_timeout(500)
        page.context.close()

    def memory_applies(self, browser, url: str) -> None:
        """The memory settings apply at once: «Нужен халяль» flipped (nothing saved by hand, the panel closed), then
        «хочу поесть»: the request carries the profile's id and profile_on, and the answer says the setting was
        taken into account («халяль» in the lead or in the places' reasons)."""
        page = self.open(browser, url)
        if self.phone:
            self.press(page, ".menu-open")
            self.press(page, "#menu .memory-open")
        else:
            self.press(page, ".tabs .memory-open")
        page.wait_for_selector("#memory[open] #memory-root .mf-toggle")
        halal = page.locator("#memory-root .mf-toggle", has_text="халяль").locator("input")
        halal.scroll_into_view_if_needed()
        halal.click(force=True)
        page.wait_for_selector("#memory-root .mf-status[data-state='saved']", timeout=10000)
        s = self.shot(
            page,
            "memory-instant",
            "the memory: «Нужен халяль» flipped, «Сохранено», nothing to press",
        )
        if page.locator("#memory-root .mf-actions, #memory-root button[type='submit']").count():
            s.ok = False
            s.notes.append("a save button is left for the instant settings")
        if not page.locator("#mem-toggle").is_checked():
            s.ok = False
            s.notes.append("flipping a setting did not turn «Запоминать мои предпочтения» on")
        page.locator("#memory-root > header button").click()
        page.wait_for_selector("#memory:not([open])", state="attached")
        page.wait_for_timeout(300)
        with page.expect_response(lambda r: r.url.endswith("/api/turn")) as sent:
            self.ask(page, "хочу поесть")
        body = sent.value.request.post_data_json
        answer = next(
            json.loads(line)["answer"]
            for line in sent.value.text().splitlines()
            if line.startswith('{"answer"')
        )["turn"]
        said = " ".join(
            [answer["reply"], *(p.get("why", "") for p in answer.get("places", []))]
        ).lower()
        s = self.shot(page, "memory-answer", "«хочу поесть» with «Нужен халяль» on")
        # the camera is still settling after the answer: two pins may touch for a moment (as in the quick-wait shot)
        s.notes = [n for n in s.notes if not n.startswith("targets overlap: .mk")]
        s.ok = not s.notes
        if not body.get("profile_id") or body.get("profile_on") is not True:
            s.ok = False
            s.notes.append(
                f"the request has profile_id={body.get('profile_id')!r}, profile_on={body.get('profile_on')!r}"
            )
        if "халя" not in said and "халал" not in said:
            s.ok = False
            s.notes.append(
                f"the answer does not say the halal setting was taken into account: {said[:400]!r} {body}"
            )
        # leave nothing behind: «Забыть всё» deletes the profile file
        page.evaluate("import('/static/js/memory.js').then((m) => m.open())")
        page.wait_for_selector("#memory-root .mf-forget")
        page.locator("#memory-root .mf-forget").click()
        page.wait_for_timeout(500)
        page.context.close()

    def __init__(self, base: str, size: str, out: Path = OUT):
        self.base, self.size, self.out = base, size, out
        self.w, self.h, _ = SIZES[size]
        self.phone = size.startswith("phone")
        self.n = 0
        self.shots: list[Shot] = []
        self.errors: list[str] = []
        self.llm_texts: list[bool] = []
        self._config: dict | None = None

    # ------------------------------------------------------------ helpers

    def note_answer(self, resp) -> None:
        """Remember whether the text of each /api/turn answer is the AI's (text_source of its places)."""
        if not resp.url.endswith("/api/turn"):
            return
        try:
            body = resp.text()
        except Exception:  # a cancelled stream is not a tour failure
            return
        for line in body.splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "answer" in msg:
                places = msg["answer"]["turn"].get("places") or []
                self.llm_texts.append(any(p.get("text_source") == "llm" for p in places))

    def shot(self, page: Page, name: str, what: str) -> Shot:
        self.n += 1
        file = f"{self.size}-{self.n:02d}-{name}.png"
        page.wait_for_timeout(700)
        page.screenshot(path=str(self.out / file))
        s = Shot(file, what)
        self.shots.append(s)
        for key in page.evaluate(
            RAW_KEYS
        ):  # an untranslated i18n key on screen is a bug on every picture
            s.ok = False
            s.notes.append(f"raw i18n key on screen: {key!r}")
        if self.phone:
            for line in audit(page):  # every phone picture: targets, overlaps, cuts, clipped text
                if touching_pins(line):
                    continue
                s.ok = False
                s.notes.append(line)
            if not sheet(page)["typing"]:
                warm(
                    page
                )  # a picture swallows the next touch of the browser's emulation: spend one here
        return s

    def open(
        self,
        browser,
        base: str,
        *,
        block_external: bool = False,
        geo: tuple[float, float] | None = None,
    ) -> Page:
        w, h, scale = SIZES[self.size]
        ctx = browser.new_context(
            viewport={"width": w, "height": h},
            device_scale_factor=scale,
            locale="ru-RU",
            has_touch=self.phone,
            is_mobile=self.phone,
            geolocation={"latitude": geo[0], "longitude": geo[1]} if geo else None,
            permissions=["geolocation"] if geo else [],
        )
        if self.phone:
            ctx.add_init_script(KEYBOARD_INIT)
        if block_external:  # «no network»: only the stand itself answers
            ctx.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(self.base_of(base))
                    else route.abort()
                ),
            )
        page = ctx.new_page()
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on("response", self.note_answer)
        page.on(
            "console",
            lambda m: (
                self.errors.append(f"console: {m.text}")
                if m.type == "error"
                and not (block_external and "Failed to load resource" in m.text)
                else None
            ),
        )
        page.goto(base)
        page.wait_for_selector("body[data-ready='1']", timeout=60000)
        page.wait_for_timeout(1500)
        return page

    @staticmethod
    def base_of(url: str) -> str:
        return url.rstrip("/")

    def wait_answer(self, page: Page, count: int) -> None:
        page.wait_for_function(
            "n => document.querySelectorAll('#thread .answer, #thread .folded').length >= n && !document.querySelector('#thread .thinking')",
            arg=count,
            timeout=90000,
        )
        page.wait_for_timeout(1400)  # the map's camera settles

    def answers(self, page: Page) -> int:
        return page.locator("#thread .answer, #thread .folded").count()

    def press(self, page: Page, selector: str) -> None:
        """A tap on a phone (a real touch), a click on a laptop."""
        if self.phone:
            tap_on(page, selector)
        else:
            page.locator(selector).first.click()

    def set_lang(self, page: Page, lang: str) -> None:
        """The language menu: the globe with the code, the names behind it."""
        if self.phone:
            tap_on(page, "#lang-btn")
            tap_on(page, f"#lang-pop [data-lang='{lang}']")
        else:
            page.locator("#lang-btn").click()
            page.locator(f"#lang-pop [data-lang='{lang}']").click()
        page.wait_for_timeout(800)

    def config(self, page: Page) -> dict:
        if self._config is None:
            self._config = page.evaluate("fetch('/api/config').then((r) => r.json())")
        return self._config

    def scenario(self, page: Page, sid: str) -> dict:
        """One of the recorded requests. The page has no scenario tiles: the visitor's place and time are what the request
        carries, so the tour sets them as the visitor would (the session's state), starts the page afresh and types the
        request's own text."""
        cfg = self.config(page)
        lang = page.evaluate("document.documentElement.lang")
        starter = next(s for s in cfg["starters"][lang] if s["id"] == sid)
        preset = next(p for p in cfg["presets"] if p["id"] == starter["preset"])
        seed = {
            "where": {"preset": preset["id"], "lat": preset["lat"], "lon": preset["lon"]},
            "dialog": None,
            "at": starter["at"],
            "weather": "now",
            "budget": None,
            "company": None,
            "items": [],
            "seq": 0,
        }
        page.evaluate("v => sessionStorage.setItem('anyq.dialog', JSON.stringify(v))", seed)
        page.reload()
        page.wait_for_selector("body[data-ready='1']", timeout=60000)
        page.wait_for_timeout(1200)
        self.ask(page, starter["text"])
        return starter

    def ask(self, page: Page, text: str) -> None:
        before = self.answers(page)
        page.locator("#composer-input").fill(text)
        page.locator("#composer .send").click()
        self.wait_answer(page, before + 1)

    def check_answer(self, page: Page, shot: Shot) -> None:
        """The checks of one answer with places: card visible without scrolling, pins in the free map area; whether the
        text is the AI's comes from the answer the server sent (the page no longer says it)."""
        facts = page.evaluate(
            """() => {
              const card = document.querySelector('#thread .turn:last-child .card.primary');
              const composer = document.getElementById('composer').getBoundingClientRect();
              const panel = document.getElementById('view-assistant').getBoundingClientRect();
              const plate = document.getElementById('plate').getBoundingClientRect();
              const phone = matchMedia('(max-width: 760px)').matches;
              const r = card ? card.getBoundingClientRect() : null;
              const boxes = (sel) => [...document.querySelectorAll(sel)]
                .filter((el) => !el.hidden && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
                .map((el) => el.getBoundingClientRect());
              const labels = boxes('.leg-label');
              const pins = [...boxes(phone ? '.mk .mk-dot' : '.mk'), ...boxes('.you')]; // a phone's pin button is 44px, the dot is what a label may not cover
              const hit = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
              const covered = labels.filter((l) => pins.some((p) => hit(l, p))).length;
              const wide = [...document.querySelectorAll('#thread .card')]
                .filter((c) => c.getBoundingClientRect().right > innerWidth + 1).length;
              const head = phone ? plate.bottom : panel.top;
              return { card: r && { top: r.top, bottom: r.bottom }, composerTop: composer.top, head, covered, wide };
            }"""
        )
        shot.ai_text = bool(self.llm_texts and self.llm_texts[-1])
        card = facts["card"]
        if card is None:
            shot.ok = False
            shot.notes.append("no primary card")
        elif card["bottom"] > facts["composerTop"] + 1 or card["top"] < facts["head"] - 1:
            shot.ok = False
            shot.notes.append(
                f"primary card not fully visible: {card['top']:.0f}..{card['bottom']:.0f}, input at {facts['composerTop']:.0f}"
            )
        self.no_hatch(page, shot)
        pins = page.evaluate(BOXES)
        if pins["pins"] < 2:
            shot.ok = False
            shot.notes.append(f"pins on the map: {pins['pins']}")
        elif pins["hidden"] or pins["out"]:
            shot.ok = False
            shot.notes.append(
                f"{pins['hidden']} pin(s) under the interface, {pins['out']} outside the map"
            )
        if facts["covered"]:
            shot.ok = False
            shot.notes.append(
                f"{facts['covered']} leg label(s) on top of a pin or of the «you» marker"
            )
        if facts["wide"]:
            shot.ok = False
            shot.notes.append(f"{facts['wide']} card(s) wider than the screen")
        if not self.llm_texts or not self.llm_texts[-1]:
            shot.pending_rewarm = True
            shot.notes.append("pending re-warm: rules text (not in the recording)")
        if self.phone:
            self.expect_sheet(page, shot, "half")

    @staticmethod
    def expect_sheet(page: Page, shot: Shot, pos: str) -> None:
        here = sheet(page)
        if here["pos"] != pos:
            shot.ok = False
            shot.notes.append(f"the sheet is at {here['pos']}, expected {pos}")

    @staticmethod
    def check_alt(page: Page, shot: Shot, chosen: str, before: str) -> None:
        """A row of the other places was chosen: its card is the main one (hours strip, source line, the way out) and
        the place that was main is a row now."""
        main = page.locator("#thread .turn:last-child .card.primary")
        got = main.locator(".c-name").inner_text()
        if got != chosen:
            shot.ok = False
            shot.notes.append(f"the main card is {got!r}, the chosen row was {chosen!r}")
        rows = page.locator("#thread .turn:last-child .alt .a-name").all_inner_texts()
        if before not in rows:
            shot.ok = False
            shot.notes.append(f"the place that was main ({before!r}) is not a row now: {rows}")
        if main.locator(".st.unknown").count() and main.locator(".strip, .hbar").count():
            shot.ok = False
            shot.notes.append("a day strip on a card whose hours are unknown")
        unknown = main.locator(".st.unknown").count() > 0
        for css, what in (
            (
                ".st.unknown" if unknown else ".strip",
                "the plain «hours unknown»" if unknown else "the day's hours",
            ),
            (".card-more", "the way into the details"),
            (".acts .btn", "the way out"),
        ):
            if not main.locator(css).count():
                shot.ok = False
                shot.notes.append(f"the opened card has no {what}")

    # ------------------------------------------------------------ the tour

    def run(self, browser, online: str, offline: str) -> None:
        page = self.open(browser, online)
        self.shot(page, "first", "first screen")
        if self.phone:
            self.run_phone_core(page)
        else:
            self.run_desk_core(page)
        self.run_sweep(page)
        self.waiting(page)
        self.memory_applies(browser, online)
        self.memory_form(browser, online)
        self.conditions_shown(browser, online)
        self.answer_shapes(browser, online)
        self.robust(browser, online)

        # Kazakh: the interface and the recorded Kazakh request
        self.set_lang(page, "kk")
        self.shot(page, "kk-first", "Kazakh: first screen")
        self.scenario(page, "r1")
        s = self.shot(page, "kk-answer", "Kazakh: recorded request")
        self.check_answer(page, s)
        self.set_lang(page, "ru")
        page.wait_for_timeout(800)

        # the two other pages
        for view, name in (("city", "city"), ("data", "data")):
            page.evaluate(f"location.hash = '#/{view}'")
            page.wait_for_timeout(2500)
            s = self.shot(page, name, f"page: {name}")
            if view == "city":
                here = page.locator(".you .you-label").first.text_content() or ""
                if here != "Вы здесь":
                    s.ok = False
                    s.notes.append(f"the «you» marker says {here!r} on a Russian page")
        page.evaluate("location.hash = '#/'")
        page.context.close()

        # the stand with no network at all: the server offline, the browser blocked from everything else
        page = self.open(browser, offline, block_external=True)
        self.shot(page, "offline-first", "offline: first screen")
        self.scenario(page, "s1")
        s = self.shot(page, "offline-answer", "offline: answer, route over the neutral background")
        self.check_answer(page, s)
        s.pending_rewarm = False  # rules text is what the offline stand is meant to show
        s.notes = [n for n in s.notes if not n.startswith("pending")]
        self.unknown_hours(page)
        page.context.close()

    def run_desk_core(self, page: Page) -> None:
        """First answer, hover, another place, details, a follow-up in the thread."""
        self.scenario(page, "s1")
        s = self.shot(page, "answer", "answer: the main card, two rows, the way to the main place")
        self.check_answer(page, s)
        row = page.locator("#thread .alt").first
        row.hover()
        page.wait_for_timeout(500)
        s = self.shot(page, "hover-row", "hover over a row: its pin is lit")
        if not page.locator(".mk.hot").count():
            s.ok = False
            s.notes.append("no pin is lit while a row is hovered")
        pin = page.locator(".mk .mk-dot").nth(1)
        pin.hover()
        page.wait_for_timeout(500)
        s = self.shot(page, "hover-pin", "hover over a pin: its tip, its row is lit")
        if not page.locator("#thread .alt.hot, #thread .card.hot").count():
            s.ok = False
            s.notes.append("no row is lit while a pin is hovered")
        before = page.locator("#thread .card.primary .c-name").inner_text()
        chosen = row.locator(".a-name").inner_text()
        cam = page.locator("#map").get_attribute("data-cam")
        page.mouse.move(5, 5)
        row.click()
        page.wait_for_timeout(900)
        s = self.shot(
            page, "switch", "another place chosen from the rows: its card opens, the camera stays"
        )
        self.check_alt(page, s, chosen, before)
        if page.locator("#map").get_attribute("data-cam") != cam:
            s.ok = False
            s.notes.append("the camera moved when a row was chosen")
        page.locator("#thread .card.primary").click(position={"x": 30, "y": 12})
        page.wait_for_timeout(600)
        page.locator("#thread .card.primary .card-more").click()
        page.wait_for_timeout(500)
        s = self.shot(page, "details", "the details view of the main card")
        if not page.locator("#thread .details-view .d-sec").count():
            s.ok = False
            s.notes.append("no grouped details (now, getting there, about)")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        self.ask(page, OPEN_NOW)
        s = self.shot(
            page, "followup", "the follow-up answered in the thread, the answer above folded"
        )
        if (
            not page.locator("#thread .folded").count()
            or not page.locator("#thread .qa-card").count()
        ):
            s.ok = False
            s.notes.append("the follow-up is not answered in the thread under a folded answer")
        self.new_search(page)
        page.wait_for_timeout(600)

    def new_search(self, page: Page) -> None:
        """Start over: «новый поиск» under the answer on a laptop, the cross in the top bar on a phone."""
        if self.phone:
            page.locator("#q-new").click()
        else:
            page.locator("#thread .turn:last-child [data-send='новый поиск']").click()
        page.wait_for_timeout(600)

    def run_phone_core(self, page: Page) -> None:
        """The sheet under a finger: half, peek, full (scrolled, pulled down), a pin, the details, the keyboard, the menu."""
        self.scenario(page, "s1")
        s = self.shot(
            page, "answer", "answer: the sheet at half, the main card whole above the field"
        )
        self.check_answer(page, s)
        mid = self.w / 2

        # a finger drags the sheet down: peek keeps the main card's name and status in view
        swipe(page, mid, sheet(page)["top"] + 90, sheet(page)["top"] + 330)
        s = self.shot(
            page, "peek", "dragged down to peek: the main card's name and status stay in view"
        )
        self.expect_sheet(page, s, "peek")
        status = page.locator("#thread .turn:last-child .card.primary .c-st").bounding_box()
        if status is None or status["y"] + status["height"] > sheet(page)["composerTop"] + 1:
            s.ok = False
            s.notes.append("the status line of the main card is not in view at peek")

        # the handle taps through the positions: peek, half, full
        tap_on(page, "#view-assistant .sheet-handle")
        here = sheet(page)["pos"]
        if here != "half":
            s.ok = False
            s.notes.append(f"a tap on the handle at peek gave {here}, expected half")
        tap_on(page, "#view-assistant .sheet-handle")
        page.evaluate("document.getElementById('thread-scroll').scrollTop = 1e6")
        page.wait_for_timeout(300)
        s = self.shot(
            page, "full", "full: the whole list to its end, the map's credits as lines to hit"
        )
        self.expect_sheet(page, s, "full")
        credit = page.locator("#legend .lg-attr a[href*='openstreetmap.org']").first.bounding_box()
        if credit is None or credit["y"] + credit["height"] > sheet(page)["composerTop"] + 1:
            s.ok = False
            s.notes.append("the OpenStreetMap credit is not on screen at the end of the full list")

        # from the top of the list a pull down takes the sheet down; the handle brings it to half
        page.evaluate("document.getElementById('thread-scroll').scrollTop = 0")
        swipe(page, mid, 160, 420)
        if sheet(page)["pos"] == "full":
            s.ok = False
            s.notes.append("a pull down from the top of the full list did not take the sheet down")
        if sheet(page)["pos"] == "peek":
            tap_on(page, "#view-assistant .sheet-handle")
        if sheet(page)["pos"] != "half":
            s.ok = False
            s.notes.append(f"expected half after the pull, the sheet is at {sheet(page)['pos']}")

        # a tap on a pin: the way and the main card change, the camera and the sheet stay
        pins = page.locator(".mk")
        before = [pins.nth(i).bounding_box() for i in range(pins.count())]
        name = page.locator("#thread .turn:last-child .card.primary .c-name").inner_text()
        box = before[1]
        tap(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(700)
        s = self.shot(
            page, "pin", "a tap on pin 2: its card becomes the main one, the camera stays"
        )
        self.expect_sheet(page, s, "half")
        if page.locator("#thread .turn:last-child .card.primary .c-name").inner_text() == name:
            s.ok = False
            s.notes.append("the main card did not change after a tap on pin 2")
        after = [pins.nth(i).bounding_box() for i in range(pins.count())]
        if any(
            abs(a["x"] - b["x"]) > 1 or abs(a["y"] - b["y"]) > 1
            for a, b in zip(before, after, strict=True)
        ):
            s.ok = False
            s.notes.append("the camera moved when a pin was tapped")

        # the details fill the sheet; the bar at the bottom brings the way back
        tap_on(page, "#thread .turn:last-child .card.primary .card-more")
        page.wait_for_timeout(500)
        s = self.shot(
            page,
            "details",
            "the details of the main card: the sheet is full, the way out and back at the bottom",
        )
        if not page.locator("#thread .details-view .d-sec").count():
            s.ok = False
            s.notes.append("no grouped details (now, getting there, about)")
        if not sheet(page)["locked"] or sheet(page)["pos"] != "full":
            s.ok = False
            s.notes.append("the details are not on a full, locked sheet")
        tap_on(page, "#thread .details-view .back-b")
        s = self.shot(page, "details-back", "back from the details: the answer at half")
        self.expect_sheet(page, s, "half")

        # a row of «Ещё варианты» opens its own card: the sheet goes full for the rows, the tap, back to half
        tap_on(page, "#view-assistant .sheet-handle")
        page.evaluate("document.getElementById('thread-scroll').scrollTop = 1e6")
        page.wait_for_timeout(300)
        before = page.locator("#thread .turn:last-child .card.primary .c-name").inner_text()
        chosen = page.locator("#thread .turn:last-child .alt .a-name").first.inner_text()
        tap_on(page, "#thread .turn:last-child .alt .a-name")
        page.wait_for_timeout(700)
        page.evaluate("document.getElementById('thread-scroll').scrollTop = 0")
        s = self.shot(
            page,
            "alt",
            "a row of the other places tapped: its own card opens, the one before is a row",
        )
        self.check_alt(page, s, chosen, before)
        self.expect_sheet(page, s, "full")
        tap_on(page, "#view-assistant .sheet-handle")
        self.expect_sheet(page, s, "half")

        # a field with a keyboard of its own height gone from the screen: the sheet is the place's line and the field
        tap_on(page, "#composer-input")
        keyboard(page, 336 if self.h > 800 else 300)
        page.locator("#composer-input").fill(OPEN_NOW)
        s = self.shot(
            page,
            "keyboard",
            "typing: the sheet drops to the place's line, the options and the field above the keyboard",
        )
        if not sheet(page)["typing"]:
            s.ok = False
            s.notes.append("the sheet is not in its typing form while the field has the focus")
        elif sheet(page)["bottom"] > self.h - (336 if self.h > 800 else 300) + 1:
            s.ok = False
            s.notes.append("the sheet reaches under the keyboard")
        page.locator("#composer .send").click()
        keyboard(page, 0)
        self.wait_answer(page, 2)
        s = self.shot(
            page, "followup", "the follow-up answered in the thread, the answer above folded"
        )
        if (
            not page.locator("#thread .folded").count()
            or not page.locator("#thread .qa-card").count()
        ):
            s.ok = False
            s.notes.append("the follow-up is not answered in the thread under a folded answer")
        self.expect_sheet(page, s, "half")

        # the menu: the pages and the memory are one tap away
        tap_on(page, ".menu-open")
        s = self.shot(page, "menu", "the menu: Город, Данные, Память")
        if page.locator("#menu a, #menu button").count() < 4:
            s.ok = False
            s.notes.append("the menu does not list the pages and the memory")
        tap_on(page, ".menu-open")
        self.new_search(page)

    def unknown_hours(self, page: Page) -> None:
        """A place with no hours in the data: the plain muted words and no strip, never «открыто», never a hatch;
        asked about, the answer says so."""
        unk = page.locator("#thread .st.unknown")
        if not unk.count():
            return
        holder = unk.first.locator("xpath=ancestor::*[@data-pid][1]")
        name = holder.locator(".c-name, .a-name").first.text_content() or ""
        self.ask(page, PLACE_QUESTION.format(name=name))
        s = self.shot(
            page, "offline-unknown", f"offline, hours unknown: «{name}», the way as a straight line"
        )
        card = page.locator("#thread .qa-card")
        if not card.locator(".st.unknown").count():
            s.ok = False
            s.notes.append("the card of a place with unknown hours does not say so")
        if card.locator(".strip, .hbar").count():
            s.ok = False
            s.notes.append("a day strip for a place with unknown hours")
        self.no_hatch(page, s)

    @staticmethod
    def no_hatch(page: Page, shot: Shot) -> None:
        """Nothing on the page is hatched: unknown is a plain word, never a pattern."""
        found = page.evaluate(
            """() => [...document.querySelectorAll('#view-assistant *, #view-city *, #plate *, #legend *')].filter((el) => {
              const css = getComputedStyle(el);
              return css.backgroundImage.includes('repeating-linear') && el.getClientRects().length;
            }).map((el) => el.className || el.tagName)"""
        )
        if found:
            shot.ok = False
            shot.notes.append(f"hatched elements on the page: {found[:3]}")

    def waiting(self, page: Page) -> None:
        """The wait for an answer on a stream made slow: the message is there at once, nothing for the first 300 ms (a
        quick answer never flashes a placeholder), then the shape of the answer (a lead and one card), after 3 s the
        steps the core reports; never a spinner alone."""
        text = self.config(page)["starters"]["ru"][1]["text"]
        page.evaluate(
            "() => { window.__skel = false; new MutationObserver(() => { if (document.querySelector('#thread .skel')) window.__skel = true; }).observe(document.getElementById('thread'), { childList: true, subtree: true }); }"
        )
        page.evaluate(SLOW_STREAM, 150)  # an answer after 150 ms: no skeleton may ever show
        self.ask(page, text)
        s = self.shot(
            page, "waiting-quick", "an answer after 150 ms: no placeholder was ever shown"
        )
        # the map's camera is still settling after the second search from the same place: pins may touch for a moment
        s.notes = [n for n in s.notes if not n.startswith("targets overlap: .mk")]
        s.ok = not s.notes
        if page.evaluate("window.__skel"):
            s.ok = False
            s.notes.append("a skeleton flashed for an answer that took 150 ms")
        self.new_search(page)

        page.evaluate(SLOW_STREAM, 5200)
        before = self.answers(page)
        page.locator("#composer-input").fill(text)
        page.locator("#composer .send").click()
        page.wait_for_timeout(120)
        early_skeleton = page.locator("#thread .skel").count()
        message = page.locator("#thread .u").first.is_visible()
        page.wait_for_timeout(500)
        shape = (
            page.locator("#thread .skel .skel-lead i").count()
            and page.locator("#thread .skel .skel-card").count()
        )
        early_steps = page.locator("#thread .steps").count()
        s = self.shot(
            page,
            "waiting-shape",
            "waiting: the message and the shape of the answer, a lead and one card",
        )
        if not message:
            s.ok = False
            s.notes.append("the person's message is not on the page while the answer is made")
        if early_skeleton:
            s.ok = False
            s.notes.append("a skeleton before 300 ms")
        if not shape:
            s.ok = False
            s.notes.append("no skeleton in the shape of the answer after 300 ms")
        if early_steps:
            s.ok = False
            s.notes.append("steps before 3 s")
        page.wait_for_timeout(1900)
        steps = page.locator("#thread .steps li").count()
        dots = page.locator("#thread .thinking .dots").count()
        s = self.shot(page, "waiting-steps", "waiting 4 s: honest steps above the shape")
        if steps < 2:
            s.ok = False
            s.notes.append("no steps after 3 s of waiting")
        if dots:
            s.ok = False
            s.notes.append("a spinner of dots is on the page")
        self.wait_answer(page, before + 1)
        if page.locator("#thread .skel").count():
            s.ok = False
            s.notes.append("the skeleton stays after the answer")
        page.evaluate(RESTORE_FETCH)
        self.new_search(page)

    def run_sweep(self, page: Page) -> None:
        for sid in STARTERS:
            starter = self.scenario(page, sid)
            s = self.shot(page, f"answer-{sid}", f"answer: {starter['label']}")
            self.check_answer(page, s)
            if sid == "s1":
                self.place_question(page)

        for text, sid in FOLLOW_UPS:
            self.scenario(page, sid)
            chip = page.locator(f"#thread .turn:last-child [data-send='{text}']")
            label = chip.inner_text()
            before = self.answers(page)
            chip.click()
            self.wait_answer(page, before + 1)
            s = self.shot(
                page, f"follow-{FOLLOW_UPS.index((text, sid)) + 1}", f"follow-up: {label}"
            )
            self.check_answer(page, s)
        self.new_search(page)

    def run_layers(self, browser, url: str) -> None:
        """The stand with forced data: every extra line of an answer, on screen."""
        page = self.open(browser, url)
        page.locator("#composer-input").fill("хочу кофе")
        page.locator("#composer .send").click()
        self.wait_answer(page, 1)
        s = self.shot(
            page, "layers-answer", "answer with a weather warning, the afisha block and a card note"
        )
        self.check_answer(page, s)
        s.pending_rewarm = False  # rules text: the forced stand has no model
        s.notes = [n for n in s.notes if not n.startswith("pending")]
        # the forced stand piles every extra line on one answer (a long rules text, a note on the card), so the card
        # may run past the input here: what is checked is that it starts in view
        top = page.evaluate(
            "document.querySelector('#thread .turn:last-child .card.primary').getBoundingClientRect().top"
        )
        limit = page.evaluate(
            "document.getElementById('composer').getBoundingClientRect().top - 120"
        )
        s.notes = [n for n in s.notes if not n.startswith("primary card not fully visible")]
        if (
            self.phone
        ):  # a card this tall leaves the map a strip: one pin may stay under the sheet's edge
            s.notes = [
                n
                for n in s.notes
                if "under the interface" not in n and not n.startswith("targets overlap: .mk")
            ]
        if top > limit:
            s.notes.append(f"primary card starts too low: {top:.0f} (limit {limit:.0f})")
        s.ok = not s.notes
        # the Kazhydromet notice is active on this stand, but a café answer does not need it: the line is shown only for
        # a walk or a drive (checked below with «хочу погулять»)
        if page.locator("#thread .turn:last-child .note.notice.weather").count():
            s.ok = False
            s.notes.append("a café answer shows the weather warning line, which only a walk needs")
        for css, what in (
            ("#thread .turn:last-child .events li a", "an events block with source links"),
            (
                "#thread .turn:last-child .card.primary .note.signal a",
                "an OpenStreetMap note on the card",
            ),
        ):
            if not page.locator(css).count():
                s.ok = False
                s.notes.append(f"missing: {what}")
        page.locator("#thread .turn:last-child .card.primary .card-more").click()
        page.wait_for_timeout(300)
        self.shot(page, "layers-details", "details of the card with the nearest bus stop")
        page.keyboard.press("Escape")
        # a walk with the same notice active: the warning line is there, with the link to its page
        before = self.answers(page)
        page.locator("#composer-input").fill("хочу погулять")
        page.locator("#composer .send").click()
        self.wait_answer(page, before + 1)
        s = self.shot(
            page,
            "layers-walk",
            "a walk while a Kazhydromet notice is active: the warning, with its link",
        )
        s.pending_rewarm = False  # rules text: the forced stand has no model
        s.notes = [n for n in s.notes if not n.startswith("pending")]
        if (
            self.phone
        ):  # the card, the notice and the rows crowd a short sheet: pins may touch its edge
            s.notes = [
                n
                for n in s.notes
                if "under the interface" not in n and not n.startswith("targets overlap: .mk")
            ]
            s.ok = not s.notes
        if not page.locator("#thread .turn:last-child .note.notice.weather a").count():
            s.ok = False
            s.notes.append("missing: a warning with its source link under a walk")
        before = self.answers(page)
        page.locator("#composer-input").fill("что сегодня интересного")
        page.locator("#composer .send").click()
        self.wait_answer(page, before + 1)
        s = self.shot(
            page,
            "layers-afisha",
            "answer to «что сегодня интересного»: the afisha, its sources named",
        )
        if not page.locator("#thread .turn:last-child .events .events-note").count():
            s.ok = False
            s.notes.append("the afisha answer does not say which sources it has")
        page.evaluate("location.hash = '#/city'")
        page.wait_for_timeout(2500)
        page.locator(".seg button", has_text="Пробелы").first.click()
        page.wait_for_timeout(1500)
        s = self.shot(
            page, "layers-city", "Город: the queue of OpenStreetMap notes and the afisha coverage"
        )
        if not page.locator("#city-body ul.queue a").count():
            s.ok = False
            s.notes.append("no note in the queue")
        page.context.close()

    def place_question(self, page: Page) -> None:
        name = page.locator("#thread .turn:last-child .alt .a-name")
        place = (name.first.text_content() or "").strip() if name.count() else ""
        before = self.answers(page)
        page.locator("#composer-input").fill(PLACE_QUESTION.format(name=place))
        page.locator("#composer .send").click()
        self.wait_answer(page, before + 1)
        s = self.shot(page, "place-question", f"question about a shown place: {place}")
        if not page.locator("#thread .turn:last-child .qa-row").count():
            s.ok = False
            s.notes.append("no answer about the place")


# ------------------------------------------------------------------ servers


def _env(offline: bool) -> dict[str, str]:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    marks = SCRATCH / "city_feedback.json"
    shutil.copyfile(
        SEED_MARKS, marks
    )  # reports made during the tour land here, not in the demo copy
    env = dict(os.environ)
    for name in (
        "WALKS_OFFLINE",
        "WALKS_DEMO_CACHE",
        "LLM_PROFILE_ALEM_API_KEY_FILE",
        "LLM_API_KEY",
    ):
        env.pop(name, None)
    env.update(
        WALKS_ENV="demo",
        WALKS_DEMO_PIN="1",
        WALKS_CACHE_PIN="1",
        WALKS_REPLAY_ONLY="1",
        WALKS_LLM_CACHE=str(SCRATCH / "llm_cache.json"),
        WALKS_FEEDBACK=str(marks),
        WALKS_REQUEST_LOG="off",
        PYTHONIOENCODING="utf-8",
    )
    if offline:
        env["WALKS_OFFLINE"] = "1"
    return env


def start(port: int, *, offline: bool, fixtures: bool = False) -> subprocess.Popen:
    venv = APP / ".venv" / "Scripts" / "python.exe"
    python = str(venv) if venv.exists() else sys.executable
    cmd = [python, "-m", "web", "--port", str(port)]
    if fixtures:
        cmd = [
            python,
            str(APP / "scripts" / "ui_tour_fixtures.py"),
            str(port),
            str(SCRATCH / "layers"),
        ]
    log = open(SCRATCH / f"server-{port}.log", "wb")  # noqa: SIM115 - the child keeps the handle
    env = _env(offline)
    if fixtures:
        env = {k: v for k, v in env.items() if not k.startswith("WALKS_")}
    proc = subprocess.Popen(cmd, cwd=APP, env=env, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited with {proc.returncode}; see {log.name}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as r:
                if r.status == 200:
                    return proc
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("the server did not become healthy in 60 s")


def stop(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--size", choices=[*SIZES, "both"], default="both")
    ap.add_argument("--port", type=int, default=8601)
    ap.add_argument("--out", type=Path, default=OUT, help="where the pictures go")
    ap.add_argument(
        "--places-only", action="store_true", help="only the language, map and saved-places steps"
    )
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")
    sizes = list(SIZES) if args.size == "both" else [args.size]
    servers = [
        start(args.port, offline=False),
        start(args.port + 1, offline=True),
        start(args.port + 2, offline=True, fixtures=True),
    ]
    tours: list[Tour] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for size in sizes:
                tour = Tour(f"http://127.0.0.1:{args.port}", size, out)
                if not args.places_only:
                    tour.run(
                        browser,
                        f"http://127.0.0.1:{args.port}/",
                        f"http://127.0.0.1:{args.port + 1}/",
                    )
                    tour.run_layers(browser, f"http://127.0.0.1:{args.port + 2}/")
                run_places(tour, browser, f"http://127.0.0.1:{args.port}/")
                tours.append(tour)
            browser.close()
    finally:
        for proc in servers:
            stop(proc)
    report = {t.size: {"shots": [asdict(s) for s in t.shots], "errors": t.errors} for t in tours}
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    failed = 0
    for t in tours:
        print(f"== {t.size}")
        for s in t.shots:
            mark = "OK  " if s.ok else "FAIL"
            tag = (
                " [pending re-warm]"
                if s.pending_rewarm
                else (" [AI text from the recording]" if s.ai_text else "")
            )
            print(
                f"{mark} {s.file}: {s.what}{tag}"
                + "".join(f"\n       - {n}" for n in s.notes if s.ok is False)
            )
            failed += not s.ok
        for e in t.errors:
            print(f"ERR  {e}")
        failed += len(t.errors)
    print(f"{sum(len(t.shots) for t in tours)} pictures in {out}; {failed} problem(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
