"""«Поиск по вайбу»: the facets of a place come from its record (kind, tags, hours, texts, encyclopedia entries) and
from the marks of people, each with the data that said it; a person's vibe re-ranks, never filters; «под мой вайб»
searches across kinds; without a vibe every answer is exactly what it was; the free text is read by a typed model
judgment or, without a model, by a small lexicon."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from walks import generate as gen_mod
from walks import llm, vibe_judge
from walks.dialog import TurnEnv, new_state, take_turn
from walks.feedback import FeedbackEntry, FeedbackIndex
from walks.llm import LLMCall, LLMUnavailable
from walks.llm_output import LLMOutput, LLMRec
from walks.models import POI, Intent, LLMStep, PeopleEvidence, Personal
from walks.pipeline import get_pois
from walks.profile import Profile, list_items, personal_view, preferences_payload
from walks.retrieve import retrieve
from walks.vibe import (
    asks_vibe,
    evidence_of,
    focused,
    place_evidence,
    stated_vibe,
    strengths,
    vibe_bonus,
    vibe_line,
    vibe_match,
)
from walks.vibe_data import FACETS
from walks.vibe_judge import VibeReading, read_vibe, rules_reading, weights_of
from walks.vibe_turn import take_vibe_turn
from walks.walking import offline_router

ORIGIN = (51.1283, 71.4305)  # Байтерек
DEG_M = 111_320.0
DAY = datetime(2026, 10, 20, 15, 0)  # a Tuesday afternoon, before dark
INTRO = Profile(vibe={"calm": 1.0, "nature": 1.0, "culture": 0.5})
EXTRO = Profile(vibe={"lively": 1.0, "night": 1.0, "unusual": 0.5})
INTRO_TEXT = "люблю тишину, книги и парки, не люблю толпы"
EXTRO_TEXT = "люблю тусовки, музыку и новые места"

NAMES = {
    "park": "Жеруйык",
    "library": "Кітапхана",
    "museum": "Мұражай",
    "monument": "Ескерткіш",
    "quiet_cafe": "Деирмен",
    "noisy_cafe": "Креперия",
    "plain_cafe": "Коктем",
    "bar": "Лилу",
    "karaoke": "Джимми",
    "mall": "Керуен",
    "escape": "Квеструм",
    "night_cafe": "Каганат",
}


def _poi(pid: str, category: str, tags=(), north_m: float = 100.0, hours: str | None = None, **kw):
    return POI(
        id=pid,
        name=kw.pop("name", NAMES.get(pid, pid)),
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        tags=list(tags),
        opening_hours=hours,
        **kw,
    )


def _city() -> list[POI]:
    return [
        _poi("park", "park_garden", ["leisure=park"], 250, "24/7"),
        _poi("library", "coworking_library", ["amenity=library"], 300, "Mo-Su 09:00-20:00"),
        _poi("museum", "museum_gallery", ["tourism=museum"], 350, "Tu-Su 10:00-18:00"),
        _poi("monument", "attraction_landmark", ["historic=monument"], 180, "24/7"),
        _poi("quiet_cafe", "cafe", ["amenity=cafe"], 200, "Mo-Su 08:00-22:00"),
        _poi("noisy_cafe", "cafe", ["amenity=cafe"], 150, "Mo-Su 08:00-22:00"),
        _poi("plain_cafe", "cafe", ["amenity=cafe"], 100, "Mo-Su 08:00-22:00"),
        _poi("bar", "bar_nightlife", ["amenity=bar"], 220, "Mo-Su 12:00-02:00"),
        _poi(
            "karaoke",
            "bar_nightlife",
            ["overture_category=karaoke_venue"],
            260,
            "Mo-Su 14:00-04:00",
        ),
        _poi("mall", "mall", ["shop=mall"], 400, "Mo-Su 10:00-22:00"),
        _poi("escape", "entertainment", ["leisure=escape_game"], 300, "Mo-Su 10:00-23:00"),
    ]


def _mark(pid: str, signal: str, day: str = "2026-10-19") -> FeedbackEntry:
    return FeedbackEntry(poi_id=pid, signal=signal, date=day, weekday="mon", hour_bucket="day")


MARKS = FeedbackIndex(
    [
        *(_mark("quiet_cafe", "quiet", day) for day in ("2026-10-19", "2026-10-18")),
        *(_mark("noisy_cafe", "noisy", day) for day in ("2026-10-19", "2026-10-18")),
    ]
)


def _env(profile: Profile | None, pois=None) -> TurnEnv:
    return TurnEnv(
        when=DAY,
        use_llm=False,
        router=offline_router(),
        pois=pois if pois is not None else _city(),
        profile=profile,
        feedback=MARKS,
    )


def _ask(text: str, profile: Profile | None, pois=None):
    return take_vibe_turn(new_state(*ORIGIN), text, _env(profile, pois)).turn


# ---- 1. the facets of a place, from its record -----------------------------------------------------------


def test_a_park_is_nature_and_calm_by_its_kind():
    ev = place_evidence(_poi("p", "park_garden", ["leisure=park"]))
    assert strengths(ev) == {"nature": 1.0, "calm": 0.5}
    assert {e.source for e in ev} == {"kind:park"}


def test_a_library_is_calm_and_a_bit_of_culture():
    assert strengths(place_evidence(_poi("l", "coworking_library", ["amenity=library"]))) == {
        "calm": 1.0,
        "culture": 0.5,
    }


def test_a_bar_open_after_midnight_is_nightlife_by_its_kind_and_its_hours():
    ev = place_evidence(_poi("b", "bar_nightlife", ["amenity=bar"], hours="Mo-Su 12:00-02:00"))
    assert strengths(ev) == {"night": 1.0, "lively": 1.0}
    assert {e.source for e in ev if e.facet == "night"} == {"kind:bar", "late"}


@pytest.mark.parametrize(
    ("category", "tags"),
    [
        ("cafe", ["amenity=cafe"]),
        ("cafe", ["amenity=cafe", "cuisine=coffee_shop"]),
        ("restaurant", ["amenity=restaurant"]),
        ("fast_food", ["amenity=fast_food"]),
    ],
)
@pytest.mark.parametrize("hours", ["Mo-Su 08:00-01:00", "Mo-Su 08:00-00:00", "24/7"])
def test_a_meal_place_open_late_is_no_nightlife(category, tags, hours):
    ev = place_evidence(_poi("c", category, tags, hours=hours))
    assert "night" not in strengths(ev)
    assert not {e.source for e in ev} & {"late", "allday"}


def test_late_hours_are_nightlife_for_a_bar_a_cinema_or_entertainment_only():
    cinema = place_evidence(
        _poi("k", "culture_theatre_cinema", ["amenity=cinema"], hours="Mo-Su 10:00-02:00")
    )
    assert strengths(cinema) == {"culture": 0.5, "night": 1.0}
    assert {e.source for e in cinema if e.facet == "night"} == {"late"}
    games = place_evidence(
        _poi("e", "entertainment", ["leisure=escape_game"], hours="Mo-Su 10:00-00:00")
    )
    assert strengths(games)["night"] == 0.5
    allday = place_evidence(_poi("b", "entertainment", ["leisure=bowling_alley"], hours="24/7"))
    assert {e.source for e in allday if e.facet == "night"} == {"allday"}
    theatre = place_evidence(
        _poi("t", "culture_theatre_cinema", ["amenity=theatre"], hours="Mo-Su 10:00-23:30")
    )
    assert "night" not in strengths(theatre)  # an evening performance, not a night out
    early = place_evidence(
        _poi("k2", "culture_theatre_cinema", ["amenity=cinema"], hours="Mo-Su 10:00-21:00")
    )
    assert "night" not in strengths(early)
    shop = place_evidence(_poi("s", "grocery", ["shop=convenience"], hours="24/7"))
    assert shop == ()  # an errand open all night is no night out


def test_a_plain_cafe_claims_neither_quiet_nor_noise():
    have = strengths(place_evidence(_poi("c", "cafe", ["amenity=cafe", "cuisine=coffee_shop"])))
    assert have == {"food": 1.0}
    first = place_evidence(_poi("c", "cafe", ["amenity=cafe", "cuisine=coffee_shop"]))[0]
    assert first.source == "kind:coffee"  # the more telling kind is the one a card names


def test_the_marks_of_people_make_a_place_calm_or_lively():
    cafe = _poi("c", "cafe", ["amenity=cafe"])
    quiet = evidence_of(cafe, PeopleEvidence(quiet=2, noise="quiet"))
    assert strengths(quiet)["calm"] == 1.0
    assert {e.source for e in quiet if e.facet == "calm"} == {"people"}
    noisy = evidence_of(cafe, PeopleEvidence(noisy=2, noise="noisy", demo=True))
    assert {e.source for e in noisy if e.facet == "lively"} == {"people_demo"}
    mixed = evidence_of(cafe, PeopleEvidence(quiet=1, noisy=1, noise="mixed"))
    assert "calm" not in strengths(mixed)
    assert "lively" not in strengths(mixed)


def test_an_encyclopedia_entry_and_a_guide_entry_are_their_own_evidence():
    museum = _poi(
        "m",
        "museum_gallery",
        ["tourism=museum"],
        wikipedia={"ru": {"title": "Музей", "url": "https://ru.wikipedia.org/wiki/x"}},
        sources=["osm", "wikivoyage"],
    )
    ev = place_evidence(museum)
    assert {e.source for e in ev if e.facet == "culture"} == {"kind:museum", "wiki"}
    assert {e.source for e in ev if e.facet == "unusual"} == {"voyage"}


WIKI = {"ru": {"title": "Статья", "url": "https://ru.wikipedia.org/wiki/x"}}


@pytest.mark.parametrize(
    ("category", "tags"),
    [
        ("mall", ["shop=mall"]),
        ("grocery", ["shop=supermarket"]),
        ("cafe", ["amenity=cafe"]),
        ("transit_station", ["railway=station"]),
    ],
)
def test_an_article_is_no_evidence_for_a_mall_a_shop_a_cafe_or_transit(category, tags):
    ev = place_evidence(_poi("x", category, tags, wikipedia=WIKI, sources=["osm", "wikivoyage"]))
    assert not {e.source for e in ev} & {"wiki", "voyage"}
    assert "culture" not in strengths(ev)


@pytest.mark.parametrize(
    ("category", "tags"),
    [
        ("museum_gallery", ["tourism=gallery"]),
        ("attraction_landmark", ["historic=monument"]),
        ("attraction_landmark", ["amenity=place_of_worship"]),
        ("attraction_landmark", []),
        ("culture_theatre_cinema", ["amenity=theatre"]),
    ],
)
def test_an_article_is_evidence_of_art_and_history_for_a_sight(category, tags):
    ev = place_evidence(_poi("x", category, tags, wikipedia=WIKI, sources=["osm", "wikivoyage"]))
    assert {e.facet for e in ev if e.source == "wiki"} == {"culture"}
    assert {e.facet for e in ev if e.source == "voyage"} == {"unusual"}


def test_a_mall_with_an_article_does_not_suit_someone_who_dislikes_crowds():
    mall = _poi("mall", "mall", ["shop=mall"], wikipedia=WIKI, sources=["osm", "wikivoyage"])
    for weights in (read_vibe(INTRO_TEXT).weights, {"calm": 0.5, "nature": 1.0, "culture": 1.0}):
        match, facets = vibe_match(mall, None, weights)
        assert match < 0, (
            weights
        )  # busy by its kind: the quiet the person asks for counts against it
        assert facets == []
        assert vibe_line(mall, None, weights, "ru") == ""


def test_betting_is_never_a_vibe_match():
    bookmaker = _poi("bk", "bar_nightlife", ["amenity=bar"], name='Спорт-бар "Финал", БК FairPlay')
    assert place_evidence(bookmaker) == ()
    assert evidence_of(bookmaker, PeopleEvidence(noisy=2, noise="noisy")) == []
    assert vibe_line(bookmaker, None, EXTRO.vibe, "kk") == ""
    assert place_evidence(_poi("t", "entertainment", ["shop=bookmaker"])) == ()
    hall = _poi("v", "museum_gallery", ["tourism=museum"], name="Выставочный зал")
    assert strengths(place_evidence(hall))["culture"] == 1.0  # «выставка» is no bet


def test_before_the_night_and_with_children_a_bar_says_nothing_of_a_vibe():
    bar = _poi("b", "bar_nightlife", ["amenity=bar"], hours="Mo-Su 12:00-02:00")
    mall = _poi("m", "mall", ["shop=mall"])
    games = _poi("g", "entertainment", ["leisure=amusement_arcade"])
    lively = {"lively": 1.0, "night": 1.0}
    assert vibe_match(bar, None, lively)[1] == ["lively", "night"]  # at night
    assert vibe_match(bar, None, lively, day=True) == (0.0, [])
    assert vibe_match(mall, None, lively, day=True)[1] == ["lively"]  # lively in the daytime
    assert vibe_match(mall, None, lively, kids=True) == (0.0, [])
    assert vibe_match(games, None, lively, kids=True)[1] == ["lively"]
    assert vibe_line(bar, None, lively, "ru", day=True) == ""


def test_a_vibe_re_ranks_inside_the_wished_kind_only():
    bar = _poi("b", "bar_nightlife", ["amenity=bar"])
    games = _poi("g", "entertainment", ["leisure=amusement_arcade"])
    wish = Intent(categories=["entertainment"], wished=["entertainment"])
    reasons: list[str] = []
    assert vibe_bonus(bar, None, EXTRO.vibe, reasons, wish, True) == 0.0  # «ПС клуб» is no bar
    assert reasons == []
    assert vibe_bonus(games, None, EXTRO.vibe, [], wish, True) > 0
    assert vibe_bonus(bar, None, EXTRO.vibe, [], Intent(categories=["bar_nightlife"]), True) > 0


def test_hardees_closing_at_a_quarter_to_eleven_is_no_nightlife():
    found = [p for p in get_pois() if "hardee" in p.name.lower()]
    assert found
    assert all("night" not in strengths(place_evidence(p)) for p in found)


def test_an_escape_room_and_an_aquarium_are_unusual():
    assert (
        strengths(place_evidence(_poi("e", "entertainment", ["leisure=escape_game"])))["unusual"]
        == 1.0
    )
    assert (
        strengths(place_evidence(_poi("a", "entertainment", ["tourism=aquarium"])))["unusual"]
        == 1.0
    )


def test_a_place_of_worship_and_a_kids_room_carry_no_vibe():
    assert place_evidence(_poi("w", "attraction_landmark", ["amenity=place_of_worship"])) == ()
    assert place_evidence(_poi("k", "entertainment", ["leisure=playground"])) == ()


def test_only_human_written_text_is_read_for_words():
    derived = _poi("d", "park_garden", description_auto="тихий сквер", description_source="tags")
    assert "text" not in {e.source for e in place_evidence(derived)}
    own = _poi(
        "o", "restaurant", ["amenity=restaurant"], description_official="Уникальный интерьер"
    )
    assert {e.source for e in place_evidence(own) if e.facet == "unusual"} == {"text"}


def test_the_real_dataset_carries_every_facet():
    counts = dict.fromkeys(FACETS, 0)
    for poi in get_pois():
        for facet in strengths(place_evidence(poi)):
            counts[facet] += 1
    assert all(n >= 10 for n in counts.values()), (
        counts
    )  # every facet can be found somewhere in the city


# ---- 2. the person's vibe re-ranks ------------------------------------------------------------------------


def test_without_a_vibe_there_is_no_bonus_and_no_reason():
    reasons: list[str] = []
    bar = _poi("b", "bar_nightlife", ["amenity=bar"])
    assert vibe_bonus(bar, None, {}, reasons, Intent(), True) == 0.0
    assert reasons == []


def test_a_calm_vibe_lifts_a_park_and_only_its_own_search_pushes_a_bar_down():
    calm = {"calm": 1.0}
    park, bar = (
        _poi("p", "park_garden", ["leisure=park"]),
        _poi("b", "bar_nightlife", ["amenity=bar"]),
    )
    reasons: list[str] = []
    assert vibe_bonus(park, None, calm, reasons, Intent(), True) > 0
    assert vibe_bonus(bar, None, calm, [], Intent(), True) == 0.0  # an ordinary answer only lifts
    assert vibe_bonus(bar, None, focused(calm), [], Intent(), True) < 0  # «под мой вайб»
    assert reasons == ["vibe:calm"]


def test_the_card_line_names_each_facet_with_the_data_that_said_it():
    park = _poi("p", "park_garden", ["leisure=park"])
    assert vibe_line(park, None, INTRO.vibe, "ru") == "Под ваш вайб: природа (парк), тихо (парк)"
    cafe = _poi("c", "cafe", ["amenity=cafe"])
    quiet = PeopleEvidence(quiet=2, noise="quiet")
    assert vibe_line(cafe, quiet, INTRO.vibe, "ru") == "Под ваш вайб: тихо (по отметкам людей)"
    assert vibe_line(cafe, None, INTRO.vibe, "ru") == ""  # nothing in the data: nothing is claimed
    assert vibe_line(park, None, INTRO.vibe, "en") == "Your vibe: nature (park), quiet (park)"
    assert vibe_line(park, None, INTRO.vibe, "kk").startswith("Сіздің вайбыңызға: табиғат (саябақ)")


# ---- 3. «под мой вайб»: one request, two people ------------------------------------------------------------


def test_an_introvert_and_an_extrovert_get_different_answers_to_the_same_words():
    intro, extro = _ask("Под мой вайб", INTRO), _ask("Под мой вайб", EXTRO)
    assert intro.kind == extro.kind == "places"
    assert intro.reply.startswith("Под ваш вайб — тихо")
    assert extro.reply.startswith("Под ваш вайб — шумно")
    calm_ids = {"park", "library", "museum", "quiet_cafe", "monument"}
    lively_ids = {"bar", "karaoke", "mall", "escape", "noisy_cafe"}
    assert {p.id for p in intro.places} <= calm_ids
    assert {p.id for p in extro.places} <= lively_ids
    for place in [*intro.places, *extro.places]:
        assert place.vibe.startswith("Под ваш вайб: "), place
        assert "(" in place.vibe
        assert place.vibe.endswith(")")


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("под моё настроение", "ru"),
        ("Менің вайбыма сай", "kk"),
        ("Match my vibe", "en"),
    ],
)
def test_the_vibe_search_answers_in_the_language_of_the_words(text, lang):
    turn = _ask(text, INTRO)
    assert turn.kind == "places"
    assert turn.lang == lang
    assert all(p.vibe for p in turn.places)


def test_words_that_state_the_vibe_need_no_stored_one():
    turn = _ask("куда сходить интроверту", None)
    assert turn.kind == "places"
    assert turn.reply.startswith("Под ваш вайб — тихо")
    assert not {p.id for p in turn.places} & {"bar", "karaoke", "mall", "noisy_cafe"}


def test_the_vibe_search_without_a_vibe_says_where_to_set_it_and_searches_nothing():
    for profile in (None, Profile()):
        turn = _ask("Под мой вайб", profile)
        assert turn.kind == "clarify"
        assert "«Мой вайб»" in turn.reply
        assert not turn.places


def test_an_introvert_asking_for_coffee_gets_the_calmer_cafe_first():
    intro, extro = _ask("кофе", INTRO), _ask("кофе", EXTRO)
    assert intro.places[0].id == "quiet_cafe"
    assert extro.places[0].id == "noisy_cafe"
    assert {p.category for p in [*intro.places, *extro.places]} == {"cafe"}
    assert intro.places[0].vibe == "Под ваш вайб: тихо (по отметкам людей)"
    assert extro.places[0].vibe == "Под ваш вайб: шумно (по отметкам людей)"
    assert not intro.reply.startswith("Под ваш вайб")  # an ordinary answer keeps its usual lead


# the cafés' own words: a fact of the place the model's sentence can use (walks.facts.vague_ids)
COFFEE_TEXT = {
    "plain_cafe": "Десерты и кофе с собой",
    "noisy_cafe": "Блины и кофе",
    "quiet_cafe": "Чай и кофе в зерне",
    "far_cafe": "Кофе и выпечка",
    "night_cafe": "Кофе и сырники",
}


def _coffee_city(north: dict[str, float]) -> list[POI]:
    return [
        _poi(
            pid,
            "cafe",
            ["amenity=cafe"],
            m,
            "Mo-Su 08:00-22:00",
            description_official=COFFEE_TEXT[pid],
        )
        for pid, m in north.items()
    ]


NEAR_CAFES = {"plain_cafe": 100, "noisy_cafe": 150, "quiet_cafe": 200, "far_cafe": 250}


class Model:
    """The generation model: it answers with the given cafés in this order and opens with the first of them, whatever
    the person's vibe (the live «кофе» at Байтерек led with Starbucks for an introvert and an extrovert alike)."""

    def __init__(self, monkeypatch, ids: list[str]):
        self.ids = ids
        monkeypatch.setattr(llm, "llm_available", lambda: True)
        monkeypatch.setattr(gen_mod, "generate_json", self.ask)

    def ask(self, prompt, schema, **kw):
        offered = {c["poi_id"] for c in json.loads(prompt)["candidates"]}
        recs = [
            LLMRec(
                poi_id=i,
                why=f"{COFFEE_TEXT[i]}.",
                time_on_site_min=30,
                what_to_do="Возьмите кофе.",
                confidence="medium",
                generated_idea=False,
            )
            for i in self.ids
            if i in offered
        ]
        first = self.ids[0]
        opening = f"Кофе рядом — «{NAMES[first]}»: {COFFEE_TEXT[first].lower()}."
        return LLMCall(
            LLMOutput(opening=opening, recommendations=recs), LLMStep(chain=["m"], model="m")
        )


