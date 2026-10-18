"""Apply Wikivoyage listing facts to the dataset: the sites+gov stages' data/poi.enriched.json -> the same file with
`source: "wikivoyage"` facts, data/poi_enriched_stats.json extended (key `wikivoyage`), a section of
data/coverage_delta.md, the join log data/wikivoyage_joined.json.

Offline (snapshot files only; the fetch is a separate manual step, see `collect/wikivoyage/README.md`). Sources:
the Astana articles of the en/it/he/pl/ru Wikivoyage editions (snapshots in `collect/wikivoyage/snapshots/`,
each with its page metadata). Licence: CC BY-SA 4.0 for every edition (footer "Text is available under the
Creative Commons Attribution-ShareAlike License"); text is third-party content and is never presented as our own.

Fields (join rules: `collect/wikivoyage/join.py`):
  * day-qualified hours -> `opening_hours` only when the record has none (`hours_state = known`); with hours of its
    own, a schedule that differs from them goes to `opening_hours_voyage` (same weekly schedule: nothing is written);
    text without days (`hours_flags` non-empty) -> `hours_unqualified`, never `opening_hours`;
  * eat/drink listings contribute hours and prices only (see/do: hours, prices and descriptions);
  * prices are stored verbatim as `price_text` (currency included), never parsed into numbers; the field is shared
    with other stages: first-party facts win, this stage writes only when it is empty;
  * descriptions go to `description_voyage` with the source URL and edition in `field_sources`; a Wikipedia / OSM
    description, if any, is never overwritten;
  * no new records: a listing that matches nothing is logged, not added.
A dataset that already carries Wikivoyage facts is re-applied: `strip` removes exactly the fields whose
`field_sources` name this stage (and the `wikivoyage` label), then the listings are joined again, so a change of the
join rules is one command (`uv run python -m collect.wikivoyage.apply`).
The finished dataset is re-checked (`verify.check_dataset` + `sites.verify.check_dataset`); a failure aborts before
anything is written.

Usage (repo root): uv run python -m collect.wikivoyage.apply [--poi data/poi.enriched.json] [--out ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.merge import stats_for
from collect.sites.hours import analyze, same_schedule
from collect.sites.verify import check_dataset as sites_check_dataset
from collect.wikivoyage import verify
from collect.wikivoyage.editions import EDITIONS, Article, Listing, fields_of_interest, parse_article
from collect.wikivoyage import join
from collect.wikivoyage.join import Joiner

ROOT = Path(__file__).resolve().parents[2]
POI_PATH = ROOT / "data" / "poi.enriched.json"
STATS_PATH = ROOT / "data" / "poi_enriched_stats.json"
DELTA_PATH = ROOT / "data" / "coverage_delta.md"
JOINED_PATH = ROOT / "data" / "wikivoyage_joined.json"
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
DELTA_HEADING = "## Wikivoyage (hours, prices, descriptions of sights)"
SOURCE = "wikivoyage"
LICENSE = "CC BY-SA 4.0"

_TITLE = {ed.lang: ed.title for ed in EDITIONS}


def article_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikivoyage.org/wiki/{quote(title.replace(' ', '_'), safe='')}"


def already_applied(pois: list[dict]) -> bool:
    return any(SOURCE in (p.get("sources") or []) for p in pois)


def strip(pois: list[dict]) -> list[dict]:
    """The dataset without the facts this stage wrote (the fields whose `field_sources` name `wikivoyage`)."""
    out = []
    for p in pois:
        p = dict(p)
        fsrc = {k: v for k, v in (p.get("field_sources") or {}).items()}
        mine = [k for k, v in fsrc.items() if v.get("source") == SOURCE]
        for field in mine:
            del fsrc[field]
            if field == "opening_hours":
                p["opening_hours"], p["hours_state"] = None, "unknown"
            elif field == "hours_unqualified":
                p["hours_unqualified"], p["hours_unqualified_flags"] = None, []
            else:
                p.pop(field, None)
        if "field_sources" in p:
            p["field_sources"] = fsrc
        p["sources"] = [s for s in p["sources"] if s != SOURCE]
        out.append(p)
    return out


def load_articles() -> tuple[list[Article], list[str]]:
    """Parsed snapshots; the second list holds problems (missing/malformed snapshot files)."""
    articles, problems = [], []
    for ed in EDITIONS:
        text_path = SNAPSHOTS / f"{ed.lang}.wikitext"
        meta_path = SNAPSHOTS / f"{ed.lang}.meta.json"
        if not text_path.exists() or not meta_path.exists():
            problems.append(f"snapshot of {ed.lang} missing: {text_path.name} / {meta_path.name}")
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        text = text_path.read_text(encoding="utf-8")
        article = parse_article(ed.lang, text, meta["title"], meta["pageid"], meta["snapshot_date"])
        if not article.listings:
            problems.append(f"snapshot of {ed.lang} parses to zero listings")
        articles.append(article)
    return articles, problems


def fields_source(l: Listing, snapshot_date: str) -> dict:
    return {"source": SOURCE, "license": LICENSE, "snapshot_date": snapshot_date, "lang": l.edition,
            "url": article_url(l.edition, _TITLE[l.edition]), "listing": l.name}


def apply_listing(p: dict, l: Listing, fields: tuple[str, ...], snapshot_date: str) -> list[str]:
    """Add the listing's fields to POI `p` (in place); never over an existing value. Returns the touched fields."""
    src = fields_source(l, snapshot_date)
    fsrc = p.setdefault("field_sources", {})
    touched: list[str] = []
    if "hours" in fields:
        oh, flags = analyze(l.hours)
        if oh:
            if not p.get("opening_hours"):
                p["opening_hours"], p["hours_state"] = oh, "known"
                fsrc["opening_hours"] = dict(src)
                touched.append("opening_hours")
            elif not same_schedule(p["opening_hours"], oh):
                p["opening_hours_voyage"] = oh
                fsrc["opening_hours_voyage"] = dict(src)
                touched.append("opening_hours_voyage")
        elif flags and not p.get("opening_hours"):
            if not p.get("hours_unqualified"):
                p["hours_unqualified"] = l.hours
                p["hours_unqualified_flags"] = flags
                fsrc["hours_unqualified"] = {**src, "hours_flags": flags}
                touched.append("hours_unqualified")
    if "price" in fields and not p.get("price_text"):
        p["price_text"] = l.price
        fsrc["price_text"] = dict(src)
        touched.append("price_text")
    if "description" in fields and p.get("description_source", "derived") not in ("osm", "wikipedia"):
        if not p.get("description_voyage"):
            p["description_voyage"] = l.description
            fsrc["description_voyage"] = dict(src)
            touched.append("description_voyage")
    if touched and SOURCE not in p.setdefault("sources", []):
        p["sources"].append(SOURCE)
    return touched


