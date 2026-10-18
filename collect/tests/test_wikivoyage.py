"""Unit tests of the Wikivoyage stage (no network).

Run from the repository root:  uv run --with pytest python -m pytest collect/tests/test_wikivoyage.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.wikivoyage import apply, editions, join, verify  # noqa: E402
from collect.wikivoyage.editions import Listing, parse_article  # noqa: E402

SNAPSHOTS = Path(editions.__file__).resolve().parent / "snapshots"


def _listing(**kw) -> Listing:
    base = dict(edition="en", section="see", name="X", alt="", lat=51.13, lon=71.43, wikidata=None,
                hours=None, price=None, description=None)
    return Listing(**{**base, **kw})


# ---- wikitext parsing ------------------------------------------------------------------------------


def test_parse_article_routes_sections_and_aliases():
    text = """Intro.
== See ==
=== Palaces ===
* {{see
| name=Palace of Peace | alt=Бейбітшілік пен келісім сарайы | lat=51.123 | long=71.463
| hours=Lun-Dom 10:00-18:00 | price=&nbsp;500&nbsp;T | wikidata=Q2119741
| content=A pyramid. }}
== Eat ==
* {{eat
| name=Cafe | lat=51.1 | long=71.4 | hours=Lun-Dom 9:00-18:00 | price=100 T | content=Food. }}
== Sleep ==
* {{sleep
| name=Hotel | lat=51.1 | long=71.4 | hours=24/7 }}
"""
    art = parse_article("en", text, "Astana", 1, "2026-10-17")
    kinds = [(l.name, l.section) for l in art.listings]
    assert kinds == [("Palace of Peace", "see"), ("Cafe", "eat")]
    palace = art.listings[0]
    assert palace.hours == "Lun-Dom 10:00-18:00"
    assert palace.price == "500 T"  # entities and nbsp are gone
    assert palace.wikidata == "Q2119741"
    assert editions.fields_of_interest(palace) == ("hours", "price", "description")
    # eat/drink contribute hours and prices only: never a description
    cafe = art.listings[1]
    assert editions.fields_of_interest(cafe) == ("hours", "price")
    # buy/sleep never contribute anything
    assert editions.fields_of_interest(_listing(section="eat", hours=None, price=None)) == ()


def test_sections_of_real_snapshots():
    for lang, expected in (("en", 52), ("it", 51), ("he", 39), ("pl", 14), ("ru", 31)):
        meta = json.loads((SNAPSHOTS / f"{lang}.meta.json").read_text(encoding="utf-8"))
        art = parse_article(lang, (SNAPSHOTS / f"{lang}.wikitext").read_text(encoding="utf-8"),
                            meta["title"], meta["pageid"], meta["snapshot_date"])
        assert len(art.listings) == expected, lang


def test_nested_listing_belongs_to_top_section():
    text = "== Достопримечательности ==\n=== Новый город ===\n* {{listing\n| name=X | lat=1 | long=2 }}\n== Где остановиться ==\n* {{listing\n| name=Y }}"
    art = parse_article("ru", text, "Астана", 1, "2026-10-17")
    assert [l.name for l in art.listings] == ["X"]  # the Sleep listing is dropped (section not in see/eat)


# ---- join ------------------------------------------------------------------------------------------


def _poi(id="node/1", name="Байтерек", lat=51.12825, lon=71.430472, category="attraction_landmark", **kw):
    p = dict(id=id, name=name, names={}, lat=lat, lon=lon, category=category, opening_hours=None,
             hours_unqualified=None, description=None, description_source="derived", sources=["osm"])
    p.update(kw)
    return p


def test_join_by_wikidata_beats_coordinates():
    j = join.Joiner([_poi(wikidata_id="Q804210", lat=51.5, lon=71.9)])
    pair = j.best(_listing(wikidata="Q804210", lat=51.0, lon=71.0))
    assert pair and pair.rule == "wdid"


def test_join_name_score_and_false_pairs():
    j = join.Joiner([_poi(name="Байтерек")])
    pair = j.best(_listing(name="Wieża Bajterek", lat=51.1283, lon=71.4305))
    assert pair and pair.rule == "name" and pair.score >= 60
    # a tenant 3 m from the landmark shares no name token and is dropped
    j2 = join.Joiner([_poi(name="Gold Mine Coaster", lat=51.132222, lon=71.4305)])
    assert j2.best(_listing(name="Chan Szatyr", alt="", lat=51.132222, lon=71.4305)) is None
    # a translated pair (alt carries the native name) is accepted: by name when the score reaches 60,
    # otherwise by the coords+name rule
    j3 = join.Joiner([_poi(name="Свято-Успенский кафедральный собор", lat=51.149603, lon=71.481481)])
    pair3 = j3.best(_listing(name="Assumption Cathedral", alt="Успенский собор", lat=51.149603, lon=71.481481))
    assert pair3 and pair3.rule in ("name", "coords+name")
    j5 = join.Joiner([_poi(name="Свято-Успенский кафедральный собор", lat=51.149603, lon=71.481481)])
    pair5 = j5.best(_listing(name="Cathedral of the Assumption", alt="Успенский", lat=51.149603, lon=71.481481))
    assert pair5 and pair5.rule == "coords+name"
    # an eat listing needs the plain name score: a similar-named different venue nearby is dropped
    j4 = join.Joiner([_poi(id="node/2", name="Rumi", category="restaurant", lat=51.16, lon=71.43)])
    assert j4.best(_listing(section="eat", name="Ali Babas", lat=51.16, lon=71.43)) is None


def test_join_boilerplate_only_overlap_is_not_a_pair():
    # the kk/ru names of the National Academic Library share «Қазақстан Республикасының Ұлттық» with the listing of the
    # National Archives (87 m away): not the same object
    library = _poi(
        name="Национальная академическая библиотека Республики Казахстан", category="coworking_library",
        names={"kk": "Қазақстан Республикасының Ұлттық академиялық кітапханасы"}, lat=51.1283, lon=71.4305)
    j = join.Joiner([library])
    assert j.best(_listing(name="National archives", alt="Қазақстан Республикасының ұлттық мұрағаты",
                           lat=51.1283, lon=71.4305)) is None
    assert j.best(_listing(edition="it", name="Archivio nazionale del Kazakistan",
                           alt="Қазақстан Республикасының ұлттық мұрағаты", lat=51.1283, lon=71.4305)) is None
    # a state museum is not the museum of the armed forces because both are «Государственный ... Республики Казахстан»
    gold = _poi(name="Государственный музей золота и драгоценных металлов", category="museum_gallery",
                lat=51.1283, lon=71.4305)
    assert join.Joiner([gold]).best(_listing(
        edition="it", name="Museo storico delle Forze Armate della Repubblica del Kazakistan",
        lat=51.1283, lon=71.4305)) is None
    # the city name or a status word alone is no pair, not even by the 40 m coords+name rule
    astana = _poi(name="Астана", category="attraction_landmark", lat=51.1283, lon=71.4305)
    assert join.Joiner([astana]).best(_listing(name="Astana", lat=51.1283, lon=71.4305)) is None
    state = _poi(name="Государственный музей", category="museum_gallery", lat=51.1283, lon=71.4305)
    assert join.Joiner([state]).best(_listing(name="State Republic Kazakhstan", lat=51.1283, lon=71.4305)) is None
    # the content word of a same-language pair still joins them
    assert join.Joiner([state]).best(_listing(name="Государственный музей Республики Казахстан",
                                              lat=51.1283, lon=71.4305)) is not None
    only = _poi(name="Национальный", category="museum_gallery", lat=51.1283, lon=71.4305)
    assert join.Joiner([only]).best(_listing(name="National", lat=51.1283, lon=71.4305)) is None
    # true translated pairs survive: the content words remain
    nat = _poi(name="Национальный музей Республики Казахстан", category="museum_gallery", lat=51.1283, lon=71.4305)
    pair = join.Joiner([nat]).best(_listing(edition="pl", name="Muzeum Narodowe Republiki Kazachstanu",
                                            lat=51.1283, lon=71.4305))
    assert pair and pair.rule == "name"


def test_radius_cap_150m():
    j = join.Joiner([_poi(lat=51.1302, lon=71.430472)])  # ~215 m north of the listing point
    assert j.best(_listing(name="Wieża Bajterek", lat=51.12825, lon=71.430472)) is None


# ---- apply -----------------------------------------------------------------------------------------


def test_apply_listing_never_overwrites_and_routes_unqualified():
    p = _poi(id="node/3", opening_hours="Mo-Su 10:00-18:00")
    touched = apply.apply_listing(p, _listing(hours="Mo-Su 10:00-20:00", price="500 tenge",
                                              description="A tower."), ("hours", "price", "description"),
                                  "2026-10-17")
    assert touched == ["opening_hours_voyage", "price_text", "description_voyage"]
    assert p["opening_hours"] == "Mo-Su 10:00-18:00"  # never overwritten
    assert p["opening_hours_voyage"] == "Mo-Su 10:00-20:00"
    assert p["field_sources"]["price_text"]["license"] == "CC BY-SA 4.0"
    assert p["field_sources"]["price_text"]["url"] == "https://en.wikivoyage.org/wiki/Astana"
    # day-less hours go to hours_unqualified, never to opening_hours
    p2 = _poi(id="node/4")
    touched2 = apply.apply_listing(p2, _listing(hours="09:00-21:00"), ("hours",), "2026-10-17")
    assert touched2 == ["hours_unqualified"]
    assert p2["opening_hours"] is None and p2["hours_unqualified"] == "09:00-21:00"
    assert "hours" not in apply.apply_listing(p2, _listing(hours="closed"), (), "2026-10-17")


def test_apply_listing_keeps_wikipedia_description():
    p = _poi(id="node/5", description="Wikipedia text", description_source="wikipedia")
    touched = apply.apply_listing(p, _listing(description="Voyage text"), ("description",), "2026-10-17")
    assert touched == [] and not p.get("description_voyage")


def test_italian_days_convert_polish_daily_too_hebrew_stays_unqualified():
    p = _poi(id="node/9")
    touched = apply.apply_listing(p, _listing(hours="Dom-Gio 10:00-21:00, Ven-Sab 9:00-21:00"), ("hours",),
                                  "2026-10-17")
    assert touched == ["opening_hours"]
    assert p["opening_hours"] == "Mo-Th,Su 10:00-21:00; Fr,Sa 09:00-21:00" and p["hours_state"] == "known"
    p2 = _poi(id="node/10")
    apply.apply_listing(p2, _listing(edition="he", hours="פתוח בימי שישי ושבת בשעות 23:00 עד 05:00"),
                        ("hours",), "2026-10-17")
    # Hebrew day names the converter does not know: never an opening_hours, no flags either -> nothing stored
    assert p2.get("opening_hours") is None and p2.get("hours_unqualified") is None


def test_build_on_real_snapshots_fills_known_landsmarks():
    # the shipped dataset is frozen; a two-record set with the ids the snapshots carry proves the stage offline
    pois = [
        _poi(id="node/it-bayterek", name="Бейбітшілік және келісім сарайы", lat=51.123056, lon=71.463611,
             wikidata_id="Q2119741"),
        _poi(id="node/ru-atameken", name="Этно-мемориальный комплекс Карта Казахстана Атамекен",
             lat=51.1493419, lon=71.4185318),
    ]
    dataset, wv = apply.build(pois)
    st = wv["stats"]
    assert st["filled_opening_hours"] >= 1  # en Q2119741 'daily 10:00-18:00' is day-qualified
    assert dataset[0]["opening_hours"] == "Mo-Su 10:00-18:00"
    assert dataset[0]["field_sources"]["opening_hours"]["lang"] == "en"
    assert dataset[1]["price_text"]  # ru Atameken 'входной билет 400 тенге…'
    assert "wikivoyage" in dataset[0]["sources"]
    assert wv["radius_pairs"]  # every non-wdid pair is logged for the human check
    assert verify.check_dataset(dataset) == []


def test_check_dataset():
    good = _poi(id="node/6", opening_hours="Mo-Su 10:00-18:00",
                field_sources={"opening_hours": {"source": "wikivoyage", "license": "CC BY-SA 4.0",
                                                 "snapshot_date": "2026-10-17", "lang": "en",
                                                 "url": "https://en.wikivoyage.org/wiki/Astana"}})
    assert verify.check_dataset([good]) == []
    dayless = _poi(id="node/7", opening_hours="09:00-21:00",
                   field_sources={"opening_hours": {"source": "wikivoyage", "lang": "en",
                                                    "url": "https://en.wikivoyage.org/wiki/Astana",
                                                    "snapshot_date": "2026-10-17"}})
    assert verify.check_dataset([dayless])


def test_check_dataset_bad_host():
    p = _poi(id="node/8", field_sources={"price_text": {"source": "wikivoyage", "lang": "en",
                                                           "url": "https://example.com/x",
                                                           "snapshot_date": "2026-10-17"}})
    problems = verify.check_dataset([p])
    assert any("en.wikivoyage.org" in line for line in problems)


def test_a_word_that_names_the_area_is_not_a_shared_name_token():
    # «Expo 2017 buildings» (the whole exhibition site) is not the «SML EXPO Energy Hall» inside it: «expo» is carried
    # by venues of other categories too (a pub, a cafe), it names the area
    hall = _poi(id="overture/hall", name="SML EXPO Energy Hall", category="culture_theatre_cinema",
                lat=51.0892, lon=71.4161)
    pub = _poi(id="node/pub", name="Harat's Irish Pub Expo", category="bar_nightlife", lat=51.0899, lon=71.4165)
    cafe = _poi(id="node/cafe", name="Espresso Bar Expo Boulevard", category="cafe", lat=51.0899, lon=71.4170)
    expo = _listing(name="Expo 2017 buildings", wikidata="Q19858174", lat=51.08923, lon=71.41636)
    assert join.Joiner([hall, pub, cafe]).best(expo) is None
    # alone in the dataset the word still joins a museum with a name of its own
    alem = _poi(id="overture/alem", name="Nur Alem Museum of Future Energy", category="museum_gallery",
                lat=51.0892, lon=71.4161)
    pair = join.Joiner([alem, hall, pub, cafe]).best(_listing(edition="ru", name="Сфера Nur Alem", lat=51.08923,
                                                              lon=71.41636))
    assert pair and pair.rule == "coords+name" and pair.poi_id == "overture/alem"


def test_a_kind_word_is_not_a_name_match():
    # «Центральная мечеть» and «Мечеть Нурсултан» used to pair at score 63 on the word «мечеть» alone
    mosque = _poi(id="relation/m", name="Мечеть Нурсултан", names={"name:en": "Nursultan mosque"},
                  lat=51.0729, lon=71.41044)
    j = join.Joiner([mosque])
    assert j._score(_listing(edition="ru", name="Центральная мечеть"), mosque) == 0.0
    # a listing that says nothing but what it is joins the mosque next to it ...
    pair = j.best(_listing(edition="ru", name="Центральная мечеть", lat=51.07288, lon=71.410787))
    assert pair and pair.rule == "kind+near" and pair.distance_m < 40
    assert j.best(_listing(name="Grand Mosque of Astana", lat=51.07288, lon=71.41049)).rule == "kind+near"
    # ... but not a mosque 100 m away, or a museum next to it
    assert j.best(_listing(edition="ru", name="Центральная мечеть", lat=51.0738, lon=71.41044)) is None
    museum = _poi(id="way/mu", name="Музей", category="museum_gallery", lat=51.0729, lon=71.41044)
    assert join.Joiner([museum]).best(_listing(edition="ru", name="Центральная мечеть", lat=51.0729,
                                               lon=71.41044)) is None


def test_listing_and_poi_with_different_wikidata_ids_are_not_a_pair():
    p = _poi(name="Байтерек", wikidata_id="Q804210")
    other = _listing(name="Байтерек", wikidata="Q999", lat=51.12825, lon=71.430472)
    assert join.Joiner([p]).best(other) is None
    assert join.Joiner([p]).best(_listing(name="Байтерек", lat=51.12825, lon=71.430472)).rule == "name"


def test_a_merged_venue_stands_at_every_point_of_its_records_and_answers_to_every_name():
    merged = _poi(id="overture/m", name="Военно-Исторический музей ВС РК", category="museum_gallery",
                  lat=51.15611, lon=71.43085, alt_names=["Государственный военно-исторический музей"],
                  names={"name": "Военно-Исторический музей ВС РК", "name:kk": "Мемлекеттік әскери-тарихи музей"},
                  merged_from=[{"lat": 51.15593, "lon": 71.43130, "id": "way/1"}])
    listing = _listing(edition="it", name="Museo storico delle Forze Armate della Repubblica del Kazakistan",
                       alt="Қазақстан Республикасы қарулы күштерінің Әскери-Тарихи музеиі", lat=51.155913,
                       lon=71.431365)
    pair = join.Joiner([merged]).best(listing)
    assert pair and pair.poi_id == "overture/m" and pair.distance_m < 10  # the OSM point, not the Overture pin


def test_strip_removes_exactly_what_the_stage_wrote_and_build_is_repeatable():
    pois = [
        _poi(id="node/it-bayterek", name="Бейбітшілік және келісім сарайы", lat=51.123056, lon=71.463611,
             wikidata_id="Q2119741", field_sources={}, hours_state="unknown"),
        _poi(id="node/ru-atameken", name="Этно-мемориальный комплекс Карта Казахстана Атамекен",
             lat=51.1493419, lon=71.4185318, field_sources={}, hours_state="unknown",
             price_text="400 тг.", price_source="own"),
    ]
    pois[1]["field_sources"] = {"price_text": {"source": "official_site"}}
    first, _ = apply.build(pois)
    assert apply.already_applied(first)
    stripped = apply.strip(first)
    assert not apply.already_applied(stripped)
    assert stripped[0]["opening_hours"] is None and stripped[0]["hours_state"] == "unknown"
    assert "description_voyage" not in stripped[0] and stripped[0]["field_sources"] == {}
    assert stripped[1]["price_text"] == "400 тг."  # a first-party fact is not this stage's
    again, _ = apply.build(stripped)
    assert json.dumps(again, sort_keys=True) == json.dumps(first, sort_keys=True)


def test_shipped_join_log_has_no_kind_word_pair():
    log = json.loads((Path(editions.__file__).resolve().parents[2] / "data" / "wikivoyage_joined.json")
                     .read_text(encoding="utf-8"))
    names = {(r["edition"], r["listing"]) for r in log["radius_pairs"]}
    assert not {n for n in names if "Expo 2017" in n[1]}
    by = {(r["edition"], r["listing"]): r for r in log["radius_pairs"]}
    assert by[("ru", "Центральная мечеть")]["rule"] == "kind+near"
    assert all(r["rule"] in ("name", "coords+name", "kind+near") for r in log["radius_pairs"])
