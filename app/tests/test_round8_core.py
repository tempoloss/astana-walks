"""The live check of the deployed stand (wave 9): a dentist wish is a dentist, a laboratory is no dentist, and none
near is said with the nearest one; a PS evening is offered places to play, never a concert or a congress hall; the
Kazakh lines of an errand read as Kazakh («түнгі дүкен» is a food shop)."""

from __future__ import annotations

from datetime import datetime

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_facts import all_gaps
from walks.dialog_place import dist_text
from walks.dialog_strings import s
from walks.facts import named_lead, unnamed_label
from walks.generate import template_rec
from walks.hours import poi_hours
from walks.intent import parse_rules
from walks.models import POI, Candidate, Intent, IntentResult
from walks.pipeline import recommend
from walks.profile import Profile
from walks.walking import offline_router
from walks.wishes import errand_order, of_subkind

ORIGIN = (51.0906, 71.4180)
DEG_M = 111_320.0
DAY = datetime(2026, 10, 19, 15, 0)


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=kw.pop("name", poi_id),
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        opening_hours=kw.pop("hours", None),
        **kw,
    )


def _env(pois: list[POI]) -> TurnEnv:
    return TurnEnv(when=DAY, use_llm=False, router=offline_router(), pois=pois)


# ---- 1. a dentist ---------------------------------------------------------------------------------------------------


def test_a_dentist_is_asked_in_every_language():
    for text in ("где стоматолог", "зубной врач рядом", "тіс дәрігері қайда", "dentist nearby"):
        assert parse_rules(text).intent.subkind == "dentist", text
    assert parse_rules("где клиника").intent.subkind == ""
    assert parse_rules("зубная паста где купить").intent.subkind == ""  # a shop shelf, no dentist


def test_a_dentist_is_a_record_tagged_so_and_a_laboratory_is_not():
    assert of_subkind(_poi("a", 0, "clinic", tags=["amenity=dentist"]), "dentist")
    assert of_subkind(_poi("h", 0, "clinic", tags=["healthcare=dentist"]), "dentist")
    assert of_subkind(
        _poi("s", 0, "clinic", tags=["healthcare:speciality=orthodontics;dentist"]), "dentist"
    )
    assert not of_subkind(
        _poi("lab", 0, "clinic", name="Invitro", tags=["amenity=doctors"]), "dentist"
    )
    lab = Candidate(
        poi=_poi(
            "lab",
            100,
            "clinic",
            name="Invitro",
            tags=["amenity=doctors"],
            hours="Mo-Su 08:00-22:00",
        ),
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="open",
        score=5.0,
    )
    dent = Candidate(
        poi=_poi("dent", 400, "clinic", name="EliteStom", tags=["amenity=dentist"]),
        distance_m=400,
        walk_min=5,
        travel_min=5,
        hours_state="unknown",
        score=5.0,
    )
    out = errand_order([lab, dent], frozenset({"clinic"}), DAY, False, sub="dentist")
    assert [c.poi.id for c in out] == [
        "dent",
        "lab",
    ]  # a dentist with unknown hours before an open laboratory


def test_a_near_dentist_leads_by_what_it_is():
    lab = _poi(
        "lab", 300, "clinic", name="Invitro", tags=["amenity=doctors"], hours="Mo-Su 07:30-20:00"
    )
    dent = _poi(
        "dent", 700, "clinic", name="EliteStom", tags=["amenity=dentist"], hours="Mo-Su 09:00-20:00"
    )
    turn = take_turn(new_state(*ORIGIN, "ru"), "где стоматолог", _env([lab, dent])).turn
    assert turn.places[0].id == "dent"
    assert turn.reply.startswith("Ближайшая открытая стоматология — «EliteStom»")


def test_no_dentist_near_is_said_with_the_nearest_one_then_other_clinics():
    """No dentist near: one sentence naming the nearest one by its distance, never its walking minutes, that dentist
    as the last card (to route there); the other clinics first, said as the nearest of the rest."""
    lab = _poi(
        "lab", 300, "clinic", name="Invitro", tags=["amenity=doctors"], hours="Mo-Su 07:30-20:00"
    )
    clinic = _poi("cl", 500, "clinic", name="Green Clinic", tags=["amenity=clinic"])
    far = _poi("far", 9000, "clinic", name="BASDENT", tags=["amenity=dentist"])
    for lang, text, rest in (
        ("ru", "где стоматолог", "Из других клиник ближе всего — «Invitro»"),
        ("kk", "тіс дәрігері қайда", "Басқа клиникалардан ең жақыны — «Invitro»"),
        ("en", "dentist nearby", "Of the other clinics, the nearest is Invitro"),
    ):
        turn = take_turn(new_state(*ORIGIN, lang), text, _env([lab, clinic, far])).turn
        assert [p.id for p in turn.places] == ["lab", "cl", "far"]
        walk = turn.places[2].walk.text  # «пешком далеко: 8,9 км — лучше на транспорте»
        assert walk == s("walk_far", lang, d=dist_text(turn.places[2].walk.distance_m, lang))
        head = s("sub_far_dentist", lang, name="BASDENT", walk=walk)
        assert turn.reply.startswith(f"{head} {rest}"), turn.reply
        assert "мин" not in head
        assert " min" not in head
    alone = take_turn(new_state(*ORIGIN, "ru"), "где стоматолог", _env([lab, clinic])).turn
    assert alone.reply.startswith(s("sub_none_dentist", "ru"))


