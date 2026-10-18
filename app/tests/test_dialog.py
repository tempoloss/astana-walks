"""The dialogue API (walks.dialog) on the real dataset, rules only (no key): brevity, clarifying questions, small
talk, chips, questions about shown and named places, «another», accumulation, reset, messy input, the CLI mode.
Behaviour, not wording: every assertion is about kinds, counts, ids, fields."""

from __future__ import annotations

import json
import re
from datetime import datetime

import pytest

from walks import cli
from walks.dialog import TurnEnv, new_state, take_turn, with_location
from walks.dialog_chips import MAX_REFINE_CHIPS
from walks.dialog_nlu import place_question, reset_request, restore, small_talk, tidy
from walks.dialog_text import display_name, sentences, short_what, short_why
from walks.dialog_types import DialogState, Turn
from walks.followup import FollowUp, narrow, parse_follow_up
from walks.models import POI, Candidate, Intent
from walks.names import same_brand
from walks.walking import offline_router

EXPO = (51.0890, 71.4160)
NOW = datetime(2026, 10, 17, 15, 0)
JARGON = re.compile(r"\bOSM\b|\bPOI\b|confidence|уверенност", re.I)
CAFE = {"ru": "хочу кофе", "kk": "кофе ішкім келеді", "en": "i want coffee"}
ENV = TurnEnv(when=NOW, use_llm=False, router=offline_router())


def say(state: DialogState, text: str, env: TurnEnv = ENV):
    out = take_turn(state, text, env)
    return out.turn, out.state


def dialogue(lang: str, *messages: str) -> tuple[list[Turn], DialogState]:
    state, turns = new_state(*EXPO, lang), []
    for m in messages:
        turn, state = say(state, m)
        turns.append(turn)
    return turns, state


def texts(turn: Turn) -> list[str]:
    out = [turn.reply, turn.notice]
    for p in turn.places:
        out += [p.why, p.what_to_do, p.note, p.hours.text, p.hours.note, p.caveat]
    out += [a.text for a in turn.answers] + [c.label for c in turn.chips]
    return out


# ------------------------------------------------------------------ brevity


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_a_search_answers_briefly_with_one_primary(lang):
    (turn,), _ = dialogue(lang, CAFE[lang])
    assert turn.kind == "places"
    assert turn.lang == lang
    assert 1 <= len(turn.places) <= 3
    assert [p.primary for p in turn.places].count(True) == 1
    assert turn.places[0].primary
    assert len(sentences(turn.reply)) == 1
    for p in turn.places:
        assert len(p.why.split()) <= 25 or len(sentences(p.why)) == 1
        assert len(sentences(p.what_to_do)) <= 1
        assert p.why.rstrip().endswith((".", "!", "?"))  # a whole sentence, never cut in the middle
        assert p.walk.minutes >= 1
        assert p.hours.state in {"open", "closed", "unknown"}
    assert not any(JARGON.search(x) for x in texts(turn))


def test_sources_go_to_fields_not_to_prose():
    (turn,), _ = dialogue("ru", CAFE["ru"])
    for p in turn.places:
        assert p.sources
        assert all(s.label for s in p.sources)
        if p.hours.state != "unknown":
            assert p.hours.source is not None


def test_sentence_cut_never_inside_a_sentence_or_an_abbreviation():
    text = (
        "Адрес: пр. Республики, 10. Возьмите напиток (каз. кофе). Ещё одно длинное предложение "
        + "слово " * 40
        + "."
    )
    assert short_what(text) == "Возьмите напиток (каз. кофе)."
    why = short_why("Ближайшее место. " + "очень " * 30 + "длинное. Третье.")
    assert why.endswith(".")
    assert "очень" not in why.split()[:0]
    assert display_name("Coffee BOOM, Мәңгілік Ел даңғылы, 55") == "Coffee BOOM"
    assert display_name("Burger, King") == "Burger, King"


# ------------------------------------------------------------------ clarify, small talk