def _live(text: str, profile: Profile | None, pois: list[POI], feedback: FeedbackIndex = MARKS):
    env = TurnEnv(
        when=DAY,
        use_llm=True,
        router=offline_router(),
        pois=pois,
        profile=profile,
        feedback=feedback,
    )
    return take_vibe_turn(new_state(*ORIGIN), text, env)


def _sources(out) -> dict[str, str]:
    return {r.poi.id: r.text_source for r in out.result.recs}


def test_the_vibe_leads_an_ordinary_answer_whatever_card_the_model_put_first(monkeypatch):
    Model(monkeypatch, ["plain_cafe", "noisy_cafe", "quiet_cafe"])
    city = _coffee_city(NEAR_CAFES)
    intro, extro = _live("кофе", INTRO, city), _live("кофе", EXTRO, city)
    assert intro.turn.places[0].id == "quiet_cafe"
    assert extro.turn.places[0].id == "noisy_cafe"
    assert intro.turn.places[0].vibe == "Под ваш вайб: тихо (по отметкам людей)"
    assert extro.turn.places[0].vibe == "Под ваш вайб: шумно (по отметкам людей)"
    for out, first in ((intro, "Деирмен"), (extro, "Креперия")):
        assert f"«{first}»" in out.turn.reply  # the lead names the card it leads with
        assert "Коктем" not in out.turn.reply  # the model's opening named another place
        assert set(_sources(out).values()) == {"llm"}  # every card keeps the model's own text