# ---- 2. a PS evening ------------------------------------------------------------------------------------------------


def test_a_ps_evening_gets_places_to_play_never_a_concert_hall():
    hall = _poi(
        "hall",
        300,
        "entertainment",
        name="Kongress-Tsentr Astana",
        tags=["overture_category=music_venue"],
    )
    kids = _poi(
        "kids",
        350,
        "entertainment",
        name="Детская площадка в помещении",
        tags=["leisure=playground"],
    )
    theatre = _poi(
        "th", 400, "culture_theatre_cinema", name="Астана балет", tags=["amenity=theatre"]
    )
    cinema = _poi(
        "cin", 600, "culture_theatre_cinema", name="Chaplin Cinema", tags=["amenity=cinema"]
    )
    bowling = _poi(
        "bowl", 900, "entertainment", name="Duman Bowling", tags=["overture_category=bowling_alley"]
    )
    turn = take_turn(
        new_state(*ORIGIN, "ru"),
        "хочу в пску с кентами",
        _env([hall, kids, theatre, cinema, bowling]),
    ).turn
    ids = {p.id for p in turn.places}
    assert ids <= {"cin", "bowl"}, ids
    assert ids
    assert turn.reply.startswith(s("unmapped_gaming", "ru"))
    assert "Вы ищете" not in turn.reply  # the substitute kinds are not the person's words


# ---- 3. Kazakh lines of an errand -----------------------------------------------------------------------------------


def test_the_kazakh_errand_lines_say_them_of_two_kinds_and_a_night_shop_is_a_food_shop():
    assert "олардың орнына" in s("none_money", "kk")
    assert "олардың орнына" in s("none_clinic", "kk")
    assert "стоматология" not in s("none_clinic", "kk")
    assert parse_rules("түнгі дүкен").intent.categories == ["grocery"]
    assert parse_rules("дүкен").intent.categories == ["mall"]  # a bare «shop» stays a mall


# ---- 4. a sick child is no dentist's ---------------------------------------------------------------------------------

CLINICS = [
    _poi(
        "dent",
        60,
        "clinic",
        name="Доктор Дент",
        tags=["amenity=dentist"],
        hours="Mo-Su 09:00-21:00",
    ),
    _poi(
        "dent2", 300, "clinic", name="3D Dental", tags=["amenity=clinic"]
    ),  # a dentist by its name only
    _poi("poly", 340, "clinic", name="Городская поликлиника № 1", tags=["amenity=clinic"]),
    _poi("kids", 900, "clinic", name="Детская поликлиника №2", tags=["amenity=clinic"]),
]


def _sick(sick: str, sub: str = "") -> IntentResult:
    intent = Intent(categories=["clinic"], wished=["clinic"], sick=sick, subkind=sub, language="kk")
    return IntentResult(intent=intent, parser="rules")


def test_a_sick_child_gets_a_childrens_clinic_first_and_never_a_dentist():
    res = recommend(
        "ауырып қалды баламның, емхана бар ма",
        *ORIGIN,
        DAY,
        use_llm=False,
        pois=CLINICS,
        router=offline_router(),
        understood=_sick("child"),
    )
    ids = [r.poi.id for r in res.recs]
    assert ids[0] == "kids"
    assert not {"dent", "dent2"} & set(ids)
    assert not {"dent", "dent2"} & {
        c.poi.id for c in res.retrieval.candidates
    }  # nor in «тағы N орын»


def test_an_ill_adult_or_a_doctor_wish_gets_no_dentist():
    for reading in (_sick("adult"), _sick("", "doctor")):
        res = recommend(
            "емхана қайда",
            *ORIGIN,
            DAY,
            use_llm=False,
            pois=CLINICS,
            router=offline_router(),
            understood=reading,
        )
        assert {r.poi.id for r in res.recs} <= {"poly", "kids"}
    assert parse_rules("емхана қайда").intent.subkind == "doctor"
    assert parse_rules("балалар емханасы қайда").intent.subkind == "kids_doctor"


def test_no_childrens_clinic_near_is_said_then_the_nearest_clinics():
    near = [p for p in CLINICS if p.id != "kids"]
    res = recommend(
        "ауырып қалды баламның, емхана бар ма",
        *ORIGIN,
        DAY,
        use_llm=False,
        pois=near,
        router=offline_router(),
        understood=_sick("child"),
    )
    assert [r.poi.id for r in res.recs] == ["poly"]
    before, _ = all_gaps(res, res.recs, near, "ru", now=True)
    assert before == s("sub_none_kids_doctor", "ru")


