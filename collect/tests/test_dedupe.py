"""Unit tests of the same-venue merge (`collect.dedupe`) and the name machinery under it (`collect.venue_names`).

Run from the repository root:  uv run --with pytest python -m pytest collect/tests/test_dedupe.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect import dedupe  # noqa: E402
from collect import venue_names as vn  # noqa: E402
from collect.events.venues import VenueIndex  # noqa: E402
from collect.sites.verify import check_dataset as sites_check  # noqa: E402

DATA = Path(dedupe.__file__).resolve().parents[1] / "data"
LAT, LON = 51.12, 71.47
M_LAT = 1 / 111_320  # degrees of latitude per metre


def poi(id="node/1", name="Музей", category="museum_gallery", north_m=0.0, sources=None, **kw) -> dict:
    base = dict(
        id=id, name=name, name_generated=False, names={"name": name}, lat=LAT + north_m * M_LAT, lon=LON,
        category=category, tags=[], opening_hours=None, website=None, phone=None, address="Астана", wheelchair=None,
        internet_access=None, outdoor_seating=None, description=None, description_auto="x",
        description_source="derived", source=(sources or ["osm"])[0], collected_at="2026-10-17T00:00:00+00:00",
        sources=list(sources or ["osm"]), field_sources={}, overture_id=None, hours_state="unknown", brand=None,
        brand_wikidata=None, opening_hours_official=None, hours_conflict=False, hours_conflict_prefers=None,
        hours_unqualified=None, hours_unqualified_flags=[], description_official=None)
    base.update(kw)
    return base


def run(pois: list[dict]) -> tuple[list[dict], dict]:
    return dedupe.dedupe(pois)


# ---- names -------------------------------------------------------------------------------------------


def test_parse_splits_kind_boilerplate_descriptors_identity():
    p = vn.parse("Historical Museum Astana")
    assert p.kinds == {"museum"} and not p.words and p.descriptive_only
    assert vn.parse("Kazakistan Tarihi Müzesi @astana").descriptive_only  # tr: «Kazakhstan Historical Museum»
    assert vn.parse("Национальный музей Республики Казахстан").descriptive_only
    military = vn.parse("Военно-исторический музей")
    assert military.words == {"c:military"} and not military.descriptive_only  # «military» names a venue
    assert vn.parse("Центральная мечеть").kind_only and not vn.parse("Центральная мечеть").descriptive_only
    assert vn.parse("Евразия-2").nums == {"2"} and vn.parse("Кинопарк7").nums == {"7"}


def test_same_name_across_languages_and_spellings():
    pairs = [
        ("Рахмет", "Рахмет ТЦ"), ("Мега Силк Вей", "Mega Silk Way"), ("Kinopark 7", "IMAX Кинопарк7"),
        ("Военно-исторический музей", "Әскери-тарихи музейі"), ("Парк Ататюрка", "парк «Ататюрк»"),
        ("Парк Ататюрка", "Парк Ата Тюрк Астана"), ("А. С. Пушкину", "Памятник Пушкину"),
        ("Алие Молдагуловой", "Памятник Алия Молдагуловой"), ("Mosque Abu Nasr Al-Farabi", "Abu Nasr Al-Farabi mosque"),
    ]
    for a, b in pairs:
        assert vn.same_name_any([a], [b]), (a, b)


def test_different_names_stay_apart():
    pairs = [
        ("Макет ракеты-носителя Зенит", "Макет ракеты-носителя Союз"),  # one word each side lacks
        ("Евразия-2", "Евразия-3"), ("Евразия", "Евразия-3"),  # numbers decide
        ("Музей золота", "Музей первого президента"),  # only the kind is shared
        ("Национальный музей", "Национальная библиотека"),  # only a descriptor is shared
        ("Мечеть Хазрет Султан", "Мечеть Нурсултан"),
    ]
    for a, b in pairs:
        assert not vn.same_name_any([a], [b]), (a, b)


def test_address_key_needs_a_house_number():
    assert vn.address_key("Астана, проспект Республики 2") == vn.address_key("проспект Республики, 2, Астана")
    assert vn.address_key("Астана") is None


# ---- merge -------------------------------------------------------------------------------------------


def test_same_venue_merges_into_the_richest_and_carries_every_fact():
    osm = poi("way/1", "Национальный музей Республики Казахстан", opening_hours="Tu-Su 10:00-18:00",
              hours_state="known", website="https://nmrk.kz/", address="Тәуелсіздік даңғылы 54", wikidata_id="Q1",
              field_sources={"opening_hours": {"source": "osm"}, "website": {"source": "osm"}})
    pin = poi("overture/a", "National Museum of the Republic of Kazakhstan", north_m=30, sources=["overture"],
              price_text="1000 тг.", phone="+7 700 000 00 00", overture_id="a",
              field_sources={"price_text": {"source": "museum_register"}, "phone": {"source": "overture"}})
    out, log = run([osm, pin])
    assert [p["id"] for p in out] == ["way/1"] and log["stats"]["records_merged_away"] == 1
    kept = out[0]
    assert kept["price_text"] == "1000 тг." and kept["phone"] == "+7 700 000 00 00"  # facts only the pin had
    assert kept["field_sources"]["price_text"] == {"source": "museum_register"}
    assert kept["opening_hours"] == "Tu-Su 10:00-18:00" and kept["hours_state"] == "known"
    assert kept["sources"] == ["osm", "overture"] and kept["overture_id"] == "a"
    assert kept["aliases"] == ["overture/a"] and kept["merged_from"][0]["rule"] in ("name", "colocated")
    assert kept["alt_names"] == ["National Museum of the Republic of Kazakhstan"]  # the pin's own spelling is kept
    assert dedupe.resolve_alias(out, "overture/a") is kept and dedupe.resolve_alias(out, "way/1") is kept


def test_conflicting_values_stay_with_the_survivor_and_are_recorded():
    rich = poi("way/1", "Музей Абая", opening_hours="Mo-Su 10:00-18:00", hours_state="known", website="https://a.kz",
               address="ул. Абая 1", phone="+7 700 111 22 33")
    other = poi("node/2", "Музей Абая", north_m=10, opening_hours="Mo-Fr 09:00-17:00", website="https://b.kz",
                address="ул. Другая 9")
    out, _ = run([rich, other])
    assert out[0]["opening_hours"] == "Mo-Su 10:00-18:00" and out[0]["website"] == "https://a.kz"
    assert out[0]["merged_from"][0]["values_not_taken"] == {
        "opening_hours": "Mo-Fr 09:00-17:00", "website": "https://b.kz", "address": "ул. Другая 9"}


def test_never_merged():
    # different Wikidata ids: two venues whatever the names say
    a = poi("way/1", "Парк Победы", "park_garden", wikidata_id="Q1")
    b = poi("way/2", "Парк Победы", "park_garden", north_m=20, wikidata_id="Q2")
    assert len(run([a, b])[0]) == 2
    # a cinema inside a mall is not the mall
    mall = poi("way/3", "Keruen", "mall")
    cinema = poi("node/4", "Keruen", "culture_theatre_cinema", north_m=10)
    assert len(run([mall, cinema])[0]) == 2
    # chain branches: the same brand
    x = poi("node/5", "Магнум", "mall", brand="Magnum")
    y = poi("node/6", "Магнум", "mall", north_m=40, brand="Magnum")
    assert len(run([x, y])[0]) == 2
    # a name that venues in several places carry names a series
    branches = [poi(f"node/{i}", "Памятник Абаю", "attraction_landmark", north_m=1000 * i) for i in range(10, 13)]
    near = poi("node/20", "Абай", "attraction_landmark", north_m=1000 * 10 + 30, sources=["overture"])
    assert len(run([*branches, near])[0]) == 4
    # a generated name names no venue
    g1 = poi("way/7", "Парк / сквер", "park_garden", name_generated=True)
    g2 = poi("way/8", "Парк / сквер", "park_garden", north_m=20, name_generated=True)
    assert len(run([g1, g2])[0]) == 2
    # different numbers, and the three Evrasia malls
    m = [poi("way/10", "Евразия", "mall"), poi("way/11", "Евразия-2", "mall", north_m=90),
         poi("way/12", "Евразия-3", "mall", north_m=180)]
    assert len(run(m)[0]) == 3


def test_a_cluster_never_holds_two_wikidata_ids_or_spans_more_than_350_m():
    far = [poi("way/1", "Парк Ататюрка", "park_garden"),
           poi("way/2", "парк «Ататюрк»", "park_garden", north_m=200),
           poi("way/3", "Парк Ататюрка", "park_garden", north_m=400)]
    out, _ = run(far)
    assert len(out) == 2  # 1-2 and 2-3 are both within the radius, 1-3 would span 400 m


def test_kind_only_pin_is_absorbed_by_a_same_kind_record_nearby_only():
    museum = poi("way/1", "National Museum of the Republic of Kazakhstan", wikidata_id="Q1",
                 website="https://nmrk.kz/")
    pin = poi("overture/p", "Historical Museum Astana", north_m=190, sources=["overture"], overture_id="p")
    out, log = run([museum, pin])
    assert [p["id"] for p in out] == ["way/1"] and log["stats"]["kind_pins"] == 1
    assert out[0]["aliases"] == ["overture/p"] and out[0]["merged_from"][0]["rule"] == "kind_pin"
    # too far, a different kind, a pin with contacts of its own, a pin that names something: all stay
    far = poi("overture/p", "Historical Museum Astana", north_m=400, sources=["overture"])
    assert len(run([museum, far])[0]) == 2
    other_kind = poi("overture/q", "Historical Library", "museum_gallery", north_m=100, sources=["overture"])
    assert len(run([museum, other_kind])[0]) == 2
    with_site = poi("overture/r", "Historical Museum Astana", north_m=100, sources=["overture"],
                    website="https://x.kz")
    assert len(run([museum, with_site])[0]) == 2
    named = poi("overture/s", "Музей Сакена Сейфуллина", north_m=100, sources=["overture"])
    assert len(run([museum, named])[0]) == 2
    central = poi("overture/t", "Central Park Astana", "park_garden", north_m=90, sources=["overture"])
    park = poi("way/9", "Парк Астана", "park_garden", website="https://p.kz")
    assert len(run([park, central])[0]) == 2  # «Central» picks one park out; only weak descriptors are absorbed


def test_worship_rule_merges_two_cathedrals_in_different_languages():
    ov = poi("overture/c", "Our Lady of Perpetual Help Cathedral", "attraction_landmark", sources=["overture"])
    ru = poi("node/c", "Католический кафедральный собор Девы Марии", "attraction_landmark", north_m=20)
    out, log = run([ov, ru])
    assert len(out) == 1 and log["stats"]["link_rules"].get("worship") == 1
    # 60 m apart: two churches
    ru2 = poi("node/d", "Католический кафедральный собор Девы Марии", "attraction_landmark", north_m=60)
    assert len(run([ov, ru2])[0]) == 2


def test_same_street_address_widens_the_name_radius():
    a = poi("way/1", "Военно-исторический музей", address="Астана, проспект Республики 2")
    b = poi("overture/b", "Әскери-тарихи музейі", north_m=250, sources=["overture"],
            address="проспект Республики, 2, Астана")
    assert len(run([a, b])[0]) == 1
    c = poi("overture/c", "Әскери-тарихи музейі", north_m=250, sources=["overture"], address="Астана")
    assert len(run([a, c])[0]) == 2


def test_other_categories_are_measured_not_merged():
    a = poi("way/1", "Библиотека ЕНУ", "coworking_library")
    b = poi("overture/b", "Library ENU", "coworking_library", north_m=10, sources=["overture"])
    out, log = run([a, b])
    assert len(out) == 2 and log["stats"]["not_merged_outside_scope"]["pairs_by_category"] == {"coworking_library": 1}


def test_input_not_modified_and_second_run_is_refused(tmp_path):
    a = poi("way/1", "Рахмет ТЦ", "mall")
    b = poi("node/2", "Рахмет", "mall", north_m=10)
    before = json.dumps([a, b], sort_keys=True)
    out, _ = run([a, b])
    assert json.dumps([a, b], sort_keys=True) == before
    assert dedupe.already_applied(out) and not dedupe.already_applied([a, b])
    src = tmp_path / "poi.json"
    src.write_text(json.dumps(out), encoding="utf-8")
    rc = dedupe.main(["--poi", str(src), "--out", str(src), "--stats", str(tmp_path / "s.json"),
                      "--delta", str(tmp_path / "d.md"), "--log", str(tmp_path / "l.json")])
    assert rc == 1 and not (tmp_path / "l.json").exists()


def test_merged_dataset_passes_the_site_fact_check():
    a = poi("way/1", "Рахмет ТЦ", "mall", website="https://rakhmet.kz")
    b = poi("node/2", "Рахмет", "mall", north_m=10, opening_hours="Mo-Su 10:00-22:00", hours_state="known",
            field_sources={"opening_hours": {"source": "osm"}})
    out, _ = run([a, b])
    assert sites_check(out) == []


def test_events_venue_index_resolves_an_absorbed_id():
    a = poi("way/1", "Азия Парк", "mall", website="https://a.kz", names={"name": "Азия Парк", "name:en": "Asia Park"})
    b = poi("overture/b", "Asia Park Mall", "mall", north_m=40, sources=["overture"], overture_id="b")
    out, _ = run([a, b])
    index = VenueIndex(out)
    assert index.by_id("way/1")["id"] == "way/1"
    absorbed = index.by_id("overture/b")
    assert absorbed["name"] == "Asia Park Mall" and absorbed["merged_into"] == "way/1"
    assert index.by_id("overture/zzz") is None


# ---- the shipped dataset -----------------------------------------------------------------------------


def _shipped() -> list[dict]:
    return json.loads((DATA / "poi.enriched.json").read_text(encoding="utf-8"))


def test_shipped_dataset_holds_one_record_per_venue():
    pois = _shipped()
    assert len({p["id"] for p in pois}) == len(pois)
    ctx = dedupe.Context(pois)
    assert dedupe.find_pairs(pois, ctx) == []
    assert dedupe.kind_pins(pois, ctx) == []
    assert sites_check(pois) == []


def test_the_national_museum_is_one_card_with_its_price_and_old_ids_resolve():
    pois = _shipped()
    museums = [p for p in pois if p["category"] == "museum_gallery"]
    nm = dedupe.resolve_alias(pois, "overture/d8618d37-bebb-42da-b23d-0f9009deead7")  # «Historical Museum Astana»
    assert nm is not None and nm["id"] == "node/4894937300" and nm["price_text"] == "1000 тг."
    assert dedupe.resolve_alias(pois, "overture/dd3617a1-a856-439a-919d-306b4f7c1c9e") is nm  # the Turkish pin
    assert not [m for m in museums if m["name"] == "Historical Museum Astana"]
    mil = dedupe.resolve_alias(pois, "way/240391776")  # the military museum: four records, one card
    assert mil is dedupe.resolve_alias(pois, "way/1239171353") and mil["price_text"] == "500 тг."
    assert mil["wikidata_id"] == "Q85787940"
    for p in pois:
        for alias in p.get("aliases", []):
            assert alias != p["id"] and alias not in {q["id"] for q in pois}


# ---- the shown name ----------------------------------------------------------------------------------


def test_merged_card_is_shown_under_the_local_name_of_the_osm_record():
    pin = poi("overture/a", "Asia Park Mall", "mall", sources=["overture"], website="https://asia.kz",
              phone="+7 700 000 00 00", overture_id="a", description_auto="Торговый центр «Asia Park Mall» по адресу X.")
    osm = poi("way/1", "Азия Парк", "mall", north_m=40, names={"name": "Asia Park", "name:ru": "Азия Парк"})
    out, log = run([pin, osm])
    assert [p["id"] for p in out] == ["overture/a"]  # the richer record still carries the facts and the id
    card = out[0]
    assert card["name"] == "Азия Парк" and card["names"]["name"] == "Asia Park"
    assert "Asia Park Mall" in card["alt_names"]  # the other spelling stays findable
    assert card["description_auto"] == "Торговый центр «Азия Парк» по адресу X."
    assert card["website"] == "https://asia.kz" and card["aliases"] == ["way/1"]
    assert log["clusters"][0]["renamed_from"] == "Asia Park Mall" and log["clusters"][0]["survivor_name"] == "Азия Парк"


def test_osm_survivor_keeps_its_name_and_the_richest_osm_record_names_the_card():
    rich = poi("overture/r", "Military Museum", sources=["overture"], website="https://m.kz", overture_id="r")
    a = poi("way/2", "Военно-исторический музей", north_m=10)
    b = poi("way/3", "Государственный военно-исторический музей", north_m=20, phone="+7 700 111 22 33",
            address="Астана, проспект Республики 2")
    out, _ = run([rich, a, b])
    assert len(out) == 1 and out[0]["name"] == "Государственный военно-исторический музей"
    assert {"Military Museum", "Военно-исторический музей"} <= set(out[0]["alt_names"])
    assert "Государственный военно-исторический музей" not in out[0]["alt_names"]
    mall = poi("way/9", "Рахмет ТЦ", "mall", website="https://r.kz")
    other = poi("node/10", "Рахмет", "mall", north_m=10)
    assert run([mall, other])[0][0]["name"] == "Рахмет ТЦ"  # the survivor is the OSM record: nothing changes


def test_without_an_osm_record_a_wikidata_ru_or_kk_label_names_the_card_else_nothing_changes():
    a = poi("overture/a", "Keruen City", "mall", sources=["overture"], website="https://k.kz")
    b = poi("overture/b", "KeruenCity", "mall", north_m=20, sources=["overture"], labels={"kk": "Керуен Сити"})
    out, _ = run([a, b])
    assert out[0]["name"] == "Керуен Сити" and "Keruen City" in out[0]["alt_names"]
    c = poi("overture/c", "Keruen City", "mall", sources=["overture"], website="https://k.kz")
    d = poi("overture/d", "KeruenCity", "mall", north_m=20, sources=["overture"])
    assert run([c, d])[0][0]["name"] == "Keruen City"
    gen = poi("way/5", "Парк / сквер", "park_garden", name_generated=True)
    pin = poi("overture/e", "Parkname", "park_garden", sources=["overture"], website="https://p.kz")
    assert run([pin, gen])[0][0]["name"] == "Parkname"  # a generated OSM name is no name


def test_shipped_cards_carry_the_local_name_when_an_osm_record_was_merged_in():
    pois = _shipped()
    by_id = {p["id"]: p for p in pois}
    assert by_id["overture/4d2a37ab-a4d7-4c8a-abfe-4fcca724c6e5"]["name"] == "Азия Парк"
    cathedral = dedupe.resolve_alias(pois, "node/4902165007")
    assert cathedral["name"] == "Римско-Католический Приход Матери Божией Неустанной Помощи"
    for p in pois:  # a card with an OSM record in it is shown under an OSM name
        osm_names = [m["name"] for m in p.get("merged_from", []) if m["source"] == "osm"]
        if osm_names and p["source"] != "osm":
            assert p["name"] in osm_names
    for p in pois:  # every name a record had is still a name of the card
        for m in p.get("merged_from", []):
            assert m["name"] == p["name"] or m["name"] in p["alt_names"] or m["name"] in p["names"].values()
