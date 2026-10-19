"""The place-and-language part of scripts/ui_tour.py: the language menu, the first screen's chips (nothing teleports the
visitor), the map kept to Astana, the «Моё местоположение» button (inside the city, outside it, refused), the «Где вы?»
sheet (address search, nothing else) and «Мои места» (added in «Память» and by a long press, renamed, moved, deleted with
«Вернуть», kept across a reload, sent with the request, «рядом с домом» / «по пути домой», the hints).

`run_places(tour, browser, base)` takes the Tour of ui_tour.py (a size, `open`, `shot`, `press`, `set_lang`, `ask`)."""

from __future__ import annotations

import contextlib
import json

from ui_tour_phone import tap

ASTANA = {
    "south": 50.74,
    "north": 51.54,
    "west": 70.83,
    "east": 72.08,
}  # mirror of maxBounds in js/map.js
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
    expected = [
        "Под мой вайб",
        "Поесть",
        "Кофе",
        "Погулять",
        "С детьми",
        "Музей",
        "Вечером куда сходить",
    ]
    if chips != expected:
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
    if z < 8.99 or zoom < 8.99:
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
    if "геолокации" not in page.locator("#where-text").inner_text():
        fail(s, "the composer does not say the start comes from the device's location")
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


# ------------------------------------------------------------------ «Где вы?»


def open_where(t, page) -> None:
    t.press(page, "#where-change")
    page.wait_for_selector("#location[open]")
    page.wait_for_timeout(300)


def close_where(t, page) -> None:
    t.press(page, "#location .close")
    page.wait_for_timeout(300)


def open_memory(t, page) -> None:
    """«Память» from the top bar. The page's own menu is the main tour's business; here the panel is opened the way the
    button does it."""
    page.evaluate("document.querySelector('.memory-open').click()")
    page.wait_for_selector("#memory[open]")
    page.wait_for_timeout(600)


def close_memory(t, page) -> None:
    page.evaluate("document.getElementById('memory').close()")
    page.wait_for_timeout(300)


def type_address(page, field: str, text: str) -> None:
    page.locator(field).fill(text)
    page.wait_for_function("() => !document.querySelector('.addr.busy')", timeout=8000)
    page.wait_for_timeout(300)


def where_sheet(t, browser, base: str) -> None:
    """Address, «Моё местоположение», «Выбрать на карте»: nothing else; typed results carry a kind and a district."""
    page = t.open(browser, base)
    open_where(t, page)
    s = t.shot(
        page,
        "where-empty",
        "«Где вы?»: the address field and two buttons; the default start says it is one",
    )
    if page.locator("#location .loc-list, #location .loc-marks, #location .bm-row").count():
        fail(s, "the sheet still lists places")
    text = page.locator("#location").inner_text()
    for gone in (
        "EXPO",
        "Mega Silk Way",
        "Байтерек",
        "Хан Шатыр",
        "Аэропорт",
        "Мои места",
        "МОИ МЕСТА",
    ):
        if gone in text:
            fail(s, f"the sheet still names {gone!r}")
    if "центра города" not in page.locator("#loc-nudge").inner_text():
        fail(s, "the default start is not named honestly in the sheet")
    if "центр города" not in page.locator("#where-text").inner_text():
        fail(
            s,
            f"the composer does not say the start is the default: {page.locator('#where-text').inner_text()!r}",
        )
    if "Кенесары" not in (page.locator("#loc-q").get_attribute("placeholder") or ""):
        fail(s, "the placeholder gives no examples")
    type_address(page, "#loc-q", "Кенес")
    t.shot(page, "where-typing", "typing: the first suggestions")
    type_address(page, "#loc-q", "Кенесары 40")
    s = t.shot(
        page,
        "where-results",
        "«Кенесары 40»: the house first, then the street, each with kind and district",
    )
    rows = page.locator("#loc-list .addr-row")
    kinds = page.locator("#loc-list .addr-kind").all_inner_texts()
    if rows.count() < 2 or kinds[:2] != ["дом", "улица"]:
        fail(s, f"results of «Кенесары 40»: {kinds}")
    if not page.locator("#loc-list .addr-sub").first.inner_text():
        fail(s, "a result has no district")
    page.locator("#loc-q").press("ArrowDown")
    if page.locator("#loc-list .addr-row[aria-selected='true']").count() != 1:
        fail(s, "the arrow key did not mark a result")
    type_address(page, "#loc-q", "ззззыыыы")
    s = t.shot(
        page, "where-none", "nothing found: a plain line, the two other ways stay under the field"
    )
    if not page.locator("#loc-addr .addr-msg").is_visible() or not (
        page.locator("#loc-mine").is_visible() and page.locator("#loc-pick").is_visible()
    ):
        fail(s, "an empty answer left a dead end")
    type_address(page, "#loc-q", "Кенесары 40")
    page.locator("#loc-q").press("Enter")
    page.wait_for_timeout(900)
    here = where(page)
    s = t.shot(
        page, "where-picked", "the house is the start: rounded to 3 decimals, named in the composer"
    )
    if (
        here["preset"] is not None
        or abs(here["lat"] - 51.1655) > 0.003
        or not (decimals_ok(here["lat"]) and decimals_ok(here["lon"]))
    ):
        fail(s, f"the start after Enter: {here}")
    if "Кенесары" not in page.locator("#where-text").inner_text():
        fail(s, "the composer does not name the picked address")
    open_where(t, page)
    if "Кенесары" not in page.locator("#loc-list").inner_text():
        fail(s, "the last pick is not offered again")
    page.context.close()