# ---- 5. the no-playground line is the person's own wish ----------------------------------------------------------


PLAY = _poi("pg", 155, "kids_playground", name="Детская площадка", name_generated=True)
CAFE = _poi("cafe", 200, "cafe", name="Gold Coffee")
MALL = _poi("mall", 300, "mall", name="Торговый дом Азат")


def test_a_coffee_with_children_is_no_wish_for_a_playground():
    model = Intent(
        categories=["cafe", "kids_playground"], wished=["cafe"], with_kids=True, quiet=True
    )
    res = recommend(
        "тыныш жер балалармен, кофе ішіп отыруға болатын",
        *ORIGIN,
        DAY,
        use_llm=False,
        pois=[CAFE],
        router=offline_router(),
        understood=IntentResult(intent=model, parser="rules+llm"),  # the model added the playground
    )
    before, _ = all_gaps(res, res.recs, [CAFE], "kk", now=True)
    assert s("kids_none_place", "kk") not in before


def test_indoor_play_is_said_as_indoor_never_as_no_playgrounds():
    """No indoor play place near (an outdoor playground, a café, a mall): «Крытых игровых мест нет», never «площадок
    нет», whether the outdoor playground is shown as the alternative or not."""
    for pois in ([CAFE, MALL], [PLAY, CAFE, MALL]):
        turn = take_turn(
            new_state(*ORIGIN, "ru"), "где поиграть детям в помещении", _env(pois)
        ).turn
        assert turn.places
        assert s("kids_none_indoor", "ru") in turn.reply
        assert s("kids_none_place", "ru") not in turn.reply


# ---- 6. a walk with a child in the memory ------------------------------------------------------------------------


def test_a_park_with_a_child_in_the_memory_offers_the_near_playground_too():
    park = _poi("park", 900, "park_garden", name="Сквер Акжайык")
    env = TurnEnv(
        when=DAY,
        use_llm=False,
        router=offline_router(),
        pois=[park, PLAY],
        profile=Profile(with_kids=True),
    )
    turn = take_turn(new_state(*ORIGIN, "ru"), "парк если не холодно", env).turn
    assert [p.id for p in turn.places][:2] == ["park", "pg"]


# ---- 7. a post office is Kazpost's ---------------------------------------------------------------------------------


POST = [
    _poi("cdek", 150, "post", name="СДЭК", tags=['operator=УК "СДЭК"'], hours="Mo-Su 10:00-20:00"),
    _poi(
        "p17", 400, "post", name="Почта №17", tags=["operator=Қазпошта"], hours="Mo-Su 09:00-09:00"
    ),
    _poi(
        "cpo",
        700,
        "post",
        name="Центральный почтамт",
        tags=["operator=Казпочта"],
        hours="Mo-Fr 09:00-20:00",
    ),
]


def test_a_post_office_is_kazpost_and_a_courier_only_when_asked():
    assert parse_rules("what are the opening hours of the post office").intent.subkind == "kazpost"
    turn = take_turn(new_state(*ORIGIN, "en"), "where is the nearest post office", _env(POST)).turn
    assert "cdek" not in {p.id for p in turn.places}
    assert turn.places[0].id == "cpo"  # the open one; Почта №17's «09:00-09:00» is no schedule
    courier = take_turn(new_state(*ORIGIN, "ru"), "где сдэк, посылку отправить", _env(POST)).turn
    assert courier.places[0].id == "cdek"


def test_a_schedule_that_opens_and_closes_at_one_minute_is_unknown():
    assert poi_hours(POST[1], DAY).state == "unknown"
    assert (
        poi_hours(_poi("x", 0, "cafe", hours="Mo-Su 00:00-00:00"), DAY).state == "open"
    )  # the whole day


# ---- 8. an unnamed park never leads ------------------------------------------------------------------------------


def test_an_unnamed_park_never_leads_and_says_where_it_is():
    bare = _poi("bare", 100, "park_garden", name="Парк / сквер", name_generated=True)
    named = _poi("named", 800, "park_garden", name="Аллея мира")
    recs = [
        template_rec(
            Candidate(
                poi=p,
                distance_m=d,
                walk_min=d // 80,
                travel_min=d // 80,
                hours_state="unknown",
                score=5.0,
            ),
            Intent(categories=["park_garden"]),
            None,
            [],
        )
        for p, d in ((bare, 100), (named, 800))
    ]
    assert [r.poi.id for r in named_lead(recs, "ru")] == ["named", "bare"]
    assert unnamed_label(bare, "ru").startswith("Сквер без названия, район ")
    assert unnamed_label(named, "ru") == ""
    nowhere = bare.model_copy(update={"lat": 0.0, "lon": 0.0})  # no address, no district
    assert unnamed_label(nowhere, "ru") == ""
