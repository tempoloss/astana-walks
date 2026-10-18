"""Public Telegram channel afisha without login: `https://t.me/s/<channel>` (server-rendered; robots.txt absent).

Only posts that state the event as structured lines are read: «📅 6 октября, 19:00» and «📍 «Астана Арена»»
(optionally «🎟 Билеты – от 2 000 ₸»). The record keeps the extracted facts, a short title (the first line of the post,
at most 110 characters), the deep link `https://t.me/<channel>/<id>` and the channel name: never the full post or media.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import date

from collect.events import model
from collect.events.model import clean, ev

CHANNELS = ("sxodim_astana",)
TITLE_MAX = 110

_POST = re.compile(r'<div class="tgme_widget_message_wrap.*?(?=<div class="tgme_widget_message_wrap|\Z)', re.DOTALL)
_ID = re.compile(r'data-post="([^"/]+)/(\d+)"')
_TEXT = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL)
_WHEN = re.compile(r"📅\s*([^\n]+)")
_WHERE = re.compile(r"📍\s*([^\n]+)")
_PRICE = re.compile(r"🎟\s*([^\n]+)")


def _plain(fragment: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", fragment)))


def parse(page_html: str, url: str, fetched_at: str, today: date) -> list[dict]:
    events = []
    for post in _POST.findall(page_html):
        ident, body = _ID.search(post), _TEXT.search(post)
        if not (ident and body):
            continue
        text = _plain(body[1])
        wm, pm = _WHEN.search(text), _WHERE.search(text)
        if not (wm and pm):
            continue
        found = model.find_when(wm[1], today)
        if found is None or found[0].is_range or found[0].time is None:
            continue
        first = clean(text.split("\n", 1)[0].replace("📍", "")).strip()
        title = first[:TITLE_MAX].rstrip()
        place = clean(pm[1])
        price = _PRICE.search(text)
        price_text = clean(price[1]) if price else None
        evidence = [*ev("title", url, title, fetched_at), *ev("when", url, wm[0].strip(), fetched_at),
                    *ev("venue", url, pm[0].strip(), fetched_at)]
        if price_text:
            evidence += ev("price", url, price[0].strip(), fetched_at)
        channel, post_id = ident[1], ident[2]
        events.append(model.make_event(
            f"t.me/{channel}", post_id, title=title, kind="event", url=f"https://t.me/{channel}/{post_id}",
            fetched_at=fetched_at, venue_=model.venue(place.strip("«»\" ")), evidence_=evidence,
            start=model.local_dt(found[0].first, found[0].time), price_text=price_text,
            price_from=model.min_price(price_text) if price_text else None))
    return events
