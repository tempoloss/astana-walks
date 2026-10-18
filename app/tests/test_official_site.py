"""Facts from the business's own website (collect/sites): named as such, with their page; hours that disagree with OSM
or name no days never claim «open»; the website's description is quoted with its source; the unbacked-claims stripper
accepts the website's description as backing. Each behaviour in all three answer languages."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from walks import cli, pipeline
from walks.claims import strip_unbacked
from walks.generate import _data_confidence, data_notes, template_rec, template_recs
from walks.hours import poi_hours
from walks.i18n import t
from walks.models import POI, Candidate, Intent, IntentResult
from walks.reasons import _OPEN_CLAIM, Trip, facts, hours_state_text, template_what
from walks.retrieve import retrieve

LANGS = ("kk", "ru", "en")
ORIGIN = (51.09, 71.41)
NOON = datetime(2026, 10, 14, 12, 0)  # a Wednesday
NIGHT = datetime(2026, 10, 14, 3, 0)
M = 1 / 111_000
SITE_URL = "https://example.kz/cafe/astana"
SITE = {"source": "official_site", "license": "own website", "url": SITE_URL}


def poi(pid="p", north_m=200.0, **kw) -> POI:
    base = {
        "id": pid,
        "name": pid,
        "lat": ORIGIN[0] + north_m * M,
        "lon": ORIGIN[1],
        "category": "cafe",
        "sources": ["osm", "official_site"],
    }
    return POI(**{**base, **kw})


def cand(state="unknown", issue="", reasons=(), **kw) -> Candidate:
    return Candidate(
        poi=poi(**kw),
        distance_m=200,
        walk_min=3,
        travel_min=3,
        hours_state=state,
        hours_issue=issue,
        score=1.0,
        reasons=list(reasons),
    )


def intent(lang="ru", **kw) -> Intent:
    return Intent(language=lang, time_budget_min=60, **kw)


# a place whose OSM hours say open at noon while the website's say closed (they differ by the opening hour)
CONFLICT = {
    "opening_hours": "Mo-Su 09:00-21:00",
    "opening_hours_official": "Mo-Su 14:00-22:00",
    "hours_conflict": True,
}


# ---------------------------------------------------------------- the label of the source


@pytest.mark.parametrize(
    ("lang", "site"),
    [("ru", "официальный сайт"), ("kk", "ресми сайт"), ("en", "official website")],
)
def test_data_label_names_the_official_site(lang, site):
    assert poi().data_label(lang) == f"OSM + {site}"
    assert poi(sources=["official_site"]).data_label(lang) == site
    assert poi(sources=["osm", "overture", "official_site"]).data_label(lang) == (
        f"OSM + Overture + {site}"
    )


def test_data_label_defaults_to_russian_and_keeps_osm_alone_as_before():
    assert poi().data_label() == "OSM + официальный сайт"
    assert poi(sources=["osm"]).data_label() == "OSM"


def test_the_hours_source_is_the_source_of_the_field_not_of_the_record():
    plain = poi(opening_hours="Mo-Su 09:00-21:00", sources=["osm"])
    assert (plain.hours_source(), plain.hours_source_url()) == ("osm", None)
    site = poi(opening_hours="Mo-Su 09:00-21:00", field_sources={"opening_hours": SITE})
    assert (site.hours_source(), site.hours_source_url()) == ("official_site", SITE_URL)
    conflict = poi(**CONFLICT, field_sources={"opening_hours_official": SITE})
    assert (conflict.hours_source(), conflict.hours_source_url()) == ("osm", SITE_URL)
    unqualified = poi(
        hours_unqualified="с 10:00 до 22:00", field_sources={"hours_unqualified": SITE}
    )
    assert (unqualified.hours_source(), unqualified.hours_source_url()) == (
        "official_site",
        SITE_URL,
    )
    assert poi().hours_source() is None


@pytest.mark.parametrize(
    ("lang", "expect"),
    [
        ("ru", ("открыто по данным OSM", "открыто по данным официального сайта")),
        ("en", ("open according to OSM", "open according to the official website")),
        ("kk", ("OSM деректері бойынша ашық", "ресми сайт деректері бойынша ашық")),
    ],
)
def test_the_state_label_names_the_source_of_the_hours(lang, expect):
    assert hours_state_text("open", "osm", lang) == expect[0]
    assert hours_state_text("open", None, lang) == expect[0]
    assert hours_state_text("open", "official_site", lang) == expect[1]
    assert hours_state_text("closed", "official_site", lang) == t("hours_state_closed", lang)
    assert hours_state_text("unknown", "official_site", lang) == t("hours_state_unknown", lang)


# ---------------------------------------------------------------- the verdict of the hours


def test_hours_that_came_from_the_site_decide_like_any_hours():
    p = poi(opening_hours="Mo-Su 09:00-21:00", field_sources={"opening_hours": SITE})
    assert poi_hours(p, NOON) == ("open", "", "")
    assert poi_hours(p, NIGHT) == ("closed", "", "")


def test_a_conflict_where_both_say_open_keeps_open_and_says_the_sources_differ():
    p = poi(
        opening_hours="Mo-Su 09:00-21:00",
        opening_hours_official="Mo-Su 10:00-22:00",
        hours_conflict=True,
    )
    assert poi_hours(p, NOON) == ("open", "", "conflict")


def test_a_conflict_where_both_say_closed_is_closed():
    p = poi(
        opening_hours="Mo-Su 09:00-21:00",
        opening_hours_official="Mo-Su 10:00-22:00",
        hours_conflict=True,
    )
    assert poi_hours(p, NIGHT).state == "closed"


@pytest.mark.parametrize("osm_open", [True, False])
def test_when_osm_and_the_site_disagree_right_now_the_state_is_unknown_never_open(osm_open):
    osm, site = (
        ("Mo-Su 09:00-21:00", "Mo-Su 14:00-22:00")
        if osm_open
        else ("Mo-Su 14:00-22:00", "Mo-Su 09:00-21:00")
    )
    p = poi(opening_hours=osm, opening_hours_official=site, hours_conflict=True)
    assert poi_hours(p, NOON) == (
        "unknown",
        "",
        "split",
    )  # OSM closed + site open is not «closed» either


def test_a_matching_site_value_is_not_a_conflict():
    p = poi(opening_hours="Mo-Su 09:00-21:00", opening_hours_official="Mo-Su 09:00-21:00")
    assert poi_hours(p, NOON) == ("open", "", "")


def test_hours_without_days_never_drive_the_state():
    p = poi(hours_unqualified="с 10:00 до 22:00", field_sources={"hours_unqualified": SITE})
    for when in (NOON, NIGHT):
        assert poi_hours(p, when) == ("unknown", "", "unqualified")
    with_osm = poi(opening_hours="Mo-Su 09:00-21:00", hours_unqualified="с 10:00 до 22:00")
    assert poi_hours(with_osm, NOON) == ("open", "", "")  # day-qualified hours decide, as before
    assert poi_hours(poi(), NOON) == ("unknown", "", "")


# ---------------------------------------------------------------- the notes and the confidence of a card


@pytest.mark.parametrize("lang", LANGS)
def test_a_conflict_note_names_both_schedules_and_caps_the_confidence(lang):
    c = cand("open", "conflict", **CONFLICT, name_generated=False)
    notes = " ".join(data_notes(c, intent(lang)))
    assert (
        t(
            "note_hours_conflict",
            lang,
            osm=CONFLICT["opening_hours"],
            site=CONFLICT["opening_hours_official"],
        )
        in notes
    )
    assert "Mo-Su 09:00-21:00" in notes
    assert "Mo-Su 14:00-22:00" in notes
    assert (
        t("note_hours_split_tail", lang) not in notes
    )  # they agree right now: only the difference is said
    assert _data_confidence(c) == "medium"
    assert _data_confidence(cand("open", "", opening_hours="Mo-Su 09:00-21:00")) == "high"
    assert template_rec(c, intent(lang), None, [c]).confidence != "high"


def test_the_russian_conflict_note_reads_as_specified():
    c = cand("unknown", "split", **CONFLICT)
    notes = " ".join(data_notes(c, intent("ru")))
    assert (
        "Часы в OSM и на сайте расходятся: OSM Mo-Su 09:00-21:00, сайт Mo-Su 14:00-22:00." in notes
    )
    assert "статус неизвестен" in notes


@pytest.mark.parametrize("lang", LANGS)
def test_a_split_state_is_unknown_with_the_note_and_without_a_claim_of_open(lang):
    p = poi(**CONFLICT, field_sources={"opening_hours_official": SITE})
    c = retrieve([p], *ORIGIN, intent(lang, categories=["cafe"]), NOON).candidates[0]
    assert (c.hours_state, c.hours_issue) == ("unknown", "split")
    rec = template_recs([c], intent(lang, categories=["cafe"]))[0]
    assert rec.hours_state == "unknown"
    assert rec.hours_issue == "split"
    assert rec.confidence != "high"
    assert t("note_hours_split_tail", lang) in rec.notes
    assert t("note_hours_unknown", lang) not in rec.notes  # the conflict note is the explanation
    assert rec.hours_source_url == SITE_URL
    for sentence in (rec.why, rec.what_to_do):
        assert "открыто" not in sentence.lower()
        assert "open at this time" not in sentence.lower()


def test_osm_closed_and_site_open_keeps_the_place_as_unknown_instead_of_dropping_it():
    p = poi(
        opening_hours="Mo-Su 14:00-22:00",
        opening_hours_official="Mo-Su 09:00-21:00",
        hours_conflict=True,
    )
    top = retrieve([p], *ORIGIN, intent(categories=["cafe"]), NOON).candidates
    assert [(c.poi.id, c.hours_state, c.hours_issue) for c in top] == [("p", "unknown", "split")]


@pytest.mark.parametrize("lang", LANGS)
def test_unqualified_site_hours_are_quoted_with_no_days_and_the_state_stays_unknown(lang):
    p = poi(hours_unqualified="с 10:00 до 22:00", field_sources={"hours_unqualified": SITE})
    c = retrieve([p], *ORIGIN, intent(lang, categories=["cafe"]), NOON).candidates[0]
    assert (c.hours_state, c.hours_issue) == ("unknown", "unqualified")
    notes = " ".join(data_notes(c, intent(lang)))
    assert t("note_hours_unqualified", lang, raw="с 10:00 до 22:00") in notes
    assert "с 10:00 до 22:00" in notes
    assert t("note_hours_unknown", lang) not in notes
    rec = template_rec(c, intent(lang), None, [c])
    assert (rec.hours_state, rec.hours_source, rec.hours_source_url) == (
        "unknown",
        "official_site",
        SITE_URL,
    )


def test_the_russian_unqualified_note_reads_as_specified():
    c = cand("unknown", "unqualified", hours_unqualified="с 10:00 до 22:00")
    assert "на сайте: с 10:00 до 22:00, дни не указаны" in " ".join(data_notes(c, intent("ru")))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize(
    ("raw", "quoted"),
    [
        ("работает с 09.00 до 20.00 ч.", "с 09.00 до 20.00 ч."),
        ("Открыто с 10:00 до 22:00", "с 10:00 до 22:00"),
        ("с 10:00 до 22:00", "с 10:00 до 22:00"),
    ],
)
def test_the_quoted_site_hours_never_read_as_a_claim_of_open_beside_an_unknown_state(
    lang, raw, quoted
):
    c = cand("unknown", "unqualified", hours_unqualified=raw)
    notes = " ".join(data_notes(c, intent(lang)))
    assert quoted in notes
    assert not _OPEN_CLAIM.search(notes)


# ---------------------------------------------------------------- the facts of a card


@pytest.mark.parametrize(
    ("lang", "word", "other"),
    [
        ("ru", "официального сайта", "OSM"),
        ("en", "official website", "OSM"),
        ("kk", "ресми сайт", "OSM"),
    ],
)
def test_open_is_attributed_to_the_source_of_the_hours(lang, word, other):
    site = cand("open", opening_hours="Mo-Su 09:00-21:00", field_sources={"opening_hours": SITE})
    said = " ".join(facts(site, intent(lang), None, [site], Trip(5, 30)))
    assert word in said.lower()
    assert other not in said
    osm = cand(
        "open",
        opening_hours="Mo-Su 09:00-21:00",
        field_sources={"opening_hours": {"source": "osm"}},
    )
    assert word not in " ".join(facts(osm, intent(lang), None, [osm], Trip(5, 30))).lower()
    always = cand("open", opening_hours="24/7", field_sources={"opening_hours": SITE})
    assert word in " ".join(facts(always, intent(lang), None, [always], Trip(5, 30))).lower()


# ---------------------------------------------------------------- the website's description


DESCRIPTION = (
    "Lilou Bar — коктейльный бар-бистро с панорамным видом. Работаем ежедневно с 15:00 до 02:00."
)


@pytest.mark.parametrize("lang", LANGS)
def test_the_site_description_is_quoted_with_its_source_and_without_its_hours(lang):
    c = cand(description_official=DESCRIPTION, field_sources={"description_official": SITE})
    what = template_what(c, intent(lang))
    assert (
        t("info_site", lang, text="Lilou Bar — коктейльный бар-бистро с панорамным видом.") in what
    )
    assert "15:00" not in what  # hours are the card's own fields
    assert poi(
        description_official=DESCRIPTION, field_sources={"description_official": SITE}
    ).official_description_credit(lang) == (t("src_official_site", lang), SITE_URL)


def test_without_a_site_description_the_what_to_do_is_as_before():
    what = template_what(cand(address="пр. Республики, 1"), intent("ru"))
    assert "официальн" not in what
    assert "пр. Республики, 1" in what
    assert poi().official_description_credit("ru") is None


def test_the_site_description_counts_as_a_real_description():
    plain, official = poi(), poi(description_official=DESCRIPTION)
    assert not plain.has_real_description()
    assert official.has_real_description()
    assert DESCRIPTION in official.real_text()
    assert plain.real_text() == ""


# ---------------------------------------------------------------- the unbacked-claims stripper


def test_the_site_description_backs_an_attribute_claim_that_no_other_field_states():
    sentence = "Это семейное место: подходит для детей."
    assert strip_unbacked(sentence, cand())[1] == ["kids"]
    backed = cand(description_official="Семейный ресторан для детей и взрослых.")
    assert strip_unbacked(sentence, backed) == (sentence, [])
    view = "С террасы открывается панорамный вид на город."
    assert strip_unbacked(view, cand())[1] == ["viewpoint"]
    assert (
        strip_unbacked(view, cand(description_official="Бар с панорамным видом на Астану."))[1]
        == []
    )


def test_hours_that_came_from_the_site_back_a_round_the_clock_claim():
    sentence = "Работает круглосуточно."
    assert strip_unbacked(sentence, cand("open", opening_hours="Mo-Su 09:00-21:00"))[1] == [
        "round_clock"
    ]
    site = cand("open", opening_hours="24/7", field_sources={"opening_hours": SITE})
    assert strip_unbacked(sentence, site) == (sentence, [])
    late = cand("open", opening_hours="Mo-Su 12:00-24:00", field_sources={"opening_hours": SITE})
    assert strip_unbacked("Открыто допоздна.", late)[1] == []


# ---------------------------------------------------------------- end to end


def _run(pois, monkeypatch, lang="ru"):
    it = intent(lang, categories=["cafe"])
    monkeypatch.setattr(
        pipeline, "parse_intent", lambda *a, **k: IntentResult(intent=it, parser="rules")
    )
    return pipeline.recommend("x", *ORIGIN, NOON, use_llm=False, pois=pois)


def test_a_site_hours_card_says_open_by_the_site_and_exposes_the_page(monkeypatch):
    p = poi(opening_hours="Mo-Su 09:00-21:00", field_sources={"opening_hours": SITE})
    rec = _run([p], monkeypatch).recs[0]
    assert (rec.hours_state, rec.hours_source, rec.hours_source_url) == (
        "open",
        "official_site",
        SITE_URL,
    )
    assert "официального сайта" in rec.why
    assert "OSM" not in rec.why


def test_the_cli_prints_the_source_of_the_hours_and_the_page(tmp_path, monkeypatch, capsys):
    path = tmp_path / "poi.json"
    p = poi(opening_hours="Mo-Su 09:00-21:00", field_sources={"opening_hours": SITE})
    path.write_text(json.dumps([p.model_dump(mode="json")]), encoding="utf-8")
    monkeypatch.setenv("POI_PATH", str(path))
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    argv = ["--lat", str(ORIGIN[0]), "--lon", str(ORIGIN[1]), "--q", "кафе, прогулка 45 минут", "--no-llm",
            "--weather", "off", "--time", "2026-10-14 12:00"]  # fmt: skip
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "данные OSM + официальный сайт" in out
    assert "открыто по данным официального сайта" in out
    assert SITE_URL in out
