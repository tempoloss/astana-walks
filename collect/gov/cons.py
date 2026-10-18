"""ЦОН branches of Astana from gov4c.kz (НАО «Правительство для граждан»): `/ru/contacts/speccony/287/` and the kk / en
versions of the same page. One table, 14 rows: №, name, schedule (ru / kk / en repeated in one cell, separated by «-»),
address. The page has no per-branch phone (the contact centre 1414 is national, not a branch fact: not stored).

Hours: a day-qualified schedule («С понедельника по пятницу с 09:00 до 20:00 суббота с 09:00 до 13:00») becomes
`Hours.opening_hours` (scope `venue`). The specialised departments print two schedules in one cell («Прием …, Выдача
…»): the reception schedule is the one a visitor needs and goes into `opening_hours`, the issuing schedule is kept in
`Hours.note` with the flag `two_schedules`. Text that cannot be read unambiguously keeps `opening_hours = None`.

Usage (repo root): uv run python -m collect.gov.cons [--out data/gov/facts/gov4c.kz.json]
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.gov.addr import parse_address
from collect.gov.model import Evidence, GovRecord, Hours
from collect.sites.fetch import Page, SiteFetcher
from collect.sites.hours import analyze, validate_osm
from collect.sites.store import norm_ws, now_iso

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "data" / "gov" / "facts" / "gov4c.kz.json"
BASE = "https://gov4c.kz"
ASTANA_ID = 287  # /contacts/speccony/<id>/: 287 = «Филиал по городу Астана» (287..306 = the 21 regions)
PAGES = {"ru": f"{BASE}/ru/contacts/speccony/{ASTANA_ID}/", "kk": f"{BASE}/contacts/speccony/{ASTANA_ID}/",
         "en": f"{BASE}/en/contacts/speccony/{ASTANA_ID}/"}
SOURCE_HOST = "gov4c.kz"


class _Table(HTMLParser):
    """Rows of every <table>: [[cell lines]] where a cell is split on <br> into its text lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[list[str]]] = []
        self._row: list[list[str]] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = [""]
        elif tag == "br" and self._cell is not None:
            self._cell.append("")

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append([norm_ws(x) for x in self._cell if norm_ws(x)])
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell[-1] += data


def parse_rows(page_html: str) -> dict[int, dict]:
    """{row number: {"name", "hours_lines", "address"}} of the branch table (header and title rows skipped)."""
    p = _Table()
    p.feed(page_html)
    out: dict[int, dict] = {}
    for row in p.rows:
        if len(row) != 4 or not row[0] or not row[0][0].isdigit():
            continue
        out[int(row[0][0])] = {"name": " ".join(row[1]), "hours_lines": row[2], "address": " ".join(row[3])}
    return out


def hours_segments(lines: list[str]) -> list[str]:
    """The cell's lines split on the «-» separator lines into the per-language texts: [ru, kk, en]."""
    segs, cur = [], []
    for ln in lines:
        if ln == "-":
            segs.append(" ".join(cur))
            cur = []
        else:
            cur.append(ln)
    segs.append(" ".join(cur))
    return [s for s in segs if s]


_PIECE = re.compile(r"(при[её]м|выдача)", re.IGNORECASE)
_TIMES = re.compile(r"(\d{1,2}):(\d{2})\D{1,12}?(\d{1,2}):(\d{2})")


def _fix_times(text: str) -> str:
    return re.sub(r"(\d):\s+(\d{2})", r"\1:\2", text)  # «13:\n00» typo of the register


def _split_pieces(ru: str) -> list[tuple[str, str]]:
    parts = _PIECE.split(ru)
    return [(parts[i].casefold().replace("ё", "е"), parts[i + 1].strip(" ,;.")) for i in range(1, len(parts) - 1, 2)]


