"""The web UI's server (app/web) end to end through its JSON endpoints, on the real dataset: what the Streamlit
AppTests of the former UI checked (k >= 5 for the real log, the three memory layers, the recorded-answer stand, an
answer without a key, the languages) is checked here on `/api/*`.

Every WALKS_* path points into tmp_path: the tests never write data/city_feedback.json or app/.local."""

from __future__ import annotations

import json
import re

import pytest
from starlette.testclient import TestClient

from tests.test_city_layer import BASE, ORIGIN, _poi, _rec
from walks import llm
from walks.presets import PRESETS, SCENARIOS
from web.server import Release, create_app

BAITEREK = PRESETS["Байтерек"]
KHAN_SHATYR = PRESETS["Хан Шатыр"]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WALKS_OFFLINE", "1")  # no network of any kind: rules answers
    monkeypatch.setenv("WALKS_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("WALKS_STATE_FILE", str(tmp_path / "conversation.json"))
    # the city page tests below read the simulated demand file, which is served only under this flag
    monkeypatch.setenv("WALKS_DEMAND_SIM", "1")
    (tmp_path / "marks.json").write_text("[]", encoding="utf-8")
    return TestClient(create_app())


def _turn(client, text, place=BAITEREK, **extra) -> dict:
    """POST /api/turn and the last line of its NDJSON stream: the answer (or the error)."""
    body = {"text": text, "lat": place[0], "lon": place[1], **extra}
    res = client.post("/api/turn", json=body)
    assert res.status_code == 200, res.text
    lines = [json.loads(line) for line in res.text.strip().splitlines()]
    assert "answer" in lines[-1], lines[-1]
    return lines[-1]["answer"]


def _names(answer: dict) -> list[str]:
    return [p["name"] for p in answer["turn"]["places"]]


# ---- the stand -------------------------------------------------------------------------------------


def test_the_page_the_health_check_and_the_security_headers(client):
    assert client.get("/healthz").text == "ok"
    page = client.get("/")
    assert page.status_code == 200
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/vendor/maplibre-gl-6.14.0/LICENSE.txt").status_code == 200


def test_the_page_is_not_transformed_and_static_modules_are_revalidated(client):
    """`no-transform` keeps a Cloudflare proxy from injecting its analytics script into the page (the CSP blocks it);
    `no-cache` on /static makes a proxy revalidate the ES modules after a release instead of serving old ones."""
    page = client.get("/")
    directives = {d.strip() for d in page.headers["cache-control"].split(",")}
    assert {"no-cache", "no-transform"} <= directives
    assert "script-src 'self';" in page.headers["content-security-policy"]
    static = client.get("/static/vendor/maplibre-gl-6.14.0/LICENSE.txt")
    assert static.headers.get_list("cache-control") == ["no-cache"]
    # revalidation stays a cheap 304
    assert static.headers.get("etag") or static.headers.get("last-modified")


def test_the_page_links_its_assets_under_its_release_and_an_edit_makes_a_new_one(client, tmp_path):
    """A proxy keeps static files for hours whatever the server says, so the page links them under its release: a
    module's relative imports stay inside it, it is kept for a year, and an edited file changes the release at once."""
    html = client.get("/").text
    release = re.search(r'src="/static/v-([0-9a-f]{12})/js/main\.js"', html).group(1)
    assert '"/static/css/' not in html
    assert '"/static/js/' not in html
    # what main.js's `./assistant.js` resolves to
    versioned = client.get(f"/static/v-{release}/js/assistant.js")
    assert versioned.status_code == 200
    assert versioned.content == client.get("/static/js/assistant.js").content
    assert versioned.headers.get_list("cache-control") == ["public, max-age=31536000, immutable"]
    assert "nosniff" in versioned.headers["x-content-type-options"]
    stale = client.get("/static/v-000000000000/js/assistant.js")  # an older page's link
    assert stale.status_code == 200
    assert stale.headers.get_list("cache-control") == ["no-cache"]
    assert client.get(f"/static/v-{release}/js/missing.js").status_code == 404

    root = tmp_path / "static"
    (root / "js").mkdir(parents=True)
    (root / "js" / "main.js").write_text("a", encoding="utf-8")
    built = Release(root)
    before = built.current
    (root / "js" / "main.js").write_text("ab", encoding="utf-8")
    assert built.take() != before


def test_every_asset_the_page_links_is_served(client):
    html = client.get("/").text
    links = re.findall(r'(?:href|src)="(/static/[^"]+)"', html)
    assert links
    missing = [u for u in links if client.get(u).status_code != 200]
    assert missing == []


def test_config_names_the_mode_the_places_and_the_starters_of_every_language(client):
    cfg = client.get("/api/config").json()
    assert cfg["mode"]["offline"] is True
    assert {p["id"] for p in cfg["presets"]} == set(PRESETS)
    for lang, rows in cfg["starters"].items():
        assert [r["id"] for r in rows][:5] == ["s0", "s1", "s2", "s3", "s4"], lang
        assert all(r["label"] and r["text"] and r["preset"] in PRESETS for r in rows)
    assert len(cfg["starters"]["kk"][1]["text"]) > 0
    assert cfg["starters"]["ru"][1]["label"] != cfg["starters"]["ru"][1]["text"]  # a short label


def test_every_string_of_the_page_is_there_in_three_languages(client):
    table = client.get("/api/strings").json()
    assert len(table) > 300
    for key, entry in table.items():
        assert len(entry) == 3, key
        assert all(entry), key
    assert "sig_has_socket" in table  # the core's wording of the marks


# ---- a turn ------------------------------------------------------------------------------------------


def test_a_turn_without_a_key_is_rules_text_with_steps_and_a_route(client):
    res = client.post(
        "/api/turn",
        json={"text": "Тихое место с кофе и розеткой", "lat": BAITEREK[0], "lon": BAITEREK[1]},
    )
    lines = [json.loads(line) for line in res.text.strip().splitlines()]
    stages = [x["stage"] for x in lines if "stage" in x]
    assert stages[:2] == ["parse", "search"]
    answer = lines[-1]["answer"]
    turn = answer["turn"]
    assert turn["kind"] == "places"
    assert turn["meta"]["generation"] == "template"  # no model: the text of the data
    assert turn["places"][0]["primary"] is True
    assert {"state", "text"} <= set(turn["places"][0]["hours"])
    assert turn["route"]["stops"]
    # one entry per leg, None: no street line for it
    assert len(answer["route_shape"]) == len(turn["route"]["stops"])


def test_a_bad_body_is_refused(client):
    assert client.post("/api/turn", json={"text": "", "lat": 51.1, "lon": 71.4}).status_code == 422
    assert (
        client.post("/api/turn", json={"text": "кафе", "lat": 951, "lon": 71.4}).status_code == 422
    )
    bad = {"text": "кафе", "lat": 51.1, "lon": 71.4, "x": 1}
    assert client.post("/api/turn", json=bad).status_code == 422
    assert client.post("/api/turn", content=b"{").status_code in (400, 422)


def test_the_answer_language_follows_the_question_or_the_chosen_language(client):
    kk = _turn(client, "Баламен қайда баруға болады?", PRESETS["EXPO"])
    assert kk["turn"]["lang"] == "kk"
    fixed = _turn(client, "кафе", lang="en", lang_fixed=True)
    assert fixed["turn"]["lang"] == "en"
    assert fixed["turn"]["places"][0]["hours"]["text"] != ""


def test_a_question_about_a_shown_place_is_answered_from_the_data(client):
    first = _turn(client, "Тихое место с кофе и розеткой")
    name = first["turn"]["places"][1]["name"]
    second = _turn(client, f"до скольки работает {name}?", state=first["state"])
    assert second["turn"]["kind"] == "place_answer"
    assert second["turn"]["answers"]
    assert second["turn"]["answers"][0]["text"]


def test_closer_then_other_places_never_repeats_what_was_shown(client):
    first = _turn(client, "Кафе")
    chips = {c["send"]: c for c in first["turn"]["chips"]}
    assert "а поближе?" in chips
    closer = _turn(client, "а поближе?", state=first["state"])
    assert closer["turn"]["meta"]["continued"] is True
    more = _turn(client, "что-то другое", state=closer["state"])
    assert more["turn"]["places"]
    assert not set(_names(more)) & set(_names(first))
    assert not set(_names(more)) & set(_names(closer))


def test_in_frost_the_kids_answer_has_no_outdoor_playground(client):
    answer = _turn(
        client, "С ребёнком: площадка или интерактивный музей", KHAN_SHATYR, weather="frost"
    )
    assert answer["turn"]["places"]
    assert all(p["category"] != "kids_playground" for p in answer["turn"]["places"])


def test_an_indoor_kids_centre_is_not_badged_as_another_category(client):
    answer = _turn(client, "С ребёнком: площадка или интерактивный музей", KHAN_SHATYR)
    assert answer["turn"]["places"]
    assert "другая категория" not in " ".join(p["caveat"] for p in answer["turn"]["places"])


def test_the_expanded_radius_is_said_on_the_card(monkeypatch, tmp_path, client):
    path = tmp_path / "poi.json"
    path.write_text(
        json.dumps([_poi("far-park", BASE * 1.3, "park_garden").model_dump(mode="json")]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POI_PATH", str(path))
    answer = _turn(client, "парк, прогулка 45 минут", ORIGIN)
    place = answer["turn"]["places"][0]
    assert place["padding"] == "expanded"
    assert re.search(r"расширен|чуть дальше", json.dumps(place, ensure_ascii=False))


def test_no_private_provider_name_reaches_the_page(monkeypatch, client):
    monkeypatch.setenv("LLM_CHAIN", "openai:private/model@gw,gemini:gemini-2.5-flash")
    monkeypatch.setenv("LLM_PROFILE_GW_BASE_URL", "https://gateway.example/v1")
    answer = _turn(client, "Тихое место с кофе и розеткой")
    blob = json.dumps(answer, ensure_ascii=False)
    blob += client.get("/api/config").text + client.get("/api/data").text
    assert not re.search(r"@gw|openai:|gateway\.example|private/model", blob)


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_a_scenario_answers_in_the_chosen_language(client, lang):
    scenario = SCENARIOS[1]
    answer = _turn(
        client, scenario.text_in(lang), PRESETS[scenario.preset], lang=lang, lang_fixed=True
    )
    turn = answer["turn"]
    assert turn["lang"] == lang
    assert turn["places"]
    assert all(c["label"] for c in turn["chips"])


def test_the_interface_follows_the_request_until_a_language_is_chosen(client):
    assert _turn(client, "A quiet cafe with wifi")["turn"]["lang"] == "en"
    chosen = _turn(client, "A quiet cafe with wifi", lang="kk", lang_fixed=True)
    assert chosen["turn"]["lang"] == "kk"


def test_in_frost_a_card_of_another_category_carries_the_badge(client):
    answer = _turn(client, "Прогулка с ребёнком, площадка", (51.1197, 71.4601), weather="frost")
    assert "другая категория" in " ".join(p["caveat"] for p in answer["turn"]["places"])


# ---- the stand with recorded answers only ----------------------------------------------------------


def _boom(*_a, **_k):
    raise AssertionError("no model call may be made in replay-only mode")


def test_replay_only_stand_is_honest_and_makes_no_model_call(monkeypatch, client):
    monkeypatch.delenv("WALKS_OFFLINE")
    monkeypatch.setenv("WALKS_REPLAY_ONLY", "1")
    monkeypatch.setattr(llm, "ask", _boom)
    mode = client.get("/api/config").json()["mode"]
    assert mode["replay_only"] is True
    assert mode["ai"] is True  # the toggle is on: the recorded answers are the AI
    answer = _turn(client, "Тихое кафе с розеткой на 40 минут")  # not in the recording
    assert answer["turn"]["meta"]["generation"] == "template"
    assert answer["turn"]["meta"]["cached"] is False


# ---- «Город» ---------------------------------------------------------------------------------------


def _log(tmp_path, monkeypatch, n=6) -> None:
    log = tmp_path / "requests.jsonl"
    rec = _rec(cands={"none": 1}, recs={"none": 1}, nearby=2)
    log.write_text("\n".join(json.dumps(rec) for _ in range(n)) + "\n", encoding="utf-8")
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))


def test_the_simulated_demand_is_served_only_under_its_flag(client, monkeypatch):
    monkeypatch.delenv("WALKS_DEMAND_SIM")
    monkeypatch.setenv("WALKS_REQUEST_LOG", "off")
    off = client.get("/api/city/demand?source=sim&k=5").json()
    assert off == {"sources": [], "empty": True}  # no real log yet: the honest empty state
    monkeypatch.setenv("WALKS_DEMAND_SIM", "1")
    assert client.get("/api/city/demand?source=sim&k=5").json()["simulated"] is True


def test_the_simulated_demand_is_labelled_and_k_can_be_lowered(client):
    sim = client.get("/api/city/demand?source=sim&k=5").json()
    assert sim["simulated"] is True
    assert sim["k_min"] == 2
    keys = {"requests", "no_place", "hours_unknown", "padded", "cells_shown", "cells_hidden"}
    assert keys <= set(sim["totals"])
    low = client.get("/api/city/demand?source=sim&k=2").json()
    assert low["k"] == 2
    high = client.get("/api/city/demand?source=sim&k=100").json()
    assert high["totals"]["cells_hidden"] > sim["totals"]["cells_hidden"]
    assert high["totals"]["cells_shown"] == 0


def test_the_real_log_never_shows_a_group_below_five(client, tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch)
    real = client.get("/api/city/demand?source=real&k=2").json()
    assert real["source"] == "real"
    assert real["simulated"] is False
    assert real["k_min"] == 5
    assert real["k"] == 5  # asked for 2, answered with 5
    assert all(f["properties"]["requests"] >= 5 for f in real["cells"]["features"])
    csv = client.get("/api/city/export/demand.csv?source=real&k=2")
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]


