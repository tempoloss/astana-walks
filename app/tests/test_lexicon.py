"""The rule parser's lexicon (walks.lexicon / lexicon_data) and the demo cache pin (WALKS_CACHE_PIN)."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from walks import generate as gen_mod
from walks import llm
from walks.followup import parse_follow_up
from walks.intent import detect_language, parse_rules, parse_time_budget
from walks.lexicon import match
from walks.lexicon_concepts import CONCEPTS
from walks.lexicon_data import FLAGS
from walks.models import POI, Candidate, Intent, LLMStep

EVENING = datetime(2026, 10, 20, 19, 30)
NOON = datetime(2026, 10, 20, 12, 0)


def cats(text: str, when: datetime | None = None) -> list[str]:
    return parse_rules(text, when).intent.categories


# ---- the lexicon itself ---------------------------------------------------------------------------


def test_lexicon_is_consistent_and_wide():
    names = [c.name for c in CONCEPTS]
    assert len(names) == len(set(names))
    for c in CONCEPTS:
        assert set(c.flags) <= FLAGS, c.name
        assert set(c.unless) <= set(names), c.name
        assert c.tier in {"kind", "mood", "activity"}
        assert c.ru or c.kk or c.en, c.name
    frequent = {
        "coffee",
        "eat_quick",
        "eat_generic",
        "drink_alcohol",
        "sport_gym",
        "kids",
        "cheap",
        "stroll",
    }
    for c in CONCEPTS:
        if c.name in frequent:
            assert min(len(c.ru) - 15, len(c.en) - 12, len(c.kk) - 4) >= 0, c.name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # eat quickly / fully / generically
        ("хочу перекусить", {"fast_food", "cafe"}),
        ("где можно взять шаурму", {"fast_food"}),
        ("a quick bite near me", {"fast_food", "cafe"}),
        ("поужинать в хорошем ресторане", {"restaurant"}),
        ("dinner with a view", {"restaurant"}),
        ("я голодный", {"restaurant", "cafe", "fast_food"}),
        ("i am starving", {"restaurant", "cafe", "fast_food"}),
        ("тамақ жегім келеді", {"restaurant"}),
        # coffee
        ("выпить капучино", {"cafe"}),
        ("где выпить кофе", {"cafe"}),  # «выпить» is not a bar when it is about coffee
        ("a flat white and a croissant", {"cafe"}),
        ("кофе ішкім келеді", {"cafe"}),
        # alcohol, dance
        ("выпить и потанцевать", {"bar_nightlife"}),
        ("хочу в клуб", {"bar_nightlife"}),
        ("craft beer and cocktails", {"bar_nightlife"}),
        ("сыра ішейік", {"bar_nightlife"}),
        # sport
        ("поиграть в футбол или побегать", {"sport", "park_garden"}),
        ("где позаниматься йогой", {"sport"}),
        ("looking for a gym or a pool", {"sport"}),
        ("жаттығу залы керек", {"sport"}),
        # culture, shopping, views, library, kids
        ("сходить на концерт", {"culture_theatre_cinema"}),
        ("хочу в кино", {"culture_theatre_cinema"}),
        ("купить подарок маме", {"mall"}),
        ("shopping mall", {"mall"}),
        ("посмотреть закат", {"viewpoint"}),
        ("где почитать книгу в тишине", {"coworking_library", "cafe"}),
        ("поработать с ноутбуком", {"cafe", "coworking_library"}),
        ("площадка для малыша", {"kids_playground"}),
        # stroll / dog / weather
        ("хочу пройтись и подышать", {"park_garden", "attraction_landmark", "viewpoint"}),
        ("погулять с собакой", {"park_garden"}),
        ("переждать дождь", {"cafe", "museum_gallery", "mall", "coworking_library"}),
        ("it is freezing, somewhere warm to wait out the cold", {"cafe", "museum_gallery", "mall"}),
        ("с девушкой вечером", {"restaurant", "cafe", "viewpoint", "culture_theatre_cinema"}),
        ("халяль", {"restaurant", "cafe", "fast_food"}),
    ],
)
def test_concepts_in_ru_kk_en_map_to_categories(text, expected):
    assert expected <= set(cats(text)), cats(text)


def test_a_named_kind_beats_the_moods():
    # «с ребёнком» alone implies playground / museum; naming a kind replaces that default
    assert cats("с ребёнком") == ["kids_playground", "museum_gallery"]
    assert cats("с ребёнком в кафе") == ["cafe"]
    assert cats("переждать дождь с кофе") == ["cafe"]


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("недорого и быстро", "budget", "low"),
        ("cheap eats", "budget", "low"),
        ("бесплатно погулять", "budget", "low"),
        ("люксовый ресторан", "budget", "high"),
        ("an upscale place", "budget", "high"),
        ("на машине", "mode", "car"),
        ("поеду на автобусе", "mode", "transit"),
        ("by taxi", "mode", "car"),
        ("с коляской", "accessibility", True),
        ("a wheelchair friendly cafe", "accessibility", True),
        ("с малышом", "with_kids", True),
        ("my daughter and I", "with_kids", True),
        ("тихо и спокойно", "quiet", True),
        ("somewhere peaceful", "quiet", True),
        ("с розеткой", "needs_wifi_socket", True),
        ("after midnight", "night", True),
        ("ночью", "night", True),
    ],
)
def test_flags(text, field, value):
    assert getattr(parse_rules(text).intent, field) == value


def test_halal_and_unusual_add_retrieval_keywords():
    assert {"halal", "халяль"} <= set(parse_rules("халяль").intent.free_text_keywords)
    assert "необычн" in parse_rules("что-то необычное").intent.free_text_keywords


def test_hurry_shortens_the_default_time_and_a_stated_time_wins():
    assert parse_rules("быстро перекусить").intent.time_budget_min == 30
    assert parse_rules("быстро перекусить, у меня 2 часа").intent.time_budget_min == 120
    assert parse_rules("перекусить").intent.time_budget_min == 60


def test_fast_with_a_meal_adds_quick_places():
    assert {"fast_food", "cafe"} <= set(cats("быстро пообедать"))
    assert "fast_food" not in cats("пообедать")


# ---- typos ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("кде паесть дешево и быстра", {"restaurant", "cafe", "fast_food"}),
        ("рестаран рядом", {"restaurant"}),
        ("пакушать бы", {"restaurant"}),
        ("коктелй и танцы", {"bar_nightlife"}),
        ("chepest burgr", {"fast_food"}),
        ("a quite resturant", {"restaurant"}),
    ],
)
def test_typos_are_understood(text, expected):
    assert expected <= set(cats(text)), cats(text)


def test_a_typo_is_named_in_the_note_and_exact_words_are_not_flagged():
    note = parse_rules("кде паесть").note
    assert "паесть→поесть" in note
    assert "опечатки" not in parse_rules("поесть").note


@pytest.mark.parametrize(
    "text",
    [
        "подробные детали маршрута",
        "как добраться до вокзала",
        "интересное место на общественном транспорте на 3 часа",
        "победа над собой",
        "Маған жақын жерден тамақ керек",
        "хочу активность на вечер",
        "good review of the place",
    ],
)
def test_ordinary_words_are_not_typos_of_concepts(text):
    res = parse_rules(text)
    assert "опечатки" not in res.note
    assert not set(res.intent.categories) & {"sport", "bar_nightlife", "park_garden", "mall"}
    assert not res.intent.with_kids


def test_short_stems_never_fuzzy_match():
    assert match("барон").active == {}
    assert match("парки").has("park")  # a real inflection, a prefix match


# ---- negation -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "absent"),
    [
        ("поужинать без алкоголя", "bar_nightlife"),
        ("ресторан, no alcohol please", "bar_nightlife"),
        ("dinner without alcohol", "bar_nightlife"),
        ("алкогольсіз кафе", "bar_nightlife"),
        ("безалкогольный бар и ужин", "bar_nightlife"),
        ("не хочу фастфуд, хочу поесть", "fast_food"),
        ("i don't want fast food, just somewhere to eat", "fast_food"),
        ("поесть, только не бургеры", "fast_food"),
        ("погулять, но не в парке", "park_garden"),
    ],
)
def test_negated_kinds_are_excluded(text, absent):
    assert absent not in cats(text)


def test_negation_keeps_the_rest_and_says_so():
    res = parse_rules("не хочу фастфуд, хочу поесть")
    assert res.intent.categories == ["restaurant", "cafe"]
    assert "fast_food" in res.note
    assert cats("не хочу фастфуд, хочу кофе") == ["cafe"]  # a named cafe survives «not fast food»


def test_negated_flags_are_not_set():
    assert not parse_rules("поесть без детей").intent.with_kids
    assert not parse_rules("no kids").intent.with_kids
    assert parse_rules("поесть с детьми").intent.with_kids
    assert parse_rules("не на машине").intent.mode != "car"


def test_not_knowing_is_not_negation():
    assert "restaurant" in cats("не знаю, где поесть")
    assert "restaurant" in cats("не знаю где поужинать")


def test_cheap_phrase_is_not_negated_expensive():
    assert parse_rules("не дорого").intent.budget == "low"
    assert parse_rules("not expensive").intent.budget == "low"


# ---- night inference ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["выпить и потанцевать", "хочу в бар", "drinks and dancing", "в клуб"]
)
def test_drink_or_dance_in_the_evening_is_night(text):
    assert parse_rules(text, EVENING).intent.night
    assert parse_rules(text, datetime(2026, 10, 21, 2, 30)).intent.night  # small hours count too
    assert not parse_rules(text, NOON).intent.night
    assert not parse_rules(text).intent.night  # nothing says it is late


def test_evening_in_the_text_is_enough_without_a_clock():
    assert parse_rules("пива сегодня вечером").intent.night
    assert parse_rules("beer tonight").intent.night
    assert parse_rules("клуб после 22:00").intent.night


def test_evening_alone_is_not_night_and_coffee_in_the_evening_neither():
    assert not parse_rules("с девушкой вечером", EVENING).intent.night
    assert not parse_rules("кофе", EVENING).intent.night
    assert not parse_rules("выпить кофе", EVENING).intent.night


def test_a_bar_ruled_out_does_not_make_night():
    assert not parse_rules("ужин без алкоголя", EVENING).intent.night


# ---- language -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Хочу кофе", "ru"),
        ("Кофе қайда ішуге болады", "kk"),
        ("Маған жақын жерде тыныш кафе керек", "kk"),
        ("серуендегім келеді", "kk"),
        ("жақсы кофехана керек", "kk"),
        ("a quiet cafe", "en"),
        ("Cafe near EXPO", "en"),
        ("хочу в бар", "ru"),  # «бар» is a bar here, not the kazakh «there is»
        ("Рядом с Mega Silk Way, прогулка 30–60 мин", "ru"),
        ("30 минут", "ru"),
        ("", "ru"),
    ],
)
def test_language(text, lang):
    assert detect_language(text) == lang
    assert parse_rules(text).intent.language == lang


# ---- the follow-ups still read through the lexicon -----------------------------------------------


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("а подешевле", "budget", "low"),
        ("немного потише", "quiet", "yes"),
        ("а с розеткой", "wifi_socket", "yes"),
        ("а если с ребёнком", "with_kids", "yes"),
        ("а без ребёнка", "with_kids", "no"),
        ("а без алкоголя", "no_alcohol", True),
        ("алкогольсіз", "no_alcohol", True),
    ],
)
def test_follow_ups_use_the_lexicon(text, field, value):
    fu = parse_follow_up(text, Intent(categories=["bar_nightlife"]))
    assert fu is not None
    assert getattr(fu, field) == value


def test_a_message_naming_a_kind_is_a_new_request_but_a_negated_kind_is_not():
    prev = Intent(categories=["bar_nightlife"])
    assert parse_follow_up("а теперь кофе", prev) is None
    assert parse_follow_up("а без бара", prev) is None  # nothing changes: not a refinement we know


# ---- WALKS_CACHE_PIN ------------------------------------------------------------------------------


def _poi(pid: str) -> Candidate:
    poi = POI(id=pid, name=pid, lat=51.09, lon=71.4, category="cafe")
    return Candidate(
        poi=poi, distance_m=100, walk_min=1, travel_min=1, hours_state="unknown", score=1.0
    )


def test_pin_drops_the_time_bucket_and_the_extras(monkeypatch):
    intent, cands = Intent(categories=["cafe"]), [_poi("a"), _poi("b")]
    normal = gen_mod.cache_material(intent, 51.089, 71.416, cands, NOON, {"k": 1})
    assert normal != gen_mod.cache_material(intent, 51.089, 71.416, cands, EVENING, {"k": 1})
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    pinned = gen_mod.cache_material(intent, 51.089, 71.416, cands, NOON, {"k": 1})
    assert pinned == gen_mod.cache_material(intent, 51.089, 71.416, cands, EVENING, None)
    assert pinned == gen_mod.cache_material(
        intent, 51.0893, 71.4161, cands, datetime(2026, 1, 1), None
    )
    assert pinned != gen_mod.cache_material(intent, 51.090, 71.416, cands, NOON)  # other cell
    assert pinned != gen_mod.cache_material(
        Intent(categories=["park_garden"]), 51.089, 71.416, cands, NOON
    )
    assert pinned != gen_mod.cache_material(
        intent, 51.089, 71.416, cands[:1], NOON
    )  # other candidates


def test_pinned_key_ignores_the_chain_but_not_the_schema():
    k = llm._full_key("m", ["gemini:a"], Intent, pinned=True)
    assert k == llm._full_key("m", ["gemini:b", "openai:x@gw"], Intent, pinned=True)
    assert k != llm._full_key("m", ["gemini:a"], Intent)
    assert llm._full_key("m", ["gemini:a"], Intent) != llm._full_key("m", ["gemini:b"], Intent)


@pytest.fixture
def asked(monkeypatch):
    """generate_json with a scripted model; `calls` counts the requests that reached it."""
    calls: list[str] = []
    monkeypatch.setattr(llm, "_usable", lambda spec: True)
    monkeypatch.setattr(llm, "_skip_reason", lambda spec: (SimpleNamespace(label=spec), None))

    def ask(link, prompt, system, schema, timeout_s):
        calls.append(link.label)
        return Intent(categories=["park_garden"], time_budget_min=45)

    monkeypatch.setattr(llm, "ask", ask)
    return calls


def _call(models=("gemini:a",), key="k"):
    return llm.generate_json(
        "p", Intent, system="s", models=list(models), timeout_s=5, cache_key=key
    )


def test_pinned_cache_replays_through_another_chain(monkeypatch, tmp_path, asked):
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "c.json"))
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    assert not _call().step.cached
    again = _call(("openai:z@gw", "gemini:a"))
    assert again.step.cached
    assert again.value.categories == ["park_garden"]
    assert asked == ["gemini:a"]


def _recording(tmp_path, key_material="k", *, pinned=True):
    path = tmp_path / "demo.json"
    value = Intent(categories=["cafe"], time_budget_min=30)
    key = llm._full_key(key_material, ["gemini:a"], Intent, pinned=pinned)
    path.write_text(
        json.dumps({key: {"model": "gemini:rec", "json": value.model_dump_json(), "label": "x"}}),
        encoding="utf-8",
    )
    return path


def test_demo_recording_is_read_before_the_chain_and_never_written(monkeypatch, tmp_path, asked):
    demo = _recording(tmp_path)
    before = demo.read_text(encoding="utf-8")
    monkeypatch.setenv("WALKS_ENV", "demo")
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    monkeypatch.setenv("WALKS_DEMO_CACHE", str(demo))
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "runtime.json"))
    hit = _call()
    assert hit.step.cached
    assert hit.step.model == "gemini:rec"
    assert hit.value.categories == ["cafe"]
    assert not asked
    miss = _call(
        key="other"
    )  # not recorded: the chain answers and only the runtime cache learns it
    assert not miss.step.cached
    assert asked == ["gemini:a"]
    assert demo.read_text(encoding="utf-8") == before


def test_demo_recording_wins_over_a_runtime_entry_of_the_same_key(monkeypatch, tmp_path, asked):
    """A developer's runtime cache can hold another answer under a pinned key (a live run through another chain):
    the demo must still play what was recorded, or the next recorded step misses and falls to the template."""
    demo = _recording(tmp_path)
    key = llm._full_key("k", ["gemini:a"], Intent, pinned=True)
    runtime = tmp_path / "runtime.json"
    other = Intent(categories=["bar_nightlife"], time_budget_min=90)
    runtime.write_text(
        json.dumps({key: {"model": "gemini:live", "json": other.model_dump_json()}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WALKS_ENV", "demo")
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    monkeypatch.setenv("WALKS_DEMO_CACHE", str(demo))
    monkeypatch.setenv("WALKS_LLM_CACHE", str(runtime))
    hit = _call()
    assert hit.step.model == "gemini:rec"
    assert hit.value.categories == ["cafe"]
    assert not asked


def test_demo_recording_answers_while_google_is_simulated_down(monkeypatch, tmp_path, asked):
    demo = _recording(tmp_path)
    monkeypatch.setenv("WALKS_ENV", "demo")
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    monkeypatch.setenv("WALKS_DEMO_CACHE", str(demo))
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "runtime.json"))
    monkeypatch.setenv("WALKS_SIMULATE_GOOGLE_DOWN", "1")
    assert _call().step.cached
    assert not asked


@pytest.mark.parametrize(
    "env",
    [
        {"WALKS_ENV": ""},  # not the demo environment
        {"WALKS_CACHE_PIN": ""},  # keys would not match anyway: not even read
        {"WALKS_LLM_CACHE": "off"},  # «no cache» means no recording either
        {"WALKS_DEMO_CACHE": "off"},
    ],
)
def test_demo_recording_is_off_outside_the_pinned_demo(monkeypatch, tmp_path, asked, env):
    demo = _recording(tmp_path)
    monkeypatch.setenv("WALKS_ENV", "demo")
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    monkeypatch.setenv("WALKS_DEMO_CACHE", str(demo))
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "runtime.json"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert not _call().step.cached
    assert asked == ["gemini:a"]


def test_offline_ignores_every_cache(monkeypatch, tmp_path, asked):
    demo = _recording(tmp_path)
    monkeypatch.setenv("WALKS_ENV", "demo")
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    monkeypatch.setenv("WALKS_DEMO_CACHE", str(demo))
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    with pytest.raises(llm.LLMUnavailable):  # the guarantee is the template, not the recording
        _call()
    assert not asked


def test_pinned_intent_key_survives_a_parser_change(monkeypatch):
    from walks.intent import intent_cache_key

    a, b = parse_rules("Кофе  рядом").intent, Intent()
    assert intent_cache_key("Кофе  рядом", a) != intent_cache_key("Кофе  рядом", b)
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    assert intent_cache_key("Кофе  рядом", a) == intent_cache_key("кофе рядом", b)


def test_warm_cache_plan_covers_the_five_scenarios_and_six_follow_ups():
    import sys
    from pathlib import Path

    from walks import demo_pin

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import warm_cache

    steps = warm_cache.plan()
    firsts = [s for s in steps if s.base is None]
    # one pinned moment per scenario, not 14:00 and 19:00
    assert {s.text for s in firsts} >= {sc.text for sc in warm_cache.SCENARIOS}
    assert len(firsts) == 5 + len(warm_cache.EXTRA)
    follow = [s for s in steps if s.base]
    assert len(follow) == 6
    assert {s.base for s in follow} <= {s.label for s in firsts}
    night = next(s for s in steps if "ночная" in s.text)
    assert demo_pin.when_for(night.text).hour == 23


# ---- the LLM refinement may not add what the request rules out ---------------------------------------


def _refined(monkeypatch, text, returned_categories):
    from walks import intent as intent_mod

    monkeypatch.setattr(llm, "llm_available", lambda: True)
    answer = Intent(categories=returned_categories, time_budget_min=45)
    monkeypatch.setattr(
        intent_mod,
        "generate_json",
        lambda *a, **kw: llm.LLMCall(answer, LLMStep(chain=["m"], model="m", ms=5)),
    )
    return intent_mod.parse_intent(text)


def test_llm_cannot_add_a_mall_to_a_stroll(monkeypatch):
    res = _refined(monkeypatch, "Рядом с Mega Silk Way, прогулка 30–60 мин", ["mall"])
    assert "mall" not in res.intent.categories
    assert res.intent.categories == ["park_garden", "attraction_landmark", "viewpoint"]
    assert "mall" in res.note
    assert "отброшено" in res.note


def test_llm_additions_that_fit_a_stroll_stay(monkeypatch):
    res = _refined(
        monkeypatch, "прогулка 45 минут", ["mall", "cafe", "bar_nightlife", "museum_gallery"]
    )
    assert res.intent.categories == [
        "park_garden",
        "attraction_landmark",
        "viewpoint",
        "cafe",
        "museum_gallery",
    ]
    assert "mall, bar_nightlife" in res.note


def test_a_kind_the_text_names_is_not_dropped(monkeypatch):
    res = _refined(monkeypatch, "прогулка и шопинг", ["mall"])
    assert "mall" in res.intent.categories  # the rules read «шопинг» themselves
    assert "отброшено" not in res.note


def test_without_a_stroll_the_llm_may_add_a_mall(monkeypatch):
    res = _refined(monkeypatch, "кофе", ["mall"])
    assert res.intent.categories == ["cafe", "mall"]


# ---- class 1: the time the text states, in ru / kk / en --------------------------------------------


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("полчаса", 30),
        ("час", 60),
        ("на часок", 60),
        ("полтора часа", 90),
        ("2 часа", 120),
        ("на 40 минут", 40),
        ("сорок пять минут", 45),
        ("два с половиной часа", 150),
        ("до поезда за час", 60),
        ("жарты сағат", 30),
        ("бір сағат", 60),
        ("екі сағат", 120),
        ("үш сағат", 180),
        ("екі сағаттай", 120),
        ("40 минут", 40),
        ("пойызға дейін бір сағат", 60),
        ("half an hour", 30),
        ("an hour", 60),
        ("2 hours", 120),
        ("90 min", 90),
        ("an hour before my train", 60),
        ("forty five minutes", 45),
        ("в 19 часов", None),
        ("встреча в 7 часов вечера", None),
        ("час пик", None),
    ],
)
def test_stated_time_in_three_languages(text, minutes):
    assert parse_time_budget(text) == minutes


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("между парами", 55),
        ("сабақ арасында", 55),
        ("between classes", 55),
        ("жду поезд", 45),
        ("пойыз күтіп отырмын", 45),
        ("waiting for my train", 45),
        ("быстро перекусить", 30),
        ("с ребёнком", 120),
        ("Турист", 120),
        ("музей", 120),
        ("кофе", 60),
        # a stated time beats every default
        ("между парами, у меня 40 минут", 40),
        ("с ребёнком на час", 60),
        ("с ребёнком, полчаса", 30),
        ("жду поезд, два часа", 120),
        ("turist museum for an hour", 60),
        ("музей на 90 минут", 90),
        # a hurry or a wait outweighs a long visit
        ("быстро с детьми", 30),
        ("жду поезд с ребёнком", 45),
        # the airport reserve applies to a flight only
        ("Турист, 2 часа до вылета", 60),
        ("3 часа до вылета", 120),
        ("2 часа до поезда", 120),
        ("2 hours before my train", 120),
    ],
)
def test_time_budget_precedence(text, minutes):
    assert parse_rules(text).intent.time_budget_min == minutes


# ---- class 2: a name in the query is a location, not a category -----------------------------------


@pytest.mark.parametrize(
    ("text", "absent"),
    [
        ("возле парка Момышулы", "park_garden"),
        ("рядом с парком", "park_garden"),
        ("недалеко от музея", "museum_gallery"),
        ("у музея", "museum_gallery"),
        ("Парк Горького", "park_garden"),
        ("парк имени Момышулы", "park_garden"),
        ("я у ТЦ Mega", "mall"),
        ("Момышулы паркі жанында", "park_garden"),
        ("музей қасында", "museum_gallery"),
        ("паркке жақын", "park_garden"),
        ("near Momyshuly Park", "park_garden"),
        ("near the park", "park_garden"),
        ("at the mall", "mall"),
        ("next to the museum", "museum_gallery"),
        ("Central Park", "park_garden"),
    ],
)
def test_a_named_or_nearby_place_is_not_a_category(text, absent):
    res = parse_rules(text)
    assert absent not in res.intent.categories
    assert "название места в запросе" in res.note


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("кофе возле парка Момышулы", ["cafe"]),
        ("хочу кофе у музея", ["cafe"]),
        ("Момышулы паркі жанында кофе ішкім келеді", ["cafe"]),
        ("a coffee near the mall", ["cafe"]),
        ("парк возле ТЦ", ["park_garden"]),
        ("хочу в парк", ["park_garden"]),
        ("погулять в парке", ["park_garden"]),
        ("в музей", ["museum_gallery"]),
        ("паркке барғым келеді", ["park_garden"]),
        ("take me to a museum", ["museum_gallery"]),
        ("I want to go to the park", ["park_garden"]),
    ],
)
def test_a_wish_stays_a_category_next_to_a_location(text, expected):
    assert parse_rules(text).intent.categories == expected


def test_abbreviations_in_capitals_are_not_names():
    assert cats("хочу в ТЦ") == ["mall"]
    assert (
        cats("Хочу в Парк") == ["park_garden"] or cats("Хочу в Парк") == []
    )  # capitalised, still read


# ---- class 3: waiting contexts, a walk AND food ----------------------------------------------------


@pytest.mark.parametrize(
    "text", ["жду поезд", "жду рейс", "пойыз күтіп отырмын", "waiting for my train"]
)
def test_waiting_gives_a_short_near_indoor_friendly_request(text):
    i = parse_rules(text).intent
    assert i.time_budget_min == 45
    assert {"cafe", "mall"} <= set(i.categories)


@pytest.mark.parametrize(
    "text",
    [
        "погулять и поесть",
        "прогулка и перекусить",
        "серуендеп тамақтанғым келеді",
        "a walk and something to eat",
        "go for a walk and have dinner",
    ],
)
def test_a_walk_and_food_keep_both(text):
    got = set(cats(text))
    assert got & {"restaurant", "fast_food", "cafe"}
    assert {"park_garden", "attraction_landmark", "viewpoint"} <= got


def test_a_walk_to_a_named_place_stays_that_place():
    assert cats("погулять в парке") == ["park_garden"]
    assert cats("Прогулка с ребёнком, площадка") == ["kids_playground"]
    assert cats("прогулка, спортплощадка и бассейн") == [
        "kids_playground",
        "sport",
    ] or "sport" in cats("прогулка, спортплощадка и бассейн")


# ---- class 4: slang and typos for eating -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "жрать хоцца",
        "хавать",
        "пожрать",
        "кушать",
        "поесть",
        "перекусить",
        "кде паесть",
        "пажрать",
        "парекусить",
        "тамақ ішкім келеді",
        "i have the munchies",
    ],
)
def test_eating_slang_and_typos(text):
    assert set(cats(text)) & {"restaurant", "cafe", "fast_food"}, text


# ---- class 5: strollers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "с коляской",
        "гулять с коляской",
        "доступное место для коляски",
        "бала арбасымен",
        "бала арбасы",
        "with a stroller",
        "pram friendly cafe",
        "stroller",
    ],
)
def test_a_stroller_means_a_child_and_step_free(text):
    i = parse_rules(text).intent
    assert i.with_kids
    assert i.accessibility


@pytest.mark.parametrize(
    "text",
    [
        "в инвалидной коляске",
        "в кресле-коляске",
        "я колясочник",
        "мүгедек арбасымен",
        "wheelchair",
        "a wheelchair user",
    ],
)
def test_a_wheelchair_is_step_free_without_a_child(text):
    i = parse_rules(text).intent
    assert i.accessibility
    assert not i.with_kids


def test_a_stroller_does_not_make_a_long_visit():
    assert parse_rules("с коляской").intent.time_budget_min == 60
    assert parse_rules("с ребёнком").intent.time_budget_min == 120
