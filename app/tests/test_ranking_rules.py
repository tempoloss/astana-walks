"""Ranking rules that must not be bought off by a category bonus: frost / smog shelter rule, diversity within a
score margin, minimum stay vs. default budget, stroll radius and back-fill, holiday honesty of the text, the
request-wide LLM deadline and the jury setup (no key, not offline)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from eval.metrics import _OPEN_CLAIM as EVAL_OPEN_CLAIM
from walks import cli, generate, llm, llm_providers
from walks.envcfg import load_env_file
from walks.generate import pick_diverse, template_recs
from walks.i18n import padding_label, t
from walks.intent import parse_rules
from walks.models import POI, Candidate, Intent, LLMOutput, LLMRec
from walks.pipeline import recommend
from walks.radius import STROLL_TRAVEL_SHARE, TRAVEL_SHARE, is_stroll, reachable_radius_m
from walks.reasons import _OPEN_CLAIM, honest_hours_text
from walks.retrieve import retrieve
from walks.shelter import OUTDOOR_EXCLUDED, has_indoor_signal, is_outdoor_place
from walks.stay import TIGHT_FIT, TIGHT_FIT_MARGIN_MIN, fit_stay_budget
from walks.walking import offline_router
from walks.weather import manual_weather

WED_NOON = datetime(2026, 10, 14, 12, 0)
HOLIDAY_NOON = datetime(2026, 10, 26, 12, 0)  # transferred Republic Day
ORIGIN = (51.0890, 71.4160)
DEG_M = 111_320.0
APP_DIR = Path(__file__).resolve().parents[1]


def _poi(poi_id: str, north_m: float, category: str, name: str | None = None, **kw) -> POI:
    return POI(
        id=poi_id,
        name=name or poi_id,
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        **kw,
    )


def _cand(poi_id: str, category: str, score: float, reasons=(), **kw) -> Candidate:
    return Candidate(
        poi=_poi(poi_id, 100, category, **kw),
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="unknown",
        score=score,
        reasons=list(reasons),
    )


def _ids(res) -> list[str]:
    return [c.poi.id for c in res.candidates]


# ---- 1. frost / smog: parks do not come back through the category bonus ----------------------------


def test_frost_removes_parks_when_an_indoor_place_exists():
    pois = [
        _poi("park", 50, "park_garden"),
        _poi("play", 60, "kids_playground"),
        _poi("cafe", 400, "cafe"),
    ]
    intent = Intent(
        time_budget_min=120, categories=["park_garden", "kids_playground"], with_kids=True
    )
    res = retrieve(pois, *ORIGIN, intent, WED_NOON, weather=manual_weather(-25))
    assert _ids(res) == ["cafe"]  # +6 of category / kids bonus did not save the playground
    assert res.filters.excluded_outdoor == 2
    assert OUTDOOR_EXCLUDED in res.candidates[0].reasons
    why = template_recs(res.candidates, intent, manual_weather(-25))[0].why
    assert "не предлагаем" in why  # the card explains it


def test_smog_removes_outdoor_but_keeps_it_when_nothing_indoor_is_left():
    smog = manual_weather(8, pm25=80)
    intent = Intent(time_budget_min=120, categories=["park_garden"])
    only_park = retrieve([_poi("park", 50, "park_garden")], *ORIGIN, intent, WED_NOON, weather=smog)
    assert _ids(only_park) == ["park"]  # no alternative: kept, with the usual "dress warmly" note
    assert only_park.filters.excluded_outdoor == 0
    both = retrieve(
        [_poi("park", 50, "park_garden"), _poi("mall", 80, "mall")],
        *ORIGIN,
        intent,
        WED_NOON,
        weather=smog,
    )
    assert _ids(both) == ["mall"]


def test_outdoor_landmark_is_dropped_in_frost_like_a_park_when_an_indoor_place_exists():
    mon = _poi("mon", 30, "attraction_landmark", tags=["historic=monument"])
    pois = [mon, _poi("cafe", 500, "cafe")]
    intent = Intent(time_budget_min=120, categories=["attraction_landmark", "cafe"])
    res = retrieve(pois, *ORIGIN, intent, WED_NOON, weather=manual_weather(-25))
    assert _ids(res) == ["cafe"]
    assert res.filters.excluded_outdoor == 1
    assert OUTDOOR_EXCLUDED in res.candidates[0].reasons
    alone = retrieve([mon], *ORIGIN, intent, WED_NOON, weather=manual_weather(-25))
    assert _ids(alone) == [
        "mon"
    ]  # no shelter among the candidates: it stays, with the «dress warmly» note


@pytest.mark.parametrize(
    "tags",
    [
        ["amenity=place_of_worship"],
        ["overture_category=muslim_place_of_worship"],
        ["indoor=area", "tourism=attraction"],
        ["building=yes", "historic=memorial"],
        ["tourism=museum"],
        ["wikidata_class=Q32815"],
    ],
)
def test_landmark_with_an_indoor_signal_stays_in_frost(tags):
    indoor = _poi("in", 30, "attraction_landmark", tags=tags)
    assert has_indoor_signal(indoor)
    pois = [indoor, _poi("cafe", 500, "cafe")]
    intent = Intent(time_budget_min=120, categories=["attraction_landmark", "cafe"])
    res = retrieve(pois, *ORIGIN, intent, WED_NOON, weather=manual_weather(-25))
    assert set(_ids(res)) == {"in", "cafe"}
    assert res.filters.excluded_outdoor == 0


@pytest.mark.parametrize(
    "tags",
    [
        [],
        ["historic=monument"],
        ["tourism=artwork"],
        ["amenity=fountain"],
        ["museum=open_air", "tourism=museum"],
    ],
)
def test_landmark_without_an_indoor_signal_is_outdoors(tags):
    assert not has_indoor_signal(_poi("out", 30, "attraction_landmark", tags=tags))


def test_a_viewpoint_is_outdoors_whatever_its_tags():
    assert is_outdoor_place(_poi("v", 30, "viewpoint", tags=["indoor=yes"]))
    assert not is_outdoor_place(_poi("m", 30, "mall"))


def test_indoor_places_offered_for_a_requested_park_in_frost_are_substituted():
    pois = [
        _poi("park", 50, "park_garden"),
        _poi("cafe", 400, "cafe"),
        _poi("mall", 450, "mall"),
    ]
    frost = manual_weather(-25)
    only_park = Intent(time_budget_min=120, categories=["park_garden"])
    res = retrieve(pois, *ORIGIN, only_park, WED_NOON, weather=frost)
    assert {c.poi.id: c.padding for c in res.candidates} == {
        "cafe": "substituted",
        "mall": "substituted",
    }
    park_or_cafe = Intent(time_budget_min=120, categories=["park_garden", "cafe"])
    res = retrieve(pois, *ORIGIN, park_or_cafe, WED_NOON, weather=frost)
    assert {c.poi.id: c.padding for c in res.candidates} == {"cafe": "none", "mall": "substituted"}
    mild = retrieve(pois, *ORIGIN, only_park, WED_NOON, weather=manual_weather(5))
    assert mild.candidates[0].padding == "none"  # fine weather: the park itself is the answer


def test_a_substituted_card_says_so_in_its_notes_and_badge():
    pois = [_poi("park", 50, "park_garden"), _poi("cafe", 400, "cafe")]
    res = recommend(
        "парк",
        *ORIGIN,
        WED_NOON,
        use_llm=False,
        pois=pois,
        weather=manual_weather(-25),
        router=offline_router(),
    )
    assert [r.padding for r in res.recs] == ["substituted"]
    assert t("note_off_category_weather", "ru") in res.recs[0].notes
    assert padding_label("substituted", "ru") == "другая категория"


def test_a_kids_indoor_centre_is_a_match_not_a_substitute_for_a_playground_in_frost():
    centre = _poi("centre", 100, "entertainment", tags=["leisure=indoor_play"])
    plain = _poi("plain", 120, "entertainment")
    intent = Intent(time_budget_min=120, categories=["kids_playground"], with_kids=True)
    res = retrieve([centre, plain], *ORIGIN, intent, WED_NOON, weather=manual_weather(-25))
    assert {c.poi.id: c.padding for c in res.candidates} == {
        "centre": "none",
        "plain": "substituted",
    }


# ---- 2. pick_diverse follows the score --------------------------------------------------------------


def test_diversity_never_brings_in_a_much_worse_category():
    cands = [
        _cand("c1", "cafe", 4.0),
        _cand("c2", "cafe", 3.8),
        _cand("m1", "mall", 3.5),
        _cand("p1", "park_garden", -6.0),
    ]
    assert [c.poi.id for c in pick_diverse(cands)] == ["c1", "m1", "c2"]


def test_diversity_prefers_a_new_category_within_the_margin():
    cands = [_cand("c1", "cafe", 4.0), _cand("c2", "cafe", 3.9), _cand("m1", "mall", 3.0)]
    assert [c.poi.id for c in pick_diverse(cands)] == ["c1", "m1", "c2"]


def test_diversity_skips_candidates_that_break_a_rule():
    cands = [
        _cand("c1", "cafe", 2.0),
        _cand("p1", "park_garden", 1.9, reasons=["weather_outdoor"]),
    ]
    assert [c.poi.id for c in pick_diverse(cands)] == ["c1"]
    only_bad = [_cand("p1", "park_garden", 1.9, reasons=["weather_outdoor"])]
    assert [c.poi.id for c in pick_diverse(only_bad)] == [
        "p1"
    ]  # nothing else: better than no answer


# ---- 3. minimum stay vs. default budget -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("С ребёнком: площадка или интерактивный музей", 120),
        ("Хочу в музей", 120),
        ("Турист в городе", 120),
        ("Прогулка по набережной", 60),
        ("Тихое кафе с розеткой", 60),
        ("С ребёнком, 45 минут", 45),
    ],
)
def test_default_budget_fits_the_scenario(text, minutes):
    assert parse_rules(text).intent.time_budget_min == minutes


def test_museum_over_the_budget_by_a_little_is_kept_as_tight():
    museum = _cand("m", "museum_gallery", 3.0)  # min stay 60; budget 60 - 2 * 2 min = 56 left
    kept, dropped = fit_stay_budget([museum], 60)
    assert dropped == 0
    assert TIGHT_FIT in kept[0].reasons
    notes = generate.data_notes(kept[0], Intent(time_budget_min=60))
    assert any("Впритык" in n for n in notes)


def test_over_by_more_than_the_margin_is_dropped_and_counted():
    cinema = _cand("c", "culture_theatre_cinema", 3.0)  # min stay 120
    cafe = _cand("k", "cafe", 2.0)
    kept, dropped = fit_stay_budget([cinema, cafe], 120 - TIGHT_FIT_MARGIN_MIN)
    assert [c.poi.id for c in kept] == ["k"]
    assert dropped == 1


def test_excluded_min_stay_is_reported_in_filters():
    pois = [_poi("cin", 100, "culture_theatre_cinema"), _poi("cafe", 120, "cafe")]
    intent = Intent(time_budget_min=60, categories=["culture_theatre_cinema", "cafe"])
    assert retrieve(pois, *ORIGIN, intent, WED_NOON).filters.excluded_min_stay == 1


def test_every_requested_kind_stays_in_the_candidate_list():
    playgrounds = [_poi(f"play{i}", 50 + i, "kids_playground") for i in range(12)]
    museum = _poi("museum", 35, "museum_gallery")
    intent = Intent(
        time_budget_min=120, categories=["museum_gallery", "kids_playground"], with_kids=True
    )
    res = retrieve([*playgrounds, museum], *ORIGIN, intent, WED_NOON)
    assert "museum" in _ids(res)
    assert len(res.candidates) == 10


# ---- 4. stroll radius, widening, back-fill ----------------------------------------------------------


def test_stroll_uses_a_bigger_share_of_the_budget():
    stroll = parse_rules("Рядом с Mega Silk Way, прогулка 30–60 мин").intent
    assert is_stroll(stroll)
    assert not is_stroll(Intent(categories=["cafe"]))
    assert not is_stroll(Intent(categories=["park_garden", "cafe"]))
    pois = [_poi("park", 629, "park_garden")]  # the 629 m park of the brief
    res = retrieve(pois, *ORIGIN, stroll, WED_NOON)
    assert _ids(res) == ["park"]
    assert res.filters.radius_effective_m == reachable_radius_m(
        45, "walk", share=STROLL_TRAVEL_SHARE
    )
    assert res.filters.radius_effective_m > reachable_radius_m(45, "walk", share=TRAVEL_SHARE)


def test_radius_widens_before_other_categories_are_added():
    stroll = Intent(time_budget_min=45, categories=["park_garden"])
    base = reachable_radius_m(45, "walk", share=STROLL_TRAVEL_SHARE)
    pois = [_poi("far-park", base * 1.3, "park_garden"), _poi("cafe", 100, "cafe")]
    res = retrieve(pois, *ORIGIN, stroll, WED_NOON)
    assert res.filters.radius_factor == pytest.approx(1.3)
    assert "far-park" in _ids(res)
    beyond = [_poi("too-far", base * 1.6, "park_garden"), _poi("cafe", 100, "cafe")]
    res = retrieve(beyond, *ORIGIN, stroll, WED_NOON)
    assert res.filters.radius_factor == pytest.approx(1.5)
    assert "too-far" not in _ids(res)


def test_backfill_never_uses_fast_food_bars_or_other_for_a_stroll():
    stroll = Intent(time_budget_min=45, categories=["park_garden", "viewpoint"])
    pois = [
        _poi("park", 300, "park_garden"),
        _poi("ff", 20, "fast_food"),
        _poi("bar", 25, "bar_nightlife"),
        _poi("mall", 30, "mall"),
        _poi("misc", 35, "other"),
        _poi("cafe", 40, "cafe"),
    ]
    res = retrieve(pois, *ORIGIN, stroll, WED_NOON)
    assert res.filters.categories_relaxed
    assert sorted(_ids(res)) == ["cafe", "park"]
    other = Intent(time_budget_min=120, categories=["cafe", "coworking_library"])
    res = retrieve(pois, *ORIGIN, other, WED_NOON)
    assert not {"ff", "bar", "misc"} & set(_ids(res))  # whatever the intent


# ---- 5. holiday honesty -----------------------------------------------------------------------------


def test_open_claim_definition_equals_the_evals():
    assert _OPEN_CLAIM.pattern == EVAL_OPEN_CLAIM.pattern
    assert _OPEN_CLAIM.flags == EVAL_OPEN_CLAIM.flags


def _holiday_card(desc: str, hours: str = "24/7") -> Candidate:
    return Candidate(
        poi=_poi("n", 100, "cafe", opening_hours=hours, description_auto=desc),
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="unknown",
        hours_note="праздник: День Республики",
        score=1.0,
    )


def test_derived_hours_become_usual_hours_on_a_holiday():
    c = _holiday_card("Кафе «X» в Астане. Работает круглосуточно. Возьмите напиток.")
    assert honest_hours_text(c.poi.description_auto, c) == (
        "Кафе «X» в Астане. Обычно: круглосуточно; в праздник часы могут отличаться. "
        "Возьмите напиток."
    )
    c = _holiday_card("Кафе «X». Доступно для колясок, часы работы: Mo-Su,PH 06:50-23:00.", "x")
    assert honest_hours_text(c.poi.description_auto, c) == (
        "Кафе «X». Доступно для колясок, обычно: Mo-Su,PH 06:50-23:00; "
        "в праздник часы могут отличаться."
    )


def test_open_claims_are_stripped_when_hours_are_not_confirmed():
    c = _holiday_card("")
    assert honest_hours_text("Уютное место. Сейчас открыто. Работает до позднего вечера.", c) == (
        "Уютное место."
    )
    open_card = c.model_copy(update={"hours_state": "open", "hours_note": ""})
    assert "открыто" in honest_hours_text("Сейчас открыто.", open_card)
    assert honest_hours_text("Парк на открытом воздухе.", c) == "Парк на открытом воздухе."


def test_holiday_template_and_llm_text_pass_the_eval_check():
    pois = [
        _poi(
            "a",
            100,
            "cafe",
            opening_hours="24/7",
            description_auto="Кафе. Работает круглосуточно.",
        ),
        _poi(
            "b",
            150,
            "cafe",
            opening_hours="Mo-Su 10:00-22:00",
            description_auto="Кафе. Часы работы: Mo-Su 10:00-22:00.",
        ),
    ]
    intent = Intent(time_budget_min=120, categories=["cafe"])
    res = retrieve(pois, *ORIGIN, intent, HOLIDAY_NOON)
    states = {c.poi.id: c.hours_state for c in res.candidates}
    assert states == {
        "a": "open",
        "b": "unknown",
    }  # 24/7 stays open on a holiday; the rest is downgraded
    for r in template_recs(res.candidates, intent):
        assert (
            "часы работы могут отличаться" in r.notes
        )  # the holiday is said in the notes for both
        if r.hours_state != "open":
            assert not EVAL_OPEN_CLAIM.search(" ".join([r.why, r.what_to_do, r.notes]))
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id="b",
                why="Отличное кафе, оно открыто и работает.",
                time_on_site_min=40,
                what_to_do="Выпейте кофе. Открыто круглосуточно.",
                confidence="medium",
                generated_idea=False,
                notes="Работает по графику.",
            )
        ]
    )
    llm_recs, _ = generate._from_llm(out, res.candidates, intent)
    r = llm_recs[0]
    assert not EVAL_OPEN_CLAIM.search(" ".join([r.why, r.what_to_do, r.notes]))


# ---- 6. one time budget for the whole request -------------------------------------------------------


def test_default_generation_chain_drops_the_dead_model():
    chain = llm.DEFAULT_GENERATION_CHAIN
    assert "gemini:gemma-4-31b-it" not in chain
    assert chain[-1] == "gemini:gemma-4-26b-a4b-it"
    assert llm.TOTAL_DEADLINE_S == 15.0


def test_exhausted_deadline_stops_the_chain(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(llm, "_clock", lambda: now[0])
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
    calls: list[str] = []

    def slow_failure(link, prompt, system, schema, timeout_s):
        calls.append(link.model)
        now[0] += 14.5  # the first link ate almost the whole budget, then failed
        raise OSError("slow")

    monkeypatch.setattr(llm, "ask", slow_failure)
    with pytest.raises(llm.LLMUnavailable) as info:
        llm.generate_json(
            "p",
            LLMOutput,
            system="s",
            models=["gemini:a", "gemini:b", "gemini:c"],
            timeout_s=15.0,
            deadline=llm.Deadline(),
        )
    assert calls == ["a"]  # b and c were never started
    assert "бюджет времени запроса исчерпан" in str(info.value)


def test_a_link_gets_at_most_what_is_left_of_the_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(llm, "_clock", lambda: now[0])
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
    seen: list[float] = []

    def ok(link, prompt, system, schema, timeout_s):
        seen.append(timeout_s)
        return LLMOutput(recommendations=[])

    monkeypatch.setattr(llm, "ask", ok)
    deadline = llm.Deadline(15.0)
    now[0] = 10.0  # 5 s left
    llm.generate_json(
        "p", LLMOutput, system="s", models=["gemini:a"], timeout_s=15.0, deadline=deadline
    )
    assert seen == [5.0]
    seen.clear()
    llm.generate_json(
        "p",
        LLMOutput,
        system="s",
        models=["gemini:a"],
        timeout_s=15.0,
        deadline=llm.Deadline(15.0).capped(llm.INTENT_BUDGET_S),
    )
    assert seen == [llm.INTENT_BUDGET_S]


def test_pipeline_gives_one_deadline_to_intent_and_generation(monkeypatch):
    seen = []

    def intent_spy(text, *, use_llm, deadline, when, about=""):
        seen.append(("intent", deadline))
        return parse_rules(text, when)

    real_generate = generate.generate

    def generate_spy(*a, deadline=None, **kw):
        seen.append(("generate", deadline))
        return real_generate(*a, deadline=deadline, **kw)

    monkeypatch.setattr("walks.pipeline.parse_intent", intent_spy)
    monkeypatch.setattr("walks.pipeline.generate", generate_spy)
    recommend("кофе", *ORIGIN, WED_NOON, use_llm=False, router=offline_router())
    assert [k for k, _ in seen] == ["intent", "generate"]
    assert seen[0][1] is seen[1][1]
    assert isinstance(seen[0][1], llm.Deadline)


# ---- 7. jury setup: no key, no key file, no .env.demo, not offline ---------------------------------


def test_cli_without_key_prints_template_recommendations(capsys):
    code = cli.main(
        [
            "--lat",
            "51.089",
            "--lon",
            "71.403",
            "--q",
            "Тихое кафе",
            "--weather",
            "off",
            "--no-walking",
            "--time",
            "2026-10-14 12:00",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "без ИИ (шаблон из данных)" in out
    assert "ИИ не настроен" in out
    assert re.search(r"^1\. ", out, re.M)


def test_missing_env_demo_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("WALKS_ENV", "demo")
    assert load_env_file(tmp_path) is None