def test_a_vibe_match_the_model_left_out_comes_first_and_the_model_keeps_its_other_cards(
    monkeypatch,
):
    Model(monkeypatch, ["plain_cafe", "noisy_cafe", "far_cafe"])
    out = _live("кофе", INTRO, _coffee_city(NEAR_CAFES))
    assert [p.id for p in out.turn.places] == ["quiet_cafe", "plain_cafe", "noisy_cafe"]
    assert _sources(out) == {"quiet_cafe": "template", "plain_cafe": "llm", "noisy_cafe": "llm"}


def test_a_vibe_match_beyond_a_short_extra_walk_does_not_lead(monkeypatch):
    Model(monkeypatch, ["plain_cafe", "noisy_cafe"])
    far = _coffee_city({"plain_cafe": 100, "noisy_cafe": 150, "quiet_cafe": 600})
    out = _live("кофе", INTRO, far)  # 2 min to the nearest, 11 to the quiet one
    assert out.turn.places[0].id == "plain_cafe"
    assert "Коктем" in out.turn.reply


def test_without_a_vibe_the_model_keeps_its_first_card(monkeypatch):
    Model(monkeypatch, ["plain_cafe", "noisy_cafe", "quiet_cafe"])
    city = _coffee_city(NEAR_CAFES)
    for profile in (None, Profile()):
        out = _live("кофе", profile, city)
        assert [p.id for p in out.turn.places] == ["plain_cafe", "noisy_cafe", "quiet_cafe"]
        assert out.turn.reply.startswith("Кофе рядом — «Коктем»")
        assert all(p.vibe == "" for p in [*out.turn.places, *out.turn.more])


