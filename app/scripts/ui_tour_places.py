"""The place-and-language part of scripts/ui_tour.py: the language menu, the first screen's chips (nothing teleports the
visitor), the map kept to Astana, the «Моё местоположение» button (inside the city, outside it, refused) and «Мои места»
(added by the list and by a long press, edited, deleted, offered as starting points, sent with the request).

`run_places(tour, browser, base)` takes the Tour of ui_tour.py (a size, `open`, `shot`, `press`, `set_lang`, `ask`)."""

from __future__ import annotations

import contextlib
import json

from ui_tour_phone import tap

ASTANA = {"south": 50.98, "north": 51.30, "west": 71.20, "east": 71.70}
INSIDE = (51.12834, 71.43052)  # Astana, near the start
OUTSIDE = (55.7558, 37.6173)  # Moscow


def fail(shot, note: str) -> None:
    shot.ok = False
    shot.notes.append(note)


def forgive_pins(shot) -> None:
    """An answer that is not in the recording has the data's own places: two pins (or a pin and a saved place) may lie
    within a finger's width of each other. That is the map's geography, not the page's layout."""
    prefixes = ("targets overlap: .mk", "targets overlap: .bm")
    shot.notes = [n for n in shot.notes if not n.startswith(prefixes)]
    shot.ok = not shot.notes


def turn_requests(page) -> list[dict]:
    """The bodies of every POST /api/turn this page sends."""
    seen: list[dict] = []

    def on_request(req) -> None:
        if req.method == "POST" and req.url.endswith("/api/turn"):
            with contextlib.suppress(ValueError):
                seen.append(json.loads(req.post_data or "{}"))

    page.on("request", on_request)
    return seen


def cam(page) -> tuple[float, float, float]:
    zoom, lat, lon = (page.locator("#map").get_attribute("data-cam") or "0 0 0").split()
    return float(zoom), float(lat), float(lon)


def where(page) -> dict:
    return page.evaluate("JSON.parse(sessionStorage.getItem('anyq.dialog')).where")


def decimals_ok(x: float) -> bool:
    return abs(x * 1000 - round(x * 1000)) < 1e-6


# ------------------------------------------------------------------ the language menu and the first screen


def language_menu(t, browser, base: str) -> None:
    page = t.open(browser, base)
    t.press(page, "#lang-btn")
    page.wait_for_timeout(400)
    s = t.shot(page, "lang-menu", "language menu: the globe with the code, three full names")
    names = page.locator("#lang-pop button").all_inner_texts()
    if names != ["Қазақша", "Русский", "English"]:
        fail(s, f"the language menu lists {names}")
    if (page.locator(".lang-code").inner_text() or "") != "RU":
        fail(s, "the menu button does not show the current code RU")
    if page.locator("#lang-pop [aria-pressed='true']").get_attribute("data-lang") != "ru":
        fail(s, "the current language is not marked in the menu")
    t.press(page, "#lang-pop [data-lang='en']")
    page.wait_for_timeout(600)
    if page.locator(".lang-code").inner_text() != "EN" or page.locator("#lang-pop").is_visible():
        fail(s, "choosing English did not close the menu and show EN")
    page.context.close()


def first_screen(t, browser, base: str) -> None:
    """No tiles; generic chips; a chip sends its own text from where the visitor is."""
    page = t.open(browser, base)
    reqs = turn_requests(page)
    s = t.shot(page, "first-chips", "first screen: generic chips, no scenario tiles")
    if page.locator("#tiles, .tile").count():
        fail(s, "scenario tiles are still on the page")
    chips = page.locator("#starters [data-suggest]").all_inner_texts()
    if chips != ["Поесть", "Кофе", "Погулять", "С детьми", "Музей", "Вечером куда сходить"]:
        fail(s, f"first-screen chips: {chips}")
    cfg = t.config(page)
    start = next(p for p in cfg["presets"] if p["id"] == cfg["start"])
    page.locator("#starters [data-suggest='coffee']").click()
    t.wait_answer(page, 1)
    s = t.shot(
        page, "chip-answer", "a chip asked: the answer starts with its own lead, no condition boxes"
    )
    forgive_pins(s)
    if not reqs:
        fail(s, "the chip sent no request")
    else:
        body = reqs[-1]
        if (body["lat"], body["lon"]) != (start["lat"], start["lon"]):
            fail(s, f"the chip moved the visitor: {body['lat']}, {body['lon']}")
        if body["text"] != "Хочу кофе" or body.get("bookmarks") != []:
            fail(s, f"the chip's request: {body['text']!r}, bookmarks {body.get('bookmarks')}")
    if page.locator("#thread .ctx").count():
        fail(s, "a condition box is rendered above the answer")
    if not page.locator("#thread .turn:last-child .reply").count():
        fail(s, "the answer has no lead")
    page.context.close()