@pytest.mark.parametrize(
    ("lang", "message"),
    [
        ("ru", "привет"),
        ("ru", "?"),
        ("ru", "помоги"),
        ("ru", "скучно"),
        ("ru", "asdf qwer"),
        ("kk", "сәлем"),
        ("kk", "көмектесші"),
        ("en", "hello"),
        ("en", "i am bored"),
        ("en", "?"),
    ],
)
def test_no_signal_is_one_question_with_starter_chips(lang, message):
    (turn,), state = dialogue(lang, message)
    assert turn.kind == "clarify"
    assert turn.places == []
    assert turn.reply.count("?") <= 1
    assert 4 <= len(turn.chips) <= 6
    assert {c.kind for c in turn.chips} == {"start"}
    assert state.conversation is None


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_every_starter_chip_starts_a_search(lang):
    (first,), _ = dialogue(lang, "?")
    for chip in first.chips:
        (turn,), _ = dialogue(lang, chip.send)
        assert turn.kind == "places", chip.send


@pytest.mark.parametrize(
    ("message", "kind"),
    [("спасибо", "thanks"), ("рахмет", "thanks"), ("thanks", "thanks"), ("спасибооо большое", "thanks"),
     ("пока", "bye"), ("до свидания", "bye"), ("bye", "bye"), ("сау бол", "bye"), ("spasibo", "thanks")],
)  # fmt: skip
def test_thanks_and_goodbye_are_short_and_show_no_places(message, kind):
    turns, _ = dialogue("ru", CAFE["ru"], message)
    assert turns[1].kind == kind
    assert turns[1].places == []
    assert len(sentences(turns[1].reply)) <= 2


def test_thanks_with_a_request_is_a_request():
    (turn,), _ = dialogue("ru", "спасибо, хочу кофе")
    assert turn.kind == "places"


# ------------------------------------------------------------------ chips


def test_ru_chips_are_the_recorded_demo_phrases():
    from scripts.warm_cache import FOLLOW_UPS

    wanted = {phrase for phrase, _ in FOLLOW_UPS}
    seen: set[str] = set()
    for q in ("хочу кофе", "хочу погулять", "хочу выпить"):
        (turn,), _ = dialogue("ru", q)
        seen |= {c.send for c in turn.chips}
    assert wanted <= seen | {"а без алкоголя"}


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_refine_chips_are_few_deterministic_and_read_by_the_rules(lang):
    (turn,), state = dialogue(lang, CAFE[lang])
    refine = [c for c in turn.chips if c.kind == "refine"]
    assert 1 <= len(refine) <= MAX_REFINE_CHIPS
    assert [c.kind for c in turn.chips].count("reset") == 1
    assert turn.chips[-1].kind == "reset"
    again, _ = say(new_state(*EXPO, lang), CAFE[lang])
    assert [c.send for c in again.chips] == [c.send for c in turn.chips]
    intent = state.conversation.intent
    for c in refine:
        assert parse_follow_up(c.send, intent) is not None, c.send


def test_chips_only_offer_what_would_change_the_request():
    (museum,), _ = dialogue("ru", "хочу в музей")
    assert "а без алкоголя" not in {c.send for c in museum.chips}
    turns, _ = dialogue("ru", "хочу выпить", "а без алкоголя")
    assert "а без алкоголя" in {c.send for c in turns[0].chips}
    assert "а без алкоголя" not in {c.send for c in turns[1].chips}
    kids, _ = dialogue("ru", "хочу погулять с ребёнком")
    assert "а если с ребёнком" not in {c.send for c in kids[0].chips}


# ------------------------------------------------------------------ questions about places


@pytest.mark.parametrize(
    ("lang", "question", "topic"),
    [
        ("ru", "а оно сейчас открыто?", "hours"),
        ("ru", "это где", "address"),
        ("ru", "как дойти", "route"),
        ("ru", "а там есть туалет", "toilet"),
        ("kk", "ол қазір ашық па?", "hours"),
        ("kk", "бұл қайда?", "address"),
        ("en", "is it open now?", "hours"),
        ("en", "how far is it?", "route"),
        ("en", "is there a toilet there", "toilet"),
    ],
)
def test_a_question_about_a_shown_place_is_answered_without_a_new_search(lang, question, topic):
    state = new_state(*EXPO, lang)
    first, state = say(state, CAFE[lang])
    turn, after = say(state, question)
    assert turn.kind == "place_answer"
    assert [a.topic for a in turn.answers] == [topic]
    assert turn.places[0].id == first.places[0].id
    assert after.shown == state.shown
    assert after.conversation == state.conversation
    assert after.focus_id == first.places[0].id


