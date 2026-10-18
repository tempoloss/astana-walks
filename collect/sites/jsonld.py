"""schema.org JSON-LD extraction with exact evidence snippets.

`parse_json_spans` is a small lenient JSON parser that remembers, for every object, where each `"key": value` pair
sits in the source text, so the evidence snippet of a fact is a verbatim substring of the page (not a re-serialisation).
"""

from __future__ import annotations

import html as htmllib
import json
import re

from collect.sites.hours import spec_to_text, to_osm

SNIPPET_MAX = 300

_SCRIPT = re.compile(
    r"<script\b[^>]*\btype\s*=\s*[\"']?application/ld\+json[\"']?[^>]*>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
_WS = re.compile(r"\s+")

LOCAL_TYPES = frozenset({
    "localbusiness", "restaurant", "cafeorcoffeeshop", "fastfoodrestaurant", "barorpub", "bakery", "store",
    "shoppingcenter", "departmentstore", "grocerystore", "clothingstore", "electronicsstore", "museum",
    "artgallery", "movietheater", "performingartstheater", "theatergroup", "sportsactivitylocation",
    "gymorhealthclub", "sportscomplex", "stadiumorarena", "lodgingbusiness", "hotel", "touristattraction",
    "library", "park", "zoo", "amusementpark", "entertainmentbusiness", "nightclub", "place", "organization",
    "healthandbeautybusiness", "foodestablishment", "bookstore", "childcare", "playground", "citygovernment",
    "governmentoffice", "educationalorganization", "musicvenue", "eventvenue", "aquarium",
})


class SpanDict(dict):
    """A parsed JSON object that knows the source span of each of its `"key": value` pairs."""

    pairs: dict[str, tuple[int, int]]


_SCALAR = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null")


class _Parser:
    def __init__(self, text: str):
        self.s, self.i = text, 0

    def ws(self) -> None:
        while self.i < len(self.s) and (self.s[self.i].isspace() or self.s[self.i] == ","):
            self.i += 1  # commas are skipped leniently (tolerates trailing/double commas)

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c == '"':
            return self.string()
        m = _SCALAR.match(self.s, self.i)
        if not m:
            raise ValueError(f"bad JSON at {self.i}")
        self.i = m.end()
        return json.loads(m[0])

    def string(self) -> str:
        j = self.i + 1
        while self.s[j] != '"':
            j += 2 if self.s[j] == "\\" else 1
        raw = self.s[self.i + 1:j]
        self.i = j + 1
        try:
            return json.loads(f'"{raw}"', strict=False)
        except ValueError:
            return raw

    def obj(self) -> SpanDict:
        d = SpanDict()
        d.pairs = {}
        self.i += 1
        while True:
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
                return d
            start = self.i
            key = self.string()
            self.ws()
            if self.s[self.i] != ":":
                raise ValueError(f"expected ':' at {self.i}")
            self.i += 1
            d[key] = self.value()
            d.pairs[key] = (start, self.i)

    def arr(self) -> list:
        out = []
        self.i += 1
        while True:
            self.ws()
            if self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.value())


def parse_json_spans(text: str):
    p = _Parser(text)
    return p.value()


def _clip(text: str) -> str:
    return _WS.sub(" ", text).strip()[:SNIPPET_MAX]


def jsonld_blocks(page_html: str) -> list[tuple[str, object]]:
    """[(raw script text, parsed value)] for every parsable application/ld+json block."""
    out = []
    for m in _SCRIPT.finditer(page_html):
        raw = re.sub(r"^\s*(?:<!--|//<!\[CDATA\[|/\*<!\[CDATA\[\*/)|(?:-->|//\]\]>|/\*\]\]>\*/)\s*$", "", m[1]).strip()
        try:
            out.append((raw, parse_json_spans(raw)))
        except (ValueError, IndexError):
            continue
    return out


def _types(obj: dict) -> set[str]:
    t = obj.get("@type")
    return {str(x).rsplit("/", 1)[-1].lower() for x in (t if isinstance(t, list) else [t]) if x}


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _text(v) -> str | None:
    if isinstance(v, str) and v.strip():
        return _WS.sub(" ", htmllib.unescape(v)).strip()
    return None


def _address(a) -> str | None:
    if isinstance(a, str):
        return _text(a)
    if isinstance(a, dict):
        parts = [_text(a.get(k)) for k in ("streetAddress", "addressLocality")]
        parts = [p for p in parts if p]
        return ", ".join(parts) or None
    return None


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def branch_from_object(obj: SpanDict, raw: str, url: str) -> dict | None:
    """A branch dict (store.make_branch input) from one LocalBusiness-like object, or None when it has no facts."""
    if not isinstance(obj, SpanDict):
        return None
    evidence: list[dict] = []

    def ev(field: str, key: str, holder: SpanDict = obj) -> None:
        if key in holder.pairs:
            a, b = holder.pairs[key]
            evidence.append({"field": field, "url": url, "snippet": _clip(raw[a:b])})

    name = _text(obj.get("name"))
    addr = _address(obj.get("address"))
    geo = obj.get("geo") if isinstance(obj.get("geo"), dict) else obj
    lat, lon = _num(geo.get("latitude")), _num(geo.get("longitude"))
    phone = _text(_first(obj.get("telephone")))
    hours_raw = None
    if obj.get("openingHoursSpecification"):
        hours_raw = spec_to_text(obj["openingHoursSpecification"])
        key = "openingHoursSpecification"
    elif obj.get("openingHours"):
        oh = obj["openingHours"]
        hours_raw = "; ".join(x.strip() for x in (oh if isinstance(oh, list) else [oh]) if isinstance(x, str))
        key = "openingHours"
    description = _text(obj.get("description"))
    if not name or not (addr or phone or hours_raw or description or (lat is not None and lon is not None)):
        return None
    ev("name", "name")
    if addr:
        ev("address", "address")
    if lat is not None and lon is not None:
        if "geo" in obj.pairs and isinstance(obj.get("geo"), dict):
            ev("geo", "geo")
        else:
            ev("geo", "latitude")
    if phone:
        ev("phone", "telephone")
    if hours_raw:
        ev("opening_hours", key)
    if description:
        ev("description", "description")
    return {
        "name": name, "address": addr,
        "lat": lat if lat is not None and lon is not None else None,
        "lon": lon if lat is not None and lon is not None else None,
        "phone": phone, "opening_hours_raw": hours_raw or None,
        "opening_hours_osm": to_osm(hours_raw) if hours_raw else None,
        "description": description, "url": _text(obj.get("url")),
        "evidence": evidence, "method": "jsonld", "confidence": 0.9,
    }


def extract_jsonld_branches(page_html: str, url: str) -> list[dict]:
    """Every LocalBusiness-like object (address / geo / hours / phone) in the page's JSON-LD blocks."""
    out: list[dict] = []
    for raw, data in jsonld_blocks(page_html):
        for obj in _walk(data):
            if not isinstance(obj, SpanDict):
                continue
            looks_local = bool(_types(obj) & LOCAL_TYPES) or any(
                k in obj for k in ("openingHours", "openingHoursSpecification", "geo"))
            if looks_local and (b := branch_from_object(obj, raw, url)):
                out.append(b)
    return out