class TellingModel(Model):
    """The live model of the report: told «night» among the person's preferences, it leads with the café open all night
    (Qaganat at Байтерек, 772 m, for the extrovert), a place the data hold no evidence of the vibe for."""

    def __init__(self, monkeypatch):
        super().__init__(monkeypatch, [])
        self.told: list[list[str]] = []

    def ask(self, prompt, schema, **kw):
        told = json.loads(prompt).get("user_preferences", {}).get("vibe", [])
        self.told.append(told)
        night = ["night_cafe", "plain_cafe", "noisy_cafe"]
        self.ids = night if "night" in told else ["plain_cafe", "noisy_cafe", "night_cafe"]
        return super().ask(prompt, schema, **kw)


def test_the_vibe_moves_no_card_it_has_no_evidence_for(monkeypatch):
    model = TellingModel(monkeypatch)
    night = _poi(
        "night_cafe", "cafe", ["amenity=cafe"], 600, "24/7", description_official="Кофе и сырники"
    )
    city, unmarked = (
        [*_coffee_city({"plain_cafe": 100, "noisy_cafe": 150}), night],
        FeedbackIndex([]),
    )
    plain = _live("кофе", None, city, unmarked)
    for profile in (INTRO, EXTRO):
        out = _live("кофе", profile, city, unmarked)
        assert [p.id for p in out.turn.places] == [p.id for p in plain.turn.places], profile
        assert out.turn.reply == plain.turn.reply
        assert all(
            p.vibe == "" for p in out.turn.places
        )  # no evidence, so nothing was moved for the vibe
    assert model.told == [[], [], []]  # an ordinary answer tells the model no vibe


