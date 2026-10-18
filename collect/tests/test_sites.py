"""Unit tests of the official-site facts framework (collect/sites): no network, no real cache.

Run from the repository root:  uv run python -m pytest collect/tests/test_sites.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.net import NetError, Response  # noqa: E402
from collect.sites import hours, join, partition, store, verify  # noqa: E402
from collect.sites.domains import poi_domains, registrable_domain  # noqa: E402
from collect.sites.fetch import SiteFetcher, decode_body, relevant_links, visible_text  # noqa: E402
from collect.sites.inventory import build_inventory  # noqa: E402
from collect.sites.jsonld import extract_jsonld_branches  # noqa: E402


class FakeNet:
    """Stands in for collect.net.Net: serves `site` {url: (status, body, content_type)}, remembers what it fetched."""

    def __init__(self, site: dict[str, tuple[int, str | bytes, str]]):
        self.site, self.cache, self.requests = site, {}, []

    def cached(self, method, url, **_):
        return self.cache.get(url)

    def get(self, url, **_):
        self.requests.append(url)
        if url not in self.site:
            raise NetError(f"GET {url}: failed after 3 attempts (HTTP 503)")
        status, body, ctype = self.site[url]
        body = body.encode() if isinstance(body, str) else body
        resp = Response(status, body, {"content-type": ctype}, url, fetched_at=1_790_000_000.0)
        self.cache[url] = Response(status, body, {"content-type": ctype}, url, from_cache=True, via="cache",
                                   fetched_at=1_790_000_000.0)
        return resp


def fetcher(site, **kw) -> tuple[SiteFetcher, FakeNet]:
    """A fetcher over `site`; every origin mentioned gets a 404 robots.txt (= all allowed) unless it has one."""
    site = dict(site)
    for url in list(site):
        parts = url.split("/", 3)
        site.setdefault(f"{parts[0]}//{parts[2]}/robots.txt", (404, "", "text/plain"))
    net = FakeNet(site)
    return SiteFetcher(net, sleep=lambda s: None, **kw), net


# ---- domains / inventory ---------------------------------------------------------------------------


def test_registrable_domain_and_blocked():
    assert registrable_domain("https://www.starbucks.com.kz/?utm=1") == "starbucks.com.kz"
    assert registrable_domain("astana.harats.com/pubs") == "harats.com"
    assert registrable_domain("http://KFC.kz") == "kfc.kz"
    assert registrable_domain("not a url") is None
    p = {"website": "https://www.instagram.com/x; https://www.Foo.kz/a;https://taplink.cc/y"}
    assert poi_domains(p) == ["foo.kz"]
    assert poi_domains({"website": "https://wa.me/7701"}) == []
    assert poi_domains({"website": None}) == []


def _poi(i, name, cat, website=None, lat=51.1, lon=71.4, **kw):
    return {"id": i, "name": name, "names": {"name": name}, "category": cat, "website": website, "lat": lat,
            "lon": lon, "address": None, "opening_hours": None, "phone": None, "description": None, **kw}


def test_inventory_groups_sorts_and_lists_manual_targets():
    pois = [
        _poi("a", "KFC", "fast_food", "https://www.kfc.kz/stores"), _poi("b", "KFC Mega", "fast_food", "kfc.kz"),
        _poi("c", "Hall", "mall", "https://hall.kz"), _poi("d", "Museum", "museum_gallery", "https://instagram.com/m"),
        _poi("e", "Cafe", "cafe"), _poi("f", "Theatre", "culture_theatre_cinema"),
    ]
    inv = build_inventory(pois)
    assert [d["domain"] for d in inv["domains"]] == ["kfc.kz", "hall.kz"]
    assert inv["domains"][0]["poi_count"] == 2 and inv["domains"][0]["categories"] == {"fast_food": 2}
    assert {t["poi_id"] for t in inv["manual_targets"]} == {"d", "f"}  # cafe without a site is not a manual target
    assert next(t for t in inv["manual_targets"] if t["poi_id"] == "d")["social_only_website"]


def test_partitions_are_balanced_and_spread_chains():
    inv = {"domains": [{"domain": f"d{i}.kz", "poi_count": c, "categories": {}, "sample_names": [], "urls": [],
                        "brands": [], "poi_ids": []} for i, c in enumerate([24, 21, 16, 13, 13, 10, 9, 9, 7, 6, 6, 5]
                                                                         + [1] * 60)],
           "manual_targets": [{"poi_id": str(i), "name": "m"} for i in range(30)]}
    bins = partition.build_partitions(inv)
    assert [b["partition"] for b in bins] == ["p1", "p2", "p3", "p4", "p5", "p6"]
    weights = [b["weight"] for b in bins]
    assert max(weights) - min(weights) <= 25
    assert all(i["kind"] == "manual" for i in bins[5]["items"][:30])
    top = [next(b["partition"] for b in bins for i in b["items"] if i.get("domain") == f"d{k}.kz") for k in range(5)]
    assert len(set(top)) >= 4  # the biggest chains do not pile up in one list
    assert sum(b["domain_count"] for b in bins) == 72 and sum(b["manual_count"] for b in bins) == 30


# ---- hours converter -------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "osm"), [
    ("ежедневно 10:00–22:00", "Mo-Su 10:00-22:00"),
    ("Ежедневно с 10:00 до 22:00.", "Mo-Su 10:00-22:00"),
    ("Пн-Пт 9-18, сб 10-16", "Mo-Fr 09:00-18:00; Sa 10:00-16:00"),
    ("Пн–Сб 10:00–20:00, Вс — выходной", "Mo-Sa 10:00-20:00; Su off"),
    ("с пн по пт 10-19", "Mo-Fr 10:00-19:00"),
    ("будни 9-18, выходные 10-16", "Mo-Fr 09:00-18:00; Sa,Su 10:00-16:00"),
    ("круглосуточно", "24/7"),
    ("Круглосуточно, без выходных", "24/7"),
    ("Открыто 24 часа", "24/7"),
    ("дүйсенбі-жұма 09:00-18:00", "Mo-Fr 09:00-18:00"),
    ("Дс-Жм 9:00-18:00, Сб 10:00-14:00, Жс демалыс", "Mo-Fr 09:00-18:00; Sa 10:00-14:00; Su off"),
    ("Mon-Sun 10am-10pm", "Mo-Su 10:00-22:00"),
    ("Mon-Fri 9:00-18:00, Sat 10-16, Sun closed", "Mo-Fr 09:00-18:00; Sa 10:00-16:00; Su off"),
    ("Daily 10:00 - 23:00", "Mo-Su 10:00-23:00"),
    ("Mo-Fr 09:00-18:00; Sa 10:00-16:00", "Mo-Fr 09:00-18:00; Sa 10:00-16:00"),
    ("пн-чт, вс 16:00-02:00, пт-сб 16:00-04:00", "Mo-Th,Su 16:00-02:00; Fr,Sa 16:00-04:00"),  # after midnight
    ("10:00 - 22:00 ежедневно", "Mo-Su 10:00-22:00"),
    ("Пн-Вс 10:00-00:00", "Mo-Su 10:00-24:00"),
    ("пн-пт 9-13, 14-18", "Mo-Fr 09:00-13:00,14:00-18:00"),
    ("сб-чт 10-22", "Mo-Th,Sa,Su 10:00-22:00"),
    ("Пн-Вс 00:00-23:59", "24/7"),
    ("КҮНДЕЛІКТІ: 10:00 — 22:00; Жм, Сб: 10:00 — 23:00", "Mo-Su 10:00-22:00; Fr,Sa 10:00-23:00"),
    ("Пн-Вс 10-22, пт 10-23", "Mo-Su 10:00-22:00; Fr 10:00-23:00"),  # exception on a subset of the days
    ("ежедневно c 10:00 до 23:00", "Mo-Su 10:00-23:00"),  # Latin "c" typed instead of Cyrillic "с"
    ("10:00 - 18:00 Вт-Вс", "Tu-Su 10:00-18:00"),
    ("10:00 - 18:00 Сс-Жк", "Tu-Su 10:00-18:00"),  # kk abbreviations Сейсенбі-Жексенбі
    ("ПН-ВС, с 6:00 до 23:00", "Mo-Su 06:00-23:00"),  # comma between the days and the times
    ("ПН-ВС 09:00 - 00:00", "Mo-Su 09:00-24:00"),
    ("понедельник 10:00-22:00 вторник 10:00-22:00 среда 10:00-22:00", "Mo-We 10:00-22:00"),
    # Italian / Polish (Wikivoyage it/pl listings)
    ("Lun-Dom 10:00-18:00", "Mo-Su 10:00-18:00"),
    ("Mar-Sab 7:30-20:00", "Tu-Sa 07:30-20:00"),
    ("Dom-Gio 10:00-21:00, Ven-Sab 9:00-21:00", "Mo-Th,Su 10:00-21:00; Fr,Sa 09:00-21:00"),
    ("Lun-Dom 00-24", "24/7"),
    ("Venerdì 23:00-05:00, sabato 23:00-05:00", "Fr,Sa 23:00-05:00"),
    ("Wt-Nd 10:00-20:00", "Tu-Su 10:00-20:00"),
    ("pon.–pt. 10:00-18:00", "Mo-Fr 10:00-18:00"),
    ("środa 10:00-18:00", "We 10:00-18:00"),
    ("Codziennie 09:00-21:00", "Mo-Su 09:00-21:00"),
])
def test_to_osm_known_patterns(text, osm):
    assert hours.to_osm(text) == osm
    assert hours.validate_osm(osm) is True


@pytest.mark.parametrize("text", [
    "", "   ", "до 22:00", "с 10:00", "10-22 перерыв 14-15", "летом 10-22, зимой 10-20", "по записи",
    "Mon-Sun 9-5pm", "8 800 100 22 22", "Пн-Пт 9-18, Пн-Пт 14-20", "10:00-10:00", "25:00-26:00", "10:70-12:00",
    "Пн-Пт", "по договоренности", "Mon 9am-5pm Sat 10-16 PH off", "ежедневно с 10 до 22 кроме понедельника",
    "График работы ТРЦ: c 10:00 до 23:00",  # "ТРЦ" is an unknown word: callers pass only the hours part
    "Магазины: 1,2,3 этажи 10:00 - 22:00", "Время работы кассы Пн - Пт: 10:00 — 19:00",  # other things than the venue
])
def test_to_osm_refuses_what_it_does_not_understand(text):
    assert hours.to_osm(text) is None


def test_validate_osm_uses_the_app_parser():
    assert hours.validate_osm("Mo-Fr 09:00-18:00")
    assert not hours.validate_osm("Mo-Fr 9 till 18 sometimes")
    assert not hours.validate_osm("")


@pytest.mark.parametrize("text", [
    "с 18:00 до 06:00", "10:00–22:00", "c 10:00 до 23:00", "График работы: c 10:00 до 23:00",
    "с 9 до 21 часов", "00:00-23:59", "10:00-13:00, 14:00-18:00", "9-18; 14-20",
])
def test_hours_without_days_are_not_converted_and_flagged(text):
    assert hours.to_osm(text) is None
    assert hours.hours_flags(text) == ["needs_days"]


@pytest.mark.parametrize(("text", "osm"), [
    ("ежедневно c 10:00 до 23:00", "Mo-Su 10:00-23:00"),
    ("Пн-Вс 00:00-23:59", "24/7"),
    ("Пн-Вс 00:00-24:00", "24/7"),
    ("круглосуточно", "24/7"),  # a complete statement without weekdays
])
def test_days_or_round_the_clock_make_hours_convertible(text, osm):
    assert hours.to_osm(text) == osm and hours.hours_flags(text) == []


@pytest.mark.parametrize("text", [
    "00:00-00:00", "Mon-Sun 00:00-00:00", "ежедневно 00:00 - 00:00", "Пн-Пт 9-18; Сб 00:00-00:00",
    "среда 00:00-00:00",
])
def test_sentinel_range_is_ambiguous_without_round_the_clock_wording(text):
    assert hours.to_osm(text) is None
    assert "ambiguous_24h" in hours.hours_flags(text)


def test_sentinel_range_is_accepted_when_the_same_text_says_round_the_clock():
    assert hours.to_osm("Круглосуточно (00:00-00:00)") == "24/7"
    assert hours.to_osm("Mon-Fri 9-18, Sat круглосуточно, Sun 00:00-00:00") == "Mo-Fr 09:00-18:00; Sa,Su 00:00-24:00"
    assert hours.hours_flags("Круглосуточно 00:00-00:00") == []
    both = hours.hours_flags("00:00-00:00")
    assert both == ["ambiguous_24h", "needs_days"]
    assert hours.spec_to_text([{"dayOfWeek": "Monday", "opens": "00:00", "closes": "00:00"}]) is None


def test_unintelligible_text_has_no_flags():
    assert hours.hours_flags("по записи") == [] and hours.hours_flags("") == [] and hours.hours_flags(None) == []
    assert hours.hours_flags("Пн-Пт 9-18") == []


def test_spec_to_text_groups_days_and_refuses_windows():
    spec = [
        {"@type": "OpeningHoursSpecification", "dayOfWeek": ["https://schema.org/Monday", "Tuesday", "Wednesday"],
         "opens": "09:00:00", "closes": "18:00:00"},
        {"dayOfWeek": "Saturday", "opens": "10:00", "closes": "16:00"},
    ]
    assert hours.spec_to_text(spec) == "Mo-We 09:00-18:00; Sa 10:00-16:00"
    assert hours.spec_to_text([{**spec[1], "validFrom": "2026-12-31"}]) is None
    assert hours.spec_to_text([{"dayOfWeek": "Funday", "opens": "09:00", "closes": "10:00"}]) is None
    assert hours.spec_to_text([{"dayOfWeek": "Sunday", "opens": "00:00", "closes": "23:59"}]) == "Su 00:00-24:00"


# ---- JSON-LD ---------------------------------------------------------------------------------------

KFC_HTML = """<html><head><title>KFC</title>
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
 {"@type": "Restaurant", "name": "KFC Мега Астана", "telephone": "+7 7172 11-22-33",
  "address": {"@type": "PostalAddress", "streetAddress": "ул. Кабанбай батыра, 62", "addressLocality": "Астана"},
  "geo": {"@type": "GeoCoordinates", "latitude": "51.0887", "longitude": 71.4093},
  "openingHoursSpecification": [{"@type": "OpeningHoursSpecification",
     "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
     "opens": "10:00", "closes": "23:00"}],
  "description": "Ресторан быстрого питания"},
 {"@type": "Restaurant", "name": "KFC Хан Шатыр", "openingHours": ["Mo-Su 10:00-22:00"],
  "geo": {"latitude": 51.1327, "longitude": 71.4033}},
 {"@type": "WebSite", "name": "KFC.kz"}
]}
</script></head><body><p>stores</p></body></html>"""


def test_jsonld_branches_carry_verbatim_snippets():
    bs = extract_jsonld_branches(KFC_HTML, "https://kfc.kz/stores")
    assert [b["name"] for b in bs] == ["KFC Мега Астана", "KFC Хан Шатыр"]
    mega, shatyr = bs
    assert mega["opening_hours_osm"] == "Mo-Su 10:00-23:00" and mega["lat"] == 51.0887
    assert mega["address"] == "ул. Кабанбай батыра, 62, Астана" and mega["phone"] == "+7 7172 11-22-33"
    assert shatyr["opening_hours_raw"] == "Mo-Su 10:00-22:00" and shatyr["address"] is None
    page = store.norm_ws(KFC_HTML)
    for b in bs:
        assert {e["field"] for e in b["evidence"]} >= {"name", "geo", "opening_hours"}
        for e in b["evidence"]:
            assert e["snippet"] in page and len(e["snippet"]) <= 300
    # the second object's evidence is its own, not the first object's (same key names)
    assert next(e for e in shatyr["evidence"] if e["field"] == "geo")["snippet"].endswith("71.4033}")
    assert store.validate_branch({**mega, "method": "jsonld"}) == []


def test_jsonld_ignores_broken_blocks_and_junk():
    html = '<script type="application/ld+json">{"name": </script><script type="application/ld+json">[]</script>'
    assert extract_jsonld_branches(html, "https://x.kz/") == []


# ---- fetcher ---------------------------------------------------------------------------------------


def test_fetch_respects_robots_and_caches():
    robots = "User-agent: *\nDisallow: /private\nSitemap: https://kfc.kz/sm.xml\n"
    f, net = fetcher({"https://kfc.kz/robots.txt": (200, robots, "text/plain"),
                      "https://kfc.kz/stores": (200, KFC_HTML, "text/html; charset=utf-8")})
    assert f.allowed("https://kfc.kz/stores") and not f.allowed("https://kfc.kz/private/x")
    blocked = f.fetch("https://kfc.kz/private/x")
    assert blocked.robots_blocked and blocked.status == 0
    assert "https://kfc.kz/private/x" not in net.requests  # never even requested
    page = f.fetch("https://kfc.kz/stores")
    assert page.ok and page.fetched_at.startswith("2026-")
    f.fetch("https://kfc.kz/stores")
    assert net.requests.count("https://kfc.kz/stores") == 1
    assert f.robots_status("https://kfc.kz/") == "ok"
    assert f.cached_page("https://kfc.kz/stores").from_cache
    assert f.cached_page("https://kfc.kz/never") is None


def test_robots_missing_allows_but_unreachable_forbids():
    f, _ = fetcher({"https://a.kz/robots.txt": (404, "", "text/html"), "https://a.kz/x": (200, "ok", "text/html")})
    assert f.allowed("https://a.kz/x") and f.robots_status("https://a.kz/") == "absent"
    g, _ = fetcher({})  # robots.txt fetch fails (503 after retries) -> crawling not allowed
    assert not g.allowed("https://b.kz/x") and g.robots_status("https://b.kz/").startswith("unreachable")
    assert g.fetch("https://b.kz/x").robots_blocked


def test_rate_limit_one_request_per_second_per_domain():
    clock = {"t": 100.0}
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        clock["t"] += s

    site = {f"https://a.kz/{i}": (200, "x", "text/html") for i in range(3)}
    site["https://a.kz/robots.txt"] = (404, "", "text/html")
    site["https://b.kz/robots.txt"] = (404, "", "text/html")
    site["https://b.kz/0"] = (200, "x", "text/html")
    f = SiteFetcher(FakeNet(site), sleep=sleep, clock=lambda: clock["t"])
    for i in range(3):
        f.fetch(f"https://a.kz/{i}")
    f.fetch("https://b.kz/0")
    # a.kz: robots.txt is free, each of the 3 pages waits 1 s; b.kz: free robots.txt, its page waits 1 s
    assert slept == [1.0, 1.0, 1.0, 1.0]


def test_discovery_links_and_sitemap():
    home = ('<a href="/stores">Адреса</a><a href="/about">О нас</a><a href="https://other.com/stores">x</a>'
            '<a href="/img/a.png">png</a><a href="/astana/contacts#top">Астана</a><a href="mailto:a@b.kz">m</a>')
    assert set(relevant_links(home, "https://kfc.kz/")) == {"https://kfc.kz/astana/contacts", "https://kfc.kz/stores"}
    sm = ('<urlset><url><loc>https://kfc.kz/stores/astana-mega</loc></url><url><loc>https://kfc.kz/menu</loc></url>'
          '</urlset>')
    f, _ = fetcher({"https://kfc.kz/robots.txt": (404, "", "text/plain"), "https://kfc.kz/": (200, home, "text/html"),
                    "https://kfc.kz/sitemap.xml": (200, sm, "application/xml")})
    assert f.sitemap_urls("https://kfc.kz/") == ["https://kfc.kz/stores/astana-mega"]
    found = f.discover("https://kfc.kz/")
    assert "https://kfc.kz/stores" in found and "https://kfc.kz/stores/astana-mega" in found


def test_decode_body_charset_and_visible_text():
    body = "<html><meta charset=windows-1251><body><p>Режим</p><script>x=1</script><b>10:00</b>-22:00</body>"
    assert "Режим" in decode_body(body.encode("cp1251"))
    assert visible_text("<div>a</div><script>bad()</script><style>.x{}</style><p>b&amp;c</p>") == "a b&c"


# ---- store / verify --------------------------------------------------------------------------------


def _branch(url="https://kfc.kz/stores", **kw):
    base = {
        "name": "KFC Мега", "evidence": [store.evidence("name", url, "KFC Мега Астана"),
                                          store.evidence("opening_hours", url, "Mo-Su 10:00-22:00")],
        "method": "html", "confidence": 0.8, "opening_hours_raw": "Mo-Su 10:00-22:00",
    }
    return store.make_branch(**{**base, **kw})


def test_make_branch_computes_osm_and_validate_catches_missing_evidence():
    b = _branch()
    assert b["opening_hours_osm"] == "Mo-Su 10:00-22:00" and store.validate_branch(b) == []
    assert _branch(opening_hours_raw="по записи")["opening_hours_osm"] is None
    bad = {**b, "phone": "+7 700 000", "evidence": b["evidence"][:1]}
    assert any("opening_hours_raw has no evidence" in e for e in store.validate_branch({**bad, "phone": None}))
    assert any("phone has no evidence" in e for e in store.validate_branch(bad))
    assert any("not the deterministic" in e for e in store.validate_branch({**b, "opening_hours_osm": "Mo 10:00-11:00"}))
    assert store.validate_branch({**b, "evidence": []}) == ["no evidence"]
    assert any("method" in e for e in store.validate_branch({**b, "method": "guess"}))
    assert any("snippet longer" in e for e in store.validate_branch(
        {**b, "evidence": [{"field": "name", "url": "u", "snippet": "x" * 301}]}))


def test_save_load_roundtrip_and_rejections(tmp_path):
    rec = store.new_record("kfc.kz", robots_ok=True, pages=["https://kfc.kz/stores"], branches=[_branch()])
    path = store.save_facts(rec, tmp_path)
    assert path.name == "kfc.kz.json" and store.load_facts("kfc.kz", tmp_path) == rec
    assert [r["domain"] for r in store.iter_facts(tmp_path)] == ["kfc.kz"]
    with pytest.raises(ValueError, match="no evidence"):
        store.save_facts({**rec, "branches": [{**_branch(), "evidence": []}]}, tmp_path)
    with pytest.raises(ValueError, match="robots_ok is false"):
        store.save_facts({**rec, "robots_ok": False}, tmp_path)
    with pytest.raises(ValueError, match="bad domain"):
        store.facts_path("../x", tmp_path)


def test_verifier_drops_unverifiable_facts_and_recomputes_osm():
    url = "https://kfc.kz/stores"
    f, _ = fetcher({url: (200, "<p>KFC  Мега\n Астана</p><b>Mo-Su 10:00-22:00</b><i>ул. Абая 1</i>", "text/html")})
    f.fetch(url)
    good = _branch(url, address="ул. Абая 1",
                   evidence=[store.evidence("name", url, "KFC Мега Астана"),
                             store.evidence("opening_hours", url, "Mo-Su 10:00-22:00"),
                             store.evidence("address", url, "ул. Абая 1")])
    phantom = _branch(url, phone="+7 700 1", evidence=[store.evidence("name", url, "KFC Мега Астана"),
                                                       store.evidence("phone", url, "+7 700 1"),
                                                       store.evidence("opening_hours", url, "Mo-Su 10:00-22:00")])
    ghost = _branch(url, name="Ghost", evidence=[store.evidence("name", url, "Ghost branch"),
                                                 store.evidence("opening_hours", url, "Mo-Su 09:00-20:00")],
                    opening_hours_raw="Mo-Su 09:00-20:00")
    uncached = _branch("https://kfc.kz/other")
    rec = store.new_record("kfc.kz", robots_ok=True, branches=[good, phantom, ghost, uncached])
    cleaned, stats = verify.verify_record(rec, verify.Verifier(f))
    assert [b["name"] for b in cleaned["branches"]] == ["KFC Мега", "KFC Мега"]
    assert cleaned["branches"][0]["address"] == "ул. Абая 1"
    assert cleaned["branches"][1]["phone"] is None  # its phone snippet is not on the page
    assert stats["evidence_dropped"] >= 5 and stats["fact_dropped_phone"] == 1 and stats["branches_dropped"] == 2
    assert stats["evidence_page_not_cached"] == 2 and "verified_at" in cleaned
    assert rec["branches"][1]["phone"] == "+7 700 1"  # input untouched
    assert verify.verify_record({**rec, "robots_ok": False}, verify.Verifier(f))[0]["branches"] == []


def test_verifier_sees_json_escapes_and_entities():
    url = "https://x.kz/api"
    body = json.dumps({"s": [{"n": "Кафе «Алтын»", "h": "пн-вс 10:00-22:00"}]})  # ensure_ascii => \uXXXX in source
    f, _ = fetcher({url: (200, body, "application/json")})
    f.fetch(url)
    v = verify.Verifier(f)
    assert v.snippet_found(url, "Кафе «Алтын»") and v.snippet_found(url, '"h": "пн-вс 10:00-22:00"')
    assert not v.snippet_found(url, "Кафе «Алтын-2»")


# ---- join ------------------------------------------------------------------------------------------


def test_join_matches_by_coords_name_domain_and_address(tmp_path):
    url = "https://kfc.kz/stores"
    page = ("KFC Мега Астана Mo-Su 10:00-22:00 +7 7172 11-22-33 ул. Кабанбай батыра, 62 "
            "Mall Keruen Mo-Fr 09:00-20:00 KFC Далеко 10-22 Кофейня Ромашка проспект Тауелсиздик 34 Пн-Вс 8-20")
    f, _ = fetcher({url: (200, page, "text/html")})
    f.fetch(url)
    pois = [
        _poi("p1", "KFC", "fast_food", "https://kfc.kz", lat=51.0888, lon=71.4094, opening_hours=None),
        _poi("p2", "KFC", "fast_food", "https://kfc.kz", lat=51.2, lon=71.5, opening_hours="Mo-Su 11:00-23:00"),
        _poi("p3", "Совсем другое", "cafe", None, lat=51.0889, lon=71.4095),
        _poi("p4", "Ромашка", "cafe", "https://kfc.kz/romashka", lat=51.3, lon=71.6, address="улица Тауелсиздик, 34"),
    ]
    mega = store.make_branch(
        "KFC Мега Астана", [store.evidence("name", url, "KFC Мега Астана"),
                            store.evidence("geo", url, "KFC Мега Астана"),
                            store.evidence("opening_hours", url, "Mo-Su 10:00-22:00"),
                            store.evidence("phone", url, "+7 7172 11-22-33")],
        "html", 0.8, lat=51.0887, lon=71.4093, opening_hours_raw="Mo-Su 10:00-22:00", phone="+7 7172 11-22-33")
    far = store.make_branch("KFC Далеко", [store.evidence("name", url, "KFC Далеко"),
                                           store.evidence("opening_hours", url, "KFC Далеко 10-22")],
                            "html", 0.8, lat=51.9, lon=71.9, opening_hours_raw="10-22")
    rom = store.make_branch("Кофейня Ромашка", [store.evidence("name", url, "Кофейня Ромашка"),
                                                store.evidence("address", url, "проспект Тауелсиздик 34"),
                                                store.evidence("opening_hours", url, "Пн-Вс 8-20")],
                            "html", 0.7, address="проспект Тауелсиздик 34", opening_hours_raw="Пн-Вс 8-20")
    rec = store.new_record("kfc.kz", robots_ok=True, branches=[mega, far, rom], fetched_at="2026-10-17T10:00:00+00:00")
    out = join.join(pois, [rec], verify.Verifier(f))
    assert set(out["pois"]) == {"p1", "p4"}
    j1 = out["pois"]["p1"]
    assert j1["method"] == "coords+name" and j1["distance_m"] < 30
    assert j1["fields"]["opening_hours"] == "Mo-Su 10:00-22:00" and set(j1["new_fields"]) >= {"opening_hours", "phone"}
    src = j1["field_sources"]["opening_hours"]
    assert src["source"] == "official_site" and src["url"] == url and src["snapshot_date"] == "2026-10-17"
    assert "own website" in src["license"] and src["snippet"] == "Mo-Su 10:00-22:00"
    assert out["pois"]["p4"]["method"] == "domain+address" and out["pois"]["p4"]["fields"]["opening_hours"] == "Mo-Su 08:00-20:00"
    assert out["unmatched"] == [] and out["stats"]["verify"]["branches_dropped_outside_astana"] == 1  # (51.9, 71.9)
    assert out["stats"]["new_opening_hours"] == 2 and out["stats"]["hours_after"] == out["stats"]["hours_before"] + 2


def test_join_reports_conflicts_without_overwriting():
    url = "https://x.kz/c"
    f, _ = fetcher({url: (200, "Cafe Mo-Su 09:00-21:00", "text/html")})
    f.fetch(url)
    pois = [_poi("p1", "Cafe", "cafe", "https://x.kz", opening_hours="Mo-Su 10:00-22:00")]
    b = store.make_branch("Cafe", [store.evidence("name", url, "Cafe"), store.evidence("geo", url, "Cafe"),
                                   store.evidence("opening_hours", url, "Mo-Su 09:00-21:00")],
                          "html", 0.8, lat=51.1, lon=71.4, opening_hours_raw="Mo-Su 09:00-21:00")
    out = join.join(pois, [store.new_record("x.kz", robots_ok=True, branches=[b])], verify.Verifier(f))
    j = out["pois"]["p1"]
    assert j["new_fields"] == [] and j["conflicts"]["opening_hours"] == {
        "poi": "Mo-Su 10:00-22:00", "official": "Mo-Su 09:00-21:00"}
    assert out["stats"]["conflict_opening_hours"] == 1 and out["stats"]["new_opening_hours"] == 0


def test_address_match_needs_street_and_house():
    assert join.address_match("Астана, улица Кабанбай батыра, 62", "Кабанбай Батыр даңғылы, 62")
    assert not join.address_match("ул. Абая 1", "ул. Абая 2")
    assert not join.address_match("ул. Абая 1", None)
    assert join.split_address("проспект Тауелсиздик, 34А")[1] == "34а"


def test_join_does_not_attach_a_branch_to_the_mall_it_stands_in():
    url = "https://kfc.kz/stores"
    f, _ = fetcher({url: (200, "KFC Астана | Керуен Mo-Su 10:00-22:00 KFC Астана | Сарыарка", "text/html")})
    f.fetch(url)
    pois = [_poi("mall", "Керуен", "mall", None, lat=51.1281, lon=71.4254),
            _poi("kfc", "KFC", "fast_food", "https://kfc.kz", lat=51.12815, lon=71.42545)]
    b = store.make_branch("KFC Астана | Керуен", [store.evidence("name", url, "KFC Астана | Керуен"),
                                                   store.evidence("opening_hours", url, "Mo-Su 10:00-22:00")],
                          "html", 0.8, lat=51.1281, lon=71.4254, opening_hours_raw="Mo-Su 10:00-22:00")
    out = join.join(pois, [store.new_record("kfc.kz", robots_ok=True, branches=[b])], verify.Verifier(f))
    assert list(out["pois"]) == ["kfc"]  # the brand-leading key matches, the mall at the end of the name does not


def test_join_without_coords_prefers_the_best_name_over_a_bare_address_match():
    url = "https://nmrk.kz/c"
    f, _ = fetcher({url: (200, "Национальный музей Республики Казахстан Вт-Вс 10:00-18:00 проспект Тауелсиздик 54",
                          "text/html")})
    f.fetch(url)
    pois = [_poi("o", "Qazaqstan Respýblıkasynyń Ulttyq mýzeıі", "entertainment", "https://nmrk.kz",
                 address="проспект Тауелсиздик, 54"),
            _poi("m", "Национальный музей Республики Казахстан", "museum_gallery", "https://nmrk.kz")]
    b = store.make_branch("Национальный музей Республики Казахстан",
                          [store.evidence("name", url, "Национальный музей Республики Казахстан"),
                           store.evidence("address", url, "проспект Тауелсиздик 54"),
                           store.evidence("opening_hours", url, "Вт-Вс 10:00-18:00")],
                          "html", 0.7, address="проспект Тауелсиздик 54", opening_hours_raw="Вт-Вс 10:00-18:00")
    out = join.join(pois, [store.new_record("nmrk.kz", robots_ok=True, branches=[b])], verify.Verifier(f))
    assert list(out["pois"]) == ["m"] and out["pois"]["m"]["fields"]["opening_hours"] == "Tu-Su 10:00-18:00"


# ---- hours_flags through store / verify / join -------------------------------------------------------------


def test_make_branch_and_save_keep_raw_and_flags_for_dayless_hours(tmp_path):
    url = "https://x.kz/c"
    b = store.make_branch("Mall", [store.evidence("name", url, "Mall"),
                                   store.evidence("opening_hours", url, "с 18:00 до 06:00")],
                          "html", 0.7, opening_hours_raw="с 18:00 до 06:00")
    assert b["opening_hours_raw"] == "с 18:00 до 06:00" and b["opening_hours_osm"] is None
    assert b["hours_flags"] == ["needs_days"] and store.validate_branch(b) == []
    amb = store.make_branch("Mall", [store.evidence("name", url, "Mall"),
                                     store.evidence("opening_hours", url, "Пн-Вс 00:00-00:00")],
                            "html", 0.7, opening_hours_raw="Пн-Вс 00:00-00:00")
    assert amb["hours_flags"] == ["ambiguous_24h"] and amb["opening_hours_osm"] is None
    # a hand-built branch without the derived key is completed by save_facts; a wrong key is rejected by validate
    legacy = {k: v for k, v in b.items() if k != "hours_flags"}
    store.save_facts(store.new_record("x.kz", robots_ok=True, branches=[legacy]), tmp_path)
    assert store.load_facts("x.kz", tmp_path)["branches"][0]["hours_flags"] == ["needs_days"]
    assert any("hours_flags" in e for e in store.validate_branch({**b, "hours_flags": []}))
    assert any("deterministic" in e for e in store.validate_branch({**b, "opening_hours_osm": "Mo-Su 18:00-06:00"}))


def test_verify_recomputes_osm_and_flags_of_files_crawled_under_older_rules():
    url = "https://x.kz/c"
    f, _ = fetcher({url: (200, "<p>Mall</p><p>c 10:00 до 23:00</p><p>Mon-Sun 00:00-00:00</p><p>Пн-Пт 9-18</p>",
                          "text/html")})
    f.fetch(url)

    def old(name, raw, osm):  # shape written before hours_flags existed
        b = store.make_branch(name, [store.evidence("name", url, "Mall"), store.evidence("opening_hours", url, raw)],
                              "html", 0.7, opening_hours_raw=raw)
        b.pop("hours_flags")
        b["opening_hours_osm"] = osm
        return b

    rec = store.new_record("x.kz", robots_ok=True, branches=[
        old("A", "c 10:00 до 23:00", "Mo-Su 10:00-23:00"), old("B", "Mon-Sun 00:00-00:00", "Mo-Su 00:00-24:00"),
        old("C", "Пн-Пт 9-18", "Mo-Fr 09:00-18:00")])
    cleaned, stats = verify.verify_record(rec, verify.Verifier(f))
    a, b, c = cleaned["branches"]
    assert (a["opening_hours_osm"], a["hours_flags"], a["opening_hours_raw"]) == (None, ["needs_days"], "c 10:00 до 23:00")
    assert (b["opening_hours_osm"], b["hours_flags"]) == (None, ["ambiguous_24h"])
    assert (c["opening_hours_osm"], c["hours_flags"]) == ("Mo-Fr 09:00-18:00", [])
    assert stats["hours_downgraded"] == 2 and stats["hours_downgraded_needs_days"] == 1
    assert stats["hours_downgraded_ambiguous_24h"] == 1 and stats["osm_recomputed"] == 2
    assert stats["hours_flag_needs_days"] == 1 and stats["hours_flag_ambiguous_24h"] == 1
    assert rec["branches"][0]["opening_hours_osm"] == "Mo-Su 10:00-23:00"  # input untouched


def test_join_puts_dayless_hours_into_hours_unqualified_only():
    url = "https://x.kz/c"
    f, _ = fetcher({url: (200, "Green Mall c 10:00 до 23:00 Cafe Пн-Пт 9-18", "text/html")})
    f.fetch(url)
    pois = [_poi("mall", "Green Mall", "mall", "https://x.kz", lat=51.1, lon=71.4),
            _poi("cafe", "Cafe", "cafe", "https://x.kz", lat=51.2, lon=71.5),
            _poi("hall", "Hall", "mall", "https://x.kz", lat=51.24, lon=71.55, opening_hours="Mo-Su 10:00-22:00")]
    mall = store.make_branch("Green Mall", [store.evidence("name", url, "Green Mall"),
                                            store.evidence("geo", url, "Green Mall"),
                                            store.evidence("opening_hours", url, "c 10:00 до 23:00")],
                             "html", 0.7, lat=51.1, lon=71.4, opening_hours_raw="c 10:00 до 23:00")
    cafe = store.make_branch("Cafe", [store.evidence("name", url, "Cafe"), store.evidence("geo", url, "Cafe"),
                                      store.evidence("opening_hours", url, "Пн-Пт 9-18")],
                             "html", 0.7, lat=51.2, lon=71.5, opening_hours_raw="Пн-Пт 9-18")
    hall = store.make_branch("Hall", [store.evidence("name", url, "Cafe"), store.evidence("geo", url, "Cafe"),
                                      store.evidence("opening_hours", url, "c 10:00 до 23:00")],
                             "html", 0.7, lat=51.24, lon=71.55, opening_hours_raw="c 10:00 до 23:00")
    out = join.join(pois, [store.new_record("x.kz", robots_ok=True, branches=[mall, cafe, hall])], verify.Verifier(f))
    m = out["pois"]["mall"]
    assert "opening_hours" not in m["fields"] and "opening_hours_raw" not in m["fields"]
    assert m["fields"]["hours_unqualified"] == "c 10:00 до 23:00" and m["new_fields"] == ["hours_unqualified"]
    src = m["field_sources"]["hours_unqualified"]
    assert src["source"] == "official_site" and src["hours_flags"] == ["needs_days"] and src["url"] == url
    assert "opening_hours" not in m["field_sources"]
    assert out["pois"]["cafe"]["fields"]["opening_hours"] == "Mo-Fr 09:00-18:00"
    assert out["pois"]["hall"]["new_fields"] == []  # the POI already has hours: nothing new, nothing overwritten
    assert out["stats"]["new_opening_hours"] == 1 and out["stats"]["new_hours_unqualified"] == 1
    assert out["stats"]["hours_after"] == out["stats"]["hours_before"] + 1


# ---- bbox / schedules / apply ------------------------------------------------------------------------------------
def _geo_branch(url, name, snippet_hours, lat, lon, hours=None, **kw):
    ev = [store.evidence("name", url, name), store.evidence("geo", url, name)]
    if hours:
        ev.append(store.evidence("opening_hours", url, snippet_hours))
    return store.make_branch(name, ev, "html", 0.8, lat=lat, lon=lon, opening_hours_raw=hours, **kw)


def test_verifier_drops_branches_outside_the_astana_box():
    url = "https://x.kz/c"
    f, _ = fetcher({url: (200, "Inside Outside", "text/html")})
    f.fetch(url)
    inside, outside = _geo_branch(url, "Inside", None, 51.1, 71.4), _geo_branch(url, "Outside", None, 50.85, 71.36)
    out, stats = verify.verify_record(store.new_record("x.kz", robots_ok=True, branches=[inside, outside]),
                                      verify.Verifier(f))
    assert [b["name"] for b in out["branches"]] == ["Inside"] and stats["branches_dropped_outside_astana"] == 1
    assert store.in_astana(51.1, 71.4) and not store.in_astana(51.1, 71.7) and not store.in_astana(None, None)


def test_same_schedule_is_semantic():
    assert hours.same_schedule("Mo-Su 12:00-00:00", "Mo-Su 12:00-24:00")
    assert hours.same_schedule("Fr-Sa 09:00-01:00; Mo-Th,Su 09:00-00:00", "Mo-Th,Su 09:00-24:00; Fr,Sa 09:00-01:00")
    assert not hours.same_schedule("Mo-Su 10:00-22:00", "Mo-Su 10:00-23:00")
    assert not hours.same_schedule("Mo-Su 10:00-22:00", "с 10:00 до 22:00")  # not an OSM string


def _apply_fixture(poi_hours):
    from collect.sites import apply as ap
    url = "https://x.kz/c"
    f, _ = fetcher({url: (200, "Cafe Mo-Su 09:00-21:00 Cafe Annex Mo-Su 10:00-20:00 Other far", "text/html")})
    f.fetch(url)
    pois = [_poi("p1", "Cafe", "cafe", "https://x.kz", opening_hours=poi_hours,
                 field_sources={"opening_hours": {"source": "osm", "snapshot_date": "2026-10-16"}} if poi_hours else {},
                 sources=["osm"], hours_state="known" if poi_hours else "unknown"),
            _poi("p2", "Cafe Two", "cafe", "https://x.kz", lat=51.2, lon=71.5, sources=["osm"], field_sources={})]
    cafe = _geo_branch(url, "Cafe", "Mo-Su 09:00-21:00", 51.1, 71.4, "Mo-Su 09:00-21:00")
    new = _geo_branch(url, "Cafe Annex", "Mo-Su 10:00-20:00", 51.15, 71.45, "Mo-Su 10:00-20:00")
    far = _geo_branch(url, "Other", None, 50.5, 71.4)  # outside the box: never reaches the join
    rec = store.new_record("x.kz", robots_ok=True, branches=[cafe, new, far], fetched_at="2026-10-17T10:00:00+00:00")
    return ap.build(pois, [rec], verify.Verifier(f))


def test_apply_fills_hours_only_when_osm_has_none_and_creates_new_poi():
    data, _, stats = _apply_fixture(None)
    p1 = next(p for p in data if p["id"] == "p1")
    assert p1["opening_hours"] == "Mo-Su 09:00-21:00" and p1["hours_state"] == "known"
    assert p1["field_sources"]["opening_hours"]["source"] == "official_site" and "official_site" in p1["sources"]
    assert p1["hours_conflict"] is False and p1["opening_hours_official"] is None
    new = [p for p in data if p["id"].startswith("site/x.kz/")]
    assert len(new) == 1 and new[0]["name"] == "Cafe Annex" and new[0]["category"] == "cafe"
    assert new[0]["sources"] == ["official_site"] and new[0]["opening_hours"] == "Mo-Su 10:00-20:00"
    assert new[0]["match_confidence"] == 0.8 and new[0]["official_site_match"]["match_method"] == "new_poi"
    assert {"name", "lat", "lon", "category", "opening_hours"} <= set(new[0]["field_sources"])
    assert stats["poi_total_before"] == 2 and stats["poi_total_after"] == 3 and stats["new_pois"] == 1
    assert stats["hours_day_qualified_before"] == 0 and stats["hours_day_qualified_after"] == 2


def test_apply_conflict_keeps_osm_and_flags_it():
    data, _, stats = _apply_fixture("Mo-Su 10:00-22:00")
    p1 = next(p for p in data if p["id"] == "p1")
    assert p1["opening_hours"] == "Mo-Su 10:00-22:00" and p1["opening_hours_official"] == "Mo-Su 09:00-21:00"
    assert p1["hours_conflict"] is True and p1["hours_conflict_prefers"] == "official_site"
    assert p1["field_sources"]["opening_hours"]["source"] == "osm"
    assert p1["field_sources"]["opening_hours_official"]["source"] == "official_site"
    assert stats["hours_conflicts"] == 1


def test_apply_equal_schedule_is_not_a_conflict():
    data, _, stats = _apply_fixture("Mo-Su 09:00-21:00")
    p1 = next(p for p in data if p["id"] == "p1")
    assert p1["hours_conflict"] is False and p1["opening_hours_official"] == "Mo-Su 09:00-21:00"
    assert stats["hours_conflicts"] == 0 and stats["hours_confirmed_same"] == 1


def test_apply_marks_an_applied_dataset_and_extends_the_merge_stats_with_the_official_sites():
    from collect.sites import apply as ap
    data, _, stats = _apply_fixture("Mo-Su 10:00-22:00")
    assert ap.already_applied(data) and not ap.already_applied([p for p in data if "official_site_match" not in p])
    prev = {"after": {"total": 2}, "per_source_counts": {"osm_only": 2, "with_wikidata": 0},
            "description_source_counts": {}, "overture": {"total": 5}}
    for p in data:  # the fixture POIs carry only what the join reads; `stats_for` reads the whole record
        p.setdefault("description_source", "derived")
    ship = ap.shipped_stats(prev, data, stats)
    assert ship["after"]["total"] == 3 and ship["official_sites"] is stats and ship["overture"] == {"total": 5}
    ps = ship["per_source_counts"]
    assert (ps["osm_only"], ps["official_site_only"], ps["with_official_site"], ps["with_wikidata"]) == (2, 1, 2, 0)
    assert sum(ps[k] for k in ("osm_only", "overture_only", "osm_and_overture", "wikidata_only", "official_site_only")) == 3


def test_new_poi_names_dedupe_and_third_party_coordinates():
    from collect.sites import apply as ap
    assert ap.site_head("Del Papa — пр. Кабанбай батыр, 62", "пр. Кабанбай батыр, 62") == "Del Papa"
    assert ap.site_head("Шашлычок, Астана, Туран 55", "Астана, Туран 55") == "Шашлычок"
    assert ap.site_head("RUMI (г. Астана, Петрова, 28)", "г. Астана, Петрова, 28") == "RUMI"
    assert ap.address_ok("Қабанбай батыр даңғ. 62, Алматы, Қазақстан") is None
    prof = {"x.kz": {"brand": "Coffee BOOM", "category": "cafe"}}
    desc = {"name": "Орталық саябақтағы сағаттың жанында", "address": "Астана қ., Тұран даңғылы, 2г"}
    assert ap.display_name(desc, prof["x.kz"]) == ("Coffee BOOM, Тұран даңғылы, 2г", "domain_brand+address")
    assert ap.display_name({"name": "Жүргенов көшесінде", "address": None}, prof["x.kz"])[0] is None
    b = {"name": "Cafe A", "address": None, "lat": 51.1, "lon": 71.4, "confidence": 0.8, "method": "html",
         "evidence": [store.evidence("geo", "https://x.kz", "Cafe A")], "hours_flags": []}
    c = {"domain": "x.kz", "branch": b, "snapshot": "2026-10-17T10:00:00+00:00", "third_party": False}
    twin = {**c, "branch": {**b, "name": "Cafe A", "lat": 51.10002}}
    other_name = {**c, "branch": {**b, "name": "Zebra Grill", "lat": 51.103}}
    profiles = {"x.kz": {"brand": None, "category": "cafe"}}
    out, skipped = ap.make_new_pois([c, twin, other_name], [], profiles)
    assert [p["name"] for p in out] == ["Cafe A", "Zebra Grill"]  # the same-place same-name twin is dropped
    assert skipped and any("earlier new POI" in k for k in skipped)  # (Zebra Grill 0 m away has a dissimilar name)
    same_point = {**c, "branch": {**b, "name": "Zebra Grill"}}  # another venue on the very same point: a map default
    out2, sk2 = ap.make_new_pois([c, same_point], [], profiles)
    assert out2 == [] and sk2["placeholder coordinates (shared with a different venue)"] == 2
    out3, sk3 = ap.make_new_pois([{**c, "third_party": True}], [], profiles)
    assert out3 == [] and "coordinates from a third-party backend" in sk3


# ---- a domain speaks only for POIs it agrees with (brand + category) --------------------------------------------
def test_brand_agreement_and_category_compatibility():
    from collect.sites import agree
    cats = agree.own_categories([_poi("c", "Coffee BOOM", "cafe", "https://coffeeboom.kz"),
                                 _poi("k", "KFC", "fast_food", "https://kfc-kazakhstan.kz")])
    mall = _poi("m", "Mega Silk Way", "mall", "http://astana.megacenter.kz")
    bar = _poi("b", "Kömir Highvill Ishim", "bar_nightlife")
    shop = _poi("s", "Coffee BOOM Mega", "cafe")
    assert not agree.speaks_for("coffeeboom.kz", mall, cats)  # neither the name nor the category agrees
    assert not agree.speaks_for("coffeeboom.kz", bar, cats)  # food category, but the brand is not in its name
    assert agree.speaks_for("coffeeboom.kz", shop, cats)
    assert agree.speaks_for("kfc.kz", _poi("k2", "KFC", "fast_food"), cats)  # kfc.kz ~ kfc-kazakhstan.kz brand
    assert agree.speaks_for("kfc.kz", _poi("k3", "КФС", "fast_food", "https://kfc-kazakhstan.kz"), cats)
    assert not agree.speaks_for("kfc.kz", _poi("k4", "KFC", "mall"), cats)  # 'shop=mall' named KFC
    assert agree.speaks_for("edagoroda.kz", _poi("e", 'Гриль-бар "ЕдаГорода"', "restaurant", "https://ppsh.kz"), {})
    assert agree.same_brand("chabad.kz", "chabadkz.org") and not agree.same_brand("kfc.kz", "keruen.kz")


def test_join_never_attaches_a_chain_branch_to_the_mall_it_stands_in():
    url = "https://coffeeboom.kz/c"
    f, _ = fetcher({url: (200, "Mega Silk Way ТК-де Mo-Su 08:00-24:00 Coffee BOOM Mega Silk Way Mo-Su 08:00-22:00", "text/html")})
    f.fetch(url)
    pois = [_poi("mall", "Mega Silk Way", "mall", "http://astana.megacenter.kz", lat=51.1, lon=71.4),
            _poi("cb", "Coffee BOOM", "cafe", "https://coffeeboom.kz", lat=51.1001, lon=71.4001)]
    inside = _geo_branch(url, "Mega Silk Way ТК-де", "Mega Silk Way ТК-де Mo-Su 08:00-24:00", 51.1, 71.4, "Mo-Su 08:00-24:00")
    out = join.join(pois, [store.new_record("coffeeboom.kz", robots_ok=True, branches=[inside])], verify.Verifier(f))
    assert out["pois"] == {}  # the old behaviour: score 100 by name, the mall got the coffee shop's hours
    assert [u["name"] for u in out["unmatched"]] == ["Mega Silk Way ТК-де"]  # a branch of its own, not the mall


def test_check_dataset_fails_when_the_hours_domain_is_not_backed_by_the_poi():
    src = {"source": "official_site", "url": "https://coffeeboom.kz/e/437", "snapshot_date": "2026-10-17"}
    mall = _poi("m", "Mega Silk Way", "mall", "http://astana.megacenter.kz", opening_hours="Mo-Su 10:00-22:00",
                field_sources={"opening_hours": {"source": "osm"}, "opening_hours_official": src},
                opening_hours_official="Mo-Su 08:00-24:00", hours_conflict=True,
                official_site_match={"domain": "coffeeboom.kz"})
    shop = _poi("cb", "Coffee BOOM", "cafe", "https://coffeeboom.kz", opening_hours="Mo-Su 08:00-24:00",
                field_sources={"opening_hours": src}, official_site_match={"domain": "coffeeboom.kz"})
    problems = verify.check_dataset([mall, shop])
    assert len(problems) == 1 and "Mega Silk Way" in problems[0] and "coffeeboom.kz" in problems[0]
    vendor = _poi("g", "Golpas", "bar_nightlife", "https://golpas.cafe", opening_hours="Mo-Su 12:00-01:00",
                  field_sources={"opening_hours": {"source": "official_site", "url": "https://ailillu.kz/api"}},
                  official_site_match={"domain": "golpas.cafe"})
    assert any("not on golpas.cafe" in p for p in verify.check_dataset([vendor]))  # a vendor platform is no own site
    lone = _poi("x", "Cafe", "cafe", None, hours_conflict=True, field_sources={"opening_hours": {"source": "osm"}})
    assert any("hours_conflict" in p for p in verify.check_dataset([lone]))
    assert verify.check_dataset([shop]) == []


def test_apply_refuses_to_write_a_dataset_that_fails_the_check(tmp_path):
    from collect.sites import apply as ap
    url = "https://coffeeboom.kz/c"
    f, _ = fetcher({url: (200, "Mega Silk Way Mo-Su 08:00-24:00", "text/html")})
    f.fetch(url)
    mall = _poi("m", "Mega Silk Way", "mall", "http://astana.megacenter.kz", lat=51.1, lon=71.4)
    data, _, _ = ap.build([mall, _poi("cb", "Coffee BOOM", "cafe", "https://coffeeboom.kz", lat=51.3, lon=71.6)],
                          [store.new_record("coffeeboom.kz", robots_ok=True, branches=[
                              _geo_branch(url, "Mega Silk Way", "Mega Silk Way Mo-Su 08:00-24:00", 51.1, 71.4,
                                          "Mo-Su 08:00-24:00")])], verify.Verifier(f))
    assert verify.check_dataset(data) == []  # the mall stays untouched: the join did not attach the branch
    assert next(p for p in data if p["id"] == "m")["opening_hours"] is None


def test_all_day_every_day_is_stored_as_24_7_whatever_the_spelling():
    for text in ("круглосуточно", "Пн-Вс 00:00-23:59", "Mo-Su 00:00-24:00", "ежедневно 00:00-24:00"):
        assert hours.to_osm(text) == "24/7", text
    assert hours.to_osm("Пн-Пт 00:00-24:00") == "Mo-Fr 00:00-24:00"  # not every day: stays a schedule


# ---- crawler cross-checks: the day order / "today" markers of the two store-locator templates ----------------------
def _crawler(domain):
    import importlib.util
    spec = importlib.util.spec_from_file_location("c_" + domain.replace(".", "_"),
                                                  Path(__file__).resolve().parents[1] / "sites" / "crawlers" / f"{domain}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# FakeNet stamps every page 1_790_000_000 = Monday 2026-09-21 18:33 in Astana (UTC+5)
def _starbucks_page(card):
    week = r'\"monday\":\"07:00-22:00\",\"tuesday\":\"07:00-22:00\",\"wednesday\":\"07:00-22:00\",\"thursday\":\"07:00-22:00\",' \
           r'\"friday\":\"07:00-22:00\",\"saturday\":\"08:00-23:00\",\"sunday\":\"08:00-23:00\"'
    store_json = (r'{\"id\":\"7\",\"storeAddress\":\"Достық көш. 16\",\"phone\":\"1\",\"name\":\"Starbucks Талан Тауэрс\",'
                  r'\"weeklyWorkingHours\":{' + week + r'},\"location\":{\"lon\":71.432155,\"lat\":51.124967},\"filters\":{}}')
    html = ('<span class="text-[24px] font-semibold leading-none">Starbucks Талан Тауэрс</span></div>'
            f'<div class="text-gray-800 text-[12px]">{card}</div>')
    return html + store_json


def test_starbucks_weekly_json_is_read_per_day_and_checked_against_the_card_of_today():
    url = "https://www.starbucks.com.kz/stores"
    f, _ = fetcher({url: (200, _starbucks_page("07:00-22:00"), "text/html")})  # Monday's card = Monday's JSON
    branches, _, notes = _crawler("starbucks.com.kz").crawl(f)
    b = branches[0]
    assert b["opening_hours_osm"] == "Mo-Fr 07:00-22:00; Sa,Su 08:00-23:00"  # weekdays 07-22 are real, not a 1 h shift
    assert "Hours not stored" not in notes
    # the same page read on a Saturday would show the Saturday value on the card: that is today's interval, which
    # is how a one-hour "difference" with the Mon-Fri hours arises; a card that matches no JSON day is rejected
    f2, _ = fetcher({url: (200, _starbucks_page("08:00-23:00"), "text/html")})  # card says 08-23 on a Monday
    branches2, _, notes2 = _crawler("starbucks.com.kz").crawl(f2)
    assert branches2[0]["opening_hours_raw"] is None and "Hours not stored" in notes2


def _hardees_page(bold_day):
    rows = "".join(
        f'<tr><td{" class=\"font-weight-bold mainColor\"" if d == bold_day else ""}>{d}</td>'
        f'<td class="text-right"> {"10:00 - 00:00" if d == "суббота" else "10:00 - 22:45"} <br /></td></tr>'
        for d in ("воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"))
    return ('<div id="store_collapse_card_157" class="x" data-cat-id="2410"><h5 class="card-title">Hardee`s Астана | '
            'Mega Expo</h5><td class="details-text">просп. Кабанбай Батыра 62, Астана</td>'
            '<tr data-lat="51.08858" data-lng="71.40870"></tr>'
            f'<div id="takeaway_store_157"><table><tbody>{rows}</tbody></table></div></div>')


def test_hardees_table_is_sunday_first_and_saturday_closes_at_midnight():
    url = "https://www.hardees.kz/stores"
    f, _ = fetcher({url: (200, _hardees_page("понедельник"), "text/html")})  # the platform bolds today (Monday)
    b = _crawler("hardees.kz").crawl(f)[0][0]
    assert b["opening_hours_osm"] == "Mo-Fr,Su 10:00-22:45; Sa 10:00-24:00"  # Sa rolls into Sunday 00:00, not Su
    from opening_hours import OpeningHours
    from datetime import datetime
    oh = OpeningHours(b["opening_hours_osm"])
    assert oh.is_open(datetime(2026, 10, 17, 23, 50)) and oh.is_open(datetime(2026, 10, 18, 22, 30))  # Sa late, Su 22:30
    assert not oh.is_open(datetime(2026, 10, 18, 23, 50))  # Sunday closes 22:45; "Su 10:00-00:00" would keep it open
    f2, _ = fetcher({url: (200, _hardees_page("суббота"), "text/html")})  # bold row says Saturday on a Monday
    b2 = _crawler("hardees.kz").crawl(f2)[0][0]
    assert b2["opening_hours_raw"] is None  # the site's own "today" marker disagrees with the weekday: hours skipped


# ---- museum register (e-museum.kz) --------------------------------------------------------------------------------
def test_register_join_matches_by_name_and_address_and_labels_the_source():
    url = "https://e-museum.kz/wp-json/wp/v2/museum?region=3952&lang=ru"
    body = ('[{"id":1,"title":{"rendered":"Музей Сакена Сейфуллина"},"work_hours":"09:00 - 18:00",'
            '"ticket_price":"500 тг","site":"www.astanamuseums.kz","addresscity":"Астана қаласы",'
            '"addressstreet":"Әуезов көшесі 20 А","slug":"m1","link":"https://e-museum.kz/ru/museum/m1/"},'
            '{"id":2,"title":{"rendered":"«Алжир» комплекс"},"work_hours":"09:00 - 18:00",'
            '"ticket_price":"300 тг.","site":"museum-alzhir.kz","addresscity":"Ақмол ауылы",'
            '"addressstreet":"Линейная 2б","slug":"m2","link":"https://e-museum.kz/ru/museum/m2/"}]')
    f, _ = fetcher({url: (200, body, "application/json")})
    f.fetch(url)
    pois = [_poi("seif", "Музей Сакена Сейфуллина", "museum_gallery", lat=51.17, lon=71.42,
                 address="Астана, Мұхтар Әуезов көшесі, 20"),
            _poi("nat", "Национальный музей Республики Казахстан", "museum_gallery", lat=51.1, lon=71.4,
                 opening_hours="Tu-Su 10:00-18:00",
                 field_sources={"opening_hours": {"source": "official_site", "snapshot_date": "2026-10-16",
                                                  "url": "https://nmrk.kz/ru/about-museum/contacts/"}})]
    rec = store.new_record("e-museum.kz", robots_ok=True, pages=[url], branches=[], notes="",
                           source_label="museum_register")
    b = store.make_branch("Музей Сакена Сейфуллина",
                          [store.evidence("name", url, '"title":{"rendered":"Музей Сакена Сейфуллина"}'),
                           store.evidence("opening_hours", url, '"work_hours":"09:00 - 18:00"'),
                           store.evidence("price", url, '"ticket_price":"500 тг"')],
                          "html", 0.7, opening_hours_raw="09:00 - 18:00", price_text="500 тг",
                          url="https://e-museum.kz/ru/museum/m1/")
    rec["branches"] = [b]
    out, _ = join.join_branches(pois, [rec], verify.Verifier(f))
    j = out["pois"]["seif"]
    assert j["fields"]["price_text"] == "500 тг" and j["fields"]["hours_unqualified"] == "09:00 - 18:00"
    assert j["field_sources"]["price_text"]["source"] == "museum_register"
    assert j["source_label"] == "museum_register"


def test_register_never_trades_day_qualified_hours_for_dayless_register_hours():
    url = "https://e-museum.kz/wp-json/wp/v2/museum?region=3952&lang=ru"
    body = ('[{"id":1,"title":{"rendered":"Национальный музей Республики Казахстан"},"work_hours":"10:00 - 18:00",'
            '"ticket_price":"1000 тг.","addresscity":"Астана қаласы","addressstreet":"Тәуелсіздік даңғылы 54",'
            '"slug":"m1","link":"https://e-museum.kz/ru/museum/m1/"}]')
    site_url = "https://nmrk.kz/ru/about-museum/contacts/"
    f, _ = fetcher({url: (200, body, "application/json"),
                    site_url: (200, "Национальный музей Рабочее время 10:00 - 18:00 Вт-Вс", "text/html")})
    f.fetch(url)
    f.fetch(site_url)
    pois = [_poi("nat", "Национальный музей Республики Казахстан", "museum_gallery", lat=51.1, lon=71.4,
                 website="https://nmrk.kz/")]
    reg = store.make_branch("Национальный музей Республики Казахстан",
                            [store.evidence("name", url, "Национальный музей"),
                             store.evidence("opening_hours", url, '"work_hours":"10:00 - 18:00"'),
                             store.evidence("price", url, '"ticket_price":"1000 тг."')],
                            "html", 0.7, opening_hours_raw="10:00 - 18:00", price_text="1000 тг.", url=url)
    own = store.make_branch("Национальный музей",
                            [store.evidence("name", site_url, "Национальный музей"),
                             store.evidence("opening_hours", site_url, "Рабочее время 10:00 - 18:00 Вт-Вс")],
                            "html", 0.75, lat=51.1, lon=71.4, opening_hours_raw="10:00 - 18:00 Вт-Вс",
                            url=site_url)
    rec_reg = store.new_record("e-museum.kz", robots_ok=True, branches=[reg], source_label="museum_register")
    rec_own = store.new_record("nmrk.kz", robots_ok=True, branches=[own])
    out, _ = join.join_branches(pois, [rec_reg, rec_own], verify.Verifier(f))
    j = out["pois"]["nat"]
    # the site's day-qualified schedule is what the POI gets; the register contributes the price and the day-less text
    assert j["fields"]["opening_hours"] == "Tu-Su 10:00-18:00"
    assert j["fields"]["price_text"] == "1000 тг."  # merged into the earlier entry
    assert j["field_sources"]["price_text"]["source"] == "museum_register"
    # the official_site hours stay backed by their own domain
    assert j["official_domain"] == "nmrk.kz"


def test_register_address_alone_does_not_match_a_co_located_museum():
    url = "https://e-museum.kz/wp-json/wp/v2/museum?region=3952&lang=ru"
    body = '[{"id":1,"title":{"rendered":"Государственный историко-культурный музей-заповедник «Бозоқ»"},' \
           '"addresscity":"Астана қаласы","addressstreet":"Тәуелсіздік даңғылы  54","slug":"m1",' \
           '"link":"https://e-museum.kz/ru/museum/m1/"}]'
    f, _ = fetcher({url: (200, body, "application/json")})
    f.fetch(url)
    pois = [_poi("nat", "Национальный музей Республики Казахстан", "museum_gallery", lat=51.1, lon=71.4,
                 address="Астана, Тәуелсіздік даңғылы 54")]
    b = store.make_branch("Государственный историко-культурный музей-заповедник «Бозоқ»",
                          [store.evidence("name", url, "Бозоқ"), store.evidence("address", url, "Тәуелсіздік 54")],
                          "html", 0.7, address="Тәуелсіздік даңғылы 54", url=url)
    rec = store.new_record("e-museum.kz", robots_ok=True, branches=[b], source_label="museum_register")
    out, _ = join.join_branches(pois, [rec], verify.Verifier(f))
    assert "nat" not in out["pois"]  # the name (38) is below the floor: the reserve is not the National Museum


def test_e_museum_rest_collector_keeps_astana_cards_and_drops_the_region_leak():
    em = _crawler("e-museum.kz")
    body = ('[{"id":1,"title":{"rendered":"Музей Сакена Сейфуллина"},"work_hours":"09:00 - 18:00",'
            '"ticket_price":"500 тг","site":"www.astanamuseums.kz","addresscity":"\u0410\u0441\u0442\u0430\u043d'
            '\u0430 \u049b\u0430\u043b\u0430\u0441\u044b","addressstreet":"\u04d8\u0443\u0435\u0437\u043e'
            '\u0432 \u043a\u04e9\u0448\u0435\u0441\u0456 20","slug":"68da-ru"},'
            '{"id":2,"title":{"rendered":"\u00ab\u0410\u043b\u0436\u0438\u0440\u00bb \u043a\u043e\u043c'
            '\u043f\u043b\u0435\u043a\u0441"},"work_hours":"09:00 - 18:00","ticket_price":"300 \u0442\u0433."'
            ',"site":"museum-alzhir.kz","addresscity":"\u0410\u049b\u043c\u043e\u043b \u0430\u0443\u044b\u043b'
            '\u044b","addressstreet":"\u041b\u0438\u043d\u0435\u0439\u043d\u0430\u044f 2\u0431",'
            '"slug":"68db-ru"}]')
    f, _ = fetcher({em.REST_URL: (200, body, "application/json")})
    branches, pages, notes = em.crawl(f)
    assert pages == [em.REST_URL]
    assert [b["name"] for b in branches] == ["Музей Сакена Сейфуллина"]  # «Алжир» (Ақмол ауылы) dropped by city
    b = branches[0]
    assert b["price_text"] == "500 тг" and b["opening_hours_raw"] == "09:00 - 18:00"
    assert b["opening_hours_osm"] is None and b["hours_flags"] == ["needs_days"]
    assert b["address"] == "Әуезов көшесі 20" and b["url"].startswith("https://e-museum.kz/ru/museum/")
    # every snippet is a verbatim slice of the raw \u-escaped JSON
    for e in b["evidence"]:
        assert e["snippet"] in body
    assert "Ақмол ауылы" in notes

