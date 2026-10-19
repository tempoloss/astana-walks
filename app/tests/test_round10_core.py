"""The live check of the stand at 19:59 from Байтерек (wave 11): «Хочу тихое кафе с розеткой, поработать час». A card
whose record confirms Wi-Fi but says nothing of sockets says sockets are not confirmed (and the same for Wi-Fi asked
and unknown); a record with neither keeps the label the eval counts; the reason says a feature once."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.card_notes import claim_notes, work_note
from walks.dialog import TurnEnv, new_state, take_turn
from walks.generate import template_recs
from walks.i18n import t
from walks.intent import parse_rules
from walks.models import POI, Candidate, Intent, PeopleEvidence, load_pois
from walks.retrieve import retrieve
from walks.walking import offline_router
from walks.wishes import asked_work_needs

BAITEREK = (51.1283, 71.4305)
EVENING = datetime(2026, 10, 19, 19, 59)
ASK = "Хочу тихое кафе с розеткой, поработать час"
FATTUSH = "node/4853972122"  # «Фаттуш»: internet_access=wlan, nothing about sockets


@pytest.fixture(scope="module")
def fattush() -> POI:
    poi = next(p for p in load_pois() if p.id == FATTUSH)
    assert "internet_access=wlan" in poi.tags
    assert not any(tag.startswith(("socket", "power_supply")) for tag in poi.tags)
    return poi


def _poi(poi_id: str, north_m: float, category: str, tags: list[str]) -> POI:
    return POI(
        id=poi_id, name=poi_id, lat=BAITEREK[0] + north_m / 111_320.0, lon=BAITEREK[1],
        category=category, tags=tags,
    )  # fmt: skip


def _card(pois: list[POI], text: str, poi_id: str):
    intent = parse_rules(text).intent
    cands = retrieve(pois, *BAITEREK, intent, EVENING).candidates
    return next(r for r in template_recs(cands, intent) if r.poi.id == poi_id)


def test_what_a_work_wish_names_is_read_from_its_words():
    assert asked_work_needs(ASK) == "both"  # «розетка» and «поработать»
    assert asked_work_needs("кафе где можно зарядить телефон") == "socket"
    assert asked_work_needs("кафе с вайфаем") == "wifi"
    assert asked_work_needs("cafe with wifi") == "wifi"
    assert asked_work_needs("кафе поработать с ноутбуком") == "both"
    assert parse_rules("кафе с вайфаем").intent.needs_wifi_socket  # every form of «вайфай»
    assert parse_rules(ASK).intent.work_needs == "both"
    assert parse_rules("тихое кафе").intent.work_needs == ""


def test_the_real_record_with_wifi_only_says_sockets_are_not_confirmed(fattush):
    card = _card([fattush], ASK, FATTUSH)
    assert t("note_socket_unverified_wifi", "ru") in card.notes
    assert (
        t("note_socket_unverified_wifi", "ru") == "Wi-Fi есть по данным; розетки не подтверждены."
    )
    assert card.why.count("Wi-Fi") == 1, card.why  # «…; в OSM указан Wi-Fi. Wi-Fi.» was said twice


def test_on_the_card_the_socket_note_comes_first_and_a_library_without_either_keeps_the_label(
    fattush,
):
    library = _poi("lib", 300, "coworking_library", [])
    env = TurnEnv(when=EVENING, use_llm=False, router=offline_router(), pois=[fattush, library])
    turn = take_turn(new_state(*BAITEREK, "ru"), ASK, env).turn
    notes = {p.id: p.note for p in turn.places}
    assert notes[FATTUSH] == t("note_socket_unverified_wifi", "ru")
    assert notes["lib"] == t("note_wifi", "ru")  # the label eval/metrics counts (`wifi_unlabeled`)


def test_wifi_asked_and_unknown_is_said_too():
    socket_only = _poi("s", 100, "cafe", ["power_supply=yes"])
    card = _card([socket_only], "cafe with wifi", "s")
    assert t("note_wifi_unverified_socket", "en") in card.notes
    sockets_asked = _card([socket_only], "кафе где можно зарядить телефон", "s")
    assert not any(
        t(k, "ru") in sockets_asked.notes for k in ("note_wifi", "note_wifi_unverified_socket")
    )


def test_peoples_marks_count_and_a_request_without_the_wish_gets_no_note(fattush):
    """Sockets marked by people: confirmed enough (the people line says it), no «не подтверждены»; a request that does
    not ask for Wi-Fi or sockets gets no such note at all."""
    intent = parse_rules(ASK).intent
    card = Candidate(
        poi=fattush, distance_m=300, walk_min=4, travel_min=4, hours_state="open", score=5.0,
        people=PeopleEvidence(socket=2),
    )  # fmt: skip
    assert work_note(card, intent) == ""
    assert (
        work_note(card.model_copy(update={"people": None}), intent) == "note_socket_unverified_wifi"
    )
    assert work_note(card, Intent(categories=["cafe"])) == ""


def test_a_stripped_socket_claim_adds_no_second_wifi_socket_note():
    precise = t("note_socket_unverified_wifi", "ru")
    assert claim_notes(["socket"], [precise], "ru") == []
    assert claim_notes(["socket"], [], "ru") == [
        t("note_wifi", "ru")
    ]  # no card note: the claim's own
