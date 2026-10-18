"""The three memory layers: dialogue follow-ups, anonymous marks of people, the opt-in personal profile.

Synthetic places on a line north of the origin; no network, no real files (WALKS_* paths point into tmp_path)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from walks import followup as followup_mod
from walks import generate as gen_mod
from walks import llm
from walks.attributes import serves_alcohol
from walks.feedback import (
    ALLOWED_FIELDS,
    SIGNALS,
    FeedbackEntry,
    FeedbackIndex,
    add_feedback,
    hours_evidence,
    hours_label,
    load_feedback,
)
from walks.followup import apply_follow_up, conversation_after, describe, parse_follow_up
from walks.models import POI, Constraints, Conversation, Intent, LLMStep
from walks.pipeline import recommend
from walks.profile import (
    Profile,
    adapt_weather,
    avoided_kinds,
    constraints_for,
    delete_profile,
    forget_item,
    list_items,
    load_profile,
    merge_into_intent,
    new_profile_id,
    personal_view,
    preferences_payload,
    profile_path,
    record_like,
    record_visit,
    remember,
    save_profile,
    suggest_chips,
    valid_id,
)
from walks.reqlog import record_for
from walks.retrieve import VISITED_PENALTY, retrieve
from walks.walking import offline_router
from walks.weather import manual_weather

NOON = datetime(2026, 10, 14, 12, 0)  # a Wednesday
ORIGIN = (51.0890, 71.4160)
DEG_M = 111_320.0
DATA = Path(__file__).resolve().parents[2] / "data"
NAMES = ["Alpha", "Bravo", "Cedar", "Delta", "Ember", "Fjord", "Garnet", "Hazel"]


def _poi(poi_id: str, north_m: float, category: str = "cafe", **kw) -> POI:
    return POI(
        id=poi_id,
        name=kw.pop("name", poi_id),
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        **kw,
    )


def _cafes(n: int = 8, step: int = 80) -> list[POI]:
    return [_poi(f"c{i}", step * (i + 1), name=NAMES[i]) for i in range(n)]


def _ask(text: str, pois: list[POI], **kw):
    return recommend(text, *ORIGIN, NOON, use_llm=False, pois=pois, router=offline_router(), **kw)


def _mark(poi_id: str, signal: str, days_ago: int = 1, bucket: str = "day", demo: bool = False):
    day = NOON.date() - timedelta(days=days_ago)
    return FeedbackEntry(
        poi_id=poi_id,
        signal=signal,  # type: ignore[arg-type]
        date=day.isoformat(),
        weekday=("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day.weekday()],  # type: ignore[arg-type]
        hour_bucket=bucket,  # type: ignore[arg-type]
        demo=demo,
    )


def _intent(**kw) -> Intent:
    return Intent(categories=["cafe"], **kw)


# ---- layer 1: follow-up parsing ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("а поближе?", "closer", True),
        ("closer please", "closer", True),
        ("жақынырақ", "closer", True),
        ("а без алкоголя", "no_alcohol", True),
        ("without alcohol", "no_alcohol", True),
        ("алкогольсіз", "no_alcohol", True),
        ("что-то другое", "more", True),
        ("ещё", "more", True),
        ("something else", "more", True),
        ("басқа", "more", True),
        ("а подешевле", "budget", "low"),
        ("cheaper", "budget", "low"),
        ("а подороже", "budget", "high"),
        ("а если с ребёнком", "with_kids", "yes"),
        ("а без ребёнка", "with_kids", "no"),
        ("with a kid", "with_kids", "yes"),
        ("потише", "quiet", "yes"),
        ("а с розеткой", "wifi_socket", "yes"),
        ("на час дольше", "extra_min", 60),
        ("подольше", "extra_min", 30),
        ("ещё полчаса", "extra_min", 30),
        ("ещё час", "extra_min", 60),
        ("покороче", "extra_min", -30),
        ("а на 2 часа", "extra_min", 120 - 60),
        ("а на машине", "mode", "car"),
    ],
)
def test_follow_up_rules_read_ru_kk_en_messages(text, field, value):
    fu = parse_follow_up(text, _intent())
    assert fu is not None
    assert getattr(fu, field) == value


@pytest.mark.parametrize(
    "text",
    [
        "Тихое место с кофе и розеткой",  # a new request: names a kind of place and says more
        "хочу в музей",  # another kind of place than the previous request
        "Рядом с Mega Silk Way, прогулка 30–60 мин",
        "расскажи пожалуйста подробно про все достопримечательности города и их историю",
        "",
    ],
)
def test_a_new_request_is_not_a_follow_up(text):
    assert parse_follow_up(text, _intent()) is None


def test_more_next_to_another_change_is_only_a_filler():
    fu = parse_follow_up("а ещё с ребёнком", _intent())
    assert fu is not None
    assert fu.with_kids == "yes"
    assert not fu.more


def test_follow_up_merges_into_a_new_intent_without_touching_the_old_one():
    prev = _intent(time_budget_min=60, quiet=True)
    conv = Conversation(
        intent=prev, constraints=Constraints(), shown_ids=["a", "b"], farthest_m=400, lat=1, lon=2
    )
    fu = parse_follow_up("а если с ребёнком, на час дольше, подешевле", prev)
    assert fu is not None
    intent, cons = apply_follow_up(conv, fu)
    assert (intent.with_kids, intent.time_budget_min, intent.budget) == (True, 120, "low")
    assert intent.quiet  # untouched flags stay
    assert not prev.with_kids  # the previous intent is not modified
    assert cons.exclude_ids == []  # not an «ещё»
    assert "Уточнение" in describe(fu, intent, cons)
    assert "+60" in describe(fu, intent, cons)


def test_closer_caps_the_radius_below_the_farthest_shown_place():
    prev = _intent()
    conv = Conversation(
        intent=prev, constraints=Constraints(), shown_ids=[], farthest_m=500, lat=1, lon=2
    )
    fu = parse_follow_up("поближе", prev)
    assert fu is not None
    assert apply_follow_up(conv, fu)[1].radius_cap_m == 400
    conv2 = conv.model_copy(update={"farthest_m": 0})
    assert apply_follow_up(conv2, fu)[1].radius_factor == pytest.approx(0.6)  # nothing shown yet


# ---- layer 1: dialogue through the pipeline ---------------------------------------------------------


def test_more_excludes_every_place_shown_so_far():
    pois = _cafes()
    first = _ask("Кафе", pois)
    conv1 = conversation_after(None, first)
    second = _ask("ещё", pois, conversation=conv1)
    conv2 = conversation_after(conv1, second)
    third = _ask("что-то другое", pois, conversation=conv2)
    ids = [{r.poi.id for r in res.recs} for res in (first, second, third)]
    assert second.continued
    assert third.continued
    assert ids[0].isdisjoint(ids[1])
    assert (ids[0] | ids[1]).isdisjoint(ids[2])
    assert conv2.shown_ids == [r.poi.id for r in first.recs] + [r.poi.id for r in second.recs]
    assert second.retrieval.filters.excluded_followup == 3
    assert second.intent.intent.categories == ["cafe"]  # the request is the same one, refined


def test_closer_after_a_request_shows_only_nearer_places():
    pois = _cafes()
    first = _ask("Кафе", pois)
    conv = conversation_after(None, first)
    second = _ask("а поближе?", pois, conversation=conv)
    cap = second.constraints.radius_cap_m
    ids_first = {r.poi.id for r in first.recs}
    farthest = max(c.distance_m for c in first.retrieval.candidates if c.poi.id in ids_first)
    assert cap == round(0.8 * farthest)
    assert second.recs
    assert all(c.distance_m <= cap for c in second.retrieval.candidates)
    assert second.follow_up_note.startswith("Уточнение")


def test_no_alcohol_drops_bars_and_alcohol_tags():
    pois = [
        _poi("wine", 50, "cafe", tags=["overture_category=bar"], name="Wine"),
        _poi("pub", 60, "bar_nightlife", name="Pub"),
        _poi("tea", 120, "cafe", name="Tea"),
        _poi("cof", 140, "cafe", name="Coffee"),
    ]
    assert serves_alcohol(pois[0])
    assert serves_alcohol(pois[1])
    assert not serves_alcohol(pois[2])
    first = _ask("Кафе", pois)
    assert "wine" in {r.poi.id for r in first.recs}
    second = _ask("а без алкоголя", pois, conversation=conversation_after(None, first))
    assert {r.poi.id for r in second.recs} == {"tea", "cof"}
    assert second.constraints.no_alcohol
    assert second.intent.intent.budget == first.intent.intent.budget


def test_a_new_request_resets_the_dialogue():
    pois = _cafes()
    first = _ask("Кафе", pois)
    conv = conversation_after(None, first)
    fresh = _ask("Кафе с Wi-Fi", pois, conversation=conv)
    assert not fresh.continued
    assert fresh.constraints.exclude_ids == []
    again = conversation_after(conv, fresh)
    assert again.shown_ids == [r.poi.id for r in fresh.recs]
    assert again.turns == 1


def test_llm_second_opinion_only_for_a_short_vague_message(monkeypatch):
    prev = _intent()
    calls: list[str] = []

    def fake_json(prompt, schema, **kw):
        calls.append(prompt)
        return llm.LLMCall(
            schema(is_follow_up=True, closer=True), LLMStep(chain=["m"], model="m", ms=1)
        )

    monkeypatch.setattr(followup_mod, "generate_json", fake_json)
    monkeypatch.setattr(followup_mod, "ai_off_reason", lambda use_llm: "")
    fu, step = followup_mod.refine_with_llm("ну поближе что ли", prev, use_llm=True)
    assert fu is not None
    assert fu.closer
    assert step is not None
    assert len(calls) == 1
    # not asked: a named other kind of place, a time, too long, or the AI is off
    assert followup_mod.refine_with_llm("хочу в музей", prev, use_llm=True) == (None, None)
    assert followup_mod.refine_with_llm("на 2 часа", prev, use_llm=True) == (None, None)
    assert followup_mod.refine_with_llm("a b c d e f g h", prev, use_llm=True) == (None, None)
    monkeypatch.setattr(followup_mod, "ai_off_reason", lambda use_llm: "off")
    assert followup_mod.refine_with_llm("ну поближе что ли", prev, use_llm=True) == (None, None)
    assert len(calls) == 1


# ---- layer 3: marks of people -----------------------------------------------------------------------


def test_people_marks_are_their_own_hours_evidence_level():
    pois = [_poi("x", 100, name="Xray"), _poi("osm", 120, name="Osmium", opening_hours="24/7")]
    idx = FeedbackIndex(
        [_mark("x", "was_open", 1), _mark("x", "was_open", 3), _mark("osm", "was_open", 2)]
    )
    res = retrieve(pois, *ORIGIN, _intent(), NOON, feedback=idx)
    x = next(c for c in res.candidates if c.poi.id == "x")
    osm = next(c for c in res.candidates if c.poi.id == "osm")
    assert x.hours_state == "unknown"  # the OSM level is untouched
    assert x.people is not None
    assert (x.people.hours, x.people.n_open) == ("open", 2)
    assert hours_evidence(x.hours_state, x.people) == "people"
    assert hours_evidence(osm.hours_state, osm.people) == "osm"
    last = (NOON.date() - timedelta(days=1)).strftime("%d.%m")
    assert hours_label(x.people) == f"люди отмечали открыто (2 раза, последний {last})"
    assert "people_open" in x.reasons
    plain = retrieve(pois, *ORIGIN, _intent(), NOON)
    plain_x = next(c for c in plain.candidates if c.poi.id == "x")
    assert x.score - plain_x.score == pytest.approx(
        1.0
    )  # two consistent marks: a plain +1, no OSM state change


def test_a_card_says_it_in_its_notes_without_calling_the_hours_confirmed():
    pois = [_poi("x", 100, name="Xray")]
    idx = FeedbackIndex([_mark("x", "was_open", 1), _mark("x", "was_open", 2)])
    res = _ask("Кафе", pois, feedback=idx)
    rec = res.recs[0]
    assert rec.hours_state == "unknown"
    assert "Люди отмечали открыто (2 раза" in rec.notes
    assert "Часы работы в данных неизвестны" in rec.notes  # the OSM level still says unknown


def test_marks_decay_and_old_ones_are_ignored():
    idx = FeedbackIndex([_mark("x", "was_open", 31)])
    assert idx.evidence("x", NOON) is None  # older than 30 days
    idx = FeedbackIndex([_mark("x", "was_open", 30)])
    assert idx.evidence("x", NOON) is not None
    fresh_closed = FeedbackIndex([_mark("x", "was_open", 25), _mark("x", "was_closed", 1)])
    ev = fresh_closed.evidence("x", NOON)
    assert ev is not None
    assert ev.hours == "closed"  # the fresh mark outweighs the old one
    assert ev.confidence == "low"  # but they contradict each other
    same_day = FeedbackIndex([_mark("x", "was_open", 2), _mark("x", "was_closed", 2)])
    ev = same_day.evidence("x", NOON)
    assert ev is not None
    assert ev.hours == "mixed"
    assert "расходятся" in (hours_label(ev) or "")
    consistent = FeedbackIndex([_mark("x", "was_open", 2), _mark("x", "was_open", 3)])
    ev = consistent.evidence("x", NOON)
    assert ev is not None
    assert ev.confidence == "medium"


def test_a_mark_from_another_part_of_the_day_counts_half():
    idx = FeedbackIndex([_mark("x", "was_open", 1, "night"), _mark("x", "was_closed", 1, "day")])
    ev = idx.evidence("x", NOON)  # noon = «day»: the closed mark wins
    assert ev is not None
    assert ev.hours == "closed"


def test_people_closed_contradicting_osm_lowers_confidence_and_says_so():
    pois = [_poi("x", 100, name="Xray", opening_hours="24/7")]
    plain = _ask("Кафе", pois)
    assert plain.recs[0].confidence == "high"
    idx = FeedbackIndex([_mark("x", "was_closed", 1), _mark("x", "was_closed", 2)])
    res = _ask("Кафе", pois, feedback=idx)
    rec = res.recs[0]
    assert rec.hours_state == "open"  # OSM says open and stays the OSM level
    assert rec.confidence != "high"
    assert "расходится с часами OSM" in rec.notes


def test_socket_marks_make_a_cafe_usable_for_a_quiet_cafe_with_a_socket():
    pois = [_poi("near", 100, name="Nearby"), _poi("far", 400, name="Faraway")]
    q = "Тихое кафе с розеткой"
    before = _ask(q, pois)
    assert before.recs[0].poi.id == "near"
    assert all("по отметкам людей" not in r.why for r in before.recs)
    idx = FeedbackIndex([_mark("far", "has_socket", 1), _mark("far", "has_socket", 2)])
    after = _ask(q, pois, feedback=idx)
    assert after.recs[0].poi.id == "far"
    why = after.recs[0].why
    assert "по отметкам людей" in why.lower()
    assert "есть розетка (2 отметки)" in why
    assert "не настоящие" not in why  # real marks are not labelled sample ones
    demo = FeedbackIndex([_mark("far", "has_socket", 1, demo=True)])
    sample = _ask(q, pois, feedback=demo).recs[0].why.lower()
    assert "(примерные, не настоящие)" in sample
    assert "демо" not in sample


def test_quiet_and_noisy_marks_move_a_quiet_request():
    pois = [_poi("a", 100, name="Aaa"), _poi("b", 110, name="Bbb")]
    idx = FeedbackIndex([_mark("a", "noisy", 1), _mark("a", "noisy", 2), _mark("b", "quiet", 1)])
    res = retrieve(pois, *ORIGIN, _intent(quiet=True), NOON, feedback=idx)
    assert [c.poi.id for c in res.candidates] == ["b", "a"]
    assert "people_noisy" in res.candidates[1].reasons


# ---- layer 3: the stored marks are anonymous --------------------------------------------------------

REQUIRED = {"poi_id", "signal", "date", "weekday", "hour_bucket"}


def test_feedback_schema_has_no_identifying_field():
    assert set(FeedbackEntry.model_fields) == ALLOWED_FIELDS == REQUIRED | {"demo"}
    forbidden = ("user", "session", "uid", "lat", "lon", "coord", "ip", "device", "name")
    assert not [f for f in FeedbackEntry.model_fields if any(w in f for w in forbidden)]
    with pytest.raises(ValueError, match="user_id"):
        FeedbackEntry.model_validate({**_mark("x", "quiet").model_dump(), "user_id": "u1"})
    with pytest.raises(ValueError, match="date"):
        FeedbackEntry.model_validate({**_mark("x", "quiet").model_dump(), "date": "not-a-day"})


def test_add_feedback_writes_only_the_allowed_fields_and_a_day_without_time(tmp_path):
    path = tmp_path / "fb.json"
    entry = add_feedback("node/1", "has_socket", datetime(2026, 10, 14, 19, 45), path)
    add_feedback("node/1", "quiet", datetime(2026, 10, 15, 8, 5), path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert set(rows[0]) == REQUIRED  # no `demo` on a real mark
    assert rows[0] == {
        "poi_id": "node/1",
        "signal": "has_socket",
        "date": "2026-10-14",
        "weekday": "wed",
        "hour_bucket": "evening",
    }
    assert entry.date == "2026-10-14"
    assert all(set(r) <= ALLOWED_FIELDS and "T" not in r["date"] for r in rows)
    assert len(load_feedback(path)) == 2
    with pytest.raises(ValueError, match="signal"):
        add_feedback("node/1", "love_it", None, path)


def test_the_shipped_seed_is_marked_demo_and_anonymous():
    rows = json.loads((DATA / "city_feedback.json").read_text(encoding="utf-8"))
    assert len(rows) >= 8
    assert all(set(r) == REQUIRED | {"demo"} for r in rows)
    assert all(r["demo"] is True for r in rows)  # every seeded entry says it is demo
    assert all(r["signal"] in SIGNALS for r in rows)
    assert all(date.fromisoformat(r["date"]) for r in rows)
    ids = {r["poi_id"] for r in rows}
    assert len(ids) >= 8
    known = {p["id"]: p for p in json.loads((DATA / "poi.enriched.json").read_text("utf-8"))}
    assert ids <= set(known)  # real places
    assert {known[i]["category"] for i in ids} == {"cafe"}


def test_feedback_off_disables_writing(monkeypatch):
    monkeypatch.setenv("WALKS_FEEDBACK", "off")
    assert len(load_feedback()) == 0
    with pytest.raises(OSError, match="отключены"):
        add_feedback("node/1", "quiet")


# ---- layer 2: profile storage -----------------------------------------------------------------------


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("WALKS_PROFILE_DIR", str(tmp_path / "profiles"))
    return tmp_path / "profiles"


def test_profile_file_is_a_random_uuid_and_forget_all_deletes_it(profiles):
    uid = new_profile_id()
    assert valid_id(uid)
    assert load_profile(uid) is None  # nothing is created by looking
    path = save_profile(uid, remember(Profile(), "with_kids"))
    assert path == profiles / f"{uid}.json"
    assert load_profile(uid) is not None
    assert delete_profile(uid)
    assert not path.exists()
    assert load_profile(uid) is None
    assert not delete_profile(uid)  # nothing left to forget


@pytest.mark.parametrize("bad", ["../x", "..\\x", "x", "", "A" * 36, None, 5])
def test_only_a_canonical_uuid_names_a_profile_file(bad, profiles):
    assert not valid_id(bad)
    assert load_profile(bad) is None  # type: ignore[arg-type]
    assert not delete_profile(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="идентификатор"):
        profile_path(bad)  # type: ignore[arg-type]


def test_the_panel_lists_every_stored_item_and_each_can_be_deleted():
    p = Profile(with_kids=True, kids_age_band="4-7", mobility="stroller", quiet=True, budget="low")
    p = remember(remember(p, "halal"), "no_alcohol")
    p = remember(remember(p, "language:en"), "walk_pace:slow")
    p = remember(p, "cold_tolerance:low")
    p = record_like(record_like(p, "cafe"), "cafe")
    p = record_visit(p, "node/7", date(2026, 10, 12))
    labels = {i.key: i.label for i in list_items(p, {"node/7": "Alpha"})}
    assert set(labels) == {
        "with_kids",
        "mobility",
        "quiet",
        "budget",
        "halal",
        "no_alcohol",
        "language",
        "walk_pace",
        "cold_tolerance",
        "visited:node/7",
        "liked:cafe",
    }
    assert "4–7" in labels["with_kids"]
    assert "Alpha" in labels["visited:node/7"]
    assert labels["liked:cafe"].endswith("×2")
    for key in labels:
        p = forget_item(p, key)
    assert list_items(p) == []
    assert p == Profile()


def test_chips_come_from_the_parsed_intent_and_save_only_on_a_click():
    intent = Intent(with_kids=True, quiet=True, budget="low", language="en")
    chips = {c.key: c.label for c in suggest_chips(intent, Constraints(no_alcohol=True), Profile())}
    assert chips["with_kids"] == "Запомнить: с ребёнком?"
    assert {"quiet", "budget:low", "no_alcohol", "language:en"} <= set(chips)
    held = Profile(with_kids=True, quiet=True, budget="low", no_alcohol=True, language="en")
    assert suggest_chips(intent, Constraints(no_alcohol=True), held) == []
    stroller = suggest_chips(Intent(accessibility=True, with_kids=True), Constraints(), Profile())
    assert [c.key for c in stroller] == ["with_kids", "mobility:stroller"]
    assert remember(Profile(), "mobility:stroller").mobility == "stroller"


# ---- layer 2: reading the profile -------------------------------------------------------------------


def test_the_request_wins_over_the_profile_and_the_profile_fills_the_gaps():
    profile = Profile(with_kids=True, quiet=True, budget="low", mobility="wheelchair", halal=True)
    asked = Intent(budget="high", categories=["cafe"])
    merged, applied = merge_into_intent(asked, profile, "дорогой ресторан")
    assert merged.budget == "high"  # the request names a budget: the profile does not override it
    assert (merged.with_kids, merged.quiet, merged.accessibility) == (True, True, True)
    assert "халяль" in merged.free_text_keywords
    assert "budget" not in applied
    assert {"with_kids", "quiet", "mobility", "halal"} <= set(applied)
    again, applied2 = merge_into_intent(Intent(quiet=True), Profile(quiet=True), "тихо")
    assert applied2 == []  # nothing changed: nothing to claim
    assert again.quiet
    open_budget, applied3 = merge_into_intent(Intent(), Profile(budget="low"), "кафе")
    assert (open_budget.budget, applied3) == ("low", ["budget"])
    assert asked.with_kids is False  # inputs are not modified
    lang, _ = merge_into_intent(Intent(), Profile(language="en"), "🙂")
    assert lang.language == "en"
    assert merge_into_intent(Intent(), Profile(language="en"), "кафе")[0].language == "ru"


def test_profile_flags_reach_the_answer_and_say_so():
    pois = _cafes(4)
    profile = Profile(with_kids=True, kids_age_band="4-7", quiet=True)
    res = _ask("Кафе", pois, profile=profile)
    assert res.intent.intent.with_kids
    assert res.profile_applied == ["with_kids", "quiet"]
    assert all(
        "Вы отмечали" not in r.why for r in res.recs
    )  # said once, in the lead (test_stated_wish)
    plain = _ask("Кафе", pois)
    assert not plain.intent.intent.with_kids
    assert plain.profile_applied == []
    assert all("Вы отмечали" not in r.why for r in plain.recs)


def test_visited_places_are_ranked_lower():
    pois = _cafes(3)
    base = retrieve(pois, *ORIGIN, _intent(), NOON)
    top = base.candidates[0]
    profile = record_visit(Profile(), top.poi.id, date(2026, 10, 1))
    res = retrieve(pois, *ORIGIN, _intent(), NOON, personal=personal_view(profile))
    seen = next(c for c in res.candidates if c.poi.id == top.poi.id)
    assert seen.score == pytest.approx(top.score - VISITED_PENALTY)
    assert "visited" in seen.reasons
    assert res.candidates[0].poi.id != top.poi.id
    answer = _ask("Кафе", pois, profile=profile)
    shown = {r.poi.id: r for r in answer.recs}
    assert top.poi.id in shown  # only three places: the visited one is still offered, last
    assert "Вы отмечали, что уже бывали здесь" in shown[top.poi.id].notes


def test_liked_categories_give_a_small_lift():
    pois = [_poi("c", 100, "cafe", name="Cafe"), _poi("p", 100, "park_garden", name="Park")]
    base = retrieve(pois, *ORIGIN, Intent(), NOON)
    liked = retrieve(
        pois, *ORIGIN, Intent(), NOON, personal=personal_view(record_like(Profile(), "park_garden"))
    )
    gain = next(c.score for c in liked.candidates if c.poi.id == "p") - next(
        c.score for c in base.candidates if c.poi.id == "p"
    )
    assert gain == pytest.approx(0.3 + 1.5)  # a request that names no kind lifts a liked kind more
    named = retrieve(
        pois,
        *ORIGIN,
        Intent(wished=["cafe"]),
        NOON,
        personal=personal_view(record_like(Profile(), "park_garden")),
    )
    plain = retrieve(pois, *ORIGIN, Intent(wished=["cafe"]), NOON)
    lift = next(c.score for c in named.candidates if c.poi.id == "p") - next(
        c.score for c in plain.candidates if c.poi.id == "p"
    )
    assert lift == pytest.approx(0.3)


def test_pace_no_alcohol_and_cold_tolerance_shape_the_search():
    cons, applied = constraints_for(Profile(walk_pace="slow", no_alcohol=True))
    assert (cons.radius_factor, cons.no_alcohol, applied) == (
        0.8,
        True,
        ["no_alcohol", "walk_pace"],
    )
    assert constraints_for(Profile())[1] == []
    chilly = adapt_weather(manual_weather(-8), Profile(cold_tolerance="low"))
    assert chilly[1]
    assert chilly[0] is not None
    assert chilly[0].adverse
    assert not adapt_weather(manual_weather(-8), Profile())[0].adverse  # type: ignore[union-attr]
    hardy, changed = adapt_weather(manual_weather(-20), Profile(cold_tolerance="high"))
    assert changed
    assert hardy is not None
    assert not hardy.adverse
    heavy, _ = adapt_weather(manual_weather(-20, 5.0), Profile(cold_tolerance="high"))
    assert heavy is not None
    assert heavy.adverse  # a downpour is not about the cold
    assert adapt_weather(None, Profile(cold_tolerance="low")) == (None, False)


# ---- layer 2: what leaves the machine ---------------------------------------------------------------


def test_only_flags_go_to_the_llm_never_the_visited_list(monkeypatch):
    pois = _cafes(4)
    profile = record_like(
        record_visit(Profile(with_kids=True, no_alcohol=True), "c0", date(2026, 10, 1)), "cafe"
    )
    seen: list[str] = []

    def fake_json(prompt, schema, **kw):
        seen.append(prompt)
        raise llm.LLMUnavailable("test: no answer")

    monkeypatch.setattr(gen_mod, "ai_off_reason", lambda use_llm: "")
    monkeypatch.setattr(gen_mod, "generate_json", fake_json)
    res = recommend(
        "Кафе",
        *ORIGIN,
        NOON,
        use_llm=True,
        pois=pois,
        router=offline_router(),
        profile=profile,
    )
    assert seen
    assert res.llm_payload is not None
    prompt, payload = seen[0], json.dumps(res.llm_payload, ensure_ascii=False)
    for text in (prompt, payload):
        assert '"c0"' not in text  # the visited place is not offered while others remain
        assert "visited" not in text
        assert "liked" not in text
        assert "2026-10-01" not in text  # the day of the visit
    assert res.llm_payload["user_preferences"] == {"with_kids": True, "no_alcohol": True}
    assert all("visited" not in c["match"] for c in res.llm_payload["candidates"])
    assert preferences_payload(profile) == {"with_kids": True, "no_alcohol": True}
    assert "c0" not in json.dumps(preferences_payload(profile))


def test_a_request_with_a_profile_is_not_written_to_the_request_log(tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    pois = _cafes(4)
    _ask("Кафе", pois, profile=Profile(with_kids=True))
    assert not log.exists()
    res = _ask("Кафе", pois)  # no profile: the usual anonymous aggregate
    assert log.exists()
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert rec["flags"]["with_kids"] is False
    assert not (set(rec) & {"profile", "visited", "liked", "uid", "poi_ids"})
    assert record_for(res) == rec
    private = _ask("Кафе", pois, profile=Profile())
    assert private.private
    follow = _ask("ещё", pois, conversation=conversation_after(None, private))
    assert follow.private  # a dialogue that started with a profile stays out of the log
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def test_a_profile_never_reaches_the_marks_file(tmp_path, monkeypatch, profiles):
    fb = tmp_path / "fb.json"
    fb.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("WALKS_FEEDBACK", str(fb))
    uid = new_profile_id()
    save_profile(uid, Profile(with_kids=True, visited=[]))
    _ask("Кафе", _cafes(3), profile=load_profile(uid))
    assert json.loads(fb.read_text(encoding="utf-8")) == []  # a request never writes a mark
    add_feedback("c1", "quiet", NOON)
    text = fb.read_text(encoding="utf-8")
    assert uid not in text
    assert "with_kids" not in text


def test_conversation_state_holds_no_text_of_the_request():
    res = _ask("Тихое кафе, пожалуйста", _cafes(3))
    state = conversation_after(None, res).model_dump_json()
    assert "Тихое кафе" not in state
    assert "пожалуйста" not in state


# ---- layer 2: the free text, the child's age, the kinds left out ------------------------------------


def test_about_is_clean_bounded_and_the_one_free_text_that_reaches_retrieval_input():
    p = Profile(about="  живу на левом\n\n берегу\t\x00 ")
    assert p.about == "живу на левом берегу"
    assert personal_view(p).about == "живу на левом берегу"
    assert personal_view(Profile()).about == ""
    with pytest.raises(ValidationError):
        Profile(about="я" * 501)
    assert len(Profile(about="я" * 500).about) == 500
    assert "about" not in preferences_payload(p)  # the flags' payload stays flags only


def test_about_is_a_stored_item_that_can_be_forgotten():
    p = Profile(about="не пью кофе")
    labels = {i.key: i.label for i in list_items(p)}
    assert "не пью кофе" in labels["about"]
    assert forget_item(p, "about").about == ""
    long = list_items(Profile(about="а" * 200))[0].label
    assert "…" in long
    assert len(long) < 120


def test_a_childs_age_needs_with_kids():
    assert Profile(with_kids=True, kids_age_band="4-7").kids_age_band == "4-7"
    assert Profile(with_kids=False, kids_age_band="4-7").kids_age_band is None
    p = remember(Profile(), "kids_age_band:4-7")  # an age alone is not kept either once validated
    assert Profile.model_validate(p.model_dump()).kids_age_band is None


def test_avoided_kinds_are_a_hard_constraint_unless_the_request_names_the_kind():
    p = Profile(avoid=["bar_nightlife", "mall", "mall"])
    assert p.avoid == ["bar_nightlife", "mall"]
    assert avoided_kinds(Intent(), p, "куда сходить") == ["bar_nightlife", "mall"]
    assert avoided_kinds(Intent(wished=["mall"]), p, "хочу в торговый центр") == ["bar_nightlife"]
    assert avoided_kinds(Intent(), Profile(), "") == []
    cafe = Profile(
        avoid=["cafe"]
    )  # «поесть» names a family: the avoided café leaves, the restaurants stay
    assert avoided_kinds(
        Intent(wished=["restaurant", "cafe", "fast_food"]), cafe, "хочу поесть"
    ) == ["cafe"]
    assert avoided_kinds(Intent(wished=["cafe"]), cafe, "хочу кофе") == []
    merged, applied = merge_into_intent(Intent(), p, "куда сходить")
    assert merged.exclude_categories == []  # the just-visited kinds keep their own, softer rule
    assert "avoid" not in applied
    assert [i.key for i in list_items(p)] == ["avoid:bar_nightlife", "avoid:mall"]
    assert forget_item(p, "avoid:mall").avoid == ["bar_nightlife"]


def test_a_like_lifts_the_kind_off_the_avoid_list():
    p = record_like(Profile(avoid=["cafe", "mall"]), "cafe")
    assert p.avoid == ["mall"]
    assert p.liked == {"cafe": 1}
    assert [i.label for i in list_items(Profile(liked={"cafe": 1}))] == ["понравилось: кафе"]