# ------------------------------------------------------------------ the map: Astana only, «Моё местоположение»


def zoom_out(page) -> None:
    for _ in range(30):
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(60)
    page.wait_for_timeout(1200)


def map_bounds(t, browser, base: str) -> None:
    page = t.open(browser, base)
    x0, y0 = t.w / 2, t.h * 0.4
    page.mouse.move(x0, y0)
    zoom_out(page)  # as far out as the map goes
    page.wait_for_timeout(1200)
    zoom, _, _ = cam(page)
    for dx, dy in ((-300, 300), (-300, 300), (300, -300), (300, -300), (-300, 0), (0, -300)):
        for _ in range(8):
            ax, ay = x0 - dx / 2, y0 - dy / 2
            page.mouse.move(ax, ay)
            page.mouse.down()
            page.mouse.move(ax + dx, ay + dy, steps=5)
            page.mouse.up()
        page.wait_for_timeout(600)
    page.wait_for_timeout(1200)
    page.mouse.move(x0, y0)
    zoom_out(page)
    page.wait_for_timeout(1200)
    s = t.shot(
        page, "bounds", "the map pushed to the north and zoomed out: it stops at the city's box"
    )
    z, lat, lon = cam(page)
    if z < 9.99 or zoom < 9.99:
        fail(s, f"zoom went below the minimum: {z}")
    if not (
        ASTANA["south"] - 0.001 <= lat <= ASTANA["north"] + 0.001
        and ASTANA["west"] - 0.001 <= lon <= ASTANA["east"] + 0.001
    ):
        fail(s, f"the camera left Astana: {lat}, {lon}")
    page.context.close()


def locate(t, browser, base: str) -> None:
    # inside the city: the point becomes the start, rounded to 3 decimals
    page = t.open(browser, base, geo=INSIDE)
    t.press(page, "#locate-bar" if t.phone else ".locate")
    page.wait_for_timeout(2500)
    s = t.shot(page, "locate-ok", "«Моё местоположение»: the device's place is the start")
    here = where(page)
    if (here["lat"], here["lon"]) != (51.128, 71.431) or here["preset"] is not None:
        fail(s, f"the start after the button: {here}")
    if not (decimals_ok(here["lat"]) and decimals_ok(here["lon"])):
        fail(s, "the start is not rounded to 3 decimals")
    if "карте" not in page.locator("#where-text").inner_text():
        fail(s, "the composer does not say it is a point on the map")
    page.context.close()

    # outside Astana: a plain line, the start stays
    page = t.open(browser, base, geo=OUTSIDE)
    before = where(page)
    t.press(page, "#locate-bar" if t.phone else ".locate")
    page.wait_for_timeout(2500)
    s = t.shot(
        page, "locate-outside", "the device is outside Astana: a plain line, the start stays"
    )
    note = page.locator("#map-note").inner_text() if page.locator("#map-note").is_visible() else ""
    if "за пределами Астаны" not in note:
        fail(s, f"no message for a place outside Astana: {note!r}")
    if where(page) != before:
        fail(s, "the start changed although the device is outside Astana")
    page.context.close()

    # refused: a plain line, the start stays
    page = t.open(browser, base)
    before = where(page)
    t.press(page, "#locate-bar" if t.phone else ".locate")
    page.wait_for_timeout(2500)
    s = t.shot(page, "locate-denied", "the location is refused: a plain line, the start stays")
    note = page.locator("#map-note").inner_text() if page.locator("#map-note").is_visible() else ""
    if "Нет доступа" not in note:
        fail(s, f"no message for a refused location: {note!r}")
    if where(page) != before:
        fail(s, "the start changed although the location was refused")
    page.context.close()


# ------------------------------------------------------------------ «Мои места»


def saved() -> str:
    return "JSON.parse(localStorage.getItem('anyq.bookmarks') || '[]')"


def open_list(t, page) -> None:
    t.press(page, "#where-change")
    page.wait_for_selector("#location[open]")
    page.wait_for_timeout(300)


def close_list(t, page) -> None:
    t.press(page, "#location .close")
    page.wait_for_timeout(300)


