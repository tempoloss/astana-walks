"""AssistantQA3 browser probe at 390x844 (phone) and 1280x800: what the person actually sees for the answers the matrix
flagged. Writes screenshots to shots/ and one JSON of measurements to ui_qa.<port>.json.

    uv run --no-project --with playwright python docs/fuzz/AssistantQA3/ui_qa.py --base http://127.0.0.1:8755
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"

FONTS = """() => {
  const q = (sel) => [...document.querySelectorAll(sel)].filter((e) => e.offsetParent !== null).slice(0, 6).map((e) => {
    const c = getComputedStyle(e);
    return {sel, text: (e.textContent || '').trim().slice(0, 40), size: c.fontSize, weight: c.fontWeight, family: c.fontFamily.slice(0, 40),
            transform: c.textTransform, spacing: c.letterSpacing, lh: c.lineHeight};
  });
  return {
    lead: q('.thread .msg-a, .thread .answer, .thread .lead, .thread li p'),
    card: q('.card h3, .card .name, .card-title'),
    all_text_sizes: [...new Set([...document.querySelectorAll('body *')].filter((e) => e.offsetParent !== null && e.childElementCount === 0 && (e.textContent || '').trim())
      .map((e) => getComputedStyle(e).fontSize))].sort((a, b) => parseFloat(a) - parseFloat(b)),
    mono: [...document.querySelectorAll('body *')].filter((e) => e.offsetParent !== null && /mono|courier|consolas/i.test(getComputedStyle(e).fontFamily)).length,
    upper: [...document.querySelectorAll('body *')].filter((e) => e.offsetParent !== null && getComputedStyle(e).textTransform === 'uppercase' && (e.textContent || '').trim()).length,
    striped: [...document.querySelectorAll('body *')].filter((e) => e.offsetParent !== null && /repeating-linear-gradient|linear-gradient\\(.*(45|135)deg/.test(getComputedStyle(e).backgroundImage)).map((e) => (typeof e.className === 'string' ? e.className : e.tagName)).slice(0, 10),
    overflowX: document.scrollingElement.scrollWidth > innerWidth + 1,
  };
}"""


def ask(page, text: str, wait_ms: int = 9000) -> None:
    n = page.locator("#thread > li").count()
    page.fill("#composer-input", text)
    page.keyboard.press("Enter")
    page.wait_for_function(f"document.querySelectorAll('#thread > li').length >= {n + 1} && document.querySelector('#thread > li:last-child .answer') !== null", timeout=wait_ms)
    page.wait_for_timeout(700)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    args = ap.parse_args()
    SHOTS.mkdir(exist_ok=True)
    port = args.base.rsplit(":", 1)[-1]
    out: dict = {"base": args.base, "console": [], "steps": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, bypass_csp=True,
                                  locale="ru-RU", geolocation={"latitude": 51.1283, "longitude": 71.4305}, permissions=["geolocation"])
        page = ctx.new_page()
        page.on("console", lambda m: out["console"].append(f"{m.type}: {m.text[:200]}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: out["console"].append(f"pageerror: {str(e)[:200]}"))
        page.goto(args.base + "/")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SHOTS / f"{port}-01-start.png"))
        out["steps"]["start_fonts"] = page.evaluate(FONTS)
        # 1. the owner's two messages at night
        ask(page, "Где прогуляться можно щас?")
        page.screenshot(path=str(SHOTS / f"{port}-02-walk-answer.png"))
        out["steps"]["walk_fonts"] = page.evaluate(FONTS)
        ask(page, "Я именно погулять хочу")
        page.screenshot(path=str(SHOTS / f"{port}-03-walk-insist.png"))
        # 2. details of the first card
        card = page.locator("#thread .card").first
        if card.count():
            card.click()
            page.wait_for_timeout(800)
            page.screenshot(path=str(SHOTS / f"{port}-04-details.png"))
            out["steps"]["details_fonts"] = page.evaluate(FONTS)
            page.keyboard.press("Escape")
        # 3. unknown hours: the badge and the strip
        out["steps"]["unknown_hours_nodes"] = page.evaluate(
            "() => [...document.querySelectorAll('[class*=unknown], [class*=hours]')].filter(e => e.offsetParent !== null).slice(0, 8).map(e => ({cls: e.className, text: (e.textContent||'').trim().slice(0, 60), bg: getComputedStyle(e).backgroundImage.slice(0, 90)}))")
        # 4. the XSS line and markup in a message
        ask(page, "<script>alert(1)</script><b>жирный</b> кофе")
        page.screenshot(path=str(SHOTS / f"{port}-05-markup.png"))
        out["steps"]["markup_is_text"] = page.evaluate(
            "() => ({scriptTags: document.querySelectorAll('#thread script').length, boldTags: [...document.querySelectorAll('#thread b')].length})")
        # 5. a long unbroken message
        ask(page, "а" * 200)
        page.screenshot(path=str(SHOTS / f"{port}-06-long-word.png"))
        out["steps"]["long_word_overflowX"] = page.evaluate("() => document.scrollingElement.scrollWidth > innerWidth + 1")
        out["steps"]["maxlength_paste"] = page.evaluate(
            "() => { const t = document.getElementById('composer-input'); t.value = 'я'.repeat(900); return {value: t.value.length, maxlength: t.maxLength}; }")
        # 6. «Где вы?»
        page.click("#where-change")
        page.wait_for_timeout(600)
        page.screenshot(path=str(SHOTS / f"{port}-07-where.png"))
        out["steps"]["where_dialog"] = page.evaluate(
            "() => ({marks: document.getElementById('loc-marks').innerText.slice(0, 300), list: document.getElementById('loc-list').innerText.slice(0, 400), actions: document.querySelector('.loc-actions').innerText})")
        page.keyboard.press("Escape")
        # 7. memory panel
        page.click(".memory-open >> visible=true", timeout=3000) if page.locator(".memory-open").first.is_visible() else page.click(".menu-open")
        page.wait_for_timeout(300)
        if not page.locator("#memory[open]").count():
            page.locator("#menu .memory-open").click()
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SHOTS / f"{port}-08-memory.png"))
        out["steps"]["memory_text"] = page.evaluate("() => document.getElementById('memory-root').innerText.slice(0, 1800)")
        out["steps"]["memory_fonts"] = page.evaluate(FONTS)
        browser.close()
    (HERE / f"ui_qa.{port}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "steps"}, ensure_ascii=False, indent=1))
    print("steps:", list(out["steps"]))


if __name__ == "__main__":
    sys.exit(main())