def test_the_city_page_data_exports_and_languages(client):
    for lang in ("kk", "ru", "en"):
        city = client.get(f"/api/city/demand?lang={lang}").json()
        assert city["categories"], lang
        assert all(c["label"] for c in city["categories"]), lang
    quality = client.get("/api/city/quality").json()
    assert quality["cells"]["features"]
    for name, media in (
        ("demand.csv", "text/csv"),
        ("demand.geojson", "geo+json"),
        ("quality.csv", "text/csv"),
        ("quality.geojson", "geo+json"),
    ):
        res = client.get(f"/api/city/export/{name}")
        assert res.status_code == 200, name
        assert media in res.headers["content-type"], name
    assert client.get("/api/city/export/other.csv").status_code == 404
    assert client.get("/api/city/nonsense").status_code == 404
    assert client.get("/api/districts").json()["features"]


def test_every_export_and_the_district_outlines_carry_the_osm_attribution(client):
    for name in ("demand.geojson", "quality.geojson"):
        res = client.get(f"/api/city/export/{name}")
        body = res.json()
        assert body["features"], name
        assert "© OpenStreetMap contributors" in body["attribution"], name
        assert "Open Database License (ODbL)" in body["attribution"], name
        assert "https://www.openstreetmap.org/copyright" in body["attribution"], name
        assert body["license"] == "ODbL-1.0", name
    for name in ("demand.csv", "quality.csv"):
        text = client.get(f"/api/city/export/{name}").text
        notice, header, *rows = text.splitlines()
        assert notice.startswith("# Contains information from OpenStreetMap"), name
        assert "© OpenStreetMap contributors" in notice, name
        assert header.startswith("cell,lat,lon,"), name  # the table itself is unchanged
        assert rows, name
        assert not any(r.startswith("#") for r in rows), name

    districts = client.get("/api/districts")
    assert "geo+json" in districts.headers["content-type"]
    outlines = districts.json()
    assert outlines["features"]
    assert "© OpenStreetMap contributors" in outlines["attribution"]
    assert outlines["license"] == "ODbL-1.0"
    assert "Есіл ауданы" in {
        f["properties"]["name"] for f in outlines["features"]
    }  # the data itself is unchanged