def test_the_vibe_puts_no_card_without_evidence_over_the_models_first(monkeypatch):
    Model(monkeypatch, ["quiet_cafe", "plain_cafe", "far_cafe"])
    quiet = FeedbackIndex([_mark("quiet_cafe", "quiet", d) for d in ("2026-10-19", "2026-10-18")])
    out = _live("кофе", EXTRO, _coffee_city(NEAR_CAFES), quiet)
    assert (
        out.turn.places[0].id == "quiet_cafe"
    )  # the model's own first: no nearby café has a line to lead with
    assert all(p.vibe == "" for p in out.turn.places)


def test_the_rows_under_the_cards_carry_their_vibe_line_too():
    out = take_vibe_turn(new_state(*ORIGIN), "Под мой вайб", _env(INTRO))
    rows = out.turn.more
    assert rows
    people = {c.poi.id: c for c in out.result.retrieval.candidates}
    for row in rows:
        c = people[row.id]
        assert row.vibe == vibe_line(c.poi, c.people, INTRO.vibe, "ru", day=True)
    assert any(row.vibe.startswith("Под ваш вайб: ") for row in rows)


def test_a_night_life_vibe_in_the_daytime_is_not_a_list_of_bars():
    day = _ask("Под мой вайб", EXTRO)  # 15:00
    assert not {p.id for p in day.places} & {"bar", "karaoke"}
    assert all("(бар)" not in p.vibe for p in [*day.places, *day.more])
    env = _env(EXTRO)
    env.when = datetime(2026, 10, 20, 22, 30)
    night = take_vibe_turn(new_state(*ORIGIN), "Под мой вайб", env).turn
    assert {p.id for p in night.places} & {"bar", "karaoke"}


