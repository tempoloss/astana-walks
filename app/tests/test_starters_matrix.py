"""The starter buttons of the web page, behaviour only (rules, no network, no model): every scenario of the brief in
ru / kk / en, sent from its preset and its own time exactly as web/turns.py sends it, must answer with places in the
language of the request; and each refine chip of the recorded demo (scripts/warm_cache.py FOLLOW_UPS) must still
answer with places after its base scenario, in the three languages."""

from __future__ import annotations

import re
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_questions import place_question
from walks.dialog_strings import STRINGS, s
from walks.dialog_types import Turn
from walks.hours import local_now
from walks.lexicon import is_info_question
from walks.presets import PRESETS, SCENARIOS
from walks.walking import offline_router
from walks.weather import make_weather

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from warm_cache import FOLLOW_UPS

LANGS = ("ru", "kk", "en")
CYRILLIC = re.compile(r"[а-яёәіңғүұқөһА-ЯЁӘІҢҒҮҰҚӨҺ]")
QUOTED_NAME = re.compile(r"[«“][^»”]*[»”]")
# a brand the official site spells with one Cyrillic look-alike inside a Latin word («Өzen»): the site's own letters
MIXED_SCRIPT_WORD = re.compile(r"\b(?=\w*[A-Za-z])(?=\w*[а-яёәіңғүұқөһА-ЯЁӘІҢҒҮҰҚӨҺ])\w+\b")
RUSSIAN_ONLY = re.compile(
    r"[ёэъщЁЭЪЩ]"
)  # letters Kazakh does not use: a Russian sentence in a kk reply has one


def env(at: time | None) -> TurnEnv:
    """The web's env of a starter: the preset's time (None: the pinned clock), unknown weather, no model."""
    when = datetime.combine(local_now().date(), at) if at else None
    return TurnEnv(
        when=when,
        weather=make_weather(fetched_at="12:00"),
        use_llm=False,
        router=offline_router(),
    )


def send(lang: str, scenario_index: int, text: str, state=None):
    sc = SCENARIOS[scenario_index]
    lat, lon = PRESETS[sc.preset]
    state = state or new_state(lat, lon, lang)
    return take_turn(state, text, env(sc.at))


def place_names(turn: Turn) -> list[str]:
    return [p.name for p in turn.places]


def prose(turn: Turn) -> list[str]:
    """What the user reads of a turn, place names and brands left out (they are the data's own words)."""
    out = [turn.reply, turn.notice, *(n.text for n in turn.notices)]
    for p in turn.places:
        out += [p.why, p.what_to_do, p.note, p.hours.text, p.hours.note, p.caveat, p.walk.text]
    out += [c.label for c in turn.chips]
    cleaned = []
    for text in out:
        for name in place_names(turn):
            text = text.replace(name, "")
        cleaned.append(MIXED_SCRIPT_WORD.sub("", QUOTED_NAME.sub("", text)))
    return cleaned


def opener(lang: str) -> str:
    """The words of the reply sentence after the place name, in `lang` («жерінен бастаңыз»)."""
    entry = STRINGS["ld_pick"][("kk", "ru", "en").index(lang)]
    return entry.split("{name}")[1].split(",")[0].strip("» ")


def assert_answers_with_places(turn: Turn, lang: str) -> None:
    assert turn.kind == "places", (turn.kind, turn.reply)
    assert turn.lang == lang
    assert 1 <= len(turn.places) <= 3
    assert [p.primary for p in turn.places].count(True) == 1
    assert turn.places[0].primary
    assert opener(lang) in turn.reply, turn.reply
    if lang == "en":
        stray = [x for x in prose(turn) if CYRILLIC.search(x)]
        assert not stray, stray
    elif lang == "kk":
        stray = [x for x in prose(turn) if RUSSIAN_ONLY.search(x)]
        assert not stray, stray


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("index", range(len(SCENARIOS)), ids=lambda i: f"s{i}")
def test_every_scenario_answers_with_places(index, lang):
    out = send(lang, index, SCENARIOS[index].text_in(lang))
    assert_answers_with_places(out.turn, lang)


def chip_key(ru_send: str) -> str:
    keys = [k[2:] for k, entry in STRINGS.items() if k.startswith("q_") and entry[1] == ru_send]
    assert len(keys) == 1, (ru_send, keys)
    return keys[0]


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize(("ru_send", "index"), FOLLOW_UPS, ids=[f[0] for f in FOLLOW_UPS])
def test_every_follow_up_chip_answers_with_places(ru_send, index, lang):
    base = send(lang, index, SCENARIOS[index].text_in(lang))
    assert_answers_with_places(base.turn, lang)
    follow_up = s(f"q_{chip_key(ru_send)}", lang)  # the `send` of the chip in this language
    out = send(lang, index, follow_up, base.state)
    assert_answers_with_places(out.turn, lang)
    assert out.turn.meta.continued  # read as a refinement of the base answer, not as a new search


@pytest.mark.parametrize(
    "text",
    [
        "2 hours before the flight",
        "I have two hours to kill",
        "a few hours in the city, what to see",
    ],
)
def test_a_length_of_time_in_hours_is_not_a_question_about_opening_hours(text):
    assert place_question(text, allow_kind=True) is None
    assert not is_info_question(text)


@pytest.mark.parametrize("text", ["opening hours?", "what are the hours", "hours of the museum"])
def test_the_word_hours_alone_is_still_a_question_about_a_place(text):
    assert place_question(text, allow_kind=True).topic == "hours"
    assert is_info_question(text)