def test_the_data_page_counts_the_sources(client):
    data = client.get("/api/data?lang=ru").json()
    assert data["sources"]["osm"] > 1000
    assert data["coverage"]["places"] > 1000
    assert 0 < data["coverage"]["hours"] < 100


def test_the_data_page_has_a_card_per_source_with_its_links(client):
    data = client.get("/api/data?lang=ru").json()
    cards = {c["id"]: c for c in data["cards"]}
    assert {
        "osm",
        "overture",
        "wikidata",
        "wikipedia",
        "wikivoyage",
        "sites",
        "museums",
        "gov",
    } <= set(cards)
    assert {"met", "kazhydromet", "gtfs", "afisha", "valhalla", "basemap"} <= set(cards)
    assert len(cards) == len(data["cards"])
    for card in data["cards"]:
        assert card["group"] in {"places", "weather", "moving", "city"}
        assert all(u.startswith("https://") for u in card["links"])
        assert all(lic["label"] and lic["url"].startswith("https://") for lic in card["licences"])
        assert (card["count"] is None) == (card["unit"] is None)
    # the counts are those of the sources block, not a second count
    assert cards["osm"]["count"] == data["sources"]["osm"] > 1000
    assert (cards["gtfs"]["unit"], cards["afisha"]["unit"]) == ("stops", "events")
    assert cards["gtfs"]["count"] > 0
    assert cards["afisha"]["count"] > 0
    assert cards["met"]["count"] is None


