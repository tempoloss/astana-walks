"""«Мой вайб» through the web API: the form offers the facets in the page's language, saves the axis and the chips at
once, reads the free text into facets on save (the lexicon here: no network), lists and forgets the vibe like any
other stored item; «Под мой вайб» answers with the vibe's lines, or says where to set it."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from walks.presets import PRESETS
from walks.vibe_data import FACETS
from web.server import create_app

BAITEREK = PRESETS["Байтерек"]
INTRO_TEXT = "люблю тишину, книги и парки, не люблю толпы"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "WALKS_OFFLINE", "1"
    )  # no network: the lexicon reads the text, the template writes
    monkeypatch.setenv("WALKS_PROFILE_DIR", str(tmp_path / "profiles"))
    return TestClient(create_app())


def _save(client, uid=None, **form):
    return client.post("/api/profile", json={"id": uid, "action": "save", "form": form})


def _turn(client, text, uid=None, on=True) -> dict:
    body = {
        "text": text,
        "lat": BAITEREK[0],
        "lon": BAITEREK[1],
        "profile_on": on,
        "profile_id": uid,
    }
    res = client.post("/api/turn", json=body)
    assert res.status_code == 200, res.text
    return json.loads(res.text.strip().splitlines()[-1])["answer"]


def test_the_form_offers_the_facets_in_the_language_of_the_page(client):
    view = client.get("/api/profile?lang=ru").json()
    assert [f["key"] for f in view["vibe_facets"]] == list(FACETS)
    assert view["vibe_facets"][0]["name"] == "Тихо"
    assert client.get("/api/profile?lang=en").json()["vibe_facets"][2]["name"] == "Nature"
    assert view["form"]["vibe"] == {}
    assert view["form"]["vibe_text"] == ""
    assert view["vibe_text_max"] == 300


def test_the_axis_and_the_chips_are_saved_at_once_listed_and_forgotten(client):
    view = _save(client, vibe={"calm": 1.0, "nature": 1.0}).json()
    uid = view["id"]
    assert view["form"]["vibe"] == {"calm": 1.0, "nature": 1.0}
    labels = {i["key"]: i["label"] for i in view["items"]}
    assert labels["vibe"] == "ваш вайб: тихо, природа"
    view = client.post("/api/profile", json={"id": uid, "action": "forget", "key": "vibe"}).json()
    assert view["form"]["vibe"] == {}
    assert "vibe" not in {i["key"] for i in view["items"]}


def test_the_free_text_is_read_into_facets_on_save(client):
    view = _save(client, vibe_text=INTRO_TEXT).json()
    assert view["form"]["vibe_text"] == INTRO_TEXT
    assert view["form"]["vibe"]["calm"] == 1.0
    assert view["form"]["vibe"]["nature"] == 1.0
    assert "lively" not in view["form"]["vibe"]
    again = _save(client, view["id"], vibe={"lively": 1.0}, vibe_text=INTRO_TEXT).json()
    assert again["form"]["vibe"] == {
        "lively": 1.0
    }  # the same text is not read again: the chips stand


@pytest.mark.parametrize(
    "form",
    [
        {"vibe": {"cozy": 1.0}},  # no such facet
        {"vibe": {"calm": 2.0}},  # weights are 0..1
        {"vibe_text": "x" * 301},
    ],
)
def test_the_form_refuses_what_is_not_a_vibe(client, form):
    assert _save(client, **form).status_code == 422


def test_my_vibe_searches_across_kinds_with_a_line_on_every_card(client):
    uid = _save(client, vibe={"calm": 1.0, "nature": 1.0, "culture": 0.5}).json()["id"]
    answer = _turn(client, "Под мой вайб", uid)
    turn = answer["turn"]
    assert turn["kind"] == "places"
    assert turn["reply"].startswith("Под ваш вайб — ")
    assert all(p["vibe"].startswith("Под ваш вайб: ") for p in turn["places"])


def test_my_vibe_without_a_vibe_says_where_to_set_it(client):
    turn = _turn(client, "Под мой вайб", on=False)["turn"]
    assert turn["kind"] == "clarify"
    assert "«Мой вайб»" in turn["reply"]
    assert turn["places"] == []


def test_an_answer_without_a_vibe_has_no_vibe_lines(client):
    turn = _turn(client, "кофе", on=False)["turn"]
    assert turn["places"]
    assert all(p["vibe"] == "" for p in turn["places"])