def test_with_children_the_vibe_has_no_bar_and_no_noisy_mall_and_keeps_art():
    family = Profile(vibe={"lively": 1.0, "culture": 1.0}, with_kids=True)
    turn = _ask("Под мой вайб", family)
    shown = {p.id for p in [*turn.places, *turn.more]}
    assert not shown & {"bar", "karaoke"}
    assert "mall" not in {p.id for p in turn.places}
    assert "искусство и история" in turn.reply
    assert all("торговый центр" not in p.vibe for p in [*turn.places, *turn.more])


def test_the_vibe_line_speaks_the_language_of_the_answer():
    env = _env(INTRO)
    env.language = "kk"
    turn = take_vibe_turn(new_state(*ORIGIN), "кофе", env).turn
    assert turn.lang == "kk"
    assert turn.places[0].vibe == "Сіздің вайбыңызға: тыныш (адамдардың белгілері бойынша)"


@pytest.mark.parametrize(
    "text", ["Под мой вайб", "под моё настроение", "Менің вайбыма", "my vibe", "match my vibe"]
)
def test_the_phrases_that_name_the_stored_vibe(text):
    assert asks_vibe(text)


@pytest.mark.parametrize("text", ["кофе", "куда сходить вечером", "вайфай есть?", "мой дом"])
def test_ordinary_words_do_not_ask_for_the_vibe(text):
    assert not asks_vibe(text)