def test_the_source_cards_carry_the_licence_duties(client):
    """docs/licensing.md: the ODbL notice links the OSM copyright page, Overture's licences are named per
    contributor with the Foursquare notice, Open-Meteo is linked next to its data, Wikipedia names CC BY-SA."""
    cards = {c["id"]: c for c in client.get("/api/data?lang=en").json()["cards"]}

    def licences(card_id):
        return {lic["label"]: lic["url"] for lic in cards[card_id]["licences"]}

    assert licences("osm") == {"ODbL 1.0": "https://www.openstreetmap.org/copyright"}
    overture = licences("overture")
    assert set(overture) == {"CDLA-Permissive-2.0", "Apache-2.0 · Foursquare", "CC0 1.0"}
    assert (
        overture["Apache-2.0 · Foursquare"]
        == "https://opensource.foursquare.com/places-notice-txt/"
    )
    assert "https://open-meteo.com" in cards["openmeteo"]["links"]
    assert set(licences("wikipedia")) == set(licences("wikivoyage")) == {"CC BY-SA 4.0"}
    assert {"CC BY 4.0", "NLOD 2.0"} == set(licences("met"))


def test_the_valhalla_card_links_the_public_server_terms_only_for_the_public_server(
    client, monkeypatch
):
    def links():
        cards = client.get("/api/data?lang=ru").json()["cards"]
        return next(c for c in cards if c["id"] == "valhalla")["links"]

    monkeypatch.delenv("WALKS_VALHALLA_URL", raising=False)
    assert any("fossgis.de" in u for u in links())
    monkeypatch.setenv("WALKS_VALHALLA_URL", "http://127.0.0.1:8002/route")
    assert not any("fossgis.de" in u for u in links())


