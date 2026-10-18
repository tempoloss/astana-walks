"""Tests of the state-object layer (collect/gov) on fixtures: no network, no real cache.

Run from the repository root:  uv run python -m pytest collect/tests/test_gov.py -q
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_sites import fetcher  # noqa: E402

from collect.gov import apply as gapply  # noqa: E402
from collect.gov import catalog, cons, geocode, osm, rca, sport  # noqa: E402
from collect.gov import verify as gverify  # noqa: E402
from collect.gov.addr import norm_house, parse_address, same_address, same_street, street_key  # noqa: E402
from collect.gov.model import GovRecord, validate_record  # noqa: E402
from collect.sites.verify import Verifier  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "gov"
ROOT = Path(__file__).resolve().parents[2]


def fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def cson_records() -> tuple[list[GovRecord], Verifier]:
    f, _ = fetcher({cons.PAGES["ru"]: (200, fixture("gov4c_ru.html"), "text/html; charset=utf-8"),
                    cons.PAGES["kk"]: (200, fixture("gov4c_kk.html"), "text/html; charset=utf-8"),
                    cons.PAGES["en"]: (404, "", "text/html")})
    pages = {lang: f.fetch(url) for lang, url in cons.PAGES.items()}
    return cons.build_records(pages), Verifier(f)


def sport_records() -> tuple[list[GovRecord], Verifier]:
    url = sport.export_url(sport.SLUG, 0)
    f, _ = fetcher({url: (200, fixture("sport_730.json"), "application/json")})
    pairs = sport.fetch_rows(f, sport.SLUG)
    return [sport.build_record(r, p) for r, p in pairs], Verifier(f)


# ---- addresses -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, street, house", [
    ("ул. Мангилик ел, 30", "ул. Мангилик ел", "30"),
    ("ул. С. Муканова, здание 2", "ул. С. Муканова", "2"),
    ("ул. А 82, здание 8, блок «К»", "ул. А 82", "8"),
    ("ул. А 82, блок «М» (здание вокзала Нурлы жол первый этаж)", "ул. А 82", None),
    ("г.Астана , пр. Туран, 48", "пр. Туран", "48"),
    ("г. Астана, \nул.  Джангильдина 9а\n", "ул. Джангильдина", "9а"),
    ("ул. Тауелсиздик, 16/1", "ул. Тауелсиздик", "16/1"),
])
def test_parse_address(raw, street, house):
    a = parse_address(raw)
    assert (a.street, a.house) == (street, house)


def test_kazakh_and_russian_spellings_agree():
    assert same_street(street_key("ул. Мангилик ел"), street_key("Мәңгілік Ел даңғылы"))
    assert same_street(street_key("ул. Тауелсиздик"), street_key("Тәуелсіздік даңғылы"))
    assert same_street(street_key("пр.Кабанбай батыра"), street_key("Қабанбай Батыр даңғылы"))
    assert not same_street(street_key("ул. Мангилик ел"), street_key("ул. Кенесары"))
    assert norm_house("14А") == norm_house("14a") == "14а"
    assert not same_address(parse_address("ул. Мангилик ел"), parse_address("Мәңгілік Ел даңғылы, 30"))  # no house


# ---- ЦОН -----------------------------------------------------------------------------------------------------


def test_cson_parse_hours_and_evidence():
    recs, verifier = cson_records()
    assert [r.extra["row"] for r in recs] == [1, 2, 3, 4]
    esil, spec, migr, odd = recs
    assert esil.hours.opening_hours == "Mo-Fr 09:00-20:00; Sa 09:00-13:00" and esil.hours.scope == "venue"
    assert esil.names["kk"].startswith("Халыққа қызмет") and esil.address["by_lang"]["kk"] == "Мәңгілік ел көшесі, 30"
    # two schedules in one cell: the reception is the visitor's, the issue schedule stays in the note
    assert spec.hours.opening_hours == "Mo-Fr 09:00-18:00; Sa 09:00-12:00"
    assert spec.hours.note == "Выдача: Mo-Fr 09:00-20:00; Sa 09:00-13:00" and "two_schedules" in spec.hours.flags
    assert (spec.address["street"], spec.address["house"]) == ("ул. С. Муканова", "2")
    assert migr.address["house"] is None
    # a time without days is never a day-qualified schedule
    assert odd.hours.opening_hours is None and odd.hours.raw == "с 10:00 до 22:00"
    assert odd.hours.flags
    for r in recs:
        assert validate_record(r) == []
        assert all(verifier.snippet_found(e.url, e.snippet) for e in r.evidence), r.name


def test_cson_has_no_invented_phone():
    recs, _ = cson_records()
    assert all(r.phone_raw is None and not any(e.field == "phone" for e in r.evidence) for r in recs)


def test_cson_hours_typo_and_unparsed():
    assert cons.parse_cson_hours("С понедельника по пятницу с 09:00 до 13:\n00".replace("\n", " ")).opening_hours \
        == "Mo-Fr 09:00-13:00"
    h = cons.parse_cson_hours("по записи")
    assert h.opening_hours is None and h.flags


# ---- sport register № 730 ------------------------------------------------------------------------------------


def test_sport_hours_are_administration_scope_only():
    recs, verifier = sport_records()
    assert len(recs) == 2
    for r in recs:
        assert r.hours.scope == "administration" and r.hours.opening_hours is None and r.hours.raw == "08:30-18:00"
        assert any(e.field == "admin_hours" for e in r.evidence) and not any(e.field == "opening_hours" for e in r.evidence)
        assert validate_record(r) == []
        assert all(verifier.snippet_found(e.url, e.snippet) for e in r.evidence), r.name
    assert "Иванов" not in json.dumps([r.to_dict() for r in recs], ensure_ascii=False)  # the head's name is not stored
    assert recs[0].address["house"] == "47" and recs[1].address["house"] == "48"


def test_scope_rule_is_validated():
    recs, _ = sport_records()
    bad = GovRecord.from_dict(recs[0].to_dict())
    bad.hours.opening_hours = "Mo-Su 08:30-18:00"
    assert any("administration hours must not carry opening_hours" in e for e in validate_record(bad))


def test_export_paging_starts_at_0_then_101():
    rows = [{"id": str(i)} for i in range(1, 101)]
    f, net = fetcher({sport.export_url("x", 0): (200, json.dumps(rows), "application/json"),
                      sport.export_url("x", 101): (200, json.dumps([{"id": "101"}]), "application/json")})
    got = sport.fetch_rows(f, "x")
    assert len(got) == 101 and got[-1][1].url == sport.export_url("x", 101)
    assert [u for u in net.requests if "exportjson" in u] == [sport.export_url("x", 0), sport.export_url("x", 101)]


# ---- catalogue ----------------------------------------------------------------------------------------------


def test_catalog_coordinate_detection():
    meta = {"fields": {"a": {"labelRu": "Наименование", "type": "String", "orderNumber": "2"},
                       "b": {"labelRu": "Геопозиция", "type": "Geoposition", "orderNumber": 1}}}
    fields = catalog.schema_fields(meta)
    assert [f["key"] for f in fields] == ["b", "a"] and catalog.schema_coordinate_fields(fields) == ["b"]
    assert catalog.row_has_coordinates([{"x": "53.287832, 69.418304"}])
    assert not catalog.row_has_coordinates([{"mr": "г. Астана, ул. Абая 1", "id": "3"}])


def test_catalog_describe_counts_rows():
    f, _ = fetcher({
        f"{catalog.HOST}/datasets/getmeta?index=s": (200, json.dumps({"fields": {"k": {"labelRu": "Имя"}},
                                                                      "owner": {"fullnameRu": "Упр."}}), "application/json"),
        sport.export_url("s", 0): (200, json.dumps([{"id": "1", "k": "a"}, {"id": "2", "k": "b"}]), "application/json")})
    d = catalog.describe(f, {"apiUri": "s", "id": "s", "nameRu": "Набор"})
    assert d["row_count"] == 2 and d["has_coordinates"] is False and d["fields"] == [{"key": "k", "label": "Имя", "type": None}]


# ---- OSM fetch helpers ---------------------------------------------------------------------------------------


def _mojibake(text: str) -> str:
    """UTF-8 bytes read as cp1252 (bytes cp1252 leaves undefined become C1 controls), as the mirror serves some ways."""
    out = []
    for b in text.encode("utf-8"):
        try:
            out.append(bytes([b]).decode("cp1252"))
        except UnicodeDecodeError:
            out.append(chr(b))
    return "".join(out)


def test_fix_mojibake():
    assert _mojibake("ЦОН") != "ЦОН"
    assert osm.fix_mojibake(_mojibake("ЦОН района «Сарыарка»")) == ("ЦОН района «Сарыарка»", True)
    assert osm.fix_mojibake(_mojibake("Мәңгілік Ел даңғылы")) == ("Мәңгілік Ел даңғылы", True)
    assert osm.fix_mojibake("Центр обслуживания") == ("Центр обслуживания", False)
    assert osm.fix_mojibake("ул. Абая 5") == ("ул. Абая 5", False)


def test_overpass_regexes_widen_kazakh_letters():
    rx = osm.street_regex(street_key("ул. Тауелсиздик"))
    assert rx and "[" in rx
    assert osm.house_values("14а") == ["14A", "14a", "14А", "14а"] and osm.house_values("16/1") == ["16/1"]
    q = osm.address_query(1, street_key("ул. Мангилик ел"), "30")
    assert '["addr:housenumber"="30"]["addr:street"~' in q and "nwr(area.a)" in q


def test_reduce_element_repairs_and_keeps_centre():
    el = {"type": "way", "id": 5, "center": {"lat": 51.1, "lon": 71.4},
          "tags": {"name": _mojibake("ЦОН"), "addr:street": "Абая", "other": "x"}}
    red = osm.reduce_element(el)
    assert red["ref"] == "way/5" and red["tags"]["name"] == "ЦОН" and red["encoding_repaired"] and "other" not in red["tags"]


# ---- geocoding by matching ----------------------------------------------------------------------------------


def cand(ref, lat, lon, **tags):
    return {"ref": ref, "lat": lat, "lon": lon, "tags": tags, "encoding_repaired": False}


def geocoded(records, elements, pois=()):
    geocode.geocode_all(records, {"elements": elements, "fetched_at": "2026-10-17T00:00:00+00:00"}, list(pois))
    return {r.extra.get("row", r.extra.get("row_id")): r.geocode for r in records}


def test_cson_matched_by_name_and_address_only():
    recs, _ = cson_records()
    g = geocoded(recs, [
        cand("way/1", 51.12, 71.43, name="Центр обслуживания населения района Есиль", **{"addr:street": "Мәңгілік Ел даңғылы",
                                                                                        "addr:housenumber": "30"}),
        cand("way/2", 51.11, 71.40, name="Специализированный ЦОН №1", **{"addr:street": "улица Сабита Муканова",
                                                                         "addr:housenumber": "2"}),
        cand("way/3", 51.15, 71.45, **{"addr:street": "Республика даңғылы", "addr:housenumber": "43"}),
    ])
    assert (g[1].status, g[1].method, g[1].ref) == ("matched_osm", "osm_name_address", "way/1")
    assert (g[2].method, g[2].ref) == ("osm_name_address", "way/2")  # 'Муканова' = 'Сабита Муканова', the №1 agrees
    assert (g[4].method, g[4].ref) == ("osm_address", "way/3")  # an unnamed building at the registry's address
    assert g[3].status == "unmapped" and "no house number" in g[3].reason  # 'А 82, блок М': counted, not placed
    assert g[3].lat is None


def test_house_number_must_match():
    recs, _ = cson_records()
    g = geocoded(recs, [cand("way/1", 51.1, 71.4, name="ЦОН", **{"addr:street": "Мәңгілік Ел даңғылы",
                                                                 "addr:housenumber": "32"})])
    assert g[1].status == "unmapped" and "30" in g[1].reason


def test_name_only_match_needs_a_unique_district_and_no_address():
    recs, _ = cson_records()
    esil = recs[0]
    nameonly = cand("node/9", 51.2, 71.5, name="Центр обслуживания населения района Есиль")
    assert geocode.geocode_osm(esil, [geocode.Elem.from_candidate(nameonly)], Counter({"есиль": 1})).method == "osm_name"
    twice = Counter({"есиль": 2})  # two registry rows name the district: a name alone cannot tell them apart
    assert geocode.geocode_osm(esil, [geocode.Elem.from_candidate(nameonly)], twice).status == "unmapped"
    other_addr = cand("node/8", 51.2, 71.5, name="ЦОН района Есиль", **{"addr:street": "Кенесары", "addr:housenumber": "1"})
    assert geocode.geocode_osm(esil, [geocode.Elem.from_candidate(other_addr)], Counter({"есиль": 1})).status == "unmapped"


def test_ambiguous_candidates_far_apart_stay_unmapped():
    recs, _ = cson_records()
    a = {"addr:street": "Мәңгілік Ел даңғылы", "addr:housenumber": "30"}
    g = geocoded(recs[:1], [cand("way/1", 51.1, 71.4, **a), cand("way/2", 51.2, 71.5, **a)])
    assert g[1].status == "unmapped" and "farther than" in g[1].reason and g[1].candidates == 2


def test_sport_matches_poi_by_name_and_address_or_unique_name():
    recs, _ = sport_records()
    alau = {"id": "way/166267459", "name": "Ледовый дворец Алау", "names": {"name": "Ледовый дворец Алау"},
            "category": "sport", "address": "Астана, Қабанбай Батыр даңғылы, 47", "lat": 51.1048, "lon": 71.4050}
    arena = {"id": "wikidata/Q746559", "name": "Астана Арена", "names": {"name": "Астана Арена"}, "category": "sport",
             "address": None, "lat": 51.1082, "lon": 71.4026}
    arena2 = {**arena, "id": "node/1", "category": "transit_station", "lat": 51.2}
    wrong = {**alau, "id": "node/2", "name": "Ледовый дворец Алау", "address": "Астана, Кенесары, 5"}
    g = geocoded(recs, [], [wrong, alau, arena, arena2])
    assert (g["4"].status, g["4"].method, g["4"].ref) == ("matched_poi", "poi_name_address", "way/166267459")
    assert (g["7"].status, g["7"].ref) == ("matched_poi", "wikidata/Q746559")  # the sport one of two same-named POIs


# ---- apply ---------------------------------------------------------------------------------------------------


def poi(pid, name, category="sport", **kw):
    base = {"id": pid, "name": name, "name_generated": False, "names": {"name": name}, "lat": 51.1, "lon": 71.4,
            "category": category, "tags": [], "opening_hours": None, "website": None, "phone": None, "address": None,
            "wheelchair": None, "internet_access": None, "outdoor_seating": None, "description": None,
            "description_auto": "x", "description_source": "derived", "source": "osm", "collected_at": "2026-10-16",
            "sources": ["osm"], "field_sources": {}, "overture_id": None, "hours_state": "unknown", "brand": None,
            "brand_wikidata": None, "opening_hours_official": None, "hours_conflict": False,
            "hours_conflict_prefers": None, "hours_unqualified": None, "hours_unqualified_flags": [],
            "description_official": None}
    return {**base, **kw}


def applied():
    c_recs, _ = cson_records()
    s_recs, _ = sport_records()
    records = c_recs + s_recs
    alau = poi("way/1", "Ледовый дворец Алау", address="Астана, Қабанбай Батыр даңғылы, 47", opening_hours="Mo-Su 10:00-22:00")
    pois = [alau, poi("n/2", "Кофейня", "cafe")]
    geocode.geocode_all(records, {"fetched_at": "2026-10-17T00:00:00+00:00", "elements": [
        cand("way/10", 51.12, 71.43, name="Центр обслуживания населения района Есиль",
             **{"addr:street": "Мәңгілік Ел даңғылы", "addr:housenumber": "30"}),
        cand("way/11", 51.13, 71.44, **{"addr:street": "Республика даңғылы", "addr:housenumber": "43"})]}, pois)
    return pois, records, *gapply.build(pois, records)


def test_apply_creates_cson_attaches_sport_and_counts_unmapped():
    pois, records, dataset, joined, stats = applied()
    new = [p for p in dataset if p["id"].startswith("gov/cson/")]
    assert len(new) == 2 and {p["category"] for p in new} == {"other"} and all("gov_service=cson" in p["tags"] for p in new)
    esil = next(p for p in new if "Есиль" in p["name"])
    assert esil["opening_hours"] == "Mo-Fr 09:00-20:00; Sa 09:00-13:00" and esil["hours_state"] == "known"
    assert esil["source"] == "state_registry" and esil["field_sources"]["opening_hours"]["source"] == "state_registry"
    assert esil["field_sources"]["lat"]["source"] == "osm" and esil["field_sources"]["lat"]["ref"] == "way/10"
    assert "state_registry" in esil["field_sources"]["opening_hours"]["license"] or "401-V" in esil["field_sources"]["opening_hours"]["license"]
    alau = next(p for p in dataset if p["id"] == "way/1")
    assert alau["opening_hours"] == "Mo-Su 10:00-22:00"  # the registry's office week never replaces or fills hours
    assert alau["admin_hours"]["raw"] == "08:30-18:00" and alau["admin_hours"]["scope"] == "administration"
    assert "state_registry" in alau["sources"] and alau["state_registry_match"]["kind"] == "sport_facility"
    assert stats["cson_found"] == 4 and stats["sport_records"] == 2 and stats["new_pois"] == 2
    assert stats["unmapped"] == 3 and len(stats["unmapped_records"]) == 3  # Specialised №1, А 82, Астана-Арена: no match
    assert Counter(j["action"] for j in joined)["kept_unmapped"] == 3
    assert gverify.check_dataset(dataset) == []


def test_admin_hours_never_become_opening_hours():
    _, _, dataset, _, _ = applied()
    assert all(p["opening_hours"] != "08:30-18:00" for p in dataset)
    tampered = json.loads(json.dumps(dataset))
    alau = next(p for p in tampered if p["id"] == "way/1")
    alau["field_sources"]["opening_hours"] = dict(alau["field_sources"]["admin_hours"])
    alau["opening_hours"] = "Mo-Fr 08:30-18:00"
    assert any("scope" in line for line in gverify.check_dataset(tampered))


def test_attach_fills_empty_hours_only_when_day_qualified():
    recs, _ = cson_records()
    p = poi("x/1", "ЦОН Есиль", "other")
    recs[0].geocode = geocode.Geocode("matched_poi", 51.1, 71.4, "poi_name_address", "x/1")
    assert gapply.attach(p, recs[0], "poi_name_address") == ["opening_hours", "address"] and p["hours_state"] == "known"
    q = poi("x/2", "ЦОН", "other", opening_hours="Mo-Fr 10:00-12:00")
    assert gapply.attach(q, recs[0], "poi_name_address")[0] == "opening_hours_state" and q["opening_hours"] == "Mo-Fr 10:00-12:00"
    odd = poi("x/3", "Сектор", "other")
    gapply.attach(odd, cson_records()[0][3], "poi_name")
    assert odd["opening_hours"] is None  # «с 10:00 до 22:00» names no days


def test_attach_writes_address_kk_only_for_a_unique_register_street():
    recs, _ = cson_records()
    rec = recs[0]  # ул. Мангилик ел, 30 -> the RCA register's «Мәңгілік Ел»
    rec.geocode = geocode.Geocode("matched_poi", 51.1, 71.4, "poi_name_address", "x/1")
    rca_map = {"мангилик ел": {"key": "мангилик ел", "ru": "Мәңгілік Ел", "kk": "Мәңгілік Ел даңғылы",
                               "former": [], "id": "108251"}}
    p = poi("x/1", "ЦОН Есиль", "other", address="ул. Мангилик ел, 30")
    assert "address_kk" in gapply.attach(p, rec, "poi_name_address", rca_map)
    assert p["address_kk"] == "Мәңгілік Ел даңғылы" and p["field_sources"]["address_kk"]["source"] == "state_registry"
    q = poi("x/2", "ЦОН", "other", address="ул. Мангилик ел, 30", address_kk="уже есть")
    assert "address_kk" not in gapply.attach(q, rec, "poi_name_address", rca_map)  # never overwritten
    # two register streets agree with the same key: no kk form (ambiguous)
    two = {"мангилик ел": rca_map["мангилик ел"], "мангилик ел 2": rca_map["мангилик ел"]}
    r = poi("x/3", "ЦОН", "other", address="ул. Мангилик ел, 30")
    assert "address_kk" not in gapply.attach(r, rec, "poi_name_address", two)


def test_apply_refuses_a_dataset_that_already_has_registry_facts():
    _, _, dataset, _, _ = applied()
    assert gapply.already_applied(dataset)


def test_verify_drops_facts_without_found_evidence():
    recs, _ = cson_records()
    f, _ = fetcher({cons.PAGES["ru"]: (200, "<html><body><table></table></body></html>", "text/html")})
    f.fetch(cons.PAGES["ru"])
    cleaned, st = gverify.verify_record(recs[0].to_dict(), Verifier(f))
    assert cleaned is None and st["records_dropped"] == 1


# ---- RCA (keyless api/detailed: ps_centers display + street gazetteer) ---------------------------------------


def ps_row(**kw):
    return {"NameRus": "Сектор Тест Отдела №1 Есильского района Департамента Центр обслуживания населения",
            "NameKaz": "Тест секторы", "AddressRus": "г.Астана ул.Кажымукана,8 а",
            "AddressKaz": "Қажымукан көш.,8 а", "PhoneNumber": "8 701 555 10 03",
            "Region": "710000000; Г.АСТАНА", "geoposition": "", "IsMarkedToDelete": "true",
            "TaxStructure": "", "ModifiedDate": "09.06.2020 10:55:19", **kw}


def test_rca_builds_display_record_with_evidence_and_keeps_geoposition_in_extra():
    rec = rca.build_ps_record(ps_row(geoposition="51.089165,71.417368"), "https://data.egov.kz/api/detailed/x")
    assert rec.kind == "cson" and rec.source == "data.egov.kz"
    assert {e.field for e in rec.evidence} == {"name", "address", "phone"}
    assert rec.address["house"] == "8а" and rec.extra["geoposition"] == "51.089165,71.417368"
    assert rec.extra["display"] and rec.extra["marked_to_delete"]
    assert gverify.validate_record(rec) == []


def test_rca_ps_record_needs_name_and_address():
    assert rca.build_ps_record(ps_row(NameRus=""), "u") is None
    assert rca.build_ps_record(ps_row(AddressRus=""), "u") is None


def test_rca_gazetteer_former_names_and_keys():
    rows = [
        {"id": "1", "name_rus": "Тұран", "name_kaz": "Тұран", "d_geonims_type_id": "11", "s_ats_id": "108584",
         "actual": "1", "modified": "2026-10-15 11:42:01", "old_path_rus": "…, улица Тәуелсіздік;…, улица Тұран;",
         "old_path_kaz": ""},
        {"id": "2", "name_rus": "Кенесары", "name_kaz": "Кенесары", "d_geonims_type_id": "11", "s_ats_id": "107989",
         "actual": "false", "modified": None, "old_path_rus": None, "old_path_kaz": None},
        {"id": "3", "name_rus": "41", "name_kaz": "41", "d_geonims_type_id": "19", "s_ats_id": "107989",
         "actual": "1", "modified": None, "old_path_rus": None, "old_path_kaz": None},
    ]
    g = rca.build_gazetteer(rows, [], "https://data.egov.kz/api/detailed/s_geonims?source=%7B%7D")
    assert g["streets"] == 2 and g["coordinates"] is False and "401-V" in g["license"]
    turan = next(i for i in g["items"] if i["id"] == "1")
    assert turan["former"] == ["Тәуелсіздік"] and turan["district"] == "Есиль" and turan["actual"]
    assert g["with_former_names"] == 1


def test_rca_lookup_and_kk(tmp_path):
    rca_map = {"туран": {"key": "туран", "ru": "Тұран", "kk": "Тұран", "former": [], "id": "1"},
               "кабанба батир": {"key": "кабанба батир", "ru": "Қабанбай Батыр", "kk": "Қабанбай Батыр",
                                 "former": [], "id": "2"}}
    assert geocode.rca_lookup("туран", rca_map)["ru"] == "Тұран"
    assert geocode.rca_lookup("Туран", rca_map)["ru"] == "Тұран"  # any street text is folded before the lookup
    assert geocode.rca_lookup("кабанбай батыра", rca_map)["key"] == "кабанба батир"  # fuzzy agrees
    assert geocode.rca_lookup("несусветная", rca_map) is None
    kk = geocode.rca_address_kk(parse_address("пр. Туран, 30"), rca_map)
    assert kk == "Тұран"
    assert geocode.rca_address_kk(parse_address("ул. Несуществующая, 1"), rca_map) is None


def test_rca_alias_matching_agrees_on_the_current_key():
    current = {"key": "туран", "ru": "Тұран", "kk": "Тұран", "former": ["Тәуелсіздік"], "id": "1"}
    rca_map = {"туран": current, "тауелсиздик": current}  # load_gazetteer indexes a former name to the same entry
    a = parse_address("ул. Тәуелсіздік, 34")
    b = parse_address("Тұран даңғылы, 34")
    assert geocode.same_address_alias(a, b, rca_map)  # the old name matches the current street
    assert a.house == "34" and a.raw == "ул. Тәуелсіздік, 34"  # nothing rewritten: keys decide, text stays printed
    elem = geocode.Elem.from_candidate(cand("way/9", 51.1, 71.4, **{"addr:street": "Тұран даңғылы",
                                                                    "addr:housenumber": "34"}))
    assert geocode.same_address_alias(a, elem.address, rca_map)
    assert not same_address(a, elem.address)  # without the alias layer this would not match
    assert not geocode.same_address_alias(a, parse_address("Тұран даңғылы, 35"), rca_map)  # house still decides


def test_rca_stage_files_roundtrip():
    facts_path = ROOT / "data" / "gov" / "facts" / "ps_centers.json"
    gaz_path = ROOT / "data" / "gazetteer" / "rca_streets.json"
    if not facts_path.exists() or not gaz_path.exists():
        pytest.skip("collect.gov.rca has not been run")
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    assert facts["stats"]["rows_astana"] == 11 and facts["stats"]["with_geoposition"] <= 2
    assert facts["robots"] in ("ok", "absent")
    assert all(r["extra"]["display"] for r in facts["records"])  # a display, never a coordinate source
    gaz = json.loads(gaz_path.read_text(encoding="utf-8"))
    assert gaz["streets"] > 2900 and gaz["coordinates"] is False
    # a bare numbered street («41») is legitimate register data; rows without a name are not
    assert all(i["ru"].strip() for i in gaz["items"]) and all(i["key"] for i in gaz["items"])
    assert len(gaz["type_words"]) >= 80


# ---- the shipped data (written by `collect.gov.*`) ----------------------------------------------------------


def test_shipped_gov_data_is_consistent():
    joined_path = ROOT / "data" / "gov" / "joined.json"
    if not joined_path.exists():
        pytest.skip("collect.gov.apply has not been run")
    joined = json.loads(joined_path.read_text(encoding="utf-8"))
    facts = [r for p in sorted((ROOT / "data" / "gov" / "facts").glob("*.json"))
             for r in json.loads(p.read_text(encoding="utf-8"))["records"]]
    assert {j["record_id"] for j in joined["records"]} == {r["id"] for r in facts}
    # the ps_centers display rows are evidence-backed but never a coordinate source: they are kept, never placed
    for j in joined["records"]:
        if j["record_id"].startswith("gov/cson-pc/"):
            assert j["action"] in ("kept_unmapped", "geocoded_not_created"), j["record_id"]
            assert j["poi_id"] is None or j["action"] == "kept_unmapped"
    pois = json.loads((ROOT / "data" / "poi.enriched.json").read_text(encoding="utf-8"))
    assert gverify.check_dataset(pois) == []
    unmapped = [j for j in joined["records"] if j["action"] == "kept_unmapped"]
    assert len(unmapped) == joined["stats"]["unmapped"] and all(j["geocode"]["reason"] for j in unmapped)
    assert all(p["opening_hours"] != (p.get("admin_hours") or {}).get("raw") for p in pois if p.get("admin_hours"))
    cat = json.loads((ROOT / "collect" / "gov" / "catalog.json").read_text(encoding="utf-8"))
    assert cat["summary"]["enumerated"] == len(cat["datasets"]) == cat["summary"]["published_datasets"]
