# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.50"]
# ///
"""Fresh screenshots of the live stand for the deck: one real request per shot, nothing pinned.

    uv run docs/presentation/deck/shots/shoot.py [--only id,id] [--base URL]

Every turn goes to https://anyq.an8kk.dev with the browser's geolocation set to the start point and the real clock and
weather of the stand. Each attempt is appended to shots.jsonl with the query, the start point, the time and the whole
/api/turn answer; an answer whose meta.generation is not "llm" is kept as a rejected attempt and asked again. No profile
is created (the memory panel is never opened). 45 s between turns so the model chain is not under load.

`--only sat_walk --base http://127.0.0.1:PORT/` is the satellite shot: the app of the branch with the «Спутник» layer run
locally in production mode (`python -m web`, no WALKS_* flag, the Esri key file in ARCGIS_API_KEY_FILE), the layer
switched on, one walk request from Байтерек, the camera set to z16–17 over the route; the row records the base, the
camera and who wrote the text, whatever it was (the layer is the point of the shot).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://anyq.an8kk.dev/"
HERE = Path(__file__).resolve().parent
LOG = HERE / "shots.jsonl"
ASTANA = timezone(timedelta(hours=5))
GAP_S = 45
TRIES = 3

START = {
    "Байтерек": (51.1283, 71.4305),
    "Хан Шатыр": (51.1325, 71.4033),
    "EXPO": (51.0890, 71.4160),
    "Mega Silk Way": (51.0886, 71.4030),
}

SHOTS = [
    {"id": "hero_walk", "view": "desktop", "start": "Mega Silk Way", "query": "Хочу погулять час на свежем воздухе", "steps": True},
    {"id": "kids_ru", "view": "phone", "start": "Хан Шатыр", "query": "Куда сходить с ребёнком на час?"},
    {"id": "kids_kk", "view": "phone", "start": "EXPO", "lang": "kk", "query": "Балаға қайда баруға болады?"},
    {"id": "cafe_en", "view": "phone", "start": "Байтерек", "lang": "en", "query": "Quiet cafe to work for an hour"},
    {"id": "vibe", "view": "phone", "start": "Байтерек", "query": "Я интроверт: люблю тишину, книги и парки. Куда пойти?"},
    {"id": "pharmacy", "view": "phone", "start": "Байтерек", "query": "Где ближайшая открытая аптека?"},
    {"id": "atm", "view": "phone", "start": "Хан Шатыр", "query": "Где снять наличные рядом?"},
    {"id": "ps_club", "view": "phone", "start": "Байтерек", "query": "PS-клуб рядом"},
    {"id": "scope", "view": "phone", "start": "Байтерек", "query": "Напиши скрипт для ипотеки"},
    {"id": "typo", "view": "phone", "start": "Байтерек", "query": "кофк"},
]
CITY = {"id": "city", "view": "desktop", "start": "Байтерек", "page": "#/city", "tab": "Пробелы в данных"}
SAT = {"id": "sat_walk", "view": "desktop", "start": "Байтерек", "query": "Хочу погулять час на свежем воздухе"}
# the room the answer panel and the top bar take on a laptop: the route is framed in what is left
SAT_PAD = {"top": 110, "right": 400, "bottom": 80, "left": 40}

WAIT_ANSWER = (
    "n => document.querySelectorAll('#thread .answer, #thread .folded').length >= n"
    " && !document.querySelector('#thread .thinking')"
)


def context(browser, view: str, start: str):
    lat, lon = START[start]
    phone = view == "phone"
    return browser.new_context(
        viewport={"width": 390, "height": 844} if phone else {"width": 1920, "height": 1080},
        device_scale_factor=2 if phone else 1,
        is_mobile=phone,
        has_touch=phone,
        locale="ru-RU",
        timezone_id="Asia/Almaty",
        geolocation={"latitude": lat, "longitude": lon},
        permissions=["geolocation"],
    )


def press(page, selector: str, phone: bool) -> None:
    (page.locator(selector).first.tap if phone else page.locator(selector).first.click)()


def turn(browser, spec: dict) -> dict:
    phone = spec["view"] == "phone"
    ctx = context(browser, spec["view"], spec["start"])
    page = ctx.new_page()
    page.goto(BASE)
    page.wait_for_selector("body[data-ready='1']", timeout=60000)
    page.wait_for_timeout(1500)
    if spec.get("lang"):
        press(page, "#lang-btn", phone)
        press(page, f"#lang-pop [data-lang='{spec['lang']}']", phone)
        page.wait_for_timeout(900)
    page.locator("#composer-input").fill(spec["query"])
    sent_at = datetime.now(ASTANA)
    with page.expect_response(lambda r: r.url.endswith("/api/turn"), timeout=90000) as got:
        press(page, "#composer .send", phone)
        if spec.get("steps"):
            page.wait_for_timeout(650)
            page.screenshot(path=str(HERE / f"{spec['id']}_steps.png"))
    page.wait_for_function(WAIT_ANSWER, arg=1, timeout=90000)
    page.wait_for_timeout(3200)
    lines = [json.loads(x) for x in got.value.text().splitlines() if x.strip()]
    file = f"{spec['id']}.png"
    page.screenshot(path=str(HERE / file))
    ctx.close()
    answer = lines[-1].get("answer")
    return {
        "id": spec["id"],
        "file": file,
        "query": spec["query"],
        "start": {"name": spec["start"], "lat": START[spec["start"]][0], "lon": START[spec["start"]][1]},
        "view": spec["view"],
        "ui_lang": spec.get("lang", "ru"),
        "sent_at": sent_at.isoformat(timespec="seconds"),
        "stages": [x.get("stage") for x in lines[:-1]],
        "accepted": bool(answer) and answer["turn"]["meta"].get("generation") == "llm",
        "answer": answer,
        "error": lines[-1].get("error"),
    }


def city(browser) -> dict:
    ctx = context(browser, CITY["view"], CITY["start"])
    page = ctx.new_page()
    seen: dict[str, object] = {}
    page.on("response", lambda r: seen.__setitem__(r.url.split("?")[0].rsplit("/", 1)[-1], r) if "/api/city/" in r.url else None)
    page.goto(BASE + CITY["page"])
    page.wait_for_selector("body[data-ready='1']", timeout=60000)
    page.wait_for_timeout(4000)
    tab = page.get_by_text(CITY["tab"], exact=True)
    if tab.count():
        tab.first.click()
        page.wait_for_timeout(4000)
    page.screenshot(path=str(HERE / "city.png"))
    layers = {}
    for name, resp in seen.items():
        try:
            layers[name] = resp.json()
        except Exception:  # noqa: BLE001 - an export or an aborted request
            continue
    ctx.close()
    return {
        "id": "city",
        "file": "city.png",
        "query": None,
        "start": {"name": CITY["start"], "lat": START[CITY["start"]][0], "lon": START[CITY["start"]][1]},
        "view": "desktop",
        "ui_lang": "ru",
        "sent_at": datetime.now(ASTANA).isoformat(timespec="seconds"),
        "accepted": True,
        "city_layers": layers,
    }


def sat_zoom(shape: list[list[float]], lat: float) -> tuple[float, float, float]:
    """The centre (lat, lon) of the route and the zoom in [16, 17] that keeps it inside the free room of the screen."""
    import math

    la = [p[0] for p in shape]
    lo = [p[1] for p in shape]
    h_m = (max(la) - min(la)) * 110_540
    w_m = (max(lo) - min(lo)) * 111_320 * math.cos(math.radians(lat))
    room_w = 1920 - SAT_PAD["left"] - SAT_PAD["right"]
    room_h = 1080 - SAT_PAD["top"] - SAT_PAD["bottom"]
    m_px = max(w_m / room_w, h_m / room_h, 1e-6) * 1.25  # a margin around the route
    z = math.log2(156_543.03 * math.cos(math.radians(lat)) / m_px)
    return (max(la) + min(la)) / 2, (max(lo) + min(lo)) / 2, round(min(17.0, max(16.0, z)), 2)


def satellite(browser, base: str) -> dict:
    ctx = context(browser, SAT["view"], SAT["start"])
    page = ctx.new_page()
    tiles: list[int] = []
    page.on("response", lambda r: tiles.append(r.status) if "/tiles/esri/" in r.url else None)
    page.goto(base)
    page.wait_for_selector("body[data-ready='1']", timeout=60000)
    page.wait_for_timeout(1500)
    press(page, ".sat-btn", False)
    page.wait_for_selector("[data-sat='on']", timeout=10000)
    page.locator("#composer-input").fill(SAT["query"])
    sent_at = datetime.now(ASTANA)
    with page.expect_response(lambda r: r.url.endswith("/api/turn"), timeout=90000) as got:
        press(page, "#composer .send", False)
    page.wait_for_function(WAIT_ANSWER, arg=1, timeout=90000)
    page.wait_for_timeout(3000)
    lines = [json.loads(x) for x in got.value.text().splitlines() if x.strip()]
    answer = lines[-1].get("answer")
    cam = None
    if answer and answer.get("place_legs"):
        lat, lon, z = sat_zoom(answer["place_legs"][0]["shape"], START[SAT["start"]][0])
        page.evaluate(
            """async ([lat, lon, z, pad]) => {
              const src = document.querySelector('script[type=module]').src; // the page's own modules
              const map = await import(new URL('map.js', src));
              map.flyTo([lat, lon], z, pad, 0);
            }""",
            [lat, lon, z, SAT_PAD],
        )
        page.wait_for_timeout(6000)  # the imagery of the new view arrives
        cam = page.evaluate("document.querySelector('[data-cam]')?.dataset.cam")
    page.screenshot(path=str(HERE / f"{SAT['id']}.png"))
    ctx.close()
    return {
        "id": SAT["id"],
        "file": f"{SAT['id']}.png",
        "base": base,
        "server": "local, production mode (python -m web, no WALKS_* flag), satellite layer on (Esri World Imagery)",
        "query": SAT["query"],
        "start": {"name": SAT["start"], "lat": START[SAT["start"]][0], "lon": START[SAT["start"]][1]},
        "view": SAT["view"],
        "ui_lang": "ru",
        "sent_at": sent_at.isoformat(timespec="seconds"),
        "stages": [x.get("stage") for x in lines[:-1]],
        "camera": cam,
        "esri_tiles": {str(c): tiles.count(c) for c in sorted(set(tiles))},
        "accepted": bool(answer) and bool(tiles) and all(c == 200 for c in tiles),
        "answer": answer,
        "error": lines[-1].get("error"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args()
    only = {x for x in a.only.split(",") if x}
    if only == {SAT["id"]}:
        with sync_playwright() as pw, LOG.open("a", encoding="utf-8") as log:
            browser = pw.chromium.launch()
            row = satellite(browser, a.base)
            row["attempt"] = 1
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            meta = (row.get("answer") or {}).get("turn", {}).get("meta", {})
            print(SAT["id"], "accepted" if row["accepted"] else "rejected", meta.get("generation"), row["camera"],
                  row["esri_tiles"], row.get("error") or "", flush=True)
            browser.close()
        return
    todo = [s for s in SHOTS if not only or s["id"] in only]
    with sync_playwright() as pw, LOG.open("a", encoding="utf-8") as log:
        browser = pw.chromium.launch()
        first = True
        for spec in todo:
            for attempt in range(TRIES):
                if not first:
                    time.sleep(GAP_S)
                first = False
                try:
                    row = turn(browser, spec)
                except Exception as e:  # noqa: BLE001 - a timeout of the stand is a failed attempt, not the end
                    row = {"id": spec["id"], "query": spec["query"], "accepted": False, "error": repr(e)[:300],
                           "sent_at": datetime.now(ASTANA).isoformat(timespec="seconds")}
                row["attempt"] = attempt + 1
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
                log.flush()
                meta = (row.get("answer") or {}).get("turn", {}).get("meta", {})
                print(spec["id"], "attempt", attempt + 1, "accepted" if row["accepted"] else "rejected",
                      meta.get("generation"), meta.get("model"), row.get("error") or "", flush=True)
                if row["accepted"]:
                    break
        if not only or "city" in only:
            row = city(browser)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            print("city", sorted(row["city_layers"]), flush=True)
        browser.close()


if __name__ == "__main__":
    main()
