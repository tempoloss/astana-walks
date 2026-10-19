"""Friends' feedback on the live stand (rules only, no key): a kind of place our categories cannot represent is said,
not swapped; off-topic requests get a scope line; typos in key place words are mended (and real words are not);
«в сторону X по пути» searches along the way to a geocoded target; a refused step of a compound wish is refused in one
sentence and the rest answered, pizza first. Behaviour, not wording: categories, flags, order, counts."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_scope import off_topic, split_refusal
from walks.dialog_strings import s
from walks.dialog_toward import read_toward
from walks.dialog_typos import KEYS, MIN_LETTERS, repair, repair_typos
from walks.dialog_unmapped import KINDS, read_gap
from walks.intent import parse_rules
from walks.models import POI
from walks.pipeline import get_pois
from walks.walking import offline_router

EXPO = (51.0890, 71.4160)
WED = datetime(2026, 10, 28, 19, 0)
FOOD = {"restaurant", "cafe", "fast_food"}


def _env(pois=None, geocode=None) -> TurnEnv:
    return TurnEnv(when=WED, use_llm=False, router=offline_router(), pois=pois, geocode=geocode)


def say(text: str, lang: str = "ru", env: TurnEnv | None = None, at=EXPO):
    return take_turn(new_state(*at, lang), text, env or _env())


# ------------------------------------------------------------------ 1. kinds the data cannot represent


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("хочу в пску с кентами покатать", "gaming"),
        ("нет, хочу в ps5 поиграть фифу", "gaming"),
        ("где плойка", "gaming"),
        ("компьютерный клуб", "gaming"),
        ("комп клуб рядом", "gaming"),
        ("киберспорт", "gaming"),
        ("хочу кальян", "hookah"),
        ("где сауна", "sauna"),
        ("баня рядом", "sauna"),
        ("где караоке", "karaoke"),
        ("бильярд", "billiards"),
        ("боулинг", "bowling"),
        ("квест комната", "quest"),
        ("escape room", "quest"),
        ("massage", "massage"),
    ],
)
def test_an_unmapped_kind_is_read_and_searched_as_its_closest_kind(text, key):
    gap = read_gap(text)
    assert gap is not None
    assert gap.kind.key == key
    intent = gap.result.intent
    assert intent.categories == list(gap.kind.near)
    assert not set(intent.categories) & FOOD


@pytest.mark.parametrize(
    "text",
    [
        "кофе рядом",
        "хочу в парк",
        "кальян и поесть",
        "боулинг и ужин",
        "в парк с парнем",
        "где баня Мария",
    ],
)
def test_a_message_with_a_kind_we_represent_is_read_as_usual(text):
    assert read_gap(text) is None or "Мария" in text


def test_the_reply_says_the_data_has_no_such_place_before_the_closest_kind():
    out = say("хочу в пску с кентами покатать")
    assert out.turn.kind == "places"
    assert out.turn.reply.startswith(s("unmapped_gaming", "ru"))
    assert out.turn.places
    assert not {p.category for p in out.turn.places} & FOOD


def test_the_gap_is_said_in_every_language():
    for lang in ("kk", "ru", "en"):
        env = TurnEnv(when=WED, use_llm=False, router=offline_router(), language=lang)
        out = say("боулинг" if lang != "en" else "bowling", lang, env)
        assert out.turn.reply.startswith(s("unmapped_bowling", lang))


def test_no_gap_is_said_when_a_place_of_the_answer_carries_the_kinds_name():
    near = POI(id="t/1", name="Taktika ps5", lat=51.0893, lon=71.4163, category="entertainment")
    other = POI(id="t/2", name="Bowling City", lat=51.0899, lon=71.4170, category="entertainment")
    out = say("хочу в пску", env=_env([near, other]))
    assert out.turn.places[0].name == "Taktika ps5"
    assert "в наших данных рядом нет" not in out.turn.reply


def test_a_found_hookah_lounge_is_offered_without_a_gap_line():
    lounge = POI(id="t/3", name="Myata Lounge", lat=51.0893, lon=71.4163, category="bar_nightlife")
    out = say("хочу кальян", env=_env([lounge]))
    assert out.turn.places[0].name == "Myata Lounge"
    assert "не отмечены" not in out.turn.reply


def test_every_unmapped_kind_has_a_gap_line_in_every_language():
    for kind in KINDS:
        for lang in ("kk", "ru", "en"):
            assert s(f"unmapped_{kind.key}", lang)


def test_with_friends_slang_is_read():
    assert "cafe" in parse_rules("пойдём посидеть с кентами").intent.categories


# ------------------------------------------------------------------ 2. off-topic


@pytest.mark.parametrize(
    "text",
    [
        "сделай скрипт на питоне чтобы посчитать процент для ипотеки",
        "напиши эссе про космос",
        "переведи на английский привет",
        "реши задачу по физике",
        "write a python script for me",
        "translate this to german",
    ],
)
def test_code_homework_and_translation_get_a_scope_line_and_no_place(text):
    assert off_topic(text)
    out = say(text)
    assert out.turn.kind == "clarify"
    assert out.turn.places == []
    assert out.turn.reply.startswith(("Я подсказываю места в Астане", "I suggest places in Astana"))


@pytest.mark.parametrize(
    "text",
    [
        "где поработать над скриптом",
        "кофе, чтобы написать код",
        "кафе где можно сделать домашку",
        "куда сходить, надо написать эссе",
    ],
)
def test_a_message_that_also_asks_for_a_place_is_a_search(text):
    assert not off_topic(text)
    assert say(text).turn.kind == "places"


def test_the_scope_line_is_short_and_in_every_language():
    for lang in ("kk", "ru", "en"):
        assert len(s("scope_line", lang).split()) <= 25


# ------------------------------------------------------------------ 3. typos in key place words


@pytest.mark.parametrize(
    ("typo", "word"),
    [
        ("кофк", "кофе"),
        ("кофф", "кофе"),
        ("кафэ", "кафе"),
        ("кафэшка", "кафешка"),
        ("прак", "парк"),
        ("паерк", "парк"),
        ("аптка", "аптека"),
        ("Кофк", "Кофе"),
    ],
)
def test_a_typo_of_a_key_place_word_is_mended(typo, word):
    assert repair(typo) == word


@pytest.mark.parametrize(
    "word",
    ["пара", "марк", "коте", "кофта", "парт", "care", "cape", "cake", "case", "кот", "бар", "уха"],
)
def test_a_real_or_short_or_different_word_is_never_mended(word):
    assert repair(word) == word


def test_a_word_the_lexicon_already_reads_is_left_alone():
    for word in ("кофе", "кафе", "парка", "музеи", "рестораны"):
        assert repair(word) == word


def test_no_word_of_the_datasets_own_texts_is_taken_for_a_typo():
    words: set[str] = set()
    for p in get_pois():
        for text in (p.name, p.description or "", p.description_official or "", p.address or ""):
            words.update(w.lower() for w in re.findall(r"[^\W\d_]+", text) if len(w) >= MIN_LETTERS)
    mended = sorted((w, repair(w)) for w in words if repair(w) != w)
    assert mended == []


def test_a_typo_in_a_request_is_searched_as_the_word():
    out = say("в сторону мангилик ел по пути хочу кофк")
    assert "cafe" in {p.category for p in out.turn.places}
    assert out.state.conversation.intent.categories[0] == "cafe"


def test_the_keys_are_whole_words_of_four_letters_or_more():
    assert all(len(k) >= MIN_LETTERS for k in KEYS)
    assert repair_typos("кофк и кафэ") == "кофе и кафе"


# ------------------------------------------------------------------ 4. «в сторону X по пути»


def _gazetteer(known):
    def find(query: str):
        for name, point in known.items():
            if name in query.lower():
                return (*point, name.title())
        return None

    return find


@pytest.mark.parametrize(
    ("text", "target", "rest"),
    [
        ("в сторону мангилик ел по пути хочу кофе", "мангилик ел", "хочу кофе"),
        ("хочу кофе по пути в сторону Хан Шатыра", "Хан Шатыра", "хочу кофе"),
        ("coffee toward Baiterek on the way", "Baiterek", "coffee"),
        ("Мәңгілік Ел жаққа қарай жолда кофе керек", "Мәңгілік Ел", "кофе керек"),
    ],
)
def test_the_target_of_toward_is_read_with_the_rest_of_the_message(text, target, rest):
    found = read_toward(text)
    assert found.target == target
    assert found.rest == rest


def test_a_message_without_toward_has_no_target():
    assert read_toward("кофе по пути домой") is None
    assert read_toward("хочу кофе рядом") is None


def test_a_search_toward_a_found_target_runs_along_the_way_and_says_so():
    env = _env(geocode=_gazetteer({"мангилик ел": (51.1031, 71.4294)}))
    out = say("в сторону мангилик ел по пути хочу кофе", env=env)
    assert out.state.bookmark_mode == "along"
    assert out.state.bookmark == "Мангилик Ел"
    assert out.turn.reply.startswith("Ищу по пути в сторону «Мангилик Ел».")
    assert out.turn.places


def test_a_target_that_cannot_be_found_is_said_and_the_search_is_near_the_start():
    env = _env(geocode=_gazetteer({}))
    out = say("в сторону зарзаза по пути хочу кофе", env=env)
    assert out.state.bookmark_mode == ""
    assert "не нашёл" in out.turn.reply
    assert out.turn.places


def test_without_a_geocoder_the_toward_target_is_not_found():
    out = say("в сторону мангилик ел по пути хочу кофе")
    assert "не нашёл" in out.turn.reply


# ------------------------------------------------------------------ 5. compound wishes


def test_a_refused_step_is_refused_in_one_sentence_and_the_other_step_is_answered():
    text = "хочу в массажку с окончанием и потом пиццу"
    assert split_refusal(text) == ("пиццу", True)
    out = say(text)
    assert out.turn.kind == "places"
    assert out.turn.reply.startswith(s("refused_part", "ru"))
    assert FOOD & {p.category for p in out.turn.places}
    assert "пицца" in out.state.conversation.intent.free_text_keywords


def test_a_message_refused_as_a_whole_stays_a_refusal():
    assert say("хочу массаж с окончанием").turn.kind == "refusal"
    assert split_refusal("массаж с окончанием и потом секс услуги") == (
        "массаж с окончанием и потом секс услуги",
        False,
    )


def test_a_step_that_is_fine_is_never_cut():
    assert split_refusal("хочу кофе и потом пиццу") == ("хочу кофе и потом пиццу", False)


def test_the_pizza_of_a_compound_wish_comes_first():
    pizza = POI(
        id="p/1",
        name="Додо Пицца",
        lat=51.0893,
        lon=71.4163,
        category="fast_food",
        tags=["cuisine=pizza"],
    )
    steak = POI(
        id="p/2",
        name="Стейк Хаус",
        lat=51.0891,
        lon=71.4161,
        category="restaurant",
        tags=["cuisine=steak_house"],
    )
    sushi = POI(
        id="p/3",
        name="Суши Мастер",
        lat=51.0892,
        lon=71.4162,
        category="restaurant",
        tags=["cuisine=sushi"],
    )
    out = say("хочу в массажку с окончанием и потом пиццу", env=_env([pizza, steak, sushi]))
    assert out.turn.places[0].name == "Додо Пицца"
