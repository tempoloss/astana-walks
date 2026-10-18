"""The model reads what the rules cannot (slang, typos, a bare «куда сходить») before anything is asked back, and the
answer opens with the lead: conditions in Astana, what the person wants, the recommendation (every fact from code)."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from walks import dialog_lead, llm
from walks import generate as gen_mod
from walks import intent as intent_mod
from walks.dialog import TurnEnv, new_state, take_turn
from walks.generate import _clean_want
from walks.models import Intent, LLMOutput, LLMRec, LLMStep, Personal
from walks.presets import PRESETS
from walks.walking import offline_router
from walks.weather import make_weather

BAITEREK = PRESETS["Байтерек"]
EVENING = datetime(2026, 10, 14, 19, 0)  # a Wednesday, after the sunset of that day
LANGS = ("kk", "ru", "en")
SLANG = "куда сходить"  # nothing the rules read


def call_of(value) -> llm.LLMCall:
    return llm.LLMCall(value, LLMStep(chain=["m"], model="m", ms=5))


class Models:
    """Fake intent + generation chains that count their calls and keep the prompts they saw."""

    def __init__(self, monkeypatch, intent: Intent | Exception, want: str = ""):
        self.intent_prompts: list[str] = []
        self.gen_prompts: list[str] = []
        self.intent, self.want = intent, want
        monkeypatch.setattr(llm, "llm_available", lambda: True)
        monkeypatch.setattr(intent_mod, "generate_json", self.ask_intent)
        monkeypatch.setattr(gen_mod, "generate_json", self.ask_generation)

    def ask_intent(self, prompt, schema, **kw):
        self.intent_prompts.append(prompt)
        if isinstance(self.intent, Exception):
            raise self.intent
        return call_of(self.intent)

    def ask_generation(self, prompt, schema, **kw):
        self.gen_prompts.append(prompt)
        ids = [c["poi_id"] for c in json.loads(prompt)["candidates"]][:3]
        recs = [
            LLMRec(
                poi_id=i,
                why="Подходит под ваш запрос.",
                time_on_site_min=45,
                what_to_do="Загляните.",
                confidence="medium",
                generated_idea=False,
            )
            for i in ids
        ]
        return call_of(LLMOutput(you_want=self.want, recommendations=recs))


def say(text: str, lang: str = "ru", *, when=EVENING, use_llm=True, weather=None, **kw):
    env = TurnEnv(
        when=when,
        use_llm=use_llm,
        weather=weather or make_weather(12.0, 12.0, pm25=10.0, fetched_at="19:00"),
        router=offline_router(),
        **kw,
    )
    return take_turn(new_state(*BAITEREK, lang), text, env)


# ------------------------------------------------------------------ the model before the clarifying question


def test_a_message_the_rules_cannot_read_goes_to_the_model_once(monkeypatch):
    models = Models(monkeypatch, Intent(categories=["park_garden", "culture_theatre_cinema"]))
    out = say(SLANG)
    assert out.turn.kind == "places"
    assert out.turn.places
    assert out.turn.meta.parser == "rules+llm"
    assert len(models.intent_prompts) == 1  # the reading is reused by the search, never asked twice


def test_the_model_finding_nothing_gives_the_honest_clarify(monkeypatch):
    models = Models(monkeypatch, Intent())
    out = say(SLANG)
    assert out.turn.kind == "clarify"
    assert out.turn.chips
    assert len(models.intent_prompts) == 1
    assert not models.gen_prompts


def test_an_unavailable_model_gives_the_honest_clarify(monkeypatch):
    Models(monkeypatch, llm.LLMUnavailable("down"))
    assert say(SLANG).turn.kind == "clarify"


def test_without_a_model_the_clarify_stays_and_nothing_is_asked(monkeypatch):
    models = Models(monkeypatch, Intent(categories=["park_garden"]))
    assert say(SLANG, use_llm=False).turn.kind == "clarify"
    assert not models.intent_prompts


def test_slang_the_rules_know_is_answered_without_the_model_asking_first(monkeypatch):
    Models(monkeypatch, Intent())
    out = say("Где побухать можно", use_llm=False)
    assert out.turn.kind == "places"
    assert {p.category for p in out.turn.places} <= {"bar_nightlife"}


def test_the_model_can_refuse_what_the_rules_cannot_read(monkeypatch):
    Models(monkeypatch, Intent(refusal="drugs"))
    out = say("где достать запрещённое")
    assert out.turn.kind == "refusal"
    assert not out.turn.places


def test_a_minor_never_gets_bars_from_the_model(monkeypatch):
    Models(monkeypatch, Intent(categories=["bar_nightlife"]))
    out = say("мне 15, куда сходить")
    assert all(p.category != "bar_nightlife" for p in out.turn.places)


def test_a_follow_up_the_rules_read_does_not_call_the_model_first(monkeypatch):
    models = Models(monkeypatch, Intent(categories=["cafe"]))
    first = say("хочу кофе")
    n = len(models.intent_prompts)
    env = TurnEnv(when=EVENING, use_llm=True, router=offline_router(), weather=make_weather(12.0))
    take_turn(first.state, "а поближе?", env)
    assert len(models.intent_prompts) == n  # «поближе» is a change the rules read


# ------------------------------------------------------------------ the lead


@pytest.mark.parametrize("lang", LANGS)
def test_the_template_lead_has_conditions_wish_and_the_pick_with_the_facts(lang):
    text = {"ru": "хочу кофе", "en": "i want coffee", "kk": "кофе ішкім келеді"}[lang]
    out = say(text, lang, use_llm=False, when=None)
    turn = out.turn
    assert turn.kind == "places"
    first = turn.places[0]
    assert first.walk.text in turn.reply
    assert first.name in turn.reply
    assert dialog_lead.lower_first(first.hours.text) in turn.reply
    assert (
        "+12" in turn.reply
    )  # the temperature of the weather it was given, said for the real present
    assert turn.reply.count(". ") <= 1  # one or two sentences


def test_the_lead_says_conditions_wish_and_pick_in_this_order_with_the_models_wish(monkeypatch):
    Models(monkeypatch, Intent(categories=["cafe"]), want="Вы ищете, где выпить кофе")
    out = say(
        "куда пойти на кофе, не знаю",
        weather=make_weather(12.0, 12.0, conditions=["nmu"], pm25=10.0, fetched_at="19:00"),
        when=None,
    )
    reply = out.turn.reply
    assert reply.index("+12") < reply.index("НМУ") < reply.index("Вы ищете, где выпить кофе")
    assert reply.index("Вы ищете, где выпить кофе") < reply.index("советую")
    assert out.turn.places[0].name in reply


def test_the_temperature_is_not_claimed_for_another_hour(monkeypatch):
    out = say("хочу кофе", use_llm=False, weather=make_weather(12.0, 12.0, fetched_at="19:00"))
    assert (
        "+12" not in out.turn.reply
    )  # the time was set by hand: the weather now says nothing about it
    assert "уже темно" in out.turn.reply.lower()  # darkness is about the request's own time


def test_the_wish_the_model_writes_is_checked_before_it_is_shown():
    class P:
        class poi:
            name = "Кофейня Гранд"

    intent = Intent()
    ok = "Вы ищете, где выпить"
    assert _clean_want(ok, [], intent, "") == ok
    for bad in (
        "Вы ищете бар за 5 минут",  # a number is code's
        "Вы ищете «Гранд»",  # quoted
        "Вы ищете кофейню гранд сейчас открыта",  # a place name
        "You are looking for a bar",  # another script
        "Сейчас открыто, идите",  # an hours claim
        "Вы ищете бар. Идите туда",  # two sentences
        "",
    ):
        assert _clean_want(bad, [P], intent, "") == "", bad
    assert (
        _clean_want(
            "Вы ищете тихое место для работы", [], intent, "тихое место для работы мне нужно"
        )
        == ""
    )


def test_the_notes_of_the_user_reach_the_prompts_but_never_the_answer(monkeypatch):
    from walks.profile import Profile

    notes = "я вегетарианец и не люблю громкую музыку"
    monkeypatch.setattr("walks.pipeline.personal_view", lambda profile: Personal(about=notes))
    models = Models(
        monkeypatch,
        Intent(categories=["cafe"]),
        want="Вы ищете место, где вегетарианец и не люблю громкую музыку",
    )
    out = say(SLANG, profile=Profile())
    assert notes in models.gen_prompts[0]
    assert json.loads(models.gen_prompts[0])["user_notes"] == notes
    assert (
        "вегетарианец" not in out.turn.reply
    )  # the echo is dropped, the template composes the wish
    assert out.result is not None
    assert out.result.lead_want == ""


def test_no_notes_no_field(monkeypatch):
    models = Models(monkeypatch, Intent(categories=["cafe"]))
    say("хочу кофе")
    assert "user_notes" not in json.loads(models.gen_prompts[0])
    assert "User notes" not in models.intent_prompts[0]


def test_the_payload_has_no_location_no_raw_hours_no_derived_description(monkeypatch):
    models = Models(monkeypatch, Intent(categories=["cafe"]))
    say("хочу кофе")
    payload = json.loads(models.gen_prompts[0])
    assert "user_location_rounded" not in payload
    for c in payload["candidates"]:
        assert not {"names", "opening_hours", "distance_m", "description_source"} & c.keys()
        assert "Часы работы" not in c.get("description", "")