def build(pois: list[dict]) -> tuple[list[dict], dict]:
    articles, _ = load_articles()
    joiner = Joiner(pois)
    stats: Counter = Counter()
    pairs_log: list[dict] = []
    unmatched: list[dict] = []
    dataset = [dict(p) for p in pois]
    by_id = {p["id"]: p for p in dataset}
    for art in articles:
        stats[f"listings_{art.edition}"] = len(art.listings)
        for l in art.listings:
            fields = fields_of_interest(l)
            if not fields:
                stats["listings_without_fields"] += 1
                continue
            pair = joiner.best(l)
            if pair is None:
                unmatched.append({"edition": l.edition, "name": l.name, "section": l.section,
                                  "wikidata": l.wikidata, "lat": l.lat, "lon": l.lon, "fields": list(fields)})
                stats["unmatched"] += 1
                continue
            if pair.rule != "wdid":
                pairs_log.append({"edition": l.edition, "listing": l.name, "listing_alt": l.alt,
                                  "wikidata": l.wikidata, "section": l.section, "poi": pair.poi_id,
                                  "poi_name": by_id[pair.poi_id]["name"],
                                  "poi_category": by_id[pair.poi_id]["category"],
                                  "rule": pair.rule, "distance_m": pair.distance_m, "name_score": pair.score,
                                  "fields": list(fields)})
            touched = apply_listing(by_id[pair.poi_id], l, fields, art.snapshot_date)
            stats[f"filled_{pair.rule}"] += 1
            for f in touched:
                stats[f"filled_{f}"] += 1
    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "editions": {a.edition: {"title": a.title, "pageid": a.pageid, "snapshot_date": a.snapshot_date,
                                 "listings": len(a.listings)} for a in articles},
        "rules": join.RULES,
    }
    return dataset, {"stats": dict(stats), "meta": meta, "radius_pairs": pairs_log, "unmatched": unmatched}


# ---- shipped stats / delta -------------------------------------------------------------------------


def shipped_stats(prev: dict, dataset: list[dict], wv: dict) -> dict:
    return {**prev, "after": stats_for(dataset),
            "per_source_counts": {**prev.get("per_source_counts", {}),
                                  "with_wikivoyage": sum(1 for p in dataset if SOURCE in p["sources"])},
            "wikivoyage": wv}