# ------------------------------------------------------------------ «Мои места»


def saved() -> str:
    return "JSON.parse(localStorage.getItem('anyq.bookmarks') || '[]')"


def pick_first(page, field: str, text: str) -> None:
    type_address(page, field, text)
    page.locator(f"{field.replace('-q', '-list')} .addr-row").first.click()
    page.wait_for_timeout(300)


def add_in_memory(t, page, text: str, kind: str | None = None) -> None:
    t.press(page, "#pl-add")
    page.wait_for_selector("#bookmark[open]")
    page.wait_for_timeout(300)
    if kind:
        t.press(page, f".bm-kind[data-kind='{kind}']")
    if page.locator("#bm-move").is_visible():
        t.press(page, "#bm-move")
    pick_first(page, "#bm-q", text)
    t.press(page, "#bm-save")
    page.wait_for_timeout(500)


def places(t, browser, base: str) -> None:
    page = t.open(browser, base)
    open_memory(t, page)
    s = t.shot(page, "places-empty", "«Мои места» in «Память»: empty, one sentence and one button")
    if (
        not page.locator("#places .pl-empty").is_visible()
        or not page.locator("#pl-add").is_visible()
    ):
        fail(s, "the empty state lacks its sentence or its button")
    if "только в этом браузере" not in page.locator("#places .pl-note").inner_text():
        fail(s, "the section does not say the places stay in the browser")

    # 1. «Память»: «Добавить место» -> one sheet: kind, name, where, save
    t.press(page, "#pl-add")
    page.wait_for_selector("#bookmark[open]")
    page.wait_for_timeout(300)
    s = t.shot(
        page,
        "place-add",
        "the add sheet: kind chips, name, where (address, my location, map), save",
    )
    if page.locator("#bm-name").input_value() != "Дом":
        fail(s, "the name of a new place is not the kind's name")
    t.press(page, "#bm-save")
    s = t.shot(
        page, "place-add-error", "saving without a point: the sheet says where it is missing"
    )
    if page.evaluate(saved()):
        fail(s, "a place without a point was saved")
    if not page.locator("#bm-where-err").is_visible():
        fail(s, "no line says the point is missing")
    pick_first(page, "#bm-q", "Кенесары 40")
    if "Кенесары" not in page.locator("#bm-where-line").inner_text():
        fail(s, "the chosen address is not shown")
    t.press(page, "#bm-save")
    page.wait_for_timeout(500)
    got = page.evaluate(saved())
    s = t.shot(page, "place-saved", "saved: the list and a notice that says what happened")
    if len(got) != 1 or got[0]["kind"] != "home" or "Кенесары" not in got[0]["addr"]:
        fail(s, f"the saved place: {got}")
    if not decimals_ok(got[0]["lat"]) or not decimals_ok(got[0]["lon"]):
        fail(s, "the place is not rounded to 3 decimals")
    if "Дом сохранён" not in page.locator(".toast").inner_text():
        fail(s, "no notice says what happened")
    if page.locator("#places .pl-row").count() != 1:
        fail(s, "the list does not show the place")
    close_memory(t, page)

    # 2. the map: a long press (a right click on a laptop): start from here, or save the place
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
    if page.locator("#bm-kinds [aria-pressed='true']").get_attribute("data-kind") != "work":
        fail(s, "the second place does not default to the next free kind")
    s = t.shot(
        page, "place-from-map", "a place from the map menu: the point is set, only a name is left"
    )
    if not page.locator("#bm-where-line").is_visible():
        fail(s, "the point of the map menu is not shown")
    t.press(page, "#bm-save")
    page.wait_for_timeout(600)
    got = page.evaluate(saved())
    s = t.shot(page, "places-map", "two saved places on the map as small icons")
    if len(got) != 2 or got[1]["kind"] != "work" or got[1]["name"] != "Работа":
        fail(s, f"the saved places: {got}")
    if page.locator(".bm").count() != 2:
        fail(s, f"icons on the map: {page.locator('.bm').count()}")

    # 3. edit: rename and move
    open_memory(t, page)
    t.press(page, "#places .pl-row:nth-child(2) .pl-main")
    page.wait_for_selector("#bookmark[open]")
    page.wait_for_timeout(300)
    s = t.shot(
        page, "place-edit", "editing a saved place: rename, move, delete apart at the bottom"
    )
    if page.locator("#bm-title").inner_text() != "Изменить место":
        fail(s, "the sheet of a saved place is not titled «Изменить место»")
    if not page.locator("#bm-delete").is_visible():
        fail(s, "no «Удалить место» in the sheet")
    page.locator("#bm-name").fill("Офис")
    t.press(page, "#bm-move")
    pick_first(page, "#bm-q", "Хан Шатыр")
    t.press(page, "#bm-save")
    page.wait_for_timeout(500)
    got = page.evaluate(saved())
    if (
        got[1]["name"] != "Офис"
        or abs(got[1]["lat"] - 51.1325) > 0.005
        or "Шатыр" not in got[1]["addr"]
    ):
        fail(s, f"rename + move: {got[1]}")
    add_in_memory(t, page, "Сарайшык", "study")
    got = page.evaluate(saved())
    s = t.shot(
        page, "places-three", "«Мои места» with three places: icon by kind, name, short address"
    )
    if [b["kind"] for b in got] != ["home", "work", "study"] or page.locator(
        "#places .pl-row"
    ).count() != 3:
        fail(s, f"three places: {got}")
    if page.locator(".bm").count() != 3:
        fail(s, "the map does not show three icons")

    # 4. delete with «Вернуть»: no confirm dialog; the place comes back where it was
    t.press(page, "#places .pl-row:nth-child(1) .pl-del")
    page.wait_for_timeout(400)
    s = t.shot(page, "place-undo", "deleted: a notice with «Вернуть», no confirm dialog")
    if len(page.evaluate(saved())) != 2 or page.locator(".bm").count() != 2:
        fail(s, "the delete left the place saved or on the map")
    if "Вернуть" not in page.locator(".toast").inner_text():
        fail(s, "the notice has no «Вернуть»")
    t.press(page, ".toast-act")
    page.wait_for_timeout(400)
    got = page.evaluate(saved())
    if [b["kind"] for b in got] != ["home", "work", "study"] or page.locator(".bm").count() != 3:
        fail(s, f"«Вернуть» did not put the place back: {got}")
    # …and from the sheet's own destructive zone
    t.press(page, "#places .pl-row:nth-child(3) .pl-main")
    page.wait_for_selector("#bookmark[open]")
    t.press(page, "#bm-delete")
    page.wait_for_timeout(500)
    if len(page.evaluate(saved())) != 2 or "удалено" not in page.locator(".toast").inner_text():
        fail(s, "«Удалить место» in the sheet did not delete with a notice")
    close_memory(t, page)

    # 5. they survive a reload and ride every request
    page.reload()
    page.wait_for_selector("body[data-ready='1']", timeout=60000)
    page.wait_for_timeout(1500)
    if [b["kind"] for b in page.evaluate(saved())] != ["home", "work"] or page.locator(
        ".bm"
    ).count() != 2:
        fail(s, "the places did not survive a reload")
    reqs = turn_requests(page)
    t.ask(page, "кофе рядом с домом")
    body = reqs[-1]
    marks = body.get("bookmarks") or []
    s = t.shot(page, "near-home", "«кофе рядом с домом»: the lead names «Дом»")
    forgive_pins(s)
    if [b["kind"] for b in marks] != ["home", "work"] or not all(
        decimals_ok(b["lat"]) and decimals_ok(b["lon"]) for b in marks
    ):
        fail(s, f"bookmarks of the request: {marks}")
    if "«Дом»" not in page.locator("#thread .turn:last-child .reply").first.inner_text():
        fail(s, "the answer to «рядом с домом» does not name «Дом»")
    t.ask(page, "где поесть по пути домой")
    s = t.shot(page, "on-the-way-home", "«по пути домой»: an answer from the start toward «Дом»")
    forgive_pins(s)
    if not page.locator("#thread .turn:last-child .reply").count():
        fail(s, "no answer to «по пути домой»")
    page.context.close()


