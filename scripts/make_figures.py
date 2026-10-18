"""Generate docs/figures.md: every number on the data slides, read from the stats files.

Stdlib only. Run from anywhere:  python scripts/make_figures.py

Inputs (all under data/, written by `python -m collect.build`):
  poi_stats.json           frozen baseline data/poi.json (OSM only), the "before" side
  poi.osm_stats.json       re-collected OSM snapshot (data/poi.osm.json), the OSM part of the shipped base
  poi_enriched_stats.json  shipped data/poi.enriched.json, the "after" side
  coverage_delta.md        table rows, read by their label (cross-check only)

Exit status: 1 if an input is missing or an internal identity fails (sums, funnel). Cross-file
differences are not failures: they are printed in section 7 with both values and the canonical source.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "docs" / "figures.md"

CATEGORY_ORDER = [
    "cafe", "restaurant", "fast_food", "bar_nightlife", "museum_gallery", "attraction_landmark",
    "viewpoint", "park_garden", "kids_playground", "entertainment", "mall", "culture_theatre_cinema",
    "coworking_library", "sport", "transit_station", "other",
]

BASE_FILE = "data/poi_stats.json"
SNAP_FILE = "data/poi.osm_stats.json"
SHIP_FILE = "data/poi_enriched_stats.json"
DELTA_FILE = "data/coverage_delta.md"

failures: list[str] = []


def check_identity(label: str, ok: bool, detail: str) -> None:
    """Internal arithmetic that must hold. A failure stops the run."""
    if not ok:
        failures.append(f"{label}: {detail}")


def fmt(n: float | int | None) -> str:
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:.1f}"
    return f"{int(n):,}".replace(",", " ")


def pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def load_json(rel: str) -> dict:
    path = ROOT / rel
    if not path.is_file():
        sys.exit(f"missing input: {rel}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_delta(rel: str) -> dict[str, list[str]]:
    """coverage_delta.md table rows of the merge stage: label -> list of cell strings (without the label). The section
    of the official-site stage (its own «cafe» row counts new POIs, not all of them) is not read."""
    path = ROOT / rel
    if not path.is_file():
        sys.exit(f"missing input: {rel}")
    rows: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Official-site facts"):
            break
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2:
            rows[cells[0].replace("**", "")] = cells[1:]
    return rows


def delta_value(rows: dict[str, list[str]], prefix: str, col: int = 0) -> str | None:
    for label, cells in rows.items():
        if label.startswith(prefix):
            return cells[col]
    return None


base = load_json(BASE_FILE)
snap = load_json(SNAP_FILE)
ship = load_json(SHIP_FILE)
delta = parse_delta(DELTA_FILE)

b_cat = base["count_per_category"]
s_cat = snap["count_per_category"]
a_cat = ship["after"]["count_per_category"]
b_total, s_total, a_total = base["total"], snap["total"], ship["after"]["total"]
# what `collect.dedupe` merged away: `records_merged_away` records were absorbed into another card; each left the
# `per_source_counts` bucket the collecting stages counted it in (`absorbed_from_bucket`; a record that carried both
# OSM and Overture leaves two) and its origin (`absorbed_by_origin`). The buckets themselves are not recounted.
dd = ship.get("duplicates", {})
merged = dd.get("records_merged_away", 0)
mb = defaultdict(int, dd.get("absorbed_from_bucket", {}))
absorbed = defaultdict(int, dd.get("absorbed_by_origin", {}))
kept = defaultdict(int, dd.get("kept_by_origin", {}))
before = defaultdict(int, dd.get("records_before_by_origin", {}))
taken = defaultdict(int, dd.get("overture_pins_taken_over", {}))
paired = taken.get("osm", 0)  # absorbed Overture pins an OSM-origin card carries on now
m_cat = dd.get("by_category", {})
ps = ship["per_source_counts"]
ov = ship["overture"]
osites = ship["official_sites"]
site_new_by_cat = dict(osites["new_pois_by_category"])
for _cat, _n in ship.get("state_registry", {}).get("new_pois_by_category", {}).items():
    site_new_by_cat[_cat] = site_new_by_cat.get(_cat, 0) + _n

# ---- internal identities (must hold) ----
check_identity("baseline categories sum", sum(b_cat.values()) == b_total, f"{sum(b_cat.values())} != {b_total}")
check_identity("snapshot categories sum", sum(s_cat.values()) == s_total, f"{sum(s_cat.values())} != {s_total}")
check_identity("shipped categories sum", sum(a_cat.values()) == a_total, f"{sum(a_cat.values())} != {a_total}")
wd_only = ps["wikidata_only"]
site_only = ps["official_site_only"]
reg_only = ps.get("state_registry_only", 0)
check_identity("shipped = the per-source buckets of the collecting stages − what the merge took from each",
               (ps["osm_only"] - mb["osm_only"]) + (ps["osm_and_overture"] - mb["osm_and_overture"])
               + (ps["overture_only"] - mb["overture_only"]) + (wd_only - mb["wikidata_only"])
               + (site_only - mb["official_site_only"]) + (reg_only - mb["state_registry_only"]) == a_total,
               f"({ps['osm_only']}-{mb['osm_only']})+({ps['osm_and_overture']}-{mb['osm_and_overture']})"
               f"+({ps['overture_only']}-{mb['overture_only']})+({wd_only}-{mb['wikidata_only']})"
               f"+({site_only}-{mb['official_site_only']})+({reg_only}-{mb['state_registry_only']}) != {a_total}")
check_identity("records merged away = the buckets that lost them = the origins that lost them",
               merged == sum(mb.values()) == sum(absorbed.values()),
               f"{merged} != {sum(mb.values())} != {sum(absorbed.values())}")
check_identity("snapshot = osm_only + osm_and_overture",
               ps["osm_only"] + ps["osm_and_overture"] == s_total,
               f"{ps['osm_only']}+{ps['osm_and_overture']} != {s_total}")
check_identity("records by origin: kept + absorbed = before",
               all(kept[k] + absorbed[k] == before[k] for k in ("osm", "overture", "wikidata")),
               f"{ {k: (kept[k], absorbed[k], before[k]) for k in ('osm', 'overture', 'wikidata')} }")
check_identity("wikidata methods sum", sum(ship["wikidata_matches_by_method"].values()) == ps["with_wikidata"],
               f"{sum(ship['wikidata_matches_by_method'].values())} != {ps['with_wikidata']}")
check_identity("overture total - dropped_by_cutoff = passing_cutoff",
               ov["total"] - ov["dropped_by_cutoff"] == ov["passing_cutoff"],
               f"{ov['total']}-{ov['dropped_by_cutoff']} != {ov['passing_cutoff']}")
check_identity("overture_only_added = per_source overture_only",
               ov["overture_only_added"] == ps["overture_only"],
               f"{ov['overture_only_added']} != {ps['overture_only']}")
check_identity("description sources sum to shipped total",
               sum(ship["description_source_counts"].values()) == a_total,
               f"{sum(ship['description_source_counts'].values())} != {a_total}")
check_identity("shipped % real + % derived = 100",
               abs(ship["after"]["pct_real_description"] + ship["after"]["pct_derived_description"] - 100) < 0.11,
               f"{ship['after']['pct_real_description']} + {ship['after']['pct_derived_description']}")
check_identity("net delta = overture_only_added + wikidata_only + official_site_only + state_registry_only"
               " + (snapshot − baseline) − records merged away",
               a_total - b_total == ov["overture_only_added"] + wd_only + site_only + reg_only + (s_total - b_total)
               - merged,
               f"{a_total - b_total} != {ov['overture_only_added']} + {wd_only} + {site_only} + {reg_only}"
               f" + ({s_total - b_total}) - {merged}")
check_identity("osm_and_overture (the buckets the stages counted) = 1:1 + chain merged_into_osm",
               ps["osm_and_overture"] == ship["osm_overture_matched"] + ov["chain_duplicates"]["merged_into_osm"],
               f"{ps['osm_and_overture']} != {ship['osm_overture_matched']} + "
               f"{ov['chain_duplicates']['merged_into_osm']}")
check_identity("Overture pins taken over belong to the merged-away records", sum(taken.values()) <= merged,
               f"{sum(taken.values())} > {merged}")

# ---- section 7 inputs: cross-file comparisons (reported, not failing) ----
checks: list[list[str]] = []


def add_check(name: str, a_label: str, a: str, b_label: str, b: str, canon: str) -> None:
    status = "OK" if a == b else "РАСХОЖДЕНИЕ"
    checks.append([name, f"{a} ({a_label})", f"{b} ({b_label})", status, canon])


add_check("OSM-снимок: total", SNAP_FILE, fmt(s_total), DELTA_FILE + " «OSM POI in the re-collected snapshot»",
          fmt(int(delta_value(delta, "OSM POI in the re-collected snapshot") or -1)), "poi.osm_stats.json")
add_check("Overture-only в категориях", SHIP_FILE + " per_source_counts", fmt(ps["overture_only"]),
          DELTA_FILE + " «Overture-only, mapped category»",
          fmt(int(delta_value(delta, "Overture-only, mapped category") or -1)), "poi_enriched_stats.json")
add_check("Overture-only: overture.overture_only_added", SHIP_FILE, fmt(ov["overture_only_added"]),
          "per_source_counts.overture_only", fmt(ps["overture_only"]), "poi_enriched_stats.json")
add_check("Wikidata-совпадения", SHIP_FILE + " with_wikidata", fmt(ps["with_wikidata"]),
          DELTA_FILE + " «Wikidata matched POI»", fmt(int(delta_value(delta, "Wikidata matched POI") or -1)),
          "poi_enriched_stats.json")
add_check("OSM ∩ Overture 1:1", SHIP_FILE + " osm_overture_matched", fmt(ship["osm_overture_matched"]),
          DELTA_FILE + " «OSM ∩ Overture matched»", fmt(int(delta_value(delta, "OSM ∩ Overture matched") or -1)),
          "poi_enriched_stats.json")
add_check("Итого после обогащения (без новых POI с официальных сайтов и из госреестра, до слияния дублей)",
          SHIP_FILE + " after.total − official_site_only − state_registry_only + merged",
          fmt(a_total - site_only - reg_only + merged), DELTA_FILE + " «total» after (merge)",
          fmt(int(delta["total"][1])), f"{SHIP_FILE}: per_source_counts, duplicates")
add_check("Итого до обогащения", BASE_FILE, fmt(b_total), DELTA_FILE + " «total» before",
          fmt(int(delta["total"][0])), "poi_stats.json")
add_check("Итого до обогащения vs OSM-снимок", BASE_FILE, fmt(b_total), SNAP_FILE, fmt(s_total),
          "baseline: poi_stats.json; OSM-часть shipped: poi.osm_stats.json")

# per-category: after from shipped stats vs coverage_delta table, before vs baseline
cat_mismatch = []
for cat in CATEGORY_ORDER:
    cells = delta.get(cat)
    if cells is None:
        cat_mismatch.append(f"{cat}: нет строки в coverage_delta")
        continue
    merged_cat = m_cat.get(cat, 0)
    if int(cells[0]) != b_cat[cat] or int(cells[1]) != a_cat[cat] - site_new_by_cat.get(cat, 0) + merged_cat:
        cat_mismatch.append(f"{cat}: delta {cells[0]}/{cells[1]} vs stats {b_cat[cat]}/{a_cat[cat]} "
                            f"(без новых POI с сайтов, с учётом слитых записей: "
                            f"{a_cat[cat] - site_new_by_cat.get(cat, 0) + merged_cat})")
add_check("Категории до/после (16 строк)", DELTA_FILE, "совпадает" if not cat_mismatch else f"{len(cat_mismatch)} строк",
          BASE_FILE + " / " + SHIP_FILE, "совпадает" if not cat_mismatch else "см. ниже",
          "poi_stats.json, poi_enriched_stats.json")

# the categories where the frozen baseline and the re-collected snapshot disagree
base_vs_snap = [f"{c}: {b_cat[c]} vs {s_cat[c]}" for c in CATEGORY_ORDER if b_cat[c] != s_cat[c]]

# ---- build markdown ----
out: list[str] = []
add = out.append

add("# Цифры для слайдов и документов")
add("")
add("Файл генерируется `python scripts/make_figures.py` из статистики в `data/`. Не править вручную: исправьте входные файлы "
    "или скрипт и пересоберите.")
add("")
add("Входы: " + ", ".join(f"`{f}`" for f in [BASE_FILE, SNAP_FILE, SHIP_FILE, DELTA_FILE]) + ".")
add("")
add("**Какой датасет что означает.** `poi.json` — замороженный OSM-only вход приложения и эталон «до» (baseline). "
    "`poi.osm.json` — пересобранный OSM-снимок; это OSM-часть shipped-базы. `poi.enriched.json` — shipped-база приложения "
    "(OSM + Overture + Wikipedia + официальные сайты), датасет по умолчанию в `app/walks/models.py`.")
add("")

add("## 1. Размер базы")
add("")
add(md_table(["набор", "POI", "источник"], [
    ["baseline `data/poi.json` (OSM, замороженный вход приложения)", fmt(b_total), f"{BASE_FILE}: total"],
    ["OSM-снимок `data/poi.osm.json` (пересбор)", fmt(s_total), f"{SNAP_FILE}: total"],
    ["shipped `data/poi.enriched.json` (OSM + Overture + Wikipedia + официальные сайты)", fmt(a_total),
     f"{SHIP_FILE}: after.total"],
    ["прирост shipped относительно baseline", fmt(a_total - b_total), "вычислено: shipped − baseline"],
]))
add("")

BUCKET_NAMES = {"osm_only": "только OSM", "osm_and_overture": "OSM + Overture", "overture_only": "только Overture",
                "wikidata_only": "только Wikidata", "official_site_only": "только сайты",
                "state_registry_only": "только госреестр"}


def bucket_moves(by_bucket: dict[str, int]) -> str:
    """How merging moved records between the buckets: −n left a bucket (absorbed, or its card gained a source);
    +n arrived (an OSM card that took in an Overture pin became «OSM + Overture»)."""
    return ", ".join(f"{BUCKET_NAMES.get(k, k)} {'−' if n > 0 else '+'}{fmt(abs(n))}"
                     for k, n in sorted(by_bucket.items()) if n)


add("## 2. Состав shipped-датасета")
add("")
add(md_table(["источник записи", "записей", "доля", "источник"], [
    ["только OSM", fmt(ps["osm_only"]), f"{pct(ps['osm_only'], a_total)}%", f"{SHIP_FILE}: per_source_counts.osm_only"],
    ["OSM + Overture", fmt(ps["osm_and_overture"]), f"{pct(ps['osm_and_overture'], a_total)}%",
     f"{SHIP_FILE}: per_source_counts.osm_and_overture"],
    ["только Overture (категория отображена)", fmt(ps["overture_only"]), f"{pct(ps['overture_only'], a_total)}%",
     f"{SHIP_FILE}: per_source_counts.overture_only"],
    ["только Wikidata / Wikipedia (места без OSM и Overture)", fmt(wd_only), f"{pct(wd_only, a_total)}%",
     f"{SHIP_FILE}: per_source_counts.wikidata_only"],
    ["только официальные сайты (новые места)", fmt(site_only), f"{pct(site_only, a_total)}%",
     f"{SHIP_FILE}: per_source_counts.official_site_only"],
    ["только госреестр (ЦОН, gov4c.kz)", fmt(reg_only), f"{pct(reg_only, a_total)}%",
     f"{SHIP_FILE}: per_source_counts.state_registry_only"],
    ["слито записей об одном месте (`collect.dedupe`), корзины выше: " + bucket_moves(mb), f"−{fmt(merged)}",
     "", f"{SHIP_FILE}: duplicates.absorbed_from_bucket"],
    ["**итого**", f"**{fmt(a_total)}**", "100%", "шесть строк минус слитые записи"],
]))
add("")

add("## 3. POI по категориям")
add("")
cat_rows = []
for cat in CATEGORY_ORDER:
    cat_rows.append([cat, fmt(b_cat[cat]), fmt(s_cat[cat]), fmt(a_cat[cat]), f"{a_cat[cat] - b_cat[cat]:+d}"])
cat_rows.append(["**итого**", f"**{fmt(b_total)}**", f"**{fmt(s_total)}**", f"**{fmt(a_total)}**",
                 f"**{a_total - b_total:+d}**"])
add(md_table(["категория", "baseline (poi_stats)", "OSM-снимок (poi.osm_stats)", "shipped (poi_enriched_stats)",
              "Δ shipped − baseline"], cat_rows))
add("")
add("Баланс: сумма по категориям равна итогу в каждом наборе (проверено скриптом).")
add("")

add("## 4. Атрибуты записей")
add("")
oh_osm_origin_before = delta_value(delta, "% with opening_hours (OSM-origin records only)", 0) or "—"
oh_osm_origin_after = delta_value(delta, "% with opening_hours (OSM-origin records only)", 1) or "—"
phone_before = delta_value(delta, "% with phone", 0) or "—"
phone_after = delta_value(delta, "% with phone", 1) or "—"
add(md_table(["метрика", "baseline", "OSM-снимок", "shipped", "источник"], [
    ["% с часами работы (все записи)", fmt(base["pct_opening_hours_total"]), fmt(snap["pct_opening_hours_total"]),
     fmt(ship["after"]["pct_opening_hours_total"]), f"{BASE_FILE}, {SNAP_FILE}, {SHIP_FILE}: pct_opening_hours_total"],
    ["% с часами работы (только записи из OSM)", oh_osm_origin_before, "—", oh_osm_origin_after,
     f"{DELTA_FILE}: «OSM-origin records only»"],
    ["% реальное описание (OSM-тег или Wikipedia)", fmt(base["pct_real_description"]), fmt(snap["pct_real_description"]),
     fmt(ship["after"]["pct_real_description"]), "pct_real_description"],
    ["% описание, собранное из тегов (не реальное)", fmt(base["pct_derived_description"]),
     fmt(snap["pct_derived_description"]), fmt(ship["after"]["pct_derived_description"]), "pct_derived_description"],
    ["% с сайтом", fmt(base["pct_website"]), fmt(snap["pct_website"]), fmt(ship["after"]["pct_website"]),
     "pct_website"],
    ["% с телефоном", phone_before, "—", fmt(ship["after"]["pct_phone"]),
     f"baseline: {DELTA_FILE} «% with phone»; shipped: pct_phone"],
    ["записи с тегом wheelchair", fmt(base["count_wheelchair_tag"]), fmt(snap["count_wheelchair_tag"]), "—",
     "count_wheelchair_tag"],
    ["имя сгенерировано из категории (name_generated)", fmt(base["count_name_generated"]),
     fmt(snap["count_name_generated"]), "—", "count_name_generated"],
]))
add("")
hours_total = round(ship["after"]["pct_opening_hours_total"] * a_total / 100)
hours_osm = round(float(oh_osm_origin_after) * s_total / 100)
add(f"Записей с часами: ≈{fmt(hours_total)} из {fmt(a_total)} в shipped (≈ {fmt(hours_osm)} из {fmt(s_total)} в OSM-снимке, "
    "вычислено из процентов). Часы работы приходят из OSM и (с официальных сайтов) для записей, у которых OSM их не "
    "имел; Overture-only записи добавляют в знаменатель, но почти не добавляют часов.")
add("")

add("## 5. Описания по источнику (shipped)")
add("")
dsc = ship["description_source_counts"]
add(md_table(["источник описания", "записей", "доля", "источник"], [
    ["OSM-тег description", fmt(dsc["osm"]), f"{pct(dsc['osm'], a_total)}%", f"{SHIP_FILE}: description_source_counts.osm"],
    ["Wikipedia (extract)", fmt(dsc["wikipedia"]), f"{pct(dsc['wikipedia'], a_total)}%",
     f"{SHIP_FILE}: description_source_counts.wikipedia"],
    ["собрано из тегов (derived)", fmt(dsc["derived"]), f"{pct(dsc['derived'], a_total)}%",
     f"{SHIP_FILE}: description_source_counts.derived"],
]))
add("")
add("### Данные официальных сайтов (`collect/sites`)")
add("")
add(md_table(["показатель", "значение", "источник"], [
    ["филиалов с проверенными доказательствами", fmt(osites["branches_verified"]), "official_sites.branches_verified"],
    ["привязано к существующим POI", fmt(osites["pois_matched"]), "official_sites.pois_matched"],
    ["новых POI (первичные координаты на странице сайта)", fmt(osites["new_pois"]), "official_sites.new_pois"],
    ["часы работы с днями: было → стало",
     f"{fmt(osites['hours_day_qualified_before'])} ({fmt(osites['hours_pct_before'])}%) → "
     f"{fmt(osites['hours_day_qualified_after'])} ({fmt(osites['hours_pct_after'])}%)",
     "official_sites.hours_day_qualified_*, hours_pct_*"],
    ["часы добавлены существующим POI / новым POI",
     f"{fmt(osites['hours_new_on_existing_pois'])} / {fmt(osites['hours_new_on_new_pois'])}",
     "official_sites.hours_new_on_*"],
    ["расхождение часов OSM и сайта (в `opening_hours` остаётся OSM)", fmt(osites["hours_conflicts"]),
     "official_sites.hours_conflicts"],
    ["часы сайта без дней (не влияют на «открыто / закрыто»)", fmt(osites["hours_unqualified_pois"]),
     "official_sites.hours_unqualified_pois"],
    ["описание сайта у существующих POI", fmt(osites["filled_on_existing"].get("description_official", 0)),
     "official_sites.filled_on_existing"],
]))
add("")

add("## 6. Wikidata, Wikipedia и Overture")
add("")
wdm = ship["wikidata_matches_by_method"]
add(md_table(["показатель", "значение", "источник"], [
    ["Wikidata: совпадение по тегу OSM", fmt(wdm["tag"]), f"{SHIP_FILE}: wikidata_matches_by_method.tag"],
    ["Wikidata: совпадение по SPARQL", fmt(wdm["sparql"]), f"{SHIP_FILE}: wikidata_matches_by_method.sparql"],
    ["Wikidata: совпадение по имени (fuzzy)", fmt(wdm["fuzzy"]), f"{SHIP_FILE}: wikidata_matches_by_method.fuzzy"],
    ["**Wikidata: всего**", f"**{fmt(ps['with_wikidata'])}**", "per_source_counts.with_wikidata"],
    ["Wikipedia-статья у записи", fmt(ps["with_wikipedia_article"]), "per_source_counts.with_wikipedia_article"],
    ["Просмотры Wikimedia (популярность)", fmt(ps["with_popularity_pageviews"]),
     "per_source_counts.with_popularity_pageviews"],
    ["OSM ∩ Overture, 1:1", fmt(ship["osm_overture_matched"]), f"{SHIP_FILE}: osm_overture_matched"],
]))
add("")
add("### Воронка Overture (release " + ov["release"] + ", bbox Астаны)")
add("")
nonpoi = ov["non_poi_demoted"]
chain = ov["chain_duplicates"]
add(md_table(["шаг", "значение", "источник"], [
    ["мест в bbox, всего", fmt(ov["total"]), f"{SHIP_FILE}: overture.total"],
    [f"проходят порог уверенности ≥ {ov['cutoff']}", fmt(ov["passing_cutoff"]), "overture.passing_cutoff"],
    [f"отброшено порогом < {ov['cutoff']}", fmt(ov["dropped_by_cutoff"]), "overture.dropped_by_cutoff"],
    ["отброшено при сборке (dropped_unusable, из прошедших порог)", fmt(ov["dropped_unusable"]), "overture.dropped_unusable"],
    ["совпало с OSM 1:1", fmt(ship["osm_overture_matched"]), "osm_overture_matched"],
    ["Overture-only, категория отображена (добавлено)", fmt(ov["overture_only_added"]), "overture.overture_only_added"],
    ["Overture-only, категория other (не добавлено)", fmt(ov["overture_only_other_not_added"]),
     "overture.overture_only_other_not_added"],
]))
add("")
add("Не-POI среди прошедших порог, понижены (по причине): "
    + ", ".join(f"{k} {v}" for k, v in nonpoi["by_reason_passing_cutoff"].items())
    + f" (всего {sum(nonpoi['by_reason_passing_cutoff'].values())}; {SHIP_FILE}: overture.non_poi_demoted).")
add("")
add("Понижены из категории (прошедшие порог): "
    + ", ".join(f"{k} {v}" for k, v in nonpoi["demoted_from_category_passing_cutoff"].items()) + ".")
add("")
add(f"Дубликаты сетей: слиты в запись OSM {fmt(chain['merged_into_osm'])}; поглощены уже сопоставленной OSM-записью "
    f"{fmt(chain['absorbed_by_already_matched_osm'])}; по совпадению имени: {fmt(chain['by']['name'])} "
    f"(`overture.chain_duplicates`).")
add("")
add("### Доля совпадений с OSM по уверенности Overture")
add("")
bucket_rows = []
for key, v in ov["match_rate_by_confidence"].items():
    bucket_rows.append([key, fmt(v["records"]), fmt(v["matched_osm"]), f"{v['match_rate_pct']:.1f}%"])
add(md_table(["уверенность", "записей", "совпало с OSM", "доля совпадений"], bucket_rows))
add("")
add(f"Источник: `{SHIP_FILE}: overture.match_rate_by_confidence`. Суммы по корзинам ({fmt(sum(v['records'] for v in ov['match_rate_by_confidence'].values()))} записей) "
    "не равны числу прошедших порог: корзины охватывают кандидатов, а не только принятые записи; для слайда используйте "
    "доли по корзинам, а не абсолютные числа.")
add("")

add("## 7. Транспорт")
add("")
add(md_table(["показатель", "значение", "источник"], [
    ["станции LRT «Tarlan Astana» в OSM-снимке", fmt(snap["count_lrt_stations"]), f"{SNAP_FILE}: count_lrt_stations"],
    ["POI категории transit_station, baseline / OSM-снимок / shipped",
     f"{fmt(b_cat['transit_station'])} / {fmt(s_cat['transit_station'])} / {fmt(a_cat['transit_station'])}",
     "категории в трёх файлах статистики"],
]))
add("")

add("## 8. Сверка и расхождения")
add("")
add("Внутренняя арифметика проверена при генерации (сбой → скрипт завершается с кодом 1). Ниже — сравнение между "
    "файлами. Расхождение не скрыто: указаны оба значения и канонический источник.")
add("")
add(md_table(["проверка", "значение A (источник)", "значение B (источник)", "статус", "канон"], checks))
add("")
add("Арифметика, проверенная при генерации (все OK, иначе скрипт не завершился бы):")
add("")
add("- shipped = OSM-only + OSM+Overture + Overture-only + Wikidata-only + только официальные сайты"
    " + только госреестр (корзины стадий сбора) − слитые записи: "
    f"{fmt(ps['osm_only'])} + {fmt(ps['osm_and_overture'])} + {fmt(ps['overture_only'])} + {fmt(wd_only)} + "
    f"{fmt(site_only)} + {fmt(reg_only)} − {fmt(merged)} = {fmt(a_total)} "
    f"(корзины при слиянии: {bucket_moves(mb)});")
add(f"- OSM-часть shipped = OSM-снимок: {fmt(ps['osm_only'])} + {fmt(ps['osm_and_overture'])} = {fmt(s_total)};")
add(f"- чистый прирост = Overture-only + Wikidata-only + официальные сайты + госреестр + (OSM-снимок − baseline)"
    f" − слитые записи: {fmt(a_total - b_total)} = {fmt(ov['overture_only_added'])} + {fmt(wd_only)} + "
    f"{fmt(site_only)} + {fmt(reg_only)} + ({fmt(s_total - b_total)}) − {fmt(merged)};")
add(f"- OSM+Overture (корзины стадий сбора) = 1:1 + слияния сетей: {fmt(ps['osm_and_overture'])} = "
    f"{fmt(ship['osm_overture_matched'])} + {fmt(chain['merged_into_osm'])}; из них {fmt(paired)} карточек после"
    f" слияния дублей несут ещё и Overture-ид поглощённой записи;")
add(f"- слито записей об одном месте: {fmt(merged)} ("
    + ", ".join(f"{c} — {fmt(n)}" for c, n in sorted(m_cat.items())) + ");")
add(f"- Overture: всего − отброшено порогом = прошедшие: {fmt(ov['total'])} − {fmt(ov['dropped_by_cutoff'])} = "
    f"{fmt(ov['passing_cutoff'])}.")
add("")
if base_vs_snap:
    add(f"- baseline (`poi.json`, {fmt(b_total)}) и OSM-снимок пересбора ({fmt(s_total)}) различаются по категориям: "
        + "; ".join(base_vs_snap) + ". Канон для «до» — `poi_stats.json` (замороженный вход приложения); "
        "для OSM-части shipped — `poi.osm_stats.json`.")
else:
    add("- baseline и OSM-снимок пересбора совпадают по категориям.")
add(f"- чистый прирост {fmt(a_total - b_total)} ≠ Overture-only {fmt(ov['overture_only_added'])}: в нём ещё "
    f"{fmt(wd_only)} мест только из Wikidata / Wikipedia, {fmt(site_only)} мест только с официальных сайтов и "
    f"{fmt(s_total - b_total)} — добавки OSM-снимка пересбора "
    "относительно baseline (второй запрос Overpass и расхождение снимков). В слайдах прирост писать с этой расшифровкой.")
if cat_mismatch:
    add("- расхождения категорий с `coverage_delta.md`: " + "; ".join(cat_mismatch))
add("")

add("## 9. Вывод для слайда")
add("")
add(f"- База: {fmt(a_total)} POI в Астане (OSM + Overture + Wikipedia + официальные сайты) против {fmt(b_total)} в "
    "OSM-only baseline.")
add(f"- Часы работы: {fmt(ship['after']['pct_opening_hours_total'])}% записей по всей базе; у записей из OSM — "
    f"{oh_osm_origin_after}%; официальные сайты добавили часы с днями в "
    f"{fmt(osites['hours_day_qualified_after'] - osites['hours_day_qualified_before'])} записей "
    f"(было {fmt(osites['hours_pct_before'])}%, стало {fmt(osites['hours_pct_after'])}%).")
add(f"- Реальные описания (OSM-тег или Wikipedia): {fmt(ship['after']['pct_real_description'])}% "
    f"против {fmt(base['pct_real_description'])}% в baseline.")
add(f"- Сайт: {fmt(ship['after']['pct_website'])}% (было {fmt(base['pct_website'])}%); телефон: "
    f"{fmt(ship['after']['pct_phone'])}% (было {phone_before}%).")
add("")

if failures:
    sys.stderr.write("internal identity failed:\n" + "\n".join(f"- {f}" for f in failures) + "\n")
    sys.exit(1)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
print(f"wrote {OUT.relative_to(ROOT).as_posix()}: {len(out)} lines, {sum(1 for c in checks if c[3] != 'OK')} cross-file differences")
