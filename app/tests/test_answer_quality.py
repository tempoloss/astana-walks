"""The answer says something real: the model gets a fact sheet per place and every reason must use one of its facts
(filler is asked again once, then the template's own card); the model's opening is used only when code can stand
behind it; a dialogue does not repeat its places; every chip under an answer visibly changes it."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from walks import generate as gen_mod
from walks import llm
from walks.dialog import TurnEnv, new_state, take_turn
from walks.facts import checked_opening, concrete, sheet
from walks.intent import parse_rules
from walks.llm_output import LLMOutput, LLMRec
from walks.models import POI, Candidate, LLMStep
from walks.specific import is_generic, uses_fact
from walks.variety import generic_last, priced_kinds
from walks.walking import offline_router
from walks.weather import make_weather

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
NOON = datetime(2026, 10, 20, 13, 0)


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=kw.pop("name", poi_id),
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        opening_hours=kw.pop("hours", "Mo-Su 10:00-23:00"),
        **kw,
    )


def _cand(p: POI, walk: int = 4, **kw) -> Candidate:
    return Candidate(
        poi=p,
        distance_m=walk * 70,
        walk_min=walk,
        travel_min=walk,
        hours_state="open",
        score=5.0,
        **kw,
    )


def _city() -> list[POI]:
    return [
        _poi(
            "rest1",
            100,
            "restaurant",
            name="Дастархан",
            tags=["cuisine=regional", "outdoor_seating=yes"],
        ),
        _poi("rest2", 160, "restaurant", name="Саксаул", tags=["cuisine=regional"]),
        _poi(
            "cafe1",
            130,
            "cafe",
            name="Кофейня Луч",
            tags=["cuisine=coffee_shop", "internet_access=wlan"],
        ),
        _poi("cafe2", 190, "cafe", name="Пекарня Зерно", tags=["cuisine=pastry"]),
        _poi("ff1", 220, "fast_food", name="Бургер Бар", tags=["cuisine=burger"]),
        _poi("ff2", 260, "fast_food", name="Донер 24", tags=["cuisine=kebab"]),
        _poi("bar1", 120, "bar_nightlife", name="Паб Олд", hours="24/7"),
        _poi("bar2", 200, "bar_nightlife", name="Бар Нью", hours="24/7"),
        _poi("park1", 150, "park_garden", name="Сквер Акжайык"),
        _poi("park0", 60, "park_garden", name="Парк / сквер", name_generated=True),
        _poi("play1", 110, "kids_playground", name="Игровая Радуга"),
        # farther places a longer outing reaches
        _poi("rest_far", 1300, "restaurant", name="Ресторан Дальний", tags=["cuisine=regional"]),
        _poi("cafe_far", 1350, "cafe", name="Кофейня Дальняя", tags=["cuisine=coffee_shop"]),
        _poi("bar_far", 1300, "bar_nightlife", name="Бар Дальний", hours="24/7"),
        _poi(
            "land_far",
            1700,
            "attraction_landmark",
            name="Монумент Дальний",
            tags=["historic=monument"],
        ),
    ]


def _env(**kw) -> TurnEnv:
    return TurnEnv(when=NOON, use_llm=False, router=offline_router(), pois=_city(), **kw)


def _dialogue(*messages, env=None):
    env = env or _env()
    state, out = new_state(*ORIGIN), None
    for m in messages:
        out = take_turn(state, m, env)
        state = out.state
    assert out is not None
    return out


# ---- the fact sheet and the specificity check ---------------------------------------------------------------


def test_the_sheet_holds_the_concrete_facts_of_the_place():
    p = _poi(
        "x",
        50,
        "restaurant",
        name="Саксаул",
        tags=["cuisine=regional", "outdoor_seating=yes", "internet_access=wlan"],
        address="Астана, улица Достык, 5",
        wikipedia={
            "ru": {
                "extract": "Ресторан казахской кухни с бешбармаком и казы.",
                "url": "u",
                "title": "t",
            }
        },
        description_source="wikipedia",
    )
    item = sheet(_cand(p, reasons=["category", "visited"]), "ru", NOON)
    assert item["cuisine"] == "местная"
    assert {"столики на улице", "Wi-Fi"} <= set(item["features"])
    assert item["street"] == "улица Достык, 5"
    assert "бешбармаком" in item["about"]
    assert (
        item["status"] == "Открыто до 23:00"
    )  # the status comes ready from code, the raw schedule does not go
    assert "hours" not in item
    assert "visited" not in item["match"]  # the profile's own reasons never leave the machine


@pytest.mark.parametrize(
    "filler",
    [
        "Это кафе удобно расположено недалеко от вас и открыто в ночное время.",
        "Закажите горячие блюда в уютной обстановке.",
        "Ещё одно близкое кафе с открытыми дверями для позднего визита.",
        "Этот бар отлично подходит для ночного отдыха благодаря удобному расположению.",
        "This cozy cafe offers a welcoming indoor spot to rest.",
        "Another nearby cafe for a late visit.",
    ],
)
def test_the_owner_s_examples_of_filler_are_rejected(filler):
    assert is_generic(filler)


def test_a_reason_must_use_a_fact_of_its_own_place():
    c = _cand(
        _poi(
            "x", 50, "restaurant", name="Саксаул", tags=["cuisine=regional", "outdoor_seating=yes"]
        )
    )
    facts = concrete(c, "ru")
    assert uses_fact("Здесь местная кухня и столики на улице.", facts, c.poi.name)
    assert not uses_fact(
        "Работает до 23:00, успеете поужинать.", facts, c.poi.name
    )  # a status is no fact
    assert not uses_fact(
        "Ресторан «Саксаул» рядом с вами.", facts, c.poi.name
    )  # the name is no fact
    assert not uses_fact("Хорошее место, чтобы поесть.", facts, c.poi.name)


def _rec(poi_id: str, why: str, what: str = "Загляните.") -> LLMRec:
    return LLMRec(
        poi_id=poi_id,
        why=why,
        time_on_site_min=45,
        what_to_do=what,
        confidence="medium",
        generated_idea=False,
    )


class Model:
    """A fake generation chain: returns the queued answers in turn and keeps the payloads it saw."""

    def __init__(self, monkeypatch, *answers: LLMOutput):
        self.answers, self.seen = list(answers), []
        monkeypatch.setattr(gen_mod, "ai_off_reason", lambda use_llm: "")
        monkeypatch.setattr(gen_mod, "generate_json", self.ask)

    def ask(self, prompt, schema, **kw):
        self.seen.append(json.loads(prompt))
        value = self.answers[min(len(self.seen), len(self.answers)) - 1]
        return llm.LLMCall(value, LLMStep(chain=["m"], model="m", ms=5))


def _gen(cands):
    intent = parse_rules("хочу поесть").intent
    return gen_mod.generate(intent, *ORIGIN, cands, NOON, use_llm=True)


def test_a_vague_answer_is_asked_again_once_then_the_template_writes_the_card(monkeypatch):
    cands = [_cand(p) for p in _city()[:2]]
    vague = LLMOutput(
        recommendations=[_rec("rest1", "Отлично подходит для ужина в уютной обстановке.")]
    )
    model = Model(monkeypatch, vague, vague)
    gen = _gen(cands)
    assert len(model.seen) == 2
    assert model.seen[1]["rewrite"] == ["rest1"]
    assert (
        gen.recs[0].text_source == "template"
    )  # still filler: the fact-based card of the template
    assert not is_generic(gen.recs[0].why)


def test_a_specific_second_answer_is_used(monkeypatch):
    cands = [_cand(p) for p in _city()[:2]]
    vague = LLMOutput(recommendations=[_rec("rest1", "Отлично подходит для ужина.")])
    good = LLMOutput(
        recommendations=[
            _rec("rest1", "Местная кухня и столики на улице — можно поужинать на воздухе.")
        ]
    )
    model = Model(monkeypatch, vague, good)
    gen = _gen(cands)
    assert len(model.seen) == 2
    assert gen.recs[0].text_source == "llm"
    assert "столики на улице" in gen.recs[0].why


def test_the_payload_carries_the_sheet_and_a_specific_answer_is_asked_once(monkeypatch):
    cands = [_cand(p) for p in _city()[:2]]
    good = LLMOutput(recommendations=[_rec("rest1", "Местная кухня, а летом — столики на улице.")])
    model = Model(monkeypatch, good)
    _gen(cands)
    assert len(model.seen) == 1
    first = model.seen[0]["candidates"][0]
    assert first["cuisine"] == "местная"
    assert "столики на улице" in first["features"]


def test_the_opening_is_used_only_when_code_can_stand_behind_it():
    cands = [_cand(p) for p in _city()[:3]]
    recs = gen_mod.template_recs(cands[:2], parse_rules("хочу поесть").intent, None)
    first = recs[0].poi.name
    wx = make_weather(3.0, -1.0, pm25=10.0, fetched_at="13:00")
    ok = f"На улице +3, так что поужинать лучше в тепле: «{first}» с местной кухней в 4 минутах."
    assert checked_opening(ok, recs, cands, wx, "ru") == ok
    assert (
        checked_opening(ok.replace("4 минутах", "7 минутах"), recs, cands, wx, "ru") == ""
    )  # a number not in the data
    other = next(c.poi.name for c in cands if c.poi.id not in {r.poi.id for r in recs})
    assert (
        checked_opening(f"«{first}» лучше, чем «{other}».", recs, cands, wx, "ru") == ""
    )  # a place not shown
    assert (
        checked_opening(f"«{first}» отлично подходит для ужина.", recs, cands, wx, "ru") == ""
    )  # filler
    assert (
        checked_opening(f"Try «{first}» for dinner.", recs, cands, wx, "ru") == ""
    )  # another language
    assert (
        checked_opening("Поужинать лучше в тепле.", recs, cands, wx, "ru") == ""
    )  # the first card is not named


def test_the_lead_is_the_model_s_opening_when_it_passes(monkeypatch):
    opening = "Поесть рядом можно в «Дастархан»: местная кухня и столики на улице."
    answer = LLMOutput(
        opening=opening,
        recommendations=[
            _rec("rest1", "Местная кухня и столики на улице."),
            _rec("cafe1", "Wi-Fi и кофе."),
        ],
    )
    Model(monkeypatch, answer)
    turn = _dialogue(
        "хочу поесть",
        env=_env(use_llm=True)
        if False
        else TurnEnv(when=NOON, use_llm=True, router=offline_router(), pois=_city()),
    ).turn
    assert turn.reply.startswith(opening)
    assert "Вы ищете" not in turn.reply


# ---- variety ---------------------------------------------------------------------------------------------------


def test_a_place_shown_before_is_not_offered_again_in_the_dialogue():
    first = _dialogue("хочу поесть")
    seen = {p.id for p in first.turn.places}
    again = take_turn(first.state, "где поесть", _env()).turn
    assert again.places
    assert not seen & {p.id for p in again.places}


def test_an_unnamed_record_comes_after_the_named_places_of_its_kind():
    pois = _city()
    cands = [
        _cand(p) for p in (pois[9], pois[0], pois[8])
    ]  # «Парк / сквер», a restaurant, «Сквер Акжайык»
    order = [c.poi.id for c in generic_last(cands)]
    assert order == ["rest1", "park1", "park0"]


# ---- chips -----------------------------------------------------------------------------------------------------


def test_cheaper_and_pricier_exist_only_where_the_kind_of_place_is_the_lever():
    assert priced_kinds(["restaurant", "cafe", "fast_food"], "low") == ["fast_food", "cafe"]
    assert priced_kinds(["cafe"], "high") == ["restaurant"]
    assert priced_kinds(["bar_nightlife"], "low") == []
    assert priced_kinds(["entertainment"], "low") == []
    bars = _dialogue("хочу в бар").turn
    assert "cheaper" not in {c.id for c in bars.chips}


def test_cheaper_food_changes_the_kind_and_says_there_are_no_prices():
    base = _dialogue("хочу поесть в ресторане")
    assert "cheaper" in {c.id for c in base.turn.chips}
    cheaper = next(c for c in base.turn.chips if c.id == "cheaper")
    out = take_turn(base.state, cheaper.send, _env()).turn
    assert {p.category for p in out.places} <= {"fast_food", "cafe"}
    assert "цен в данных нет" in out.reply.lower()


@pytest.mark.parametrize("text", ["хочу поесть", "хочу кофе", "погулять", "хочу в бар"])
def test_every_chip_under_an_answer_changes_it(text):
    base = _dialogue(text)
    ids = {p.id for p in base.turn.places}
    for chip in [c for c in base.turn.chips if c.kind == "refine"]:
        out = take_turn(base.state, chip.send, _env()).turn
        assert out.kind in {"places", "none_found"}, (chip.id, out.reply)
        assert out.kind == "none_found" or {p.id for p in out.places} != ids, (
            text,
            chip.id,
            out.reply,
        )


def test_closer_never_gives_a_farther_place():
    base = _dialogue("хочу в бар")
    farthest = max(p.walk.distance_m for p in base.turn.places)
    closer = take_turn(base.state, "поближе", _env()).turn
    assert all(p.walk.distance_m <= farthest for p in closer.places)


def test_the_conditions_are_said_once_per_dialogue():
    wx = make_weather(-12.0, -18.0, pm25=10.0, fetched_at="13:00")
    env = TurnEnv(when=None, use_llm=False, router=offline_router(), pois=_city(), weather=wx)
    first = _dialogue("погулять в парке", env=env)
    line = first.state.told
    assert line
    assert line.split(",")[0] in first.turn.reply
    again = take_turn(first.state, "погулять у фонтана", env).turn
    assert line.split(",")[0] not in again.reply


def test_a_kazakh_is_there_question_is_never_a_bar():
    intent = parse_rules("туалет бар ма").intent
    assert intent.categories == ["public_toilet"]
    assert intent.language == "kk"
    assert "bar_nightlife" not in parse_rules("балалар мәзірі бар кафе бар ма").intent.categories


def test_the_kazakh_negator_negates_the_word_before_it_only():
    walk = parse_rules("суық емес болса саябаққа барайық").intent
    assert walk.categories == ["park_garden"]
    assert walk.refused == []
    no_mall = parse_rules("балаларға арналған ойын орны керек, сауда орталығы емес").intent
    assert "mall" in no_mall.refused
    assert "mall" not in no_mall.categories


def test_a_fresh_where_question_about_children_is_a_new_request_not_the_kids_chip():
    from walks.followup import parse_follow_up
    from walks.models import Intent

    cafe = Intent(categories=["cafe"], wished=["cafe"])
    assert parse_follow_up("где поиграть детям в помещении", cafe) is None
    assert (
        parse_follow_up("а если с ребёнком", cafe) is not None
    )  # the chip itself stays a change of the request


def test_closer_puts_the_nearest_place_of_the_kind_shown_first():
    base = _dialogue("хочу в бар")
    closer = take_turn(base.state, "поближе", _env()).turn
    lead = base.turn.places[0].kind
    assert closer.places[0].kind == lead  # «поближе» is a nearer bar, not a nearer café
    for kind in {p.kind for p in closer.places}:
        meters = [p.walk.distance_m for p in closer.places if p.kind == kind]
        assert meters == sorted(meters)


@pytest.mark.parametrize(
    "text",
    [
        "что посмотреть",
        "what should I see",
        "what's worth seeing",
        "не көруге болады",
        "достопримечательности",
    ],
)
def test_what_to_see_is_an_explicit_wish_of_the_sights(text):
    intent = parse_rules(text).intent
    assert set(intent.wished) == {"attraction_landmark", "viewpoint", "museum_gallery"}
    assert "cafe" not in intent.categories


def test_the_sight_the_person_stands_at_comes_first():
    from walks.presets import PRESETS

    turn = take_turn(
        new_state(*PRESETS["Байтерек"], "en"),
        "what should i see",
        TurnEnv(when=NOON, use_llm=False),
    ).turn
    assert turn.places[0].name in {
        "Baiterek",
        "Bayterek",
    }  # the record's English name in an English answer


def test_an_unstated_time_searches_as_far_as_a_90_minute_outing_and_plans_60():
    from walks.pipeline import recommend

    plain = recommend(
        "хочу поесть", *ORIGIN, NOON, use_llm=False, pois=_city(), router=offline_router()
    )
    assert plain.intent.intent.time_budget_min == 60  # the route is planned for the default hour
    assert (
        plain.retrieval.filters.radius_declared_m >= 1000
    )  # ... the choice comes from a 90-minute circle
    stated = recommend(
        "поесть на час", *ORIGIN, NOON, use_llm=False, pois=_city(), router=offline_router()
    )
    near = recommend(
        "поесть недалеко", *ORIGIN, NOON, use_llm=False, pois=_city(), router=offline_router()
    )
    for res in (stated, near):  # a stated time or «недалеко» is the person's own limit
        assert res.retrieval.filters.radius_declared_m < plain.retrieval.filters.radius_declared_m
