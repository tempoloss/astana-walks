"""AssistantQA3: the memory form end to end in the browser (owner: «Нужен халяль / Без алкоголя — это работает вообще?»).

Turns the master switch on, flips the halal and no-alcohol toggles, checks what the page stores and what it sends with the next
question, once WITHOUT pressing «Сохранить» and once after it.

    uv run --no-project --with playwright python docs/fuzz/AssistantQA3/ui_memory.py --base http://127.0.0.1:8755
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
    out: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, bypass_csp=True, locale="ru-RU")
        page = ctx.new_page()
        sent: list[dict] = []
        page.on("request", lambda r: sent.append({"url": r.url.split("/api/")[-1][:40], "body": (r.post_data or "")[:400]}) if "/api/turn" in r.url or "/api/profile" in r.url else None)
        page.goto(args.base + "/")
        page.wait_for_timeout(1200)
        page.click(".menu-open")
        page.locator("#menu .memory-open").click()
        page.wait_for_timeout(800)
        page.locator("#mem-toggle").check(force=True)
        page.wait_for_timeout(600)
        out["form_open_by_default"] = page.evaluate("() => document.querySelector('.mf-box')?.open ?? null")
        page.screenshot(path=str(SHOTS / f"{port}-m1-on.png"))
        page.evaluate("() => { const d = document.querySelector('.mf-box'); if (d) d.open = true; }")
        page.wait_for_timeout(300)
        # flip halal and no alcohol WITHOUT saving
        rows = page.locator(".mf-toggle input[type=checkbox]")
        names = page.locator(".mf-toggle").all_inner_texts()
        out["toggle_rows"] = names
        for i, nm in enumerate(names):
            if "халяль" in nm.lower() or "алкогол" in nm.lower():
                rows.nth(i).check(force=True)
        page.wait_for_timeout(400)
        page.screenshot(path=str(SHOTS / f"{port}-m2-flipped-unsaved.png"))
        out["profile_posts_after_flip"] = [s for s in sent if s["url"].startswith("profile") and "save" in s["body"]]
        page.evaluate("() => document.getElementById('memory').close()")
        sent.clear()
        ask(page, "хочу выпить")
        out["turn_after_unsaved_flip"] = [s for s in sent if s["url"].startswith("turn")][-1]["body"][:300]
        out["reply_unsaved"] = page.locator("#thread > li:last-child .reply").inner_text()
        # now save
        page.click(".menu-open")
        page.locator("#menu .memory-open").click()
        page.wait_for_timeout(800)
        page.evaluate("() => { const d = document.querySelector('.mf-box'); if (d) d.open = true; }")
        rows = page.locator(".mf-toggle input[type=checkbox]")
        for i, nm in enumerate(page.locator(".mf-toggle").all_inner_texts()):
            if "халяль" in nm.lower() or "алкогол" in nm.lower():
                rows.nth(i).check(force=True)
        page.locator(".mf-actions button[type=submit]").click()
        page.wait_for_timeout(900)
        page.screenshot(path=str(SHOTS / f"{port}-m3-saved.png"))
        page.evaluate("() => document.getElementById('memory').close()")
        sent.clear()
        ask(page, "хочу выпить")
        out["turn_after_save"] = [s for s in sent if s["url"].startswith("turn")][-1]["body"][:300]
        out["reply_saved"] = page.locator("#thread > li:last-child .reply").inner_text()
        out["cards_saved"] = page.locator("#thread > li:last-child .card .c-name").all_inner_texts()
        out["cards_saved_text"] = page.locator("#thread > li:last-child .card").first.inner_text()[:600]
        page.screenshot(path=str(SHOTS / f"{port}-m4-answer.png"))
        browser.close()
    (HERE / f"ui_memory.{port}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
