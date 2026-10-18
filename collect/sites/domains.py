"""Registrable-domain helpers (no public-suffix list dependency: only the 2nd-level suffixes seen in KZ/RU/CIS)."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# Social networks, messengers, link-in-bio pages, maps and aggregators: ToS forbid storing their data or need a
# login, so they are never crawled (and a POI whose only "website" is one of them counts as having none).
BLOCKED_DOMAINS = frozenset({
    "instagram.com", "facebook.com", "fb.com", "fb.me", "vk.com", "vk.ru", "ok.ru", "tiktok.com", "twitter.com",
    "x.com", "youtube.com", "youtu.be", "t.me", "telegram.me", "telegram.org", "wa.me", "whatsapp.com",
    "linktr.ee", "taplink.cc", "taplink.ws", "taplink.at", "bio.site", "beacons.ai",
    "2gis.kz", "2gis.ru", "2gis.com", "yandex.ru", "yandex.kz", "yandex.com", "ya.ru", "google.com", "google.kz",
    "goo.gl", "g.page", "maps.app.goo.gl", "tripadvisor.com", "tripadvisor.ru", "zoon.kz", "zoon.ru",
    "foursquare.com", "yelp.com", "booking.com", "restoran.kz", "afisha.yandex.ru", "kino.kz", "flamp.ru",
    "wikipedia.org", "wikidata.org", "wikimedia.org", "openstreetmap.org", "kamiqr.com",
})

_SECOND_LEVEL = {"com", "org", "net", "edu", "gov", "co", "ac", "mil", "biz", "info"}


def normalize_website(raw: str) -> str | None:
    """'WWW.Foo.kz/x?utm=1' -> 'https://www.foo.kz/x' (scheme forced, query/fragment dropped); None if not a URL."""
    raw = (raw or "").strip().split(";")[0].strip()
    if not raw or " " in raw:
        return None
    if "//" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    if not parts.hostname or "." not in parts.hostname:
        return None
    return f"{parts.scheme if parts.scheme in ('http', 'https') else 'https'}://{parts.netloc.lower()}{parts.path}".rstrip("/") or None


def registrable_domain(url_or_host: str) -> str | None:
    """'https://astana.harats.com/a' -> 'harats.com'; 'www.starbucks.com.kz' -> 'starbucks.com.kz'."""
    s = (url_or_host or "").strip().lower()
    if not s:
        return None
    host = urlsplit(s if "//" in s else "//" + s).hostname
    if not host or not re.fullmatch(r"[a-z0-9._-]+", host) or "." not in host:
        return None
    labels = host.strip(".").split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    keep = 3 if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL else 2
    return ".".join(labels[-keep:])


def is_blocked(domain: str | None) -> bool:
    if not domain:
        return True
    return any(domain == b or domain.endswith("." + b) for b in BLOCKED_DOMAINS)


def poi_domains(poi: dict) -> list[str]:
    """Distinct crawlable registrable domains of a POI's `website` ('a;b' lists allowed), blocked ones dropped."""
    out: list[str] = []
    for raw in re.split(r"[;\s]+", poi.get("website") or ""):
        d = registrable_domain(raw) if raw else None
        if d and not is_blocked(d) and d not in out:
            out.append(d)
    return out