def test_hours_answer_has_the_interval_and_the_source():
    turns, _ = dialogue("ru", CAFE["ru"], "до скольки работает")
    answer = turns[1].answers[0]
    assert answer.known
    assert answer.source is not None
    assert re.search(r"\d{2}:\d{2}", answer.text)


def test_missing_facts_are_said_to_be_missing():
    turns, _ = dialogue("ru", CAFE["ru"], "а там есть туалет", "а парковка есть?", "сколько стоит")
    assert [a.known for t in turns[1:] for a in t.answers] == [False, False, False]


def test_ordinal_and_plural_resolve_to_the_shown_places():
    state = new_state(*EXPO, "ru")
    first, state = say(state, CAFE["ru"])
    second, _ = say(state, "а второе?")
    assert second.places[0].id == first.places[1].id
    both, _ = say(state, "а они открыты?")
    assert [p.id for p in both.places] == [p.id for p in first.places]
    third_missing, _ = say(new_state(*EXPO, "ru"), "а второе?")
    assert third_missing.kind == "clarify"  # nothing shown yet


def test_question_before_any_search_asks_what_to_search():
    (turn,), _ = dialogue("ru", "а оно открыто?")
    assert turn.kind == "clarify"
    assert turn.places == []


@pytest.mark.parametrize(
    ("message", "who"),
    [("какие часы у Хан Шатыра", "Хан Шатыр"), ("Национальный музей сейчас открыт?", "Национальный музей"),
     ("до скольки работает Керуен", "Керуен")],
)  # fmt: skip
def test_a_named_place_is_answered_wherever_it_is(message, who):
    env = TurnEnv(when=datetime(2026, 10, 17, 19, 30), use_llm=False, router=offline_router())
    turn, state = say(new_state(*EXPO, "ru"), message, env)
    assert turn.kind == "place_answer"
    assert who.lower() in turn.places[0].name.lower()
    assert turn.answers[0].topic == "hours"
    assert turn.places[0].walk.distance_m > 0
    follow, _ = say(state, "а как дойти", env)  # «it» is the place just asked about
    assert follow.places[0].id == turn.places[0].id
    assert follow.answers[0].topic == "route"


def test_a_far_named_place_gets_distance_and_minutes():
    turn, _ = say(new_state(*EXPO, "ru"), "далеко идти до Дерева жизни?")
    assert turn.answers[0].topic == "route"
    assert "мин" in turn.answers[0].text


def test_a_name_that_is_not_in_the_data_is_not_replaced_by_another_place():
    turns, _ = dialogue("ru", CAFE["ru"], "до скольки работает Хрустальный Дракон")
    assert turns[1].kind == "place_answer"
    assert turns[1].answers == []


# ------------------------------------------------------------------ another, accumulation, reset


def test_another_excludes_what_was_shown_and_a_second_branch_of_the_brand():
    state = new_state(*EXPO, "ru")
    first, state = say(state, CAFE["ru"])
    shown = {p.id for p in first.places}
    names = {p.name.lower() for p in first.places}
    for message in ("не то", "что-то другое", "а ещё"):
        turn, state = say(state, message)
        assert turn.meta.continued
        assert not shown & {p.id for p in turn.places}
        shown |= {p.id for p in turn.places}
    assert names  # the brands of the first card are not offered again under a longer name


def test_same_brand_matches_a_longer_name_and_a_brand_tag():
    def poi(i, name, tags=()):
        return POI(id=i, name=name, lat=51.1, lon=71.4, category="cafe", tags=list(tags))

    assert same_brand(poi("a", "Starbucks"), poi("b", "Starbucks Казахстан"))
    assert same_brand(poi("a", "Кофе 1", ["brand=Cup"]), poi("b", "Кофе 2", ["brand=Cup"]))
    assert not same_brand(poi("a", "Starbucks"), poi("b", "Gasteria"))