def test_the_data_page_counts_places_by_district_in_the_asked_language(client):
    ru = client.get("/api/data?lang=ru").json()["coverage"]["districts"]
    kk = client.get("/api/data?lang=kk").json()["coverage"]["districts"]
    assert len(ru) == len(kk) >= 5
    assert [r["places"] for r in ru] == [r["places"] for r in kk]
    assert (
        sum(r["places"] for r in ru) <= client.get("/api/data?lang=ru").json()["coverage"]["places"]
    )
    assert all(0 <= r["hours"] <= 100 for r in ru)
    assert "Есиль" in {r["label"] for r in ru}
    assert not any(r["label"].endswith("ауданы") for r in kk)


def test_the_explain_lines_say_whose_weather_it_is(client):
    answer = _turn(client, "Тихое место с кофе и розеткой")
    sections = answer["explain"]["sections"]
    setting = next(s for s in sections if s["id"] == "setting")
    assert any("Погода" in line for line in setting["lines"])


# ---- memory: residents' marks and the opt-in profile -------------------------------------------------


def test_a_mark_is_one_anonymous_row_and_unknown_things_are_refused(client, tmp_path):
    first = _turn(client, "Тихое место с кофе и розеткой")
    poi = first["turn"]["places"][0]["id"]
    ok = client.post("/api/report", json={"poi_id": poi, "signal": "has_socket"})
    assert ok.json() == {"ok": True}
    rows = json.loads((tmp_path / "marks.json").read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert set(rows[0]) == {
        "poi_id",
        "signal",
        "date",
        "weekday",
        "hour_bucket",
    }  # no user, no coords
    assert rows[0]["signal"] == "has_socket"
    unknown = {"poi_id": "no/such", "signal": "has_socket"}
    assert client.post("/api/report", json=unknown).status_code == 422
    assert client.post("/api/report", json={"poi_id": poi, "signal": "bogus"}).status_code == 422
    extra = {"poi_id": poi, "signal": "was_open", "user": "x"}
    assert client.post("/api/report", json=extra).status_code == 422
    assert len(json.loads((tmp_path / "marks.json").read_text(encoding="utf-8"))) == 1


def test_the_profile_is_off_by_default_remembered_listed_and_forgotten(client, tmp_path):
    profiles = tmp_path / "profiles"
    off = _turn(
        client, "Кафе с ребёнком"
    )  # profile_on is false: nothing is read, nothing is offered
    assert off["remember"] == []
    assert not profiles.exists()
    on = _turn(client, "Кафе с ребёнком", profile_on=True)
    assert [c["key"] for c in on["remember"]] == ["with_kids"]
    assert not profiles.exists()  # saved only on an action
    view = client.post("/api/profile", json={"action": "remember", "key": "with_kids"}).json()
    uid = view["id"]
    assert uid
    assert [i["key"] for i in view["items"]] == ["with_kids"]
    assert len(list(profiles.glob("*.json"))) == 1
    stored = json.loads(next(profiles.glob("*.json")).read_text(encoding="utf-8"))
    assert stored["with_kids"] is True
    again = _turn(client, "Кафе", profile_on=True, profile_id=uid)
    assert "ребёнком" in json.dumps(again["turn"], ensure_ascii=False)  # what the profile applied
    assert client.get(f"/api/profile?id={uid}").json()["items"]
    assert (
        client.post("/api/profile", json={"id": uid, "action": "forget_all"}).json()["id"] is None
    )
    assert not list(profiles.glob("*.json"))


def test_the_profile_deletes_single_items_and_notes_visits_and_likes(client, tmp_path):
    first = _turn(client, "Тихое кафе с ребёнком")
    poi = first["turn"]["places"][0]["id"]
    uid = None
    for body in (
        {"action": "remember", "key": "quiet"},
        {"action": "remember", "key": "with_kids"},
    ):
        uid = client.post("/api/profile", json={"id": uid, **body}).json()["id"]
    client.post("/api/profile", json={"id": uid, "action": "visit", "poi_id": poi})
    like = {"id": uid, "action": "like", "poi_id": poi}
    view = client.post("/api/profile", json=like).json()
    stored = json.loads(next((tmp_path / "profiles").glob("*.json")).read_text(encoding="utf-8"))
    assert stored["quiet"] is True
    assert stored["with_kids"] is True
    assert len(stored["visited"]) == 1
    assert sum(stored["liked"].values()) == 1
    assert {"quiet", "with_kids"} <= {i["key"] for i in view["items"]}
    forget = {"id": uid, "action": "forget", "key": "quiet"}
    view = client.post("/api/profile", json=forget).json()
    stored = json.loads(next((tmp_path / "profiles").glob("*.json")).read_text(encoding="utf-8"))
    assert stored["quiet"] is False
    assert stored["with_kids"] is True
    assert "quiet" not in {i["key"] for i in view["items"]}
    nonsense = {"id": uid, "action": "remember", "key": "nonsense"}
    assert client.post("/api/profile", json=nonsense).status_code == 422
    nowhere = {"id": uid, "action": "visit", "poi_id": "no/such"}
    assert client.post("/api/profile", json=nowhere).status_code == 422


def _save(client, uid=None, **form):
    body = {"id": uid, "action": "save", "form": form}
    return client.post("/api/profile", json=body)


def _stored(tmp_path) -> dict:
    return json.loads(next((tmp_path / "profiles").glob("*.json")).read_text(encoding="utf-8"))


def test_the_form_saves_every_field_and_the_view_offers_its_pickers(client, tmp_path):
    view = client.get(
        "/api/profile"
    ).json()  # nothing stored: the form is empty, the pickers are there
    assert view["id"] is None
    assert view["form"]["about"] == ""
    assert view["form"]["liked"] == view["form"]["avoid"] == []
    assert view["about_max"] == 500
    kinds = {c["key"]: c["name"] for c in view["categories"]}
    assert kinds["bar_nightlife"] == "бар / ночная жизнь"
    assert "other" not in kinds
    assert client.get("/api/profile?lang=en").json()["categories"][0]["name"] == "cafe"
    saved = _save(
        client,
        with_kids=True,
        kids_age_bands=["4-7"],
        halal=True,
        budget="low",
        mobility="stroller",
        walk_pace="slow",
        liked=["park_garden", "cafe"],
        avoid=["bar_nightlife"],
        about="  живу на левом берегу, не пью кофе  ",
    ).json()
    uid = saved["id"]
    stored = _stored(tmp_path)
    assert stored["about"] == "живу на левом берегу, не пью кофе"
    assert stored["avoid"] == ["bar_nightlife"]
    assert set(stored["liked"]) == {"park_garden", "cafe"}
    assert saved["form"]["about"] == stored["about"]
    assert saved["form"]["liked"] == ["cafe", "park_garden"]  # the form's own order
    assert saved["form"]["kids_age_bands"] == ["4-7"]
    keys = {i["key"] for i in saved["items"]}
    assert {"about", "avoid:bar_nightlife", "liked:cafe", "with_kids"} <= keys
    again = client.get(f"/api/profile?id={uid}").json()
    assert again["form"] == saved["form"]


def test_a_childs_age_is_refused_without_with_kids_and_cleared_when_the_flag_goes(client, tmp_path):
    assert _save(client, with_kids=False, kids_age_bands=["4-7"]).status_code == 422
    assert not (tmp_path / "profiles").exists()
    uid = _save(client, with_kids=True, kids_age_bands=["8-12"]).json()["id"]
    assert _stored(tmp_path)["kids_age_bands"] == ["8-12"]
    assert _stored(tmp_path)["kids_age_band"] == "8-12"
    view = _save(client, uid, with_kids=False, kids_age_bands=[]).json()
    assert _stored(tmp_path)["kids_age_band"] is None
    assert _stored(tmp_path)["kids_age_bands"] == []
    assert view["form"]["kids_age_bands"] == []
    forgot = client.post("/api/profile", json={"id": uid, "action": "forget", "key": "with_kids"})
    assert forgot.status_code == 422  # the flag is already off: there is nothing to forget
    uid = _save(client, uid, with_kids=True, kids_age_bands=["0-3"]).json()["id"]
    client.post("/api/profile", json={"id": uid, "action": "forget", "key": "with_kids"})
    assert _stored(tmp_path)["kids_age_band"] is None  # forgetting the flag takes the age with it
    assert _stored(tmp_path)["kids_age_bands"] == []


@pytest.mark.parametrize(
    "form",
    [
        {"about": "я" * 501},
        {"kids_age_bands": ["5-6"], "with_kids": True},
        {"liked": ["cafe"], "avoid": ["cafe"]},
        {"liked": ["other"]},
        {"avoid": ["no_such_kind"]},
        {"budget": "free"},
        {"mobility": "bike"},
        {"extra_field": 1},
    ],
)
def test_the_form_refuses_what_it_does_not_offer(client, tmp_path, form):
    assert _save(client, **form).status_code == 422
    assert not (tmp_path / "profiles").exists()


def test_about_is_deleted_by_forget_all_and_by_its_own_item(client, tmp_path):
    uid = _save(client, about="хожу с собакой").json()["id"]
    assert _stored(tmp_path)["about"] == "хожу с собакой"
    view = client.post("/api/profile", json={"id": uid, "action": "forget", "key": "about"}).json()
    assert view["form"]["about"] == ""
    assert "about" not in {i["key"] for i in view["items"]}
    _save(client, uid, about="хожу с собакой")
    assert (
        client.post("/api/profile", json={"id": uid, "action": "forget_all"}).json()["id"] is None
    )
    assert not list((tmp_path / "profiles").glob("*.json"))
    assert client.get(f"/api/profile?id={uid}").json()["form"]["about"] == ""


def test_saving_the_form_keeps_the_like_counts_of_kinds_that_stay(client, tmp_path):
    first = _turn(client, "Кафе")
    poi = first["turn"]["places"][0]["id"]
    uid = client.post("/api/profile", json={"action": "like", "poi_id": poi}).json()["id"]
    client.post("/api/profile", json={"id": uid, "action": "like", "poi_id": poi})
    kind = next(iter(_stored(tmp_path)["liked"]))
    _save(client, uid, liked=[kind])
    assert _stored(tmp_path)["liked"][kind] == 2
    _save(client, uid, liked=[])
    assert _stored(tmp_path)["liked"] == {}
