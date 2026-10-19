"""The «Мой вайб» part of scripts/ui_tour.py: the first-screen chip «Под мой вайб» with no vibe set opens the vibe block of
«Память» with one sentence why (no search is sent); «Интроверт: тишина» is stored at once; the free text is read into
the chips on its «Сохранить» (the recording-only stand has no model for it: the word list reads it, walks.vibe_judge);
«Искать под мой вайб» asks, the lead names the facets and every card and row of the answer carries its «Под ваш вайб: …»
line with the data that said it.

`run_vibe(tour, browser, base)` takes the Tour of ui_tour.py (a size, `open`, `shot`, `press`, `answers`,
`wait_answer`)."""

from __future__ import annotations

INTRO_TEXT = "люблю тишину, книги и парки, не люблю толпы"
LINE = "Под ваш вайб: "


def fail(shot, note: str) -> None:
    shot.ok = False
    shot.notes.append(note)


def stored_form(page) -> dict | None:
    return page.evaluate(
        """async () => {
          const id = localStorage.getItem('anyq.profile.id');
          return id ? (await (await fetch('/api/profile?id=' + id)).json()).form : null;
        }"""
    )


def press(t, page, selector: str) -> None:
    """A tap or a click on a control, brought into view first (a touch lands where the finger is, not off screen)."""
    page.locator(selector).first.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    t.press(page, selector)


def run_vibe(t, browser, base: str) -> None:
    page = t.open(browser, base)
    press(t, page, "#starters [data-suggest='vibe']")
    page.wait_for_selector("#memory[open] #vibe-sec .vb-why", timeout=10000)
    page.wait_for_timeout(400)
    s = t.shot(
        page, "vibe-why", "«Под мой вайб» with no vibe: «Мой вайб» opens, with the sentence why"
    )
    if "вайб" not in page.locator("#vibe-sec .vb-why").inner_text():
        fail(s, "the sentence why does not speak of the vibe")
    if t.answers(page):
        fail(s, "a search was sent with no vibe set")

    press(t, page, "#vibe-sec [data-pole='calm']")
    page.wait_for_selector("#memory-root .mf-status[data-state='saved']", timeout=10000)
    page.locator("#vibe-sec .vb-text").fill(INTRO_TEXT)
    press(t, page, "#vibe-sec .vb-save")
    page.wait_for_function(
        "() => (document.querySelector('#vibe-sec .vb-read')?.textContent || '').length > 0",
        timeout=30000,
    )
    page.locator("#vibe-sec").scroll_into_view_if_needed()
    s = t.shot(
        page, "vibe-form", "«Мой вайб»: the axis, the chips the text was read into, «Понял так: …»"
    )
    form = stored_form(page) or {}
    vibe = form.get("vibe") or {}
    if vibe.get("calm") != 1 or not vibe.get("nature") or form.get("vibe_text") != INTRO_TEXT:
        fail(s, f"stored: {form.get('vibe')!r} {form.get('vibe_text')!r}")
    pressed = page.locator("#vibe-sec .mf-chip[aria-pressed='true']").all_inner_texts()
    if "Природа" not in pressed:
        fail(s, f"the chips do not show the reading: {pressed}")
    if not page.locator("#vibe-sec .vb-read").inner_text().startswith("Понял так: "):
        fail(s, "no «Понял так: …» after the save")

    before = t.answers(page)
    press(t, page, "#vibe-sec .vb-go")
    t.wait_answer(page, before + 1)
    s = t.shot(
        page,
        "vibe-answer",
        "«Искать под мой вайб»: the lead names the facets, the card and the rows their evidence",
    )
    s.notes = [
        n for n in s.notes if not n.startswith(("targets overlap: .mk", "targets overlap: .bm"))
    ]
    s.ok = (
        not s.notes
    )  # the data's own places: two pins may lie a finger apart (the map, not the page)
    turn = "#thread > li.turn:last-child"
    reply = page.locator(f"{turn} .answer .reply").first.inner_text()
    if not reply.startswith("Под ваш вайб — "):
        fail(s, f"the lead does not name the vibe: {reply!r}")
    lines = page.locator(f"{turn} .card .c-vibe, {turn} .alt .a-vibe").all_inner_texts()
    if not lines or not all(x.startswith(LINE) and x.endswith(")") for x in lines):
        fail(s, f"the cards' vibe lines: {lines}")
    page.evaluate("import('/static/js/memory.js').then((m) => m.open())")
    page.wait_for_selector("#memory-root .mf-forget")
    page.locator("#memory-root .mf-forget").click()
    page.wait_for_timeout(500)
    page.context.close()
