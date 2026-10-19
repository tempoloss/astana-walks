"""The satellite layer part of scripts/ui_tour.py: the switch «Спутник» (default OFF, remembered in localStorage `anyq.sat`),
the imagery under a recorded walk request with its route, pins and «Вы здесь», the EOX credit in the legend row while it
is on, and the map exactly as it was when it is off again. Once under the day sky and once under the night sky (the stand
runs with WALKS_FX_FAKE=1, `?fx=day` / `?fx=night`: the page has no dark theme, the night sky is its darkest map).

`run_satellite(tour, browser, base, offline)` takes the Tour of ui_tour.py (a size, `open`, `shot`, `press`, `scenario`,
`check_answer`)."""

from __future__ import annotations

OFF = "[data-sat='off']"
WALK = "s0"  # «Рядом с Mega Silk Way, прогулка 30–60 мин»: a walk, with the route to its main place
EOX_LINK = "https://s2maps.eu"


def fail(shot, note: str) -> None:
    shot.ok = False
    shot.notes.append(note)


def toggle(t, page) -> None:
    """The switch: the map's corner button on a laptop, the last row of the menu on a phone."""
    if t.phone:
        t.press(page, ".menu-open")
        t.press(page, "#sat-menu")
    else:
        t.press(page, ".sat-btn")


def pressed(t, page) -> int:
    return page.locator(f"{'#sat-menu' if t.phone else '.sat-btn'}[aria-pressed='true']").count()


def credit(page) -> list[str]:
    """The map's credit lines as the legend row names them: the texts of its links and spans, and the link targets."""
    return page.evaluate(
        """() => [...document.querySelectorAll('#legend .lg-attr a, #legend .lg-attr span:not(.dot)')]
              .map((e) => e.getAttribute('href') ? `${e.textContent}|${e.getAttribute('href')}` : e.textContent)"""
    )


def show_credit(t, page) -> None:
    """Bring the credit line into the picture: the legend plate on a laptop, the end of the sheet's list on a phone."""
    page.locator("#legend").scroll_into_view_if_needed()
    page.wait_for_timeout(300)


def outside_city(t, page, tiles: list[int]) -> None:
    """Zoom 15 inside the map's box but outside the city box (the server serves no z14-15 tile there): the overview's
    overzoomed z13 imagery must show, not a blank map, and no tile may be asked for in vain."""
    before = len(tiles)
    page.evaluate(
        """async () => {
          const src = document.querySelector('script[type=module]').src; // the page's own modules, not a second copy
          const map = await import(new URL('map.js', src));
          map.flyTo([51.3, 71.2], 15, { top: 0, right: 0, bottom: 0, left: 0 }, 0);
        }"""
    )
    page.wait_for_timeout(5000)  # the tiles of the new view arrive
    s = t.shot(
        page,
        "sat-outside",
        "satellite at zoom 15 outside the city box: overzoomed z13 imagery, not blank",
    )
    cam = page.evaluate("document.querySelector('[data-cam]').dataset.cam").split()
    if abs(float(cam[0]) - 15) > 0.1 or abs(float(cam[1]) - 51.3) > 0.01:
        fail(s, f"the camera is not where the step sent it: {cam}")
    late = tiles[before:]
    if any(code != 200 for code in late):
        fail(s, f"tile statuses outside the city box: {sorted(set(late))}")


