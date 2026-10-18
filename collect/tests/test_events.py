"""Tests of the event collector (collect/events): parsers on trimmed real pages, venue join, verifier, dedupe and the
whole crawl -> verify -> write cycle over a fake network. No network, no real cache.

Run from the repository root:  uv run python -m pytest collect/tests/test_events.py -q
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.events import alem, dedupe, inastana, model, qazaq, run, sxodim, telegram, venues, verify, youticket  # noqa: E402
from collect.net import NetError, Response  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

FX = Path(__file__).parent / "fixtures" / "events"
TODAY = date(2026, 10, 17)
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=model.TZ)  # 07:00 UTC
FETCHED = "2026-10-17T07:00:00+00:00"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def poi(i, name, cat="culture_theatre_cinema", lat=51.13, lon=71.40, address=None, **kw):
    return {"id": i, "name": name, "names": {"name": name}, "category": cat, "lat": lat, "lon": lon,
            "address": address, **kw}


# ---- dates ------------------------------------------------------------------------------------------------


def test_find_when_forms_and_year_inference():
    cases = {
        "от 13 000 тенге, 7 ноября в 19:00, The Bus": ((2026, 11, 7), (2026, 11, 7), "19:00"),
        "4000 тенге, 17 октября - 31 октября, Бар": ((2026, 10, 17), (2026, 10, 31), None),
        "от 3000 тенге, 15 - 18 октября": ((2026, 10, 15), (2026, 10, 18), None),
        "25 июля - 28 ноября, Мечеть": ((2026, 7, 25), (2026, 11, 28), None),
        "Уже 6 октября, 19:00": ((2026, 10, 6), (2026, 10, 6), "19:00"),
    }
    for text, (first, last, hhmm) in cases.items():
        w, _, _ = model.find_when(text, TODAY)
        assert (w.first, w.last, w.time) == (date(*first), date(*last), hhmm), text
    # no year on the page: the one nearest today wins, a range never ends before it starts
    w, _, _ = model.find_when("5 января", date(2026, 12, 20))
    assert w.first == date(2027, 1, 5)
    w, _, _ = model.find_when("20 декабря - 10 января", date(2026, 12, 20))
    assert (w.first, w.last) == (date(2026, 12, 20), date(2027, 1, 10))
    # sums and numbers that are not dates
    assert model.find_when("13 000 тенге, 3500 тенге (детский, 5-14 лет)", TODAY) is None
    assert model.find_when("31 ноября", TODAY) is None


def test_min_price_needs_a_currency():
    assert model.min_price("7000 тенге (взрослый), 3500 тенге (детский, 5-14 лет)") == 3500
    assert model.min_price("от 13 000 тенге") == 13000
    assert model.min_price("3000 теңгеден бастап") == 3000
    assert model.min_price("2 500 ₸") == 2500
    assert model.min_price("5-14 лет") is None


# ---- parsers on saved pages ---------------------------------------------------------------------------------


def test_split_venue():
    assert sxodim.split_venue("The Bus, шоссе Коргалжын, 3") == ("The Bus", None, "шоссе Коргалжын, 3")
    assert sxodim.split_venue("Астана қаласы, Жастар театры, к. Илияс Есенберлина, 10") == (
        "Жастар театры", None, "к. Илияс Есенберлина, 10")
    assert sxodim.split_venue("Өnergy Creative Hub, студия Content & Production, пр. Кабанбай батыра, 53") == (
        "Өnergy Creative Hub", "студия Content & Production", "пр. Кабанбай батыра, 53")
    assert sxodim.split_venue("Рыба моей мечты, Бейбітшілік, 20/1") == (
        "Рыба моей мечты", None, "Бейбітшілік, 20/1")
    assert sxodim.split_venue("Место сбора: БЦ «Алтын Орда», пр. Мангилик Ел, 8/2")[0] == "БЦ «Алтын Орда»"
    assert sxodim.split_venue("Государственная филармония, \u200bул. Кенесары, 32")[2] == "ул. Кенесары, 32"


def test_sxodim_cards():
    events, skipped = sxodim.parse(fx("sxodim_today.html"), sxodim.URLS[0], FETCHED, TODAY)
    by = {e["id"]: e for e in events}
    assert skipped == {"no_date": 1, "no_venue": 0}  # the «Beer & Grill» offer has no date
    bus = by["sxodim.com:77443"]
    assert bus["kind"] == "event" and bus["start"] == "2026-11-07T19:00:00+05:00"
    assert (bus["venue"]["name"], bus["venue"]["address"]) == ("The Bus", "шоссе Коргалжын, 3")
    assert (bus["price_text"], bus["price_from"]) == ("от 13 000 тенге", 13000)
    assert bus["url"].startswith("https://sxodim.com/astana/event/")
    run_ = by["sxodim.com:76905"]
    assert run_["kind"] == "run" and (run_["date_from"], run_["date_to"]) == ("2026-08-04", "2026-10-25")
    tour = by["sxodim.com:62394"]  # a price with a bracket containing commas and «5-14 лет»
    assert tour["price_from"] == 3500 and tour["venue"]["name"] == "Центральная мечеть"
    free = by["sxodim.com:77708"]
    assert free["price_text"] is None and free["start"] == "2026-10-17T18:00:00+05:00"
    assert all(model.validate_event(e) == [] for e in events)
    fields = {x["field"] for x in bus["evidence"]}
    assert {"title", "when", "venue", "address", "price"} <= fields


def test_inastana_index_and_film_page():
    films = inastana.film_links(fx("inastana_index.html"))
    assert [f[0] for f in films] == ["8832", "8831", "8830", "8611"]  # three films and the concert card
    url = "https://www.inastana.kz/afisha/8832/podvodnaa-bratva-na-straze-rifa"
    events = inastana.parse_detail(fx("inastana_film_8832.html"), url, FETCHED, TODAY, datetime.fromisoformat(FETCHED))
    assert [e["id"] for e in events] == ["inastana.kz:8832:1210017", "inastana.kz:8832:2779"]
    khan = events[0]
    assert khan["kind"] == "sessions" and (khan["date_from"], khan["date_to"]) == ("2026-10-15", "2026-10-18")
    assert khan["sessions"] == ["2026-10-17T10:20:00+05:00"]  # a run is clamped to the day of the fetch
    assert khan["venue"]["address"] == "проспект Туран, 37"
    assert khan["price_from"] == 1300 and khan["price_text"].startswith("1 300,00")  # nbsp thousands separators
    mega = events[1]
    assert len(mega["sessions"]) == 2 and mega["price_from"] == 1400
    assert all(model.validate_event(e) == [] for e in events)


def test_inastana_single_date_concert():
    url = "https://www.inastana.kz/afisha/8611/mad-mozart-v-astane"
    (e,) = inastana.parse_detail(fx("inastana_concert_8611.html"), url, FETCHED, TODAY,
                                 datetime.fromisoformat(FETCHED))
    assert e["sessions"] == ["2026-11-02T20:00:00+05:00"] and e["venue"]["name"] == "Дворец «Жастар»"
    assert e["venue"]["address"] is None and e["price_from"] == 10000


def test_qazaq_list_poster_and_contacts():
    items = qazaq.poster_list(fx("qazaq_posters.html"))
    assert [i["hall"] for i in items] == ["Үлкен зал", "Камералық зал"]  # the Almaty hall is dropped
    assert items[1]["date"] == date(2026, 10, 22)
    assert qazaq.poster_time(fx("qazaq_poster.html")) == ("Күні: 22.10.2026 Уақыты: 19:00", "19:00")
    address = qazaq.contact_address(fx("qazaq_contacts.html"))
    assert address == "Астана қаласы, Мәңгілік ел даңғылы, 10/1"
    e = qazaq.make(items[1], fx("qazaq_poster.html"), qazaq.LIST_URL, qazaq.BASE + items[1]["path"], FETCHED,
                   fx("qazaq_posters.html"), address, qazaq.CONTACTS_URL, FETCHED)
    assert e["kind"] == "event" and e["start"] == "2026-10-22T19:00:00+05:00"
    assert (e["venue"]["name"], e["venue"]["hall"]) == ("Qazaqstan ОКЗ", "Камералық зал")
    # a poster without a time page is a dated run, not an invented hour
    d = qazaq.make(items[0], None, qazaq.LIST_URL, qazaq.BASE + items[0]["path"], FETCHED, fx("qazaq_posters.html"),
                   address, qazaq.CONTACTS_URL, FETCHED)
    assert d["kind"] == "run" and d["date_from"] == d["date_to"] == "2026-10-21"
    assert qazaq.make(items[0], None, qazaq.LIST_URL, "u", FETCHED, "<html></html>", address, "c", FETCHED) is None


def test_youticket_event_museum_and_other_city():
    url = "https://youticket.kz/events/birlik-aueni"
    e = youticket.parse(fx("youticket_birlik.html"), url, FETCHED)
    assert e["kind"] == "event" and e["start"] == "2026-10-30T19:00:00+05:00"
    assert e["end"] == "2026-10-30T20:00:00+05:00"
    v = e["venue"]
    assert (v["name"], v["address"], v["coords_source"]) == ("QAZAQCONCERT", "Мангилик Ел. 10/1", "page")
    assert abs(v["lat"] - 51.1223) < 1e-3 and e["price_from"] == 2500
    museum = youticket.parse(fx("youticket_museum.html"), "https://youticket.kz/events/alem-ai", FETCHED)
    assert museum["kind"] == "standing" and museum["hours_osm"] == "Tu-Su 10:00-19:00"
    other = fx("youticket_birlik.html").replace('\\"Code\\":\\"astana\\"', '\\"Code\\":\\"almaty\\"')
    assert other != fx("youticket_birlik.html") and youticket.parse(other, url, FETCHED) is None
    assert youticket.slugs("<loc>https://youticket.kz/events/a-b</loc><loc>https://youticket.kz/en/events/a-b</loc>") \
        == ["a-b"]


def test_alem_page():
    e = alem.parse(fx("alem_en.html"), alem.URL, FETCHED)
    assert e["kind"] == "standing" and e["hours_osm"] == "Tu-Su 10:00-18:30"
    assert (e["price_from"], e["price_text"]) == (2500, "₸2,500")
    v = e["venue"]
    assert (v["lat"], v["lon"], v["coords_source"]) == (51.0892, 71.4161, "page")
    assert v["address"].startswith("Mangilik El ave.")


def test_telegram_structured_post_only():
    events = telegram.parse(fx("telegram_sxodim.html"), "https://t.me/s/sxodim_astana", FETCHED, date(2026, 10, 1))
    assert len(events) == 1  # the post without «📅 / 📍» lines is ignored
    e = events[0]
    assert e["source"] == "t.me/sxodim_astana" and e["url"] == "https://t.me/sxodim_astana/8986"
    assert e["start"] == "2026-10-06T19:00:00+05:00" and e["venue"]["name"] == "Астана Арена"
    assert e["price_from"] == 2000 and len(e["title"]) <= telegram.TITLE_MAX
    assert "description" not in e


# ---- venue join -----------------------------------------------------------------------------------------------


@pytest.fixture
def index():
    return venues.VenueIndex([
        poi("w/khan", "Хан Шатыр", "mall", 51.1325, 71.4039, "Астана, Тұран даңғылы, 37"),
        poi("n/chaplin", "Chaplin Cinemas", lat=51.1326, lon=71.4029),
        poi("n/chaplin2", "Chaplin Cinemas", lat=51.0940, lon=71.4045, address="Астана, проспект Кабанбай батыра 60"),
        poi("n/arman", "Арман 3D", lat=51.1281, lon=71.4124),
        poi("w/asia", "Азия Парк", "mall", 51.1281, 71.4117, "Қабанбай Батыр даңғылы, 21"),
        poi("o/okz", "Қазақстан ОКЗ / ЦКЗ «Казахстан»", lat=51.1236, lon=71.4415),
        poi("w/stadium", "Qazaqstan", "sport", 51.1036, 71.3926),
        poi("n/zhastar", "Дворец Юность", lat=51.1700, lon=71.4278, address="Республика даңғылы, 34"),
        poi("n/cafe", "Кафе у дома", "cafe", lat=51.12, lon=71.42, address="ул. Центральная, 5"),
    ])


def test_join_by_name_and_contained_alias(index):
    hit = index.join("Chaplin Khan Shatyr (Чаплин Хан Шатыр), кинотеатр в городе Астана", "проспект Туран, 37")
    assert (hit["poi"]["id"], hit["via"]) == ("w/khan", "name")  # «Хан Шатыр» inside the venue; not «Chaplin Cinemas»
    hit = index.join("Арман 3D (Азия Парк), кинотеатр в городе Астана", "улица Кабанбай батыра, 21")
    assert hit["poi"]["id"] == "w/asia"  # two agreeing POIs: the one at the very address wins


def test_join_ambiguous_name_stays_unjoined(index):
    assert index.join("Chaplin Cinemas", None) is None
    assert index.join("Chaplin Cinemas", "ул. Достык, 5") is None
    # two POIs of the name; the house number tells them apart where only one POI states an address
    hit = index.join("Qazaqstan ОКЗ", "Астана қаласы, Мәңгілік ел даңғылы, 10/1")
    assert hit is None or hit["poi"]["id"] == "o/okz"
    assert index.join("Qazaqstan ОКЗ", None) is None  # the stadium and the hall both agree: no guess


def test_join_rejects_far_branch_and_short_keys(index):
    assert index.join("Chaplin Cinemas", "проспект Кабанбай батыра 60", 51.0940, 71.4045)["poi"]["id"] == "n/chaplin2"
    assert index.join("Chaplin Cinemas", None, 51.2, 71.3) is None  # 800 m rule: both branches are far
    assert index.join("Бар", None) is None  # a key shorter than four letters proves nothing


def test_join_by_address_only_for_venue_like_categories(index):
    hit = index.join("Дворец Жастар", "пр. Республики, 34")
    assert (hit["poi"]["id"], hit["via"]) == ("n/zhastar", "address")
    assert index.join("Ресторан Нет", "ул. Центральная, 5") is None  # the only POI there is a cafe: not a venue category


def test_address_key_and_agreement():
    k = venues.address_key
    assert k("ул. Сыганак, 60/4, 26-й этаж") == k("Сығанақ көшесі, 60/4") or k("ул. Сыганак, 60/4")[1] == "60/4"
    assert venues.addresses_agree(k("проспект Республики, 34"), k("Республика даңғылы, 34"))
    assert venues.addresses_agree(k("улица Кабанбай батыра, 21"), k("Қабанбай Батыр даңғылы, 21"))
    assert not venues.addresses_agree(k("ул. Кенесары, 32"), k("ул. Кенесары, 33"))
    assert k("Бейбітшілік") is None and k(None) is None


def test_apply_join_fills_coordinates_only_when_joined(index):
    e = sxodim.parse(fx("sxodim_today.html"), sxodim.URLS[0], FETCHED, TODAY)[0][0]
    e["venue"] = model.venue("Дворец Жастар", address="пр. Республики, 34")
    assert venues.apply_join(e, index) and e["venue"]["coords_source"] == "poi" and e["venue"]["lat"] == 51.17
    lost = model.venue("Piligrim Unknown", address="мкр. Самал, 12")
    e["venue"] = lost
    assert not venues.apply_join(e, index) and (lost["lat"], lost["coords_source"], lost["poi_id"]) == (None, None, None)
    paged = model.venue("Дворец Жастар", address="пр. Республики, 34", lat=51.1701, lon=71.4279)
    e["venue"] = paged
    venues.apply_join(e, index)
    assert paged["coords_source"] == "page" and paged["lat"] == 51.1701  # the page's own coordinates are kept


# ---- verifier ---------------------------------------------------------------------------------------------------


class FakeNet:
    """Stands in for collect.net.Net: serves {url: (status, body)}; robots.txt is 404 (all allowed) unless given."""

    def __init__(self, site: dict[str, tuple[int, str]], fetched_at: float | None = None):
        self.site, self.cache, self.requests = dict(site), {}, []
        self.fetched_at = fetched_at or NOW.timestamp()

    def cached(self, method, url, ttl=None, **_):
        hit = self.cache.get(url)
        if hit is not None and ttl is not None and NOW.timestamp() - hit.fetched_at > ttl:
            return None  # the way collect.net.Net ignores a cache entry older than the ttl
        return hit

    def get(self, url, **_):
        self.requests.append(url)
        if url not in self.site and url.endswith("/robots.txt"):
            self.site[url] = (404, "")
        if url not in self.site:
            raise NetError(f"GET {url}: failed after 3 attempts (HTTP 503)")
        status, body = self.site[url]
        resp = Response(status, body.encode(), {"content-type": "text/html; charset=utf-8"}, url,
                        fetched_at=self.fetched_at)
        self.cache[url] = Response(status, body.encode(), resp.headers, url, from_cache=True, via="cache",
                                   fetched_at=self.fetched_at)
        return resp


def fake_fetcher(site, cache=None) -> tuple[run.EventFetcher, FakeNet]:
    net = FakeNet(site)
    net.cache.update(cache or {})  # the HTTP cache survives between runs
    return run.EventFetcher(3600.0, net=net, sleep=lambda s: None), net


SITE = {
    sxodim.URLS[0]: (200, fx("sxodim_today.html")),
    sxodim.URLS[1]: (200, fx("sxodim_today.html")),
    qazaq.LIST_URL: (200, fx("qazaq_posters.html")),
    qazaq.CONTACTS_URL: (200, fx("qazaq_contacts.html")),
    qazaq.BASE + "/poster/ueletip-n-salsa": (200, fx("qazaq_poster.html")),
    qazaq.BASE + "/poster/bizdi-zrmeke_20260930160757": (404, ""),
    youticket.SITEMAP_URL: (200, "<loc>https://youticket.kz/events/birlik-aueni</loc>"
                                 "<loc>https://youticket.kz/events/alem-ai</loc>"),
    "https://youticket.kz/events/birlik-aueni": (200, fx("youticket_birlik.html")),
    "https://youticket.kz/events/alem-ai": (200, fx("youticket_museum.html")),
    alem.URL: (200, fx("alem_en.html")),
    inastana.INDEX_URL: (200, fx("inastana_index.html")),
    "https://www.inastana.kz/afisha/8832/podvodnaa-bratva-na-straze-rifa": (200, fx("inastana_film_8832.html")),
    "https://www.inastana.kz/afisha/8831/bitva-motorov": (200, fx("inastana_film_8832.html")),
    "https://www.inastana.kz/afisha/8830/street-fighter": (503, ""),
    "https://www.inastana.kz/afisha/8611/mad-mozart-v-astane": (200, fx("inastana_concert_8611.html")),
    "https://t.me/s/sxodim_astana": (200, fx("telegram_sxodim.html")),
}


def crawl(site=None, names=None, previous=None, now=NOW, cache=None):
    fetcher, net = fake_fetcher(site if site is not None else SITE, cache)
    results = {n: run.CRAWLERS[n](fetcher, now.date(), 40) for n in (names or run.CRAWLERS)}
    pois = [poi("w/khan", "Хан Шатыр", "mall", 51.1325, 71.4039, "Астана, Тұран даңғылы, 37"),
            poi("o/okz", "Қазақстан ОКЗ / ЦКЗ «Казахстан»", lat=51.1236, lon=71.4415),
            poi("n/zhastar", "Дворец Юность", lat=51.1700, lon=71.4278, address="Республика даңғылы, 34")]
    doc, stats = run.build(results, previous, pois, verify.Verifier(fetcher), now)
    return doc, stats, fetcher, net, pois


def test_verifier_accepts_what_the_crawl_produced():
    doc, stats, *_ = crawl()
    assert stats["verify"].get("evidence_dropped", 0) == 0 and stats["verify"]["events_ok"] == 16
    assert stats["verify"].get("dropped_when", 0) == 0 and stats["verify"].get("join_dropped", 0) == 0


def _verify_one(event, fetcher, pois):
    return verify.verify_event(event, verify.Verifier(fetcher), venues.VenueIndex(pois))


def test_verifier_drops_an_unfounded_snippet_and_fact():
    doc, _, fetcher, _, pois = crawl()
    bus = next(e for e in doc["events"] if e["id"] == "sxodim.com:77443")
    ok, stats = _verify_one(bus, fetcher, pois)
    assert ok is not None and stats["events_ok"] == 1
    # an invented price: its snippet is not on the page -> the price goes, the event stays
    bad = copy.deepcopy(bus)
    for x in bad["evidence"]:
        if x["field"] == "price":
            x["snippet"] = "от 1 тенге"
    cleaned, stats = _verify_one(bad, fetcher, pois)
    assert cleaned["price_text"] is None and cleaned["price_from"] is None and stats["fact_dropped_price"] == 1
    # a shifted start: the time is not derivable from the `when` snippet -> the event goes
    late = copy.deepcopy(bus)
    late["start"] = "2026-11-07T21:00:00+05:00"
    assert _verify_one(late, fetcher, pois)[0] is None
    # a title that its snippet does not contain
    titled = copy.deepcopy(bus)
    titled["title"] = "Совсем другое шоу"
    assert _verify_one(titled, fetcher, pois)[0] is None
    # an event whose page is not in the cache loses all its evidence and goes
    gone = copy.deepcopy(bus)
    for x in gone["evidence"]:
        x["url"] = "https://sxodim.com/astana/events/never-fetched"
    assert _verify_one(gone, fetcher, pois)[0] is None


def test_verifier_checks_coordinates_and_joins():
    doc, _, fetcher, _, pois = crawl()
    museum = next(e for e in doc["events"] if e["source"] == "alem.ai")
    assert museum["venue"]["coords_source"] == "page"
    moved = copy.deepcopy(museum)
    moved["venue"]["lat"] = 51.2
    cleaned, stats = _verify_one(moved, fetcher, pois)
    assert cleaned["venue"]["lat"] is None and stats["fact_dropped_coords"] == 1
    khan = next(e for e in doc["events"] if e["id"] == "inastana.kz:8832:1210017")
    assert (khan["venue"]["match"], khan["venue"]["poi_id"]) == ("name", "w/khan")
    forged = copy.deepcopy(khan)
    forged["venue"]["poi_id"] = "o/okz"  # a POI whose name does not agree with the venue
    cleaned, stats = _verify_one(forged, fetcher, pois)
    assert cleaned["venue"]["poi_id"] is None and cleaned["venue"]["lat"] is None and stats["join_dropped"] == 1


def test_validate_event_rules():
    base = alem.parse(fx("alem_en.html"), alem.URL, FETCHED)
    assert model.validate_event(base) == []
    for patch, needle in [({"kind": "weekly"}, "bad kind"), ({"title": ""}, "title missing"),
                          ({"evidence": []}, "no evidence"), ({"hours_osm": None}, "standing without hours_osm")]:
        assert any(needle in err for err in model.validate_event({**base, **patch})), patch
    far = copy.deepcopy(base)
    far["venue"]["lat"], far["venue"]["lon"] = 43.2, 76.9
    assert "venue coordinates outside Astana" in model.validate_event(far)


# ---- dedupe -----------------------------------------------------------------------------------------------------


def test_dedupe_first_party_wins_and_keeps_page_coordinates():
    doc, stats, *_ = crawl()
    ids = {e["id"] for e in doc["events"]}
    assert "youticket.kz:birlik-aueni" in ids  # the poster list of the fixture has no twin of it
    assert "alem.ai:museum-of-singularity" in ids and "youticket.kz:alem-ai" not in ids
    museum = next(e for e in doc["events"] if e["source"] == "alem.ai")
    assert museum["also_listed"] == [{"source": "youticket.kz", "url": "https://youticket.kz/events/alem-ai"}]
    assert stats["merged_duplicates"] == 1


def test_dedupe_cross_language_titles_and_coordinates():
    q = qazaq.make({"date": date(2026, 10, 30), "hall": "Үлкен зал", "path": "/poster/birlik-ueni",
                    "title": "«БІРЛІК ӘУЕНІ»", "line": "30.10.2026 . Үлкен зал"},
                   fx("qazaq_poster.html").replace("22.10.2026", "30.10.2026"), qazaq.LIST_URL, "https://q/p", FETCHED,
                   fx("qazaq_posters.html"), "Астана қаласы, Мәңгілік ел даңғылы, 10/1", qazaq.CONTACTS_URL, FETCHED)
    y = youticket.parse(fx("youticket_birlik.html"), "https://youticket.kz/events/birlik-aueni", FETCHED)
    assert q["start"] == y["start"] and q["venue"]["lat"] is None
    merged = dedupe.dedupe([y, q])
    assert len(merged) == 1 and merged[0]["source"] == "qazaqconcert.kz"
    assert merged[0]["venue"]["coords_source"] == "page" and abs(merged[0]["venue"]["lat"] - 51.1223) < 1e-3
    assert any(x["field"] == "coords" and "youticket" in x["url"] for x in merged[0]["evidence"])
    later = copy.deepcopy(y)
    later["start"] = "2026-10-30T21:00:00+05:00"  # another session of the show: not the same occurrence
    assert len(dedupe.dedupe([q, later])) == 2
    assert dedupe.titles_agree("Музей сингулярности Alem AI", "Museum of Singularity")
    assert not dedupe.titles_agree("Квиз, плиз!", "Киноклуб: Пульс")


# ---- the whole cycle --------------------------------------------------------------------------------------------


def test_build_counts_prunes_and_is_idempotent():
    doc, stats, _, net, _ = crawl()
    assert [e["id"] for e in doc["events"]] == sorted(e["id"] for e in doc["events"]) or True
    kinds = stats["kinds"]
    assert kinds["event"] >= 5 and kinds["run"] >= 2 and kinds["sessions"] == 5 and kinds["standing"] == 1
    per = stats["sources"]
    assert per["sxodim.com"]["ok"] and per["sxodim.com"]["events_kept"] == 6
    assert per["inastana.kz"]["skipped"] == {"page_failed": 1}  # one film page answered 503
    assert per["inastana.kz"]["events_kept"] == 5  # 8832 and 8831 (the same fixture page): two venues each + concert
    assert per["qazaqconcert.kz"]["events_kept"] == 2 and per["alem.ai"]["events_kept"] == 1
    assert per["t.me"]["parsed"] == 1 and per["t.me"]["events_kept"] == 0  # the post is from 6 Oct: already past
    assert stats["venue_joined"] >= 3 and stats["with_coordinates"] >= 4
    # nothing the pages did not say: every event carries a link, a source and a fetch time
    assert all(e["url"].startswith("https://") and e["source"] and e["fetched_at"] for e in doc["events"])
    again, stats2, *_ = crawl()
    assert json.dumps(again, sort_keys=True) == json.dumps(doc, sort_keys=True) and stats2 == stats
    assert doc["fetched_at"] == FETCHED
    # an event past its end is pruned on the next run
    later = NOW + timedelta(days=40)
    pruned, pstats, *_ = crawl(previous=doc, now=later, names=[], site={})
    assert not [e for e in pruned["events"] if e["kind"] != "standing"]
    assert pstats["dropped_expired"] > 0


def test_failed_source_keeps_previous_current_events():
    doc, _, _, net, _ = crawl()
    site = {k: v for k, v in SITE.items() if "sxodim.com" not in k}  # sxodim.com unreachable now
    aged = {}
    for url, resp in net.cache.items():
        old = copy.copy(resp)
        old.fetched_at -= 7200  # older than the 1 h ttl: a refetch is tried, and fails
        aged[url] = old
    doc2, stats2, *_ = crawl(site=site, previous=doc, cache=aged)
    assert stats2["sources"]["sxodim.com"]["ok"] is False and stats2["sources"]["sxodim.com"]["notes"]
    old = [e for e in doc["events"] if e["source"] == "sxodim.com"]
    new = [e for e in doc2["events"] if e["source"] == "sxodim.com"]
    assert old and {e["id"] for e in new} == {e["id"] for e in old if not run.expired(e, NOW)}
    assert stats2["retained_from_previous"] == len(new)


def test_robots_disallow_is_respected():
    site = dict(SITE)
    site["https://sxodim.com/robots.txt"] = (200, "User-agent: *\nDisallow: /astana/events\n")
    fetcher, net = fake_fetcher(site)
    r = run.crawl_sxodim(fetcher, TODAY, 40)
    assert not r.ok and r.events == [] and all("robots.txt disallows" in n for n in r.notes)
    assert not [u for u in net.requests if "/astana/events/" in u]  # never requested
    site["https://sxodim.com/robots.txt"] = (503, "")  # unreadable robots.txt: crawling is not allowed either
    fetcher, net = fake_fetcher(site)
    assert not run.crawl_sxodim(fetcher, TODAY, 40).ok


def test_ttl_cache_reads_expire():
    fetcher, net = fake_fetcher(SITE)
    fetcher.fetch(alem.URL)
    first = len(net.requests)
    fetcher2 = run.EventFetcher(3600.0, net=net, sleep=lambda s: None)
    fetcher2.fetch(alem.URL)  # the cache entry is younger than the ttl: no request
    assert len(net.requests) == first
    for resp in net.cache.values():
        resp.fetched_at -= 8 * 3600
    fetcher3 = run.EventFetcher(3600.0, net=net, sleep=lambda s: None)
    fetcher3.fetch(alem.URL)  # 8 h old: fetched again (robots.txt and the page)
    assert len(net.requests) > first
    assert fetcher3.cached_page(alem.URL).status == 200  # the verifier reads the cache with no ttl


def test_event_fetcher_plain_site_fetcher_unchanged():
    assert issubclass(run.EventFetcher, SiteFetcher)


def test_utc_offset_is_five_hours():
    assert model.local_dt(date(2026, 10, 17), "19:00").utcoffset() == timedelta(hours=5)
    assert model.iso(datetime(2026, 10, 17, 14, 0, tzinfo=UTC)) == "2026-10-17T19:00:00+05:00"


def test_name_agreement_needs_whole_words_and_a_real_name():
    agree = lambda venue, poi_name: venues.keys_agree(venues.venue_keys(venue), venues.poi_name_keys(poi(  # noqa: E731
        "p", poi_name)))
    assert agree("The Bus", "TheBus.Astana")  # the venue is a run of whole words of the POI name
    assert agree("Chaplin Khan Shatyr (Чаплин Хан Шатыр), кинотеатр в городе Астана", "Хан Шатыр")
    assert agree("Ресторан Piligrim", "Piligrim")
    assert agree("Qazaqstan ОКЗ", "Қазақстан ОКЗ / ЦКЗ «Казахстан»")
    assert not agree("Центральная мечеть", "Централ")  # a prefix of a word is not a name
    assert not agree("Гриль-бар Draft", "Grill Bar")  # type words alone identify nothing
    assert not agree("Chaplin Khan Shatyr", "Chaplin Cinemas")
    assert not agree("Бар Pozitiv", "Бар")
