"""The live check of 9be639f (wave 10): a far «nearest» is said by its distance and the transport, never by walking
minutes, and it is a card of its own (to route there); an answer has one lead; a children's clinic far away is the far
option, a general clinic nearby the answer for a sick child."""

from __future__ import annotations

from datetime import datetime

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_place import dist_text
from walks.dialog_strings import s
from walks.i18n import t
from walks.models import POI, Candidate, Intent, IntentResult
from walks.pipeline import recommend
from walks.walking import offline_router
from walks.wishes import FAR_WALK_MIN, errand_order

ORIGIN = (51.0906, 71.4180)
DEG_M = 111_320.0
DAY = datetime(2026, 10, 19, 15, 30)


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


GENERAL = _poi(
    "gen", 1100, "clinic", name="Invivo", tags=["amenity=doctors"], hours="Mo-Su 08:00-22:00"
)
GREEN = _poi("green", 1200, "clinic", name="Green Clinic", tags=["amenity=clinic"])
DENT = _poi(
    "dent", 300, "clinic", name="Доктор Дент", tags=["amenity=dentist"], hours="Mo-Su 09:00-21:00"
)
KIDS_FAR = _poi(
    "kids",
    6900,
    "clinic",
    name="Медикер Педиатрия",
    tags=["amenity=clinic"],
    hours="Mo-Su 08:00-20:00",
)


def _sick_child() -> IntentResult:
    intent = Intent(categories=["clinic"], wished=["clinic"], sick="child", language="ru")
    return IntentResult(intent=intent, parser="rules")


# ---- 1. a far nearest: its distance and the transport, and a card --------------------------------------------------


def test_a_far_childrens_clinic_is_the_last_card_said_by_its_distance():
    pois = [DENT, GENERAL, GREEN, KIDS_FAR]
    res = recommend(
        "детская поликлиника рядом, ребёнок температурит",
        *ORIGIN,
        DAY,
        use_llm=False,
        pois=pois,
        router=offline_router(),
        understood=_sick_child(),
    )
    ids = [r.poi.id for r in res.recs]
    assert ids[0] == "gen"  # a general clinic nearby leads; a dentist never
    assert ids[-1] == "kids"  # the far option, as a card: its 2GIS / Yandex links lead there
    assert "dent" not in ids
    far = res.recs[-1]
    assert far.walk_min >= FAR_WALK_MIN
    assert t("note_far_on_foot", "ru") in far.notes


def test_the_reply_has_one_lead_and_no_walking_minutes_of_the_far_one():
    turn = take_turn(
        new_state(*ORIGIN, "ru"), "детская поликлиника рядом", _env([GENERAL, GREEN, KIDS_FAR])
    ).turn
    far = turn.places[-1]
    assert far.id == "kids"
    assert far.walk.text == s("walk_far", "ru", d=dist_text(far.walk.distance_m, "ru"))
    gap = s("sub_far_kids_doctor", "ru", name="Медикер Педиатрия", walk=far.walk.text)
    assert turn.reply.startswith(f"{gap} Из других клиник ближе всего — «Invivo»"), turn.reply
    assert "Ниже другие клиники" not in turn.reply
    assert "Ближайшая открытая клиника" not in turn.reply  # one lead, not two glued together
    assert f"{far.walk.minutes} мин" not in turn.reply


def test_the_far_wording_is_said_in_kazakh_and_english_too():
    for lang, text in (("kk", "балалар емханасы қайда"), ("en", "children's clinic nearby")):
        turn = take_turn(new_state(*ORIGIN, lang), text, _env([GENERAL, GREEN, KIDS_FAR])).turn
        far = turn.places[-1]
        assert far.id == "kids", (lang, [p.id for p in turn.places])
        assert far.walk.text == s("walk_far", lang, d=dist_text(far.walk.distance_m, lang))
        assert turn.reply.startswith(
            s("sub_far_kids_doctor", lang, name="Медикер Педиатрия", walk=far.walk.text)
        )


# ---- 3. a children's clinic within a walk leads, a far one never ---------------------------------------------------


def _cand(p: POI, walk: int, state: str) -> Candidate:
    return Candidate(
        poi=p, distance_m=walk * 80, walk_min=walk, travel_min=walk, hours_state=state, score=5.0
    )


def test_a_childrens_clinic_leads_within_a_walk_and_is_last_beyond_it():
    near_kids = _poi("nk", 900, "clinic", name="Детская поликлиника №2", tags=["amenity=clinic"])
    general = _cand(GENERAL, 14, "unknown")
    out = errand_order(
        [general, _cand(near_kids, 12, "unknown")],
        frozenset({"clinic"}),
        DAY,
        False,
        sub="kids_doctor",
    )
    assert [c.poi.id for c in out] == ["nk", "gen"]
    far = _cand(KIDS_FAR, 90, "open")  # open, but 90 min on foot: the far option whatever its hours
    out = errand_order([far, general], frozenset({"clinic"}), DAY, False, sub="kids_doctor")
    assert [c.poi.id for c in out] == ["gen", "kids"]


def test_a_dentist_nearby_is_no_far_card_and_says_its_minutes():
    turn = take_turn(new_state(*ORIGIN, "ru"), "где стоматолог", _env([DENT, GENERAL])).turn
    assert turn.places[0].id == "dent"
    assert turn.reply.startswith("Ближайшая открытая стоматология — «Доктор Дент»")
    assert "мин пешком" in turn.reply
    assert "лучше на транспорте" not in turn.reply