def test_introvert_and_extrovert_words_state_the_axis():
    assert stated_vibe("куда сходить интроверту") == {"calm": 1.0}
    assert stated_vibe("я экстраверт, что делать вечером") == {"lively": 1.0}
    assert stated_vibe("where to go as an introvert") == {"calm": 1.0}
    assert stated_vibe("кофе") == {}


# ---- 4. without a vibe: exactly as before -------------------------------------------------------------------


def _same(a, b) -> bool:
    drop = {"meta": {"ms"}}
    return a.turn.model_dump(exclude=drop) == b.turn.model_dump(exclude=drop) and a.state == b.state


@pytest.mark.parametrize(
    "text",
    [
        "кофе",
        "куда сходить вечером",
        "хочу в музей",
        "погулять в парке",
        "бар",
        "тихое кафе с wifi",
    ],
)
def test_without_a_vibe_every_answer_is_exactly_as_before(text):
    pois = get_pois()
    for profile in (None, Profile(), Profile(quiet=True, with_kids=True)):
        env = TurnEnv(when=DAY, use_llm=False, router=offline_router(), pois=pois, profile=profile)
        before = take_turn(new_state(*ORIGIN), text, env)
        after = take_vibe_turn(new_state(*ORIGIN), text, env)
        assert _same(before, after), (text, profile)
        assert all(p.vibe == "" for p in after.turn.places)


def test_an_empty_vibe_changes_neither_the_ranking_nor_the_model_payload():
    pois = get_pois()
    intent = take_turn(new_state(*ORIGIN), "кофе", _env(None, pois)).result.intent.intent
    plain = retrieve(pois, *ORIGIN, intent, DAY, personal=Personal())
    empty = retrieve(pois, *ORIGIN, intent, DAY, personal=personal_view(Profile()))
    assert plain.model_dump() == empty.model_dump()
    assert "vibe" not in preferences_payload(Profile(quiet=True))
    assert "vibe" not in preferences_payload(INTRO)  # an ordinary answer tells the model no vibe
    searched = INTRO.model_copy(update={"vibe": focused(INTRO.vibe)})
    assert preferences_payload(searched)["vibe"] == ["calm", "nature", "culture"]


def test_the_vibe_is_a_stored_item_that_can_be_forgotten():
    profile = INTRO.model_copy(update={"vibe_text": INTRO_TEXT})
    items = {i.key: i.label for i in list_items(profile, lang="ru")}
    assert items["vibe"] == "ваш вайб: тихо, природа, искусство и история"
    assert items["vibe_text"].startswith("ваш текст о вайбе: «люблю тишину")