def late_night(t, browser, base: str) -> None:
    """Late at night «хочу поесть» is answered «по пути домой» when a home is saved and the place really lies toward it
    (the server says so only for a place that covers a real share of the way); without a home a chip offers it."""
    # (where «Дом» is, where the visitor stands, is the first food place on the way home?): the pairs were measured
    # against the data: from Республики 5 the way to Кенесары 40 passes food places, the way to Мангилик Ел 55 does not
    night_home(t, browser, base, "Кенесары 40", "Республики 5", on_the_way=True)
    night_home(t, browser, base, "Мангилик Ел 55", "Республики 5", on_the_way=False)


def night_home(t, browser, base: str, home: str, here: str, *, on_the_way: bool) -> None:
    page = t.open(browser, base)
    open_where(t, page)
    pick_first(page, "#loc-q", home)
    page.evaluate(
        "() => { const s = JSON.parse(sessionStorage.getItem('anyq.dialog')); s.at = '23:30';"
        " sessionStorage.setItem('anyq.dialog', JSON.stringify(s)); }"
    )
    page.reload()
    page.wait_for_selector("body[data-ready='1']", timeout=60000)
    page.wait_for_timeout(1500)
    t.ask(page, "хочу поесть")
    s = t.shot(
        page, "night-hint", "late at night, food, no «Дом» saved: a chip offers «Отметить дом»"
    )
    forgive_pins(s)
    if not page.locator("#thread .mark-home").is_visible():
        fail(s, "no «Отметить дом» chip under a late-night food answer")
    page.locator("#thread .mark-home").scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    t.press(page, "#thread .mark-home")
    page.wait_for_selector("#bookmark[open]")
    if page.locator("#bm-kinds [aria-pressed='true']").get_attribute("data-kind") != "home":
        fail(s, "the chip does not open the sheet on «Дом»")
    if page.locator("#bm-where-line").is_visible() is False:
        fail(s, "the sheet does not take the visitor's own start as its point")
    t.press(page, "#bm-save")
    page.wait_for_timeout(500)
    open_where(
        t, page
    )  # «Дом» is where the visitor stood a moment ago: now they stand somewhere else
    pick_first(page, "#loc-q", here)
    page.wait_for_timeout(800)
    reqs = turn_requests(page)
    t.ask(page, "хочу поесть")
    body = reqs[-1]
    s = t.shot(
        page,
        "night-home" if on_the_way else "night-home-far",
        "late at night with «Дом» saved on the way: «по пути домой»"
        if on_the_way
        else "late at night with «Дом» far in another direction: no «по пути домой»",
    )
    forgive_pins(s)
    if [b["kind"] for b in body.get("bookmarks") or []] != ["home"]:
        fail(s, f"bookmarks of the request: {body.get('bookmarks')}")
    said = "по пути домой" in page.locator("#thread .turn:last-child .reply").first.inner_text()
    if on_the_way and not said:
        fail(
            s,
            "the late-night answer does not say «по пути домой» although the place lies on the way",
        )
    if said and not on_the_way:
        fail(s, "the late-night answer says «по пути домой» with home far in another direction")
    if page.locator("#thread .turn:last-child .mark-home").count():
        fail(s, "the «Отметить дом» chip stays although a home is saved")
    page.context.close()


def first_hint(t, browser, base: str) -> None:
    """Once, under the first answer of a visitor who marked nothing."""
    page = t.open(browser, base)
    t.ask(page, "хочу погулять")
    s = t.shot(page, "first-hint", "under the first answer: one line about «Мои места»")
    forgive_pins(s)
    if page.locator("#thread .places-hint").count() != 1:
        fail(s, "no hint about «Мои места» under the first answer")
    t.ask(page, "хочу погулять")
    if page.locator("#thread .places-hint").count():
        fail(s, "the hint came back")
    page.context.close()


def run_places(t, browser, base: str) -> None:
    language_menu(t, browser, base)
    first_screen(t, browser, base)
    map_bounds(t, browser, base)
    locate(t, browser, base)
    where_sheet(t, browser, base)
    places(t, browser, base)
    late_night(t, browser, base)
    first_hint(t, browser, base)