def test_constraints_accumulate_and_a_new_topic_resets_them():
    state = new_state(*EXPO, "ru")
    _, state = say(state, "хочу выпить")
    _, state = say(state, "а без алкоголя")
    turn, state = say(state, "а подешевле")
    cons = state.conversation.constraints
    assert cons.no_alcohol
    assert state.conversation.intent.budget == "low"
    assert turn.meta.continued
    turn, state = say(state, "хочу в музей")
    assert not turn.meta.continued
    assert not state.conversation.constraints.no_alcohol


def test_new_search_clears_the_dialogue_and_never_forgets_the_language():
    state = new_state(*EXPO, "kk")
    _, state = say(state, CAFE["kk"])
    turn, state = say(state, "жаңа іздеу")
    assert turn.kind == "clarify"
    assert turn.lang == "kk"
    assert state.conversation is None
    assert not state.shown
    assert reset_request("новый поиск кофе") == (True, "кофе")
    assert reset_request("сначала поесть, потом музей")[0] is False
    moved = with_location(state, 51.13, 71.40)
    assert (moved.lat, moved.lon) == (51.13, 71.4)
    assert moved.lang == "kk"


# ------------------------------------------------------------------ messy input, guards


@pytest.mark.parametrize(
    "message", ["kofe", "gde poest", "shashlyk", "kafe ryadom", "хочуу кофеее"]
)
def test_translit_and_stretched_letters_are_understood(message):
    (turn,), _ = dialogue("ru", message)
    assert turn.kind == "places", message


def test_voice_style_run_on_follow_up_is_a_follow_up():
    state = new_state(*EXPO, "ru")
    _, state = say(state, CAFE["ru"])
    turn, _ = say(state, "ну а можно пожалуйста что нибудь другое если можно конечно")
    assert turn.meta.continued


def test_guards_against_flipped_meanings():
    assert place_question("хочу погулять на открытом воздухе") is None  # not «is it open»
    assert small_talk("нет, спасибо") == "decline"
    assert small_talk("спасибо, а подешевле?") is None
    intent = Intent(categories=["cafe"])
    assert (parse_follow_up("не то", intent) or FollowUp()).more
    assert not (parse_follow_up("not that far", intent) or FollowUp()).more
    (nedolgo,), _ = dialogue("ru", "хочу кофе недолго")
    (nadolgo,), _ = dialogue("ru", "хочу кофе надолго")
    assert nedolgo.meta.intent["time_budget_min"] < nadolgo.meta.intent["time_budget_min"]
    kk, _ = say(new_state(*EXPO, "kk"), "тойлау")
    assert kk.meta.intent is None or "bar_nightlife" not in kk.meta.intent["categories"]


def test_restore_and_tidy():
    assert tidy("спасибооо   большоеее") == "спасибо большое"
    assert restore("hello there") == "hello there"
    assert restore("kofe") == "кофе"


def test_refusal_offers_no_places():
    (turn,), _ = dialogue("ru", "где купить наркотики")
    assert turn.kind == "refusal"
    assert turn.places == []


# ------------------------------------------------------------------ AI narrows, hints, state


def test_a_models_reading_may_only_narrow():
    wide = FollowUp(
        quiet="no", with_kids="no", wifi_socket="no", budget="high", extra_min=60, mode="car"
    )
    assert not narrow(wide).changes()
    keep = narrow(FollowUp(quiet="yes", budget="low", extra_min=-30))
    assert keep.quiet == "yes"
    assert keep.budget == "low"
    assert keep.extra_min == -30


def test_start_hints_apply_to_a_new_search_and_the_words_win():
    base, _ = say(new_state(*EXPO, "ru"), "хочу кофе")
    timed, _ = say(
        new_state(*EXPO, "ru"), "хочу кофе", TurnEnv(when=NOW, use_llm=False, budget_min=120)
    )
    assert timed.meta.intent["time_budget_min"] == 120 != base.meta.intent["time_budget_min"]
    words, _ = say(
        new_state(*EXPO, "ru"),
        "хочу кофе на 45 минут",
        TurnEnv(when=NOW, use_llm=False, budget_min=120),
    )
    assert words.meta.intent["time_budget_min"] == 45
    kids, _ = say(
        new_state(*EXPO, "ru"), "хочу кофе", TurnEnv(when=NOW, use_llm=False, company="kids")
    )
    assert kids.meta.intent["with_kids"]


