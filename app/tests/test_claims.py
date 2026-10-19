"""The attribute-backing check of the AI text (walks.claims): a sentence that asserts halal, step-free access, Wi-Fi,
sockets, quiet, suitability for children, prices, banquets, gaming machines or round-the-clock hours is kept only when a
field of the record backs it; otherwise it is dropped and the card says «не указано в данных». Fabricated model
payloads, in three languages."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks import generate as gen_mod
from walks import pipeline
from walks.claims import CLAIMS, note_keys, strip_unbacked, unbacked_kinds
from walks.generate import Generation, _from_llm
from walks.i18n import t
from walks.llm_output import LLMOutput, LLMRec
from walks.models import POI, Candidate, Intent, PeopleEvidence
from walks.presets import PRESETS

LANGS = ("kk", "ru", "en")
NOON = datetime(2026, 10, 14, 12, 0)
HOURS = "Mo-Su 09:00-18:00"  # confirmed open at noon, closes early: «до полуночи» is not backed

# (kind, {lang: a sentence that asserts it}); every sentence is an invented claim about a place with no such field
CLAIM_TEXT = {
    "halal": {
        "ru": "Кухня здесь обычно халяльная.",
        "kk": "Тағамдары әдетте халал.",
        "en": "The food here is typically halal.",
    },
    "access": {
        "ru": "Удобно гулять с коляской по ровным дорожкам.",
        "kk": "Арбамен серуендеуге ыңғайлы, тегіс жолдар бар.",
        "en": "The place is wheelchair accessible.",
    },
    "wifi": {
        "ru": "Есть бесплатный Wi-Fi.",
        "kk": "Мұнда Wi-Fi бар.",
        "en": "Free Wi-Fi is available.",
    },
    "socket": {
        "ru": "У столиков есть розетки.",
        "kk": "Үстелдерде розеткалар бар.",
        "en": "There are power sockets at the tables.",
    },
    "quiet": {
        "ru": "Здесь тихо и спокойно.",
        "kk": "Мұнда тыныш.",
        "en": "It is a quiet place.",
    },
    "kids": {
        "ru": "Отлично подходит для детей.",
        "kk": "Балаларға өте лайықты орын.",
        "en": "A great place for kids.",
    },
    "free": {
        "ru": "Вход бесплатный.",
        "kk": "Кіру ақысыз.",
        "en": "Entry is free of charge.",
    },
    "price": {
        "ru": "Недорогое место.",
        "kk": "Бағасы арзан.",
        "en": "Prices are affordable.",
    },
    "booking": {
        "ru": "Можно обсудить банкет для группы гостей.",
        "kk": "Банкет өткізуге болады.",
        "en": "Banquets can be arranged for groups.",
    },
    "gambling": {
        "ru": "Можно сыграть на игровых автоматах.",
        "kk": "Ойын автоматтарында ойнауға болады.",
        "en": "You can try the slot machines.",
    },
    "round_clock": {
        "ru": "Работает круглосуточно.",
        "kk": "Тәулік бойы жұмыс істейді.",
        "en": "It is open around the clock.",
    },
    "late_hours": {
        "ru": "Работает до полуночи.",
        "kk": "Түн ортасына дейін жұмыс істейді.",
        "en": "It stays open until midnight.",
    },
    "vegetarian": {
        "ru": "Есть вегетарианские блюда.",
        "kk": "Вегетариандық тағамдар бар.",
        "en": "There are vegetarian options.",
    },
    "vegan": {
        "ru": "Подходит для веганов.",
        "kk": "Веган тағамдары бар.",
        "en": "It is suitable for vegans.",
    },
    "gluten_free": {
        "ru": "Блюда здесь не содержат глютена.",
        "kk": "Мұндағы тағамдарда глютен жоқ.",
        "en": "The dishes here are naturally gluten-free.",
    },
    "kosher": {
        "ru": "Здесь подают кошерную еду.",
        "kk": "Мұнда кошер тағамдары бар.",
        "en": "Kosher food is served here.",
    },
    "open_early_late": {
        "ru": "Можно прийти ранним утром.",
        "kk": "Таңертең ерте барсаңыз болады.",
        "en": "A good option for an early morning breakfast.",
    },
    "toilet": {
        "ru": "Туалет доступен посетителям.",
        "kk": "Дәретхана келушілерге қолжетімді.",
        "en": "A toilet is available to visitors.",
    },
    "viewpoint": {
        "ru": "Можно подняться на смотровую площадку.",
        "kk": "Шолу алаңына шығуға болады.",
        "en": "You can go up to the observation deck.",
    },
    "interior": {
        "ru": "Можно зайти внутрь здания.",
        "kk": "Ғимараттың ішіне кіру мүмкін.",
        "en": "You can walk inside the building.",
    },
    "pets": {
        "ru": "Удобно прийти сюда с собакой.",
        "kk": "Итпен серуендеуге ыңғайлы.",
        "en": "It is pet-friendly: you can bring your dog.",
    },
    "group": {
        "ru": "Подходит для большой компании.",
        "kk": "Үлкен топқа өте лайықты.",
        "en": "A good place for a large group of friends.",
    },
}
CLEAN = {
    "ru": "Уютное место с кофе.",
    "kk": "Кофесі бар жайлы орын.",
    "en": "A cosy place with coffee.",
}
NOTE_OF = {c.kind: c.note for c in CLAIMS}


def poi(**kw) -> POI:
    base = {
        "id": "p",
        "name": "Кофейня",
        "lat": 51.09,
        "lon": 71.41,
        "category": "cafe",
        "opening_hours": HOURS,
    }
    return POI(**{**base, **kw})


def cand(reasons=(), people=None, state="open", **kw) -> Candidate:
    return Candidate(
        poi=poi(**kw),
        distance_m=300,
        walk_min=5,
        travel_min=5,
        hours_state=state,
        score=1.0,
        reasons=list(reasons),
        people=people,
    )


def card(c: Candidate, lang: str, why: str, what: str = "", notes: str = "", **intent_kw):
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id=c.poi.id,
                why=why,
                time_on_site_min=40,
                what_to_do=what or CLEAN[lang],
                confidence="high",
                generated_idea=False,
                notes=notes,
            )
        ]
    )
    intent = Intent(
        language=lang, time_budget_min=90, time_stated=True, **intent_kw
    )  # «на полтора часа»
    recs, _ = _from_llm(out, [c], intent)
    return recs[0]


def text_of(r) -> str:
    return " ".join([r.why, r.what_to_do, r.notes])


def test_every_claim_has_a_sentence_in_every_language():
    assert set(CLAIM_TEXT) == {c.kind for c in CLAIMS}
    for sentences in CLAIM_TEXT.values():
        assert set(sentences) == set(LANGS)


STATUS_KINDS = {
    "round_clock",
    "late_hours",
}  # a status the model writes in its own words is dropped (walks.status)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", sorted(CLAIM_TEXT))
def test_an_unbacked_claim_is_dropped_and_the_card_says_the_data_do_not_state_it(kind, lang):
    claim = CLAIM_TEXT[kind][lang]
    setup = {"open_early_late": {"state": "unknown"}, "interior": {"category": "park_garden"}}
    r = card(cand(**setup.get(kind, {})), lang, f"{CLEAN[lang]} {claim}")
    assert claim not in text_of(r)
    assert CLEAN[lang] in r.why  # the rest of the sentences stays
    if kind in STATUS_KINDS:
        return  # the status rule took it before the claims: the card's own status line says the hours
    assert kind in r.unbacked_claims
    if NOTE_OF[kind]:
        assert t(NOTE_OF[kind], lang) in r.notes
    assert (
        r.notes.count(t("note_wheelchair", lang)) <= 1
    )  # one note, however many sentences were dropped


@pytest.mark.parametrize("lang", LANGS)
def test_a_claim_in_what_to_do_and_in_notes_is_dropped_too(lang):
    claim = CLAIM_TEXT["halal"][lang]
    r = card(cand(), lang, CLEAN[lang], what=f"{claim} {CLEAN[lang]}", notes=claim)
    assert claim not in text_of(r)
    assert r.what_to_do == CLEAN[lang]
    assert r.unbacked_claims == ["halal", "halal"]
    assert r.notes.count(t("note_halal", lang)) == 1


BACKED = {
    "halal": {"tags": ["diet:halal=yes"]},
    "access": {"wheelchair": "yes"},
    "wifi": {"internet_access": "wlan"},
    "socket": {"tags": ["power_supply=yes"]},
    "quiet": {"reasons": ["quiet"]},
    "kids": {"tags": ["for_kids=yes"], "category": "entertainment"},
    "free": {"tags": ["fee=no"]},
    "gambling": {"tags": ["amenity=casino"]},
    "round_clock": {"opening_hours": "24/7"},
    "late_hours": {"opening_hours": "Mo-Su 10:00-23:00"},
    "vegetarian": {"tags": ["overture_category=vegetarian_restaurant"]},
    "vegan": {"tags": ["diet:vegan=yes"]},
    "gluten_free": {"tags": ["diet:gluten_free=yes"]},
    "kosher": {"tags": ["diet:kosher=yes"]},
    "open_early_late": {},
    "viewpoint": {"category": "viewpoint"},
    "interior": {"category": "museum_gallery"},
    "pets": {"tags": ["dog=yes"]},
    "toilet": {"tags": ["toilets=yes"]},
    "group": {"tags": ["capacity=40"]},
}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", sorted(BACKED))
def test_a_claim_a_field_backs_is_kept(kind, lang):
    spec = dict(BACKED[kind])
    reasons = spec.pop("reasons", [])
    claim = CLAIM_TEXT[kind][lang]
    r = card(cand(reasons=reasons, **spec), lang, f"{CLEAN[lang]} {claim}")
    assert r.unbacked_claims == []
    if (
        kind in STATUS_KINDS
    ):  # backed or not, a status is said only in the words of code (the card's hours line)
        assert claim not in r.why
        return
    assert claim in r.why


def test_marks_of_people_back_wifi_sockets_and_quiet():
    marks = PeopleEvidence(wifi=2, socket=1, noise="quiet", quiet=3)
    c = cand(people=marks)
    for kind in ("wifi", "socket", "quiet"):
        assert unbacked_kinds(CLAIM_TEXT[kind]["ru"], c) == []
    assert unbacked_kinds(CLAIM_TEXT["halal"]["ru"], c) == [
        "halal"
    ]  # marks of people do not say halal


@pytest.mark.parametrize("lang", LANGS)
def test_a_sentence_that_says_the_data_do_not_state_it_is_a_label_not_a_claim(lang):
    label = {
        "ru": "Доступность для колясок в данных не указана.",
        "kk": "Арбамен кіру мүмкіндігі деректерде көрсетілмеген.",
        "en": "Wheelchair access is not stated in the data.",
    }[lang]
    text, removed = strip_unbacked(f"{label} {CLAIM_TEXT['access'][lang]}", cand())
    assert text == label
    assert removed == ["access"]


def test_a_why_of_unbacked_claims_only_becomes_the_fact_based_reason_of_the_template():
    c = cand(reasons=["category"])
    r = card(c, "ru", f"{CLAIM_TEXT['halal']['ru']} {CLAIM_TEXT['kids']['ru']}")
    assert r.why.strip()
    assert "халяль" not in r.why.lower()
    assert "детей" not in r.why
    assert r.unbacked_claims == ["halal", "kids"]
    assert (
        r.text_source == "llm"
    )  # the card is still the model's; only its unbacked sentences are gone


def test_the_wheelchair_note_is_said_once_when_the_card_already_carries_it():
    c = cand(reasons=["wheelchair_unverified"])
    r = card(c, "en", CLAIM_TEXT["access"]["en"], accessibility=True)
    assert r.notes.count(t("note_wheelchair", "en")) == 1


def test_fabricated_payloads_of_the_fuzz_runs_lose_exactly_their_unbacked_sentences():
    # F06 / F07 (halal on a steak house and a pub), F27 + FZL-05 (accessible, flat paths), c21 (slot machines), c25 (banquet)
    steak = cand(name="KAL'BI", tags=["cuisine=steak_house"], category="restaurant")
    r = card(steak, "en", "American-style steaks. It often aligns with halal standards.")
    assert r.why == "American-style steaks."
    garden = cand(name="Ботанический сад", category="park_garden")
    r = card(garden, "ru", "Подходит для прогулок с детьми в колясках благодаря ровным дорожкам.")
    assert "ровн" not in r.why
    assert "коляск" not in r.why
    assert t("note_wheelchair", "ru") in r.notes
    mall = cand(name="Мега Силк Вей", category="mall")
    r = card(mall, "ru", "Крупный торговый центр. Можно поискать игровые автоматы.")
    assert r.why == "Крупный торговый центр."
    assert t("note_gambling", "ru") in r.notes


def test_the_pipeline_counts_the_dropped_claims_of_an_answer(monkeypatch):
    lat, lon = PRESETS["Mega Silk Way"]
    pois = [
        poi(id="a", name="Кофейня А", lat=lat + 0.002, lon=lon),
        poi(id="b", name="Кофейня Б", lat=lat, lon=lon + 0.002, category="restaurant"),
    ]

    def fake(intent, lat, lon, cands, when, **kw):
        recs = [
            LLMRec(
                poi_id=c.poi.id,
                why=f"{CLEAN['ru']} {CLAIM_TEXT['halal']['ru']} {CLAIM_TEXT['wifi']['ru']}",
                time_on_site_min=30,
                what_to_do=CLEAN["ru"],
                confidence="high",
                generated_idea=False,
            )
            for c in cands
        ]
        out, order = _from_llm(
            LLMOutput(recommendations=recs), cands, intent, kw.get("weather"), when
        )
        return Generation(out, order, "llm", "", None, "m")

    monkeypatch.setattr(pipeline, "generate", fake)
    res = pipeline.recommend("кофе", lat, lon, NOON, use_llm=False, pois=pois)
    assert len(res.recs) == 2
    assert res.unbacked_claims_removed == 2 * 2 == sum(len(r.unbacked_claims) for r in res.recs)
    assert all("халяль" not in r.why.lower() and "Wi-Fi" not in r.why for r in res.recs)


def test_note_keys_are_unique_and_every_note_exists_in_three_languages():
    keys = note_keys([c.kind for c in CLAIMS] * 2)
    assert len(keys) == len(set(keys))
    for key in keys:
        assert all(t(key, lang) for lang in LANGS)
    assert gen_mod.MAX_RECS == 3
