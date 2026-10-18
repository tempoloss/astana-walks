"""AssistantQA3: «Мои места» end to end in the browser (owner: «где можно свои места добавить? их тоже надо потестить»).

Opens «Где вы?», adds «Дом» from the current location, asks «кофе рядом с домом» and «где поесть по пути домой», and records
what the page sent and what came back.

    uv run --no-project --with playwright python docs/fuzz/AssistantQA3/ui_places.py --base http://127.0.0.1:8755
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"


def ask(page, text: str) -> None:
    n = page.locator("#thread > li").count()
    page.fill("#composer-input", text)
    page.keyboard.press("Enter")
    page.wait_for_function(f"document.querySelectorAll('#thread > li').length >= {n + 1} && document.querySelector('#thread > li:last-child .answer') !== null", timeout=20000)
    page.wait_for_timeout(600)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    args = ap.parse_args()
    port = args.base.rsplit(":", 1)[-1]
    SHOTS.mkdir(exist_ok=True)
    out: dict = {"steps": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, bypass_csp=True, locale="ru-RU",
                                  geolocation={"latitude": 51.1283, "longitude": 71.4305}, permissions=["geolocation"])
        page = ctx.new_page()
        sent: list[str] = []
        page.on("request", lambda r: sent.append(r.post_data or "") if "/api/turn" in r.url else None)
        page.goto(args.base + "/")
        page.wait_for_timeout(1200)
        page.click("#where-change")
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / f"{port}-p1-where.png"))
        out["where_text"] = page.evaluate("() => document.getElementById('location').innerText")
        page.locator(".bm-add").click()
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / f"{port}-p2-add.png"))
        out["add_form"] = page.evaluate("() => document.getElementById('bookmark').innerText")
        page.locator("[data-kind=home]").click()
        page.locator("#bm-mine").click()
        page.wait_for_timeout(800)
        out["name_value"] = page.locator("#bm-name").input_value()
        page.screenshot(path=str(SHOTS / f"{port}-p3-filled.png"))
        page.locator("#bm-save").click()
        page.wait_for_timeout(800)
        out["stored"] = page.evaluate("() => localStorage.getItem('anyq.bookmarks')")
        page.screenshot(path=str(SHOTS / f"{port}-p4-saved.png"))
        for sel in ("#location[open] .close", "#bookmark[open] .close"):
            if page.locator(sel).count():
                page.locator(sel).first.click()
        page.evaluate("() => document.querySelectorAll('dialog[open]').forEach((d) => d.close())")
        ask(page, "кофе рядом с домом")
        out["request_bookmarks"] = json.loads(sent[-1]).get("bookmarks")
        out["reply_1"] = page.locator("#thread > li:last-child .reply").inner_text()
        page.screenshot(path=str(SHOTS / f"{port}-p5-answer.png"))
        ask(page, "где поесть по пути домой")
        out["reply_2"] = page.locator("#thread > li:last-child .reply").inner_text()
        # the pin of the bookmark on the map
        out["map_has_bookmark_pin"] = page.evaluate("() => document.querySelectorAll('[class*=bm], [class*=bookmark]').length")
        browser.close()
    (HERE / f"ui_places.{port}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