def places(t, browser, base: str) -> None:
    page = t.open(browser, base)
    reqs = turn_requests(page)
    open_list(t, page)
    t.shot(page, "places-empty", "«Где вы?»: the list of places is empty and says what it is for")

    # 1. from the list: «Дом» at the start
    t.press(page, ".bm-add")
    page.wait_for_selector("#bookmark[open]")
    page.wait_for_timeout(300)
    s = t.shot(page, "place-editor", "adding a place: kind, name, position, save")
    if page.locator("#bm-name").input_value() != "Дом":
        fail(s, "the name of a new place is not the kind's name")
    t.press(page, "#bm-save")
    page.wait_for_timeout(400)
    got = page.evaluate(saved())
    start = where(page)
    if (
        len(got) != 1
        or got[0]["kind"] != "home"
        or (got[0]["lat"], got[0]["lon"]) != (start["lat"], start["lon"])
    ):
        fail(s, f"the saved place: {got}")
    close_list(t, page)

    # 2. a long press on the map (a right click on a laptop): the menu, then «Работа» there
    x, y = (90, t.h * 0.3) if t.phone else (700, 430)
    if t.phone:
        tap(page, x, y, hold_ms=900)
    else:
        page.mouse.click(x, y, button="right")
    page.wait_for_selector("#map-menu:not([hidden])")
    s = t.shot(page, "map-menu", "a long press on the map: start from here, or save the place")
    labels = page.locator("#map-menu button").all_inner_texts()
    if labels != ["Начать отсюда", "Сохранить это место"]:
        fail(s, f"the map menu: {labels}")
    if (
        t.phone
    ):  # the picture's own touch (see Tour.shot) is a tap elsewhere: the menu closed, as it should
        tap(page, x, y, hold_ms=900)
        page.wait_for_selector("#map-menu:not([hidden])")
    t.press(page, "#map-menu button:nth-child(2)")
    page.wait_for_selector("#bookmark[open]")
    t.press(page, ".bm-kind[data-kind='work']")
    if page.locator("#bm-name").input_value() != "Работа":
        fail(s, "choosing «Работа» did not name the place")
    t.press(page, "#bm-save")
    page.wait_for_timeout(600)
    got = page.evaluate(saved())
    s = t.shot(page, "places-map", "two saved places on the map as small icons")
    if (
        len(got) != 2
        or got[1]["kind"] != "work"
        or not all(decimals_ok(b["lat"]) and decimals_ok(b["lon"]) for b in got)
    ):
        fail(s, f"the saved places: {got}")
    if page.locator(".bm").count() != 2:
        fail(s, f"icons on the map: {page.locator('.bm').count()}")

    # 3. the list offers them as starting points
    open_list(t, page)
    s = t.shot(page, "places-list", "«Мои места»: the starting points, edit buttons")
    if page.locator(".bm-use").count() != 2:
        fail(s, "the list does not show both places")
    t.press(page, ".bm-row:nth-child(2) .bm-use")
    page.wait_for_timeout(900)
    if "Работа" not in page.locator("#where-text").inner_text():
        fail(s, f"the start is not «Работа»: {page.locator('#where-text').inner_text()!r}")

    # 4. every request carries them
    t.ask(page, "хочу кофе")
    body = reqs[-1]
    marks = body.get("bookmarks") or []
    if [b["kind"] for b in marks] != ["home", "work"] or not all(
        decimals_ok(b["lat"]) and decimals_ok(b["lon"]) for b in marks
    ):
        fail(s, f"bookmarks of the request: {marks}")
    if (body["lat"], body["lon"]) != (got[1]["lat"], got[1]["lon"]):
        fail(s, "the request does not start from the chosen place")
    forgive_pins(t.shot(page, "places-answer", "an answer asked from a saved place"))

    # 5. edit and delete
    open_list(t, page)
    t.press(page, ".bm-row:nth-child(2) .bm-edit")
    page.wait_for_selector("#bookmark[open]")
    page.wait_for_timeout(300)
    s = t.shot(page, "place-edit", "editing a saved place: change or delete")
    page.locator("#bm-name").fill("Офис")
    t.press(page, "#bm-save")
    page.wait_for_timeout(300)
    if page.evaluate(saved())[1]["name"] != "Офис":
        fail(s, "the new name was not saved")
    t.press(page, ".bm-row:nth-child(1) .bm-edit")
    page.wait_for_selector("#bookmark[open]")
    t.press(page, "#bm-delete")
    page.wait_for_timeout(400)
    if len(page.evaluate(saved())) != 1 or page.locator(".bm").count() != 1:
        fail(s, "deleting a place left it saved or on the map")
    page.context.close()


def run_places(t, browser, base: str) -> None:
    language_menu(t, browser, base)
    first_screen(t, browser, base)
    map_bounds(t, browser, base)
    locate(t, browser, base)
    places(t, browser, base)
