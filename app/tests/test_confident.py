"""The rules are confident of a message that only names kinds of places; then no intent model is asked and the answer is
the one the rules' reading prepares (walks.confident, walks.pipeline)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from walks import generate as gen_mod
from walks import intent as intent_mod
from walks import llm
from walks.confident import CONFIDENT_NOTE, rules_confident, same_reading
from walks.intent import parse_rules
from walks.llm_output import LLMOutput, LLMRec
from walks.models import Intent, LLMStep, load_pois
from walks.pipeline import recommend
from walks.presets import PRESETS
from walks.walking import offline_router

FIXTURE = Path(__file__).parent / "fixtures" / "poi_sample.json"

NOON = datetime(2026, 10, 14, 12, 0)
EXPO = PRESETS["EXPO"]


@pytest.mark.parametrize(
    "text",
    [
        "кофе рядом",
        "хочу кофе",
        "аптека рядом",
        "хочу в парк",
        "музей",
        "банкомат рядом",
        "продуктовый магазин рядом",
        "кофе ішкім келеді",
        "дәріхана қайда",
        "coffee nearby",
        "where is a pharmacy",
        "мұражай",
    ],
)
def test_a_message_that_only_names_one_kind_of_place_is_confident(text):
    assert rules_confident(text, parse_rules(text, NOON))


@pytest.mark.parametrize(
    "text",
    [
        "хочу поесть",  # a wish several kinds answer, not a kind's name
        "что посмотреть",
        "what should i see",
        "погулять хочу просто",
        "куда сходить с ребёнком",
        "баламен қайда баруға болады",
        "где поужинать недорого",  # a modifier
        "куда пойти вечером с друзьями",
        "кофе с wifi поработать",
        "a quiet place to read",
        "где погулять с собакой",
        "куда сходить на 2 часа",  # nothing read
        "кофе на 30 минут",  # a stated time
        "не кофе",  # a negation
        "кофе возле парка",  # where the person is
        "кафе рядом с Хан Шатыром",  # a named place
        "кофе на террасе",  # a word the rules do not read
        "кофе с видом",  # a modifier that names another kind
        "супермаркт рядом",  # a typo
        "аптека и банкомат",  # two kinds
        "где поужинать",  # a verb: the model adds the noun («ужин») as a keyword
        "хочу выпить и потанцевать",
    ],
)
def test_a_mood_a_modifier_a_verb_or_an_unread_word_is_not_confident(text):
    assert not rules_confident(text, parse_rules(text, NOON))


def test_the_persons_notes_always_go_to_the_model():
    assert not rules_confident("кофе рядом", parse_rules("кофе рядом", NOON), about="я на коляске")


def test_the_same_reading_allows_only_keywords_that_restate_the_message():
    rules = parse_rules("кофе рядом", NOON).intent
    restated = rules.model_copy(update={"free_text_keywords": ["кофе"]})
    wider = rules.model_copy(update={"categories": ["cafe", "coworking_library"]})
    assert same_reading(rules, restated, "кофе рядом")
    assert not same_reading(rules, wider, "кофе рядом")
    assert not same_reading(
        rules, rules.model_copy(update={"free_text_keywords": ["десерт"]}), "кофе рядом"
    )


class Chains:
    """A live-looking stand: the intent chain answers the rules' draft back unchanged, the generation chain picks the
    first three candidates; both count their calls."""

    def __init__(self, monkeypatch):
        self.intent_calls: list[str] = []
        self.generation_calls = 0
        monkeypatch.setattr(llm, "llm_available", lambda: True)
        monkeypatch.setattr(intent_mod, "generate_json", self.intent)
        monkeypatch.setattr(gen_mod, "generate_json", self.generation)

    def intent(self, prompt, schema, **kw):
        self.intent_calls.append(prompt)
        draft = prompt.split("Draft Intent from the rule parser:\n", 1)[1].split("\n", 1)[0]
        return llm.LLMCall(Intent.model_validate_json(draft), LLMStep(chain=["m"], model="m"))

    def generation(self, prompt, schema, **kw):
        self.generation_calls += 1
        ids = [c["poi_id"] for c in json.loads(prompt)["candidates"]][:3]
        recs = [
            LLMRec(
                poi_id=i,
                why="Кофе здесь варят.",
                time_on_site_min=30,
                what_to_do="Возьмите кофе.",
                confidence="medium",
                generated_idea=False,
            )
            for i in ids
        ]
        return llm.LLMCall(LLMOutput(recommendations=recs), LLMStep(chain=["m"], model="m"))


def _ask(text: str):
    return recommend(
        text, *EXPO, NOON, pois=load_pois(FIXTURE), router=offline_router(), use_llm=True
    )


def test_a_confident_message_asks_no_intent_model_and_keeps_the_answer(monkeypatch):
    chains = Chains(monkeypatch)
    res = _ask("кофе рядом")
    assert chains.intent_calls == []
    assert chains.generation_calls
    assert res.intent.parser == "rules"
    assert CONFIDENT_NOTE in res.intent.note
    monkeypatch.setattr("walks.pipeline.rules_confident", lambda *a, **k: False)
    asked = _ask("кофе рядом")
    assert len(chains.intent_calls) == 1  # without the skip the model reads it, and changes nothing
    assert [r.poi.id for r in asked.recs] == [r.poi.id for r in res.recs]
    assert asked.intent.intent.model_dump() == res.intent.intent.model_dump()


def test_a_message_the_rules_are_not_sure_of_still_goes_to_the_model(monkeypatch):
    chains = Chains(monkeypatch)
    _ask("что посмотреть")
    assert len(chains.intent_calls) == 1