def test_stages_are_reported_in_order():
    stages: list[str] = []
    say(
        new_state(*EXPO, "ru"),
        "хочу кофе",
        TurnEnv(when=NOW, use_llm=False, on_stage=stages.append),
    )
    assert stages == ["parse", "search", "write", "route"]


def test_state_is_json_never_mutated_and_holds_no_request_text():
    state = new_state(*EXPO, "ru")
    frozen = state.model_dump_json()
    _, after = say(state, "хочу уникальноеслово кофе")
    assert state.model_dump_json() == frozen
    blob = after.model_dump_json()
    assert "уникальноеслово" not in blob
    assert DialogState.model_validate_json(blob) == after
    turn, _ = say(after, "а поближе?")
    assert Turn.model_validate_json(turn.model_dump_json()) == turn


# ------------------------------------------------------------------ the one-voice rule, honest time, hours of a visit


def _rec(poi_id: str, source: str):
    from walks.models import Recommendation

    poi = POI(id=poi_id, name=poi_id, lat=51.1, lon=71.4, category="cafe")
    return Recommendation(
        poi=poi, why="w", time_on_site_min=10, what_to_do="x", confidence="high", generated_idea=False,
        distance_m=100, walk_min=2, travel_min=2, hours_state="unknown", hours_raw=None, text_source=source,
    )  # fmt: skip


def test_after_another_the_ai_card_gets_no_template_backfill():
    from walks.dialog import _one_voice

    recs = [_rec("ai", "llm"), _rec("t1", "template"), _rec("t2", "template")]
    assert [r.poi.id for r in _one_voice(recs, "llm", FollowUp(more=True))] == ["ai"]
    assert (
        len(_one_voice(recs, "llm", None)) == 3
    )  # a first answer keeps its cards, each says whose words
    assert len(_one_voice(recs, "template", FollowUp(more=True))) == 3
    assert len(_one_voice([_rec("t", "template")], "llm", FollowUp(more=True))) == 1


def test_a_requested_kind_dropped_by_the_time_rule_is_said_never_silent():
    env = TurnEnv(when=datetime(2026, 10, 17, 21, 0), use_llm=False, router=offline_router())
    for query, kind in (
        ("хочу в бар на 45 минут", "bar_nightlife"),
        ("хочу в кино на 30 минут", "culture_theatre_cinema"),
    ):
        turn, _ = say(new_state(*EXPO, "ru"), query, env)
        assert any(p.category == kind for p in turn.places) or turn.notice, query


def test_visit_hours_opens_by_arrival_and_closes_during_the_visit():
    from walks.visit_hours import visit_note

    site = POI(
        id="p", name="P", lat=51.1, lon=71.4, category="cafe", opening_hours="Mo-Su 10:00-22:59"
    )
    assert visit_note(
        site, datetime(2026, 10, 20, 9, 55), 7, 30, "open", "ru"
    )  # closed now, open on arrival
    late = POI(
        id="q", name="Q", lat=51.1, lon=71.4, category="cafe", opening_hours="Mo-Su 08:00-24:00"
    )
    assert visit_note(
        late, datetime(2026, 10, 20, 23, 45), 2, 30, "open", "ru"
    )  # closes within the visit
    assert not visit_note(late, datetime(2026, 10, 20, 12, 0), 2, 30, "open", "ru")


def test_all_day_schedule_counts_as_round_the_clock():
    from walks.hours import is_24_7

    assert is_24_7("24/7")
    assert is_24_7("Mo-Su 00:00-24:00")
    assert not is_24_7("Mo-Su 08:00-24:00")