def render_delta(wv: dict, s: dict) -> str:
    st = wv["stats"]
    lines = [DELTA_HEADING, "",
             f"Generated {wv['meta']['generated_at'][:10]} by `collect.wikivoyage.apply` (snapshots: "
             "`collect/wikivoyage/snapshots/`, join log: `data/wikivoyage_joined.json`). "
             "Source: the Astana articles of the en/it/he/pl/ru Wikivoyage (CC BY-SA 4.0).", "",
             f"- Listings parsed: **{sum(st[f'listings_{e}'] for e in ('en', 'it', 'he', 'pl', 'ru'))}** "
             f"(en {st.get('listings_en', 0)}, it {st.get('listings_it', 0)}, he {st.get('listings_he', 0)}, "
             f"pl {st.get('listings_pl', 0)}, ru {st.get('listings_ru', 0)}); "
             f"joined by wdid **{st.get('filled_wdid', 0)}**, by name **{st.get('filled_name', 0)}**, "
             f"by coords+name **{st.get('filled_coords+name', 0)}**; unmatched **{st.get('unmatched', 0)}**.",
             f"- Fields filled: hours **{st.get('filled_opening_hours', 0)}** (+ hours-voyage "
             f"{st.get('filled_opening_hours_voyage', 0)} when the record already had OSM/site hours; "
             f"unqualified {st.get('filled_hours_unqualified', 0)}), prices **{st.get('filled_price_text', 0)}**, "
             f"descriptions **{st.get('filled_description_voyage', 0)}**; POIs "
             f"{s['poi_total_before']} -> {s['poi_total_after']} (no new records: a listing that matches nothing is "
             "logged, not added).", "",
             "Radius pairs (rule `coords+name`/`name`) are listed in `data/wikivoyage_joined.json` for a human check; "
             "the false-pair rule is in `collect/wikivoyage/join.py`.", ""]
    return "\n".join(lines)


def _replace_section(path: Path, begin: str, end: str | None, block: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    head, sep, tail = text.partition(begin)
    if sep:
        if end:
            tail = tail.partition(end)[2]
        else:
            nxt = re.search(r"^## ", tail, re.MULTILINE)
            tail = tail[nxt.start():] if nxt else ""
    path.write_text(head.rstrip("\n") + ("\n\n" if head.strip() else "") + block.rstrip("\n") + "\n"
                    + ("\n" + tail.lstrip("\n") if tail.strip() else ""), encoding="utf-8")




def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poi", default=str(POI_PATH))
    ap.add_argument("--out", default=str(POI_PATH))
    ap.add_argument("--stats", default=str(STATS_PATH))
    ap.add_argument("--delta", default=str(DELTA_PATH))
    ap.add_argument("--joined", default=str(JOINED_PATH))
    args = ap.parse_args(argv)
    pois = json.loads(Path(args.poi).read_text(encoding="utf-8"))
    if already_applied(pois):
        pois = strip(pois)
    articles, problems = load_articles()
    if problems:
        for line in problems:
            print(f"[wikivoyage.apply] {line}", file=sys.stderr)
        return 1
    dataset, wv = build(pois)
    wv["stats"]["poi_total_before"] = len(pois)
    wv["stats"]["poi_total_after"] = len(dataset)
    checks = verify.check_dataset(dataset) + sites_check_dataset(dataset)
    if checks:
        for line in checks:
            print(f"[wikivoyage.apply] {line}", file=sys.stderr)
        print(f"[wikivoyage.apply] {len(checks)} problem(s); nothing written", file=sys.stderr)
        return 1
    stats_path = Path(args.stats)
    prev = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    ship = shipped_stats(prev, dataset, wv) if prev else {"wikivoyage": wv}
    Path(args.out).write_text(json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    Path(args.joined).write_text(json.dumps(wv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    stats_path.write_text(json.dumps(ship, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _replace_section(Path(args.delta), DELTA_HEADING, None, render_delta(wv, wv["stats"]))
    st = wv["stats"]
    print(f"[wikivoyage.apply] listings {sum(st[f'listings_{e}'] for e in ('en', 'it', 'he', 'pl', 'ru'))}; "
          f"joined wdid {st.get('filled_wdid', 0)} / name {st.get('filled_name', 0)} / coords+name "
          f"{st.get('filled_coords+name', 0)}, unmatched {st.get('unmatched', 0)}; "
          f"hours {st.get('filled_opening_hours', 0)}+voyage {st.get('filled_opening_hours_voyage', 0)}"
          f"+unqualified {st.get('filled_hours_unqualified', 0)}, prices {st.get('filled_price_text', 0)}, "
          f"descriptions {st.get('filled_description_voyage', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