def parse_cson_hours(ru: str) -> Hours:
    """Hours of one ЦОН cell from its ru text (see the module docstring for the two-schedule case)."""
    text = _fix_times(ru)
    osm, flags = analyze(text)
    if osm:
        return Hours(raw=ru, scope="venue", opening_hours=osm, flags=list(flags))
    pieces = _split_pieces(text)
    if not pieces:
        return Hours(raw=ru, scope="venue", opening_hours=None, flags=list(flags) or ["unparsed"])
    reception: list[str] = []
    issue: list[str] = []
    prev_days: str | None = None
    for kind, body in pieces:
        value, _fl = analyze(body)
        if value is None:
            m = _TIMES.search(body)
            if m is None or prev_days is None:
                return Hours(raw=ru, scope="venue", opening_hours=None, flags=["unparsed"])
            value = f"{prev_days} {int(m[1]):02d}:{m[2]}-{int(m[3]):02d}:{m[4]}"  # «Выдача с 09:00 до 13:00»: the days of the piece before
            if not validate_osm(value):
                return Hours(raw=ru, scope="venue", opening_hours=None, flags=["unparsed"])
        prev_days = value.split(" ")[0]
        (reception if kind == "прием" else issue).append(value)
    if not reception:
        return Hours(raw=ru, scope="venue", opening_hours=None, flags=["unparsed"])
    note = ("Выдача: " + "; ".join(issue)) if issue else None
    return Hours(raw=ru, scope="venue", opening_hours="; ".join(reception), note=note, flags=["two_schedules"])


def record_id(name: str, address: str) -> str:
    return "gov/cson/" + hashlib.sha1(f"cson|{norm_ws(name)}|{norm_ws(address)}".encode()).hexdigest()[:10]


def _ev(field: str, page: Page, snippet: str, lang: str) -> Evidence:
    return Evidence(field, page.url, snippet, page.fetched_at, lang)


def build_records(pages: dict[str, Page]) -> list[GovRecord]:
    """Records from the fetched pages ({lang: Page}); the ru page defines the rows, kk/en add names and addresses."""
    ru_rows = parse_rows(pages["ru"].text)
    other = {lang: parse_rows(pages[lang].text) for lang in ("kk", "en") if lang in pages and pages[lang].ok}
    records: list[GovRecord] = []
    for num, row in sorted(ru_rows.items()):
        ru_page = pages["ru"]
        name, addr_raw = row["name"], row["address"]
        evidence = [_ev("name", ru_page, name, "ru"), _ev("address", ru_page, addr_raw, "ru")]
        names = {"ru": name}
        by_lang = {"ru": addr_raw}
        for lang, rows in other.items():
            o = rows.get(num)
            if o:
                names[lang] = o["name"]
                by_lang[lang] = o["address"]
                evidence += [_ev("name", pages[lang], o["name"], lang), _ev("address", pages[lang], o["address"], lang)]
        segs = hours_segments(row["hours_lines"])
        hours = None
        if segs:
            hours = parse_cson_hours(segs[0])
            evidence.append(_ev("opening_hours", ru_page, segs[0], "ru"))
        a = parse_address(addr_raw)
        records.append(GovRecord(
            id=record_id(name, addr_raw), kind="cson", source=SOURCE_HOST, url=ru_page.url, name=name, names=names,
            address={"raw": a.raw, "street": a.street, "house": a.house, "key": a.key, "by_lang": by_lang},
            hours=hours, evidence=evidence, extra={"row": num, "branch": "Филиал по городу Астана"},
            fetched_at=ru_page.fetched_at))
    return records


def crawl(fetcher: SiteFetcher | None = None) -> dict:
    f = fetcher or SiteFetcher()
    pages = {lang: f.fetch(url) for lang, url in PAGES.items()}
    if not pages["ru"].ok:
        raise RuntimeError(f"{PAGES['ru']}: HTTP {pages['ru'].status} {pages['ru'].error}")
    records = build_records(pages)
    return {
        "source": SOURCE_HOST, "fetched_at": now_iso(), "pages": {k: v.url for k, v in pages.items()},
        "page_status": {k: v.status for k, v in pages.items()}, "robots": f.robots_status(BASE + "/"),
        "records": [r.to_dict() for r in records],
        "notes": "No per-branch phone on the page; no coordinates (join by address / OSM, collect.gov.geocode).",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    payload = crawl()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = len(payload["records"])
    with_hours = sum(1 for r in payload["records"] if (r["hours"] or {}).get("opening_hours"))
    print(f"[gov.cons] {n} branches, {with_hours} with day-qualified hours -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