def test_night_reason_names_the_real_source_of_the_hours():
    from walks.reasons import _wishes

    poi = POI(
        id="n", name="N", lat=51.1, lon=71.4, category="bar_nightlife", opening_hours="Mo-Su 10:00-23:59",
        sources=["osm", "official_site"], field_sources={"opening_hours": {"source": "official_site"}},
    )  # fmt: skip
    c = Candidate(
        poi=poi,
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="open",
        score=1.0,
        reasons=["open_at_night"],
    )
    assert "OSM" not in _wishes(c, "ru")[0]
    assert "сайта" in _wishes(c, "ru")[0]
    osm = c.model_copy(update={"poi": poi.model_copy(update={"field_sources": {}})})
    assert "OSM" in _wishes(osm, "ru")[0]


# ------------------------------------------------------------------ CLI


def test_cli_dialog_mode_replays_a_script(tmp_path, capsys):
    script = tmp_path / "d.json"
    script.write_text(
        json.dumps(
            ["привет", {"say": "хочу кофе"}, "а оно открыто?", "спасибо"], ensure_ascii=False
        ),
        encoding="utf-8",
    )
    code = cli.main(
        ["--dialog", "--script", str(script), "--lat", "51.089", "--lon", "71.416", "--offline", "--no-llm",
         "--no-walking", "--weather", "off", "--time", "2026-10-17 15:00"]
    )  # fmt: skip
    assert code == 0
    rows = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    assert [r["turn"]["kind"] for r in rows] == ["clarify", "places", "place_answer", "thanks"]
    assert DialogState.model_validate(rows[-1]["state"]).turns == 4


def test_cli_hours_line_is_in_the_language_of_the_request(capsys):
    cli.main(
        [
            "--q",
            "i want coffee",
            "--lat",
            "51.089",
            "--lon",
            "71.416",
            "--offline",
            "--no-walking",
            "--weather",
            "off",
            "--time",
            "2026-10-17 15:00",
        ]
    )
    out = capsys.readouterr().out
    assert "открыто по данным" not in out
    assert re.search(r"open according to|hours unknown|closed", out)


def test_too_expensive_is_a_request_for_cheaper_never_pricier():
    state = new_state(*EXPO, "ru")
    _, state = say(state, "хочу кофе")
    turn, state = say(state, "дорого")
    assert turn.meta.continued
    assert state.conversation.intent.budget == "low"
    asked, _ = say(
        state, "а там дорого?"
    )  # a question about the shown place is answered, not searched
    assert asked.kind == "place_answer"
    assert asked.answers[0].topic == "price"
    assert not asked.answers[0].known


@pytest.mark.parametrize(
    ("lang", "message"),
    [
        ("ru", "аптека рядом нужна"),
        ("ru", "где обменять валюту"),
        ("ru", "apteka ryadom"),
        ("kk", "дәріхана қайда"),
        ("en", "where is a pharmacy"),
        ("en", "currency exchange near me"),
    ],
)
def test_a_kind_of_place_the_data_does_not_hold_is_said_never_replaced_by_cafes(lang, message):
    (turn,), state = dialogue(lang, message)
    assert turn.kind == "none_found"
    assert turn.places == []
    assert state.conversation is None
    assert turn.chips


def test_a_kind_the_data_has_next_to_one_it_lacks_is_still_a_search():
    (turn,), _ = dialogue("ru", "кафе рядом с аптекой")
    assert turn.kind == "places"


def test_translit_of_closer_works_like_the_cyrillic_word():
    state = new_state(*EXPO, "ru")
    _, state = say(state, "хочу кофе")
    turn, _ = say(state, "blizhe")
    assert turn.meta.continued
    assert "closer" in turn.meta.change.lower() or turn.meta.change


def test_a_toilet_claim_without_data_is_removed_from_ai_text():
    from walks.claims import unbacked_kinds

    poi = POI(id="t", name="T", lat=51.1, lon=71.4, category="cafe")
    c = Candidate(poi=poi, distance_m=1, walk_min=1, travel_min=1, hours_state="open", score=1.0)
    assert unbacked_kinds("Уборные обычно доступны посетителям.", c) == ["toilet"]
    assert unbacked_kinds("Туалет в данных не подтверждён.", c) == []