def test_the_profile_keeps_only_known_facets_and_weights_between_zero_and_one():
    profile = Profile(vibe={"calm": 3.0, "nature": -1.0, "cozy": 1.0, "night": 0.5})
    assert profile.vibe == {"calm": 1.0, "night": 0.5}


# ---- 5. the free text: a typed judgment, rules without a model ---------------------------------------------


def test_the_judgment_is_one_closed_level_per_facet():
    schema = VibeReading.model_json_schema()
    assert set(schema["properties"]) == set(FACETS)
    for facet in FACETS:
        prop = schema["properties"][facet]
        levels = prop.get("enum") or schema["$defs"][prop["$ref"].split("/")[-1]]["enum"]
        assert levels == ["none", "some", "strong"]
    assert weights_of(VibeReading(calm="strong", nature="some")) == {"calm": 1.0, "nature": 0.5}


def test_without_a_model_the_rules_read_the_introvert():
    weights, source = read_vibe(INTRO_TEXT)
    assert source == "rules"
    assert weights["calm"] == 1.0
    assert weights["nature"] == 1.0
    assert weights["culture"] > 0  # the books
    assert "lively" not in weights  # «не люблю толпы» asks for the quiet, not for the crowd


def test_without_a_model_the_rules_read_the_extrovert():
    weights, source = read_vibe(EXTRO_TEXT)
    assert source == "rules"
    assert {"lively", "night", "unusual"} <= set(weights)
    assert "calm" not in weights


def test_the_named_museum_and_workshop_stay_whatever_the_model_read(monkeypatch):
    text = "Балаларыммен жүремін, мұражай мен шеберхана ұнайды"
    assert rules_reading(text).culture == "strong"
    reading = VibeReading(lively="strong")
    monkeypatch.setattr(
        vibe_judge, "generate_json", lambda p, s, **kw: LLMCall(reading, LLMStep(chain=["m"]))
    )
    monkeypatch.setattr(vibe_judge, "ai_off_reason", lambda use_llm: "")
    assert read_vibe(text).weights == {"lively": 1.0, "culture": 0.5}


@pytest.mark.parametrize(
    ("text", "facet"),
    [
        ("тыныш жерлерді, кітапты жақсы көремін", "calm"),
        ("I love parties and live music", "lively"),
        ("музеи и театры", "culture"),
        ("спорт, каток, бег по утрам", "active"),
    ],
)
def test_the_rules_read_kazakh_english_and_russian(text, facet):
    assert getattr(rules_reading(text), facet) == "strong"


def test_a_model_answer_is_used_when_there_is_one(monkeypatch):
    seen = {}

    def fake(prompt, schema, **kw):
        seen.update(prompt=prompt, schema=schema, **kw)
        return LLMCall(VibeReading(calm="strong", culture="some"), LLMStep(chain=["gemini:x"]))

    monkeypatch.setattr(vibe_judge, "generate_json", fake)
    monkeypatch.setattr(vibe_judge, "ai_off_reason", lambda use_llm: "")
    weights, source = read_vibe("тихие вечера с книгой")
    assert (weights, source) == ({"calm": 1.0, "culture": 0.5}, "model")
    assert seen["schema"] is VibeReading
    assert "тихие вечера с книгой" in seen["prompt"]


def test_a_dislike_of_crowds_is_a_strong_wish_for_quiet_whatever_the_model_read(monkeypatch):
    reading = VibeReading(calm="some", lively="some", nature="strong", culture="some")
    monkeypatch.setattr(
        vibe_judge, "generate_json", lambda p, s, **kw: LLMCall(reading, LLMStep(chain=["m"]))
    )
    monkeypatch.setattr(vibe_judge, "ai_off_reason", lambda use_llm: "")
    weights, source = read_vibe(INTRO_TEXT)  # «… не люблю толпы»
    assert source == "model"
    assert weights == {"calm": 1.0, "nature": 1.0, "culture": 0.5}  # the crowd is never a wish
    assert read_vibe("люблю парки и книги").weights == weights_of(reading)  # no dislike: as read


def test_a_failed_model_falls_back_to_the_rules(monkeypatch):
    def down(prompt, schema, **kw):
        raise LLMUnavailable("down")

    monkeypatch.setattr(vibe_judge, "generate_json", down)
    monkeypatch.setattr(vibe_judge, "ai_off_reason", lambda use_llm: "")
    weights, source = read_vibe(INTRO_TEXT)
    assert source == "rules"
    assert weights["calm"] == 1.0