def run_one(t, browser, base: str, name: str, what: str) -> None:
    tiles: list[int] = []
    page = t.open(browser, base)
    page.on("response", lambda r: tiles.append(r.status) if "/tiles/s2/" in r.url else None)
    first = page.evaluate("document.querySelector('[data-sat]')?.dataset.sat")
    if first != "off" or page.evaluate("localStorage.getItem('anyq.sat')") is not None:
        s = t.shot(page, f"{name}-default", f"{what}: the default")
        fail(s, f"satellite is not off by default: {first!r}")
    if any("Sentinel-2" in x for x in credit(page)) or tiles:
        s = t.shot(page, f"{name}-default", f"{what}: the default")
        fail(s, "the satellite credit or tiles are present while the layer is off")

    toggle(t, page)
    page.wait_for_selector("[data-sat='on']", timeout=10000)
    for _ in range(40):  # the imagery is requested
        if tiles:
            break
        page.wait_for_timeout(500)
    t.scenario(page, WALK)
    page.wait_for_timeout(2500)  # the tiles of the new view arrive
    s = t.shot(
        page,
        f"{name}-walk",
        f"{what}: a walk over the imagery, route, pins and «Вы здесь» above it",
    )
    t.check_answer(page, s)
    if page.evaluate("localStorage.getItem('anyq.sat')") != "on":
        fail(s, "the choice is not kept in localStorage")
    if pressed(t, page) != 1:
        fail(s, "the switch does not show that the layer is on")
    lines = credit(page)
    if not any(x.startswith("Sentinel-2 cloudless|") and x.endswith(EOX_LINK) for x in lines):
        fail(s, f"no linked Sentinel-2 credit in the legend row: {lines}")
    if not any(x.startswith("CC BY 4.0|") for x in lines) or not any(
        "Copernicus Sentinel data 2016" in x for x in lines
    ):
        fail(s, f"the credit lacks its licence or its Copernicus line: {lines}")
    if not tiles or any(code != 200 for code in tiles):
        fail(s, f"tile statuses {sorted(set(tiles))}")
    if not page.locator(".you .you-label").count() or not page.locator(".mk").count():
        fail(s, "the origin marker or the pins are missing over the imagery")
    show_credit(t, page)
    t.shot(page, f"{name}-credit", f"{what}: the credit line of the imagery")
    # the phone's switch is the last row of the menu: «Спутник», marked while it is on
    if t.phone and name == "sat-day":
        t.press(page, ".menu-open")
        t.shot(page, f"{name}-menu", f"{what}: the menu with its «Спутник» row, on")
        t.press(page, ".menu-open")

    if name == "sat-day":
        outside_city(t, page, tiles)

    page.reload()  # the choice is remembered
    page.wait_for_selector("body[data-ready='1']", timeout=60000)
    page.wait_for_timeout(1500)
    if page.evaluate("document.querySelector('[data-sat]')?.dataset.sat") != "on":
        fail(s, "the layer is not on again after a reload")

    toggle(t, page)
    page.wait_for_selector(OFF, timeout=10000)
    page.wait_for_timeout(800)
    if any("Sentinel-2" in x for x in credit(page)):
        fail(s, "the satellite credit stays after the layer is switched off")
    if page.evaluate("localStorage.getItem('anyq.sat')") != "off":
        fail(s, "the off choice is not kept")
    page.context.close()


def run_offline(t, browser, base: str) -> None:
    """The stand with no network (the browser blocked from everything but the stand): the imagery is the server's own cache,
    under the district outlines' place, the route over it."""
    tiles: list[int] = []
    page = t.open(browser, base, block_external=True)
    page.on("response", lambda r: tiles.append(r.status) if "/tiles/s2/" in r.url else None)
    toggle(t, page)
    page.wait_for_selector("[data-sat='on']", timeout=10000)
    t.scenario(page, "s1")
    page.wait_for_timeout(2500)
    s = t.shot(
        page, "sat-offline", "satellite on the offline stand: the cached imagery, the route over it"
    )
    t.check_answer(page, s)
    s.pending_rewarm = False  # rules text is what the offline stand is meant to show
    s.notes = [n for n in s.notes if not n.startswith("pending")]
    if not tiles or any(code != 200 for code in tiles):
        fail(s, f"tile statuses {sorted(set(tiles))}")
    if not any(x.startswith("Sentinel-2 cloudless|") for x in credit(page)):
        fail(s, "no satellite credit on the offline stand")
    page.context.close()


def run_satellite(t, browser, base: str, offline: str) -> None:
    root = base.rstrip("/")
    run_one(t, browser, f"{root}/?fx=day", "sat-day", "satellite, day sky")
    run_one(t, browser, f"{root}/?fx=night", "sat-night", "satellite, night sky")
    run_offline(t, browser, offline)
