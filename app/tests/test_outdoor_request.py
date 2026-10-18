"""A request that asks for the outdoors (a park, a viewpoint, a playground, an open-air landmark, a dog walk) is answered
outdoors whatever the weather, the air or the darkness: the card says why the walk is better kept short. A generic
request keeps the indoor substitution. The «Как получен ответ» lines name the real driver of each condition and say
whether it moved the choice. A recorded answer that leaves no card with the model's text is asked again on a stand with
live models."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks import dialog, dialog_lead, dialog_strings, llm
from walks import generate as gen_mod
from walks.card_notes import data_notes
from walks.i18n_weather import tw
from walks.llm import LLMCall, LLMUnavailable
from walks.models import (
    POI,
    Intent,
    LLMOutput,
    LLMRec,
    LLMStep,
    WeatherInfo,
    WeatherWarning,
)
from walks.pipeline import recommend
from walks.retrieve import retrieve
from walks.shelter import asks_outdoors
from walks.walking import offline_router
from walks.weather import make_weather
from web import explain as web_explain

AFTERNOON = datetime(2026, 10, 14, 15, 35)
ORIGIN = (51.0890, 71.4160)
DEG_M = 111_320.0
LANGS = ("kk", "ru", "en")
DOG_PARK = "тихий парк для прогулки с собакой"
NMU_NOTICE = WeatherWarning(
    kind="nmu",
    title="НМУ",
    text="Ожидается неблагоприятный режим погоды",
    source_url="https://www.kazhydromet.kz/",
    active=True,
)


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=poi_id,
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        **kw,
    )


def _city() -> list[POI]:
    return [
        _poi("park1", 120, "park_garden"),
        _poi("park2", 220, "park_garden"),
        _poi("park3", 320, "park_garden"),
        _poi("cafe", 150, "cafe"),
        _poi("mall", 200, "mall"),
        _poi("museum", 250, "museum_gallery"),
    ]


def _nmu() -> WeatherInfo:
    """The Kazhydromet notice of unfavourable conditions is active; no PM2.5 and no station report."""
    weather = make_weather(8, 8, 0.0, 0.0, warnings=[NMU_NOTICE], source="met-no")
    assert weather.air_bad
    assert not weather.adverse
    assert weather.pm25 is None
    return weather


def _ask(text: str, weather: WeatherInfo | None, *, language: str | None = None, pois=None):
    return recommend(
        text,
        *ORIGIN,
        AFTERNOON,
        use_llm=False,
        pois=pois or _city(),
        weather=weather,
        router=offline_router(),
        language=language,
    )


# ---- 1. a dog walk stays outdoors ------------------------------------------------------------------


def test_which_requests_ask_for_the_outdoors():
    assert asks_outdoors(Intent(pets=True))  # a dog walk
    assert asks_outdoors(Intent(pets=True, categories=["park_garden"]))
    assert asks_outdoors(Intent(pets=True, categories=["park_garden", "cafe"]))
    assert not asks_outdoors(Intent(pets=True, categories=["cafe"]))  # «кафе с собакой»
    # no pet: an explicit park, a stroll, a playground, a generic or a food request are all substituted indoors
    assert not asks_outdoors(Intent(categories=["park_garden"]))
    assert not asks_outdoors(Intent(categories=["viewpoint", "attraction_landmark"]))
    assert not asks_outdoors(Intent(categories=["kids_playground"], with_kids=True))
    assert not asks_outdoors(Intent())  # «куда сходить»
    assert not asks_outdoors(Intent(categories=["restaurant", "cafe"]))  # «куда поесть»
    assert not asks_outdoors(Intent(categories=["park_garden", "museum_gallery"]))


@pytest.mark.parametrize("lang", LANGS)
def test_a_dog_walk_in_the_park_stays_in_the_park_under_the_nmu_notice(lang):
    res = _ask(DOG_PARK, _nmu(), language=lang)
    assert res.intent.intent.pets
    assert res.retrieval.filters.air_bad
    assert res.retrieval.filters.outdoor_request
    assert res.recs
    assert {r.poi.category for r in res.recs} == {"park_garden"}
    assert {r.padding for r in res.recs} == {"none"}  # not an indoor stand-in
    for r in res.recs:
        assert tw("wx_c_nmu", lang) in r.notes  # the real reason, from the notice
        assert r.time_on_site_min <= 20  # the walk is kept short


def test_the_note_of_a_kept_park_reads_as_a_sentence_in_every_language():
    weather = _nmu()
    for lang, tail in (
        ("ru", "прогулку лучше сократить"),
        ("kk", "серуенді қысқарту жөн"),
        ("en", "better keep the walk short"),
    ):
        res = _ask(DOG_PARK, weather, language=lang)
        assert tail in res.recs[0].notes, (lang, res.recs[0].notes)


def test_a_generic_request_under_the_same_notice_still_moves_indoors():
    res = _ask("куда сходить на 2 часа", _nmu())
    assert not res.retrieval.filters.outdoor_request
    assert res.retrieval.filters.excluded_outdoor == 3  # the three parks
    assert res.recs
    assert all(r.poi.category != "park_garden" for r in res.recs)
    assert all(r.poi.category in {"cafe", "mall", "museum_gallery"} for r in res.recs)


@pytest.mark.parametrize("lang", LANGS)
def test_an_explicit_park_without_a_pet_stays_the_park_and_the_card_names_the_nmu(lang):
    res = _ask("хочу в парк", _nmu(), language=lang)
    assert res.intent.intent.categories == ["park_garden"]
    assert not res.intent.intent.pets
    assert (
        res.retrieval.filters.outdoor_request
    )  # a named park beats the shelter rule: the NMU is advice only
    assert res.recs
    assert all(r.poi.category == "park_garden" for r in res.recs)
    assert all(r.padding == "none" for r in res.recs)
    assert all(tw("wx_c_nmu", lang) in r.notes for r in res.recs)  # the card names the real reason


def test_a_food_request_is_not_an_outdoor_request():
    res = _ask("куда поесть", _nmu())
    assert not res.retrieval.filters.outdoor_request
    assert all(r.poi.category != "park_garden" for r in res.recs)


def test_the_place_a_request_starts_from_is_never_offered_as_where_to_go():
    """ORIGIN is the EXPO starting point: the EXPO record is where the user stands («рядом с EXPO»), not a place to
    walk to. Seen from a kilometre away, the same record is an ordinary candidate."""
    pois = [_poi("EXPO", 300, "attraction_landmark"), _poi("other", 400, "attraction_landmark")]
    intent = Intent(time_budget_min=120, categories=["attraction_landmark"])
    here = retrieve(pois, *ORIGIN, intent, AFTERNOON).candidates
    assert [c.poi.id for c in here] == ["other"]
    away = retrieve(pois, ORIGIN[0] + 0.01, ORIGIN[1], intent, AFTERNOON).candidates
    assert "EXPO" in [c.poi.id for c in away]


def test_another_kind_is_a_violation_while_a_place_of_the_requested_kind_is_left():
    pois = [_poi("park", 150, "park_garden"), _poi("cafe", 100, "cafe"), _poi("mall", 120, "mall")]
    intent = Intent(time_budget_min=120, categories=["park_garden"], pets=True)
    res = retrieve(pois, *ORIGIN, intent, AFTERNOON, weather=_nmu())
    assert res.filters.excluded_outdoor == 0
    assert res.candidates[0].poi.id == "park"
    assert [c.poi.id for c in res.candidates] == [
        "park"
    ]  # a walk is never padded with a café or a mall
    # the code, not the model, keeps the answer to the requested kind
    ask = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id=pid,
                why="Хорошее место.",
                time_on_site_min=30,
                what_to_do="Прогуляйтесь.",
                confidence="medium",
                generated_idea=False,
            )
            for pid in ("cafe", "mall", "park")
        ]
    )
    recs, _ = gen_mod._from_llm(ask, res.candidates, intent, _nmu(), AFTERNOON)
    assert [r.poi.id for r in recs] == ["park"]
    assert [r.poi.id for r in gen_mod.template_recs(res.candidates, intent, _nmu())] == ["park"]


def test_the_closer_park_wins_inside_the_kept_kind():
    pois = [_poi("near", 100, "park_garden"), _poi("far", 450, "park_garden")]
    intent = Intent(time_budget_min=120, categories=["park_garden"], pets=True)
    res = retrieve(pois, *ORIGIN, intent, AFTERNOON, weather=_nmu())
    assert [c.poi.id for c in res.candidates][:2] == ["near", "far"]


def test_a_card_of_a_kept_place_can_be_written_in_any_language_from_the_candidate_alone():
    pois = [_poi("park", 150, "park_garden")]
    intent = Intent(time_budget_min=120, categories=["park_garden"], pets=True)
    weather = _nmu()
    res = retrieve(pois, *ORIGIN, intent, AFTERNOON, weather=weather)
    for lang in LANGS:
        notes = " ".join(
            data_notes(res.candidates[0], intent.model_copy(update={"language": lang}), weather)
        )
        assert tw("wx_c_nmu", lang) in notes


# ---- 2. the «Как получен ответ» lines ---------------------------------------------------------------


def _setting(res, lang="ru") -> str:
    return "\n".join(web_explain._weather_lines(res, lang))


def test_the_air_line_names_the_nmu_notice_and_that_it_moved_the_choice_indoors():
    res = _ask("куда сходить на 2 часа", _nmu())
    text = _setting(res)
    assert "неблагоприятные метеоусловия (НМУ)" in text
    assert "приоритет помещениям" in text
    assert "подбор по воздуху не менялся" not in text
    assert "запрос не удался" not in text


def test_the_air_line_says_the_outdoor_request_was_kept_not_moved():
    res = _ask(DOG_PARK, _nmu())
    air = next(
        line for line in web_explain._weather_lines(res, "ru") if line.startswith("**Воздух")
    )
    assert "неблагоприятные метеоусловия (НМУ)" in air
    assert "оставлено" in air
    assert "приоритет помещениям" not in air
    assert "не менялся" not in air


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_the_lead_names_the_nmu_and_keeps_the_outdoor_request(lang):
    res = _ask(DOG_PARK, _nmu(), language=lang)
    clauses, drives = dialog_lead.conditions(res, lang, show_temp=False)
    assert any("НМУ" in c or "NMU" in c for c in clauses), clauses
    assert drives
    tail = dialog_lead._tail(res, drives, lang, set())
    assert tail == dialog_strings.s("ld_walk_short", lang)
    assert "indoor places first" not in tail
    assert "в помещении" not in tail


def test_the_air_line_names_smoke_and_haze_and_the_pm25_value_apart():
    haze = make_weather(8, 8, 0.0, 0.0, conditions=["smog"], source="metar")
    res = _ask("куда сходить на 2 часа", haze)
    assert "дым или дымка" in _setting(res)
    measured = make_weather(8, 8, 0.0, 0.0, pm25=80)
    res = _ask("куда сходить на 2 часа", measured)
    assert "PM2.5 80" in _setting(res)
    assert "приоритет помещениям" in _setting(res)


def test_the_weather_line_names_the_users_own_words_when_nothing_was_measured():
    res = _ask("куда сходить, холодно", None)
    assert res.weather is not None
    assert res.weather.temperature_c is None
    weather_line = web_explain._weather_lines(res, "ru")[0]
    assert "по вашим словам, холодно" in weather_line
    assert "не менялся" not in weather_line


def test_the_dark_line_says_whether_the_outdoors_was_kept():
    dark = make_weather(10, 10, 0.0, 0.0, pm25=5, force_dark=True)
    kept = _ask(DOG_PARK, dark)
    assert "оставлено" in web_explain._weather_lines(kept, "ru")[2]
    generic = _ask("куда сходить на 2 часа", dark)
    assert "ниже в рейтинге" in web_explain._weather_lines(generic, "ru")[2]


# ---- 3. an unusable recording on a stand with live models ---------------------------------------------


def _rec(poi_id: str, why: str, what: str) -> LLMRec:
    return LLMRec(
        poi_id=poi_id,
        why=why,
        time_on_site_min=30,
        what_to_do=what,
        confidence="medium",
        generated_idea=False,
    )


class Chain:
    """Stands in for walks.llm.generate_json: the first answer comes from the cache, a later uncached call from a model."""

    def __init__(self, monkeypatch, cached: LLMOutput, live: LLMOutput | Exception):
        self.cached, self.live, self.calls = cached, live, []
        monkeypatch.setattr(llm, "llm_available", lambda: True)
        monkeypatch.setattr(gen_mod, "generate_json", self)

    def __call__(self, prompt, schema, **kw):
        self.calls.append(kw["cache_key"])
        if kw["cache_key"] is not None:
            return LLMCall(self.cached, LLMStep(chain=["m"], model="recorded", cached=True))
        if isinstance(self.live, Exception):
            raise self.live
        return LLMCall(self.live, LLMStep(chain=["m"], model="live"))


def _candidates(intent: Intent):
    pois = [_poi("c1", 100, "cafe"), _poi("c2", 250, "cafe"), _poi("c3", 400, "cafe")]
    return retrieve(pois, *ORIGIN, intent, AFTERNOON).candidates


def _answer(texts: tuple[str, str], ids: list[str]) -> LLMOutput:
    return LLMOutput(recommendations=[_rec(i, *texts) for i in ids])


RUSSIAN = ("Хорошее место, чтобы посидеть.", "Закажите кофе.")
ENGLISH = ("A good place to sit.", "Order a coffee.")
INTENT = Intent(time_budget_min=120, categories=["cafe"], language="ru")


def _generate(candidates, intent=INTENT):
    return gen_mod.generate(intent, *ORIGIN, candidates, AFTERNOON)


def test_a_recording_in_the_wrong_language_is_not_used_and_the_models_are_asked_once(monkeypatch):
    cands = _candidates(INTENT)
    ids = [c.poi.id for c in cands]
    chain = Chain(monkeypatch, cached=_answer(ENGLISH, ids), live=_answer(RUSSIAN, ids))
    g = _generate(cands)
    assert len(chain.calls) == 2
    assert chain.calls[0] is not None
    assert chain.calls[1] is None  # the second ask bypasses the cache
    assert g.retry == "live"
    assert g.model == "live"
    assert g.step is not None
    assert not g.step.cached
    assert g.recs
    assert all(r.text_source == "llm" for r in g.recs)
    assert all("чтобы посидеть" in r.why for r in g.recs)
    assert not any("place to sit" in r.why for r in g.recs)


def test_replay_only_keeps_the_template_and_never_asks_again(monkeypatch):
    monkeypatch.setenv("WALKS_REPLAY_ONLY", "1")
    cands = _candidates(INTENT)
    ids = [c.poi.id for c in cands]
    chain = Chain(monkeypatch, cached=_answer(ENGLISH, ids), live=_answer(RUSSIAN, ids))
    g = _generate(cands)
    assert len(chain.calls) == 1
    assert g.retry == ""
    assert g.recs
    assert all(r.text_source == "template" for r in g.recs)
    assert not any("place to sit" in r.why for r in g.recs)


def test_a_failed_second_ask_keeps_the_recorded_cards_and_says_so(monkeypatch):
    cands = _candidates(INTENT)
    ids = [c.poi.id for c in cands]
    chain = Chain(monkeypatch, cached=_answer(ENGLISH, ids), live=LLMUnavailable("down"))
    g = _generate(cands)
    assert len(chain.calls) == 2
    assert g.retry == "failed"
    assert g.recs
    assert all(r.text_source == "template" for r in g.recs)


def test_a_recording_about_places_no_longer_among_the_candidates_is_asked_again(monkeypatch):
    """The data moved under a recording (a merged record, a new candidate list): none of its ids is a candidate today,
    so on a stand with live models the chain is asked once more instead of ending in the template."""
    cands = _candidates(INTENT)
    ids = [c.poi.id for c in cands]
    chain = Chain(monkeypatch, cached=_answer(RUSSIAN, ["node/gone"]), live=_answer(RUSSIAN, ids))
    g = _generate(cands)
    assert len(chain.calls) == 2
    assert g.retry == "live"
    assert g.mode == "llm"
    assert all(r.text_source == "llm" for r in g.recs)


def test_a_usable_recording_is_used_and_a_fresh_wrong_language_answer_is_not_asked_twice(
    monkeypatch,
):
    cands = _candidates(INTENT)
    ids = [c.poi.id for c in cands]
    chain = Chain(monkeypatch, cached=_answer(RUSSIAN, ids), live=_answer(ENGLISH, ids))
    g = _generate(cands)
    assert len(chain.calls) == 1
    assert g.retry == ""
    assert all(r.text_source == "llm" for r in g.recs)
    # a model's own (uncached) answer in the wrong language is the template, and is not retried
    monkeypatch.setattr(
        gen_mod,
        "generate_json",
        lambda *a, **kw: LLMCall(_answer(ENGLISH, ids), LLMStep(chain=["m"], model="m")),
    )
    g = _generate(cands)
    assert g.retry == ""
    assert all(r.text_source == "template" for r in g.recs)


def test_the_english_answer_is_written_in_english(monkeypatch):
    intent = INTENT.model_copy(update={"language": "en"})
    cands = _candidates(intent)
    ids = [c.poi.id for c in cands]
    chain = Chain(monkeypatch, cached=_answer(RUSSIAN, ids), live=_answer(ENGLISH, ids))
    g = _generate(cands, intent)
    assert len(chain.calls) == 2
    assert g.retry == "live"
    assert all(r.text_source == "llm" and "place to sit" in r.why for r in g.recs)


def test_the_retry_is_in_meta_and_in_the_explain_block(monkeypatch):
    pois = [_poi("c1", 100, "cafe"), _poi("c2", 250, "cafe"), _poi("c3", 400, "cafe")]
    ids = [p.id for p in pois]
    Chain(monkeypatch, cached=_answer(ENGLISH, ids), live=_answer(RUSSIAN, ids))
    res = recommend(
        "кофе",
        *ORIGIN,
        AFTERNOON,
        pois=pois,
        weather=None,
        router=offline_router(),
        language="ru",
    )
    assert res.generation == "llm"
    assert res.generation_retry == "live"
    assert dialog._meta(res, "").generation_retry == "live"
    lines = web_explain._generation_lines(res, "ru")
    assert any("Записанный ответ не подошёл" in line and "заново" in line for line in lines)
