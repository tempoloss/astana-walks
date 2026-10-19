"""The data behind the map's weather effects: the wind direction, the sky cover and the falling precipitation read off the
airport report (walks.metar) and MET Norway's series (walks.metno), what walks.weather carries of them, the computed
sun (walks.sun) and `GET /api/conditions` (walks.conditions). Reports are real strings of UACC."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import MET_RECORDED, MetServer, met_doc
from starlette.testclient import TestClient

from tests.test_weather_obs import _fetch, _routes
from walks import conditions, kazhydromet, metar, metno, sun
from walks import weather as wx
from walks.hours import TZ
from walks.models import WeatherWarning
from web.server import create_app

DAY = datetime(2026, 10, 20, 12, tzinfo=UTC)  # a report names only its day of the month
NOW = datetime(2026, 10, 17, 12, 30, tzinfo=UTC)  # 17:30 in Astana


def _obs(raw: str, now: datetime = DAY) -> metar.Observation:
    obs = metar.parse_metar(raw, now)
    assert obs is not None, raw
    return obs


# ------------------------------------------------------------------------------------------- the report


@pytest.mark.parametrize(
    ("raw", "direction", "cloud"),
    [
        ("METAR UACC 171200Z 30002MPS 9999 SCT026CB 10/05 Q1025 NOSIG", 300, "SCT"),
        ("UACC 151900Z 21011MPS 1500 SN BLSN SCT010 OVC026 M10/M12 Q1015 NOSIG", 210, "OVC"),
        ("UACC 171400Z VRB01MPS 3100 BR FU BKN009 01/M01 Q1030", None, "BKN"),
        ("UACC 171200Z 00000MPS 0800 MIFG SKC 05/04 Q1020", None, "CLR"),
        ("UACC 241700Z 10003MPS 0600 FZFG VV002 M00/M00 Q1029", 100, "VV"),
        ("UACC 171200Z 36004MPS CAVOK 10/05 Q1020", 0, "CLR"),
        ("SPECI UACC 161943Z 24003MPS 4500 FU", 240, None),  # a report that says nothing of the sky
    ],
)
def test_the_wind_direction_and_the_sky_of_a_report(raw, direction, cloud):
    obs = _obs(raw)
    assert (obs.wind_from_deg, obs.cloud) == (direction, cloud)


def test_clouds_after_the_temperature_group_are_the_forecast_not_the_sky():
    obs = _obs("UACC 171200Z 30002MPS 9999 FEW030 10/05 Q1025 BECMG OVC010")
    assert obs.cloud == "FEW"


@pytest.mark.parametrize(
    ("raw", "falling"),
    [
        ("UACC 091900Z 01006G11MPS 5000 -SN DRSN BKN011 OVC021 M22/M25 Q1030 NOSIG", ("snow", 1)),
        ("UACC 151900Z 21011MPS 1500 SN BLSN SCT010 M10/M12 Q1015", ("snow", 2)),
        ("UACC 062100Z 23009MPS 8000 -SHSN BLSN SCT026CB M03/M07 Q1022 RESHSN", ("snow", 1)),
        (
            "UACC 141754Z 25011G17MPS 1800 FZRA SN BKN006 M01/M02 Q0998",
            ("snow", 2),
        ),  # a mix is snow
        ("METAR UACC 171200Z 27020G30KT 4000 +TSRA BKN020CB 25/18 Q1010", ("rain", 3)),
        ("METAR UACC 140630Z 24003MPS 3000 RA BKN010 08/07 Q1010", ("rain", 2)),
        ("METAR UACC 140630Z 24003MPS 3000 -DZ BKN010 08/07 Q1010", ("rain", 1)),
        (
            "UACC 061230Z 25007MPS 9999 DRSN BKN010 OVC026 M03/M05 Q1026",
            None,
        ),  # drifting: not falling
        ("UACC 171400Z VRB01MPS 3100 BR FU BKN009 01/M01 Q1030", None),
        ("METAR UACC 171200Z 30002MPS 9999 SCT026CB 10/05 Q1025 NOSIG", None),
        (
            "METAR UACC 171200Z 30002MPS 9999 BKN026 10/05 Q1025 TEMPO RA",
            None,
        ),  # a trend is not now
        (
            "UACC 171200Z 30002MPS 9999 IC SKC M30/M32 Q1040",
            None,
        ),  # diamond dust under a clear sky is no snowfall
        (
            "UACC 171200Z 30002MPS 9999 -SN SKC M10/M12 Q1040",
            None,
        ),  # precipitation needs cloud: a contradiction
        ("UACC 171200Z 30002MPS 9999 -SN FEW030 M10/M12 Q1040", ("snow", 1)),
        ("UACC 180300Z 26002MPS 0800 R22/0800 FG VV002 03/03 Q1029", None),  # fog is not rain
        ("UACC 180500Z 24003MPS 3000 BR OVC002 05/05 Q1030", None),  # mist is not rain
        ("METAR UACC 171200Z 30002MPS 9999 VCSH BKN026 10/05 Q1025", None),  # in the vicinity
    ],
)
def test_what_falls_at_the_station_now(raw, falling):
    assert metar.falling_now(_obs(raw)) == falling


# ------------------------------------------------------------------------------------------- the forecast


def test_metno_gives_the_direction_and_the_cloud_cover_of_its_entry():
    entries = metno.parse(MET_RECORDED["body"])
    fc = metno.pick(entries, datetime(2026, 10, 17, 15, 5, tzinfo=UTC))
    assert fc is not None
    assert (fc.wind_from_deg, fc.cloud_pct) == (344, 64.1)


def test_metno_without_a_wind_speed_has_no_direction():
    body = {
        "properties": {
            "timeseries": [
                {
                    "time": "2026-10-17T15:00:00Z",
                    "data": {
                        "instant": {
                            "details": {"air_temperature": 1.0, "wind_from_direction": 90.0}
                        }
                    },
                }
            ]
        }
    }
    fc = metno.pick(metno.parse(body), datetime(2026, 10, 17, 15, 5, tzinfo=UTC))
    assert fc is not None
    assert (fc.wind_from_deg, fc.cloud_pct) == (None, None)


# ------------------------------------------------------------------------------------------- the sun


def test_the_sun_is_at_the_horizon_at_the_computed_sunrise_and_sunset():
    for day in (date(2026, 6, 21), date(2026, 10, 17), date(2026, 12, 21)):
        rise, sset = sun.computed_sun_times(day)
        for t, morning in ((rise, True), (sset, False)):
            local = datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=TZ)
            altitude, before_noon = sun.sun_altitude(local.astimezone(UTC))
            assert altitude == pytest.approx(-0.83, abs=0.5), (day, t)
            assert before_noon is morning


def test_the_sun_at_noon_and_at_night():
    noon = sun.sun_altitude(datetime(2026, 6, 21, 7, 0, tzinfo=UTC))[0]  # 12:00 in Astana
    assert noon == pytest.approx(90 - 51.13 + 23.44, abs=2.0)
    midnight, _ = sun.sun_altitude(datetime(2026, 12, 21, 19, 0, tzinfo=UTC))  # 00:00 local
    assert midnight < -30


@pytest.mark.parametrize(
    ("altitude", "morning", "name"),
    [
        (-30, False, "night"),
        (-5, True, "dawn"),
        (-5, False, "dusk"),
        (3, True, "golden"),
        (40, False, "day"),
    ],
)
def test_the_phases_of_the_sun(altitude, morning, name):
    assert conditions.phase(altitude, morning) == name


# ------------------------------------------------------------------------------------------- the weather


def test_a_fresh_report_carries_its_wind_sky_and_precipitation():
    snow = "METAR UACC 140630Z 21011G16MPS 1500 SN BLSN SCT010 OVC026 M10/M12 Q1015 NOSIG"
    w, _ = _fetch(_routes(AVIATION_URL=snow))
    assert w.source == "metar"
    assert (w.wind_from_deg, w.wind_kmh, w.wind_gust_kmh) == (210, 39.6, 57.6)
    assert (w.cloud_pct, w.precip_now, w.precip_level) == (100.0, "snow", 2)


def test_a_report_without_a_sky_group_does_not_borrow_the_forecast_sky():
    w, _ = _fetch(_routes(AVIATION_URL="METAR UACC 140630Z 24003MPS 9999 05/03 Q1020"))
    assert (w.source, w.wind_from_deg, w.cloud_pct) == ("metar", 240, None)


def test_without_a_report_the_forecast_gives_the_wind_and_the_sky():
    hour = (wx.local_now() - timedelta(hours=5)).strftime("%Y-%m-%dT%H:00:00Z")
    doc = met_doc(hour, -2.0, 80.0, 5.0, 0.0)
    details = doc["properties"]["timeseries"][0]["data"]["instant"]["details"]
    details.update(wind_from_direction=349.6, cloud_area_fraction=87.5)
    w, _ = _fetch(_routes(), met=MetServer(doc))
    assert w.source == "met-no"
    assert (w.wind_from_deg, w.cloud_pct, w.precip_now) == (350, 87.5, "")


# ------------------------------------------------------------------------------------------- the payload


def _report(minutes_ago: int = 10, **fields) -> wx.WeatherInfo:
    observed = (NOW - timedelta(minutes=minutes_ago)).astimezone(TZ).isoformat(timespec="minutes")
    base = {
        "source": "metar",
        "observed_at": observed,
        "precip_adverse": False,
        "wind_kmh": 32.4,
        "wind_from_deg": 315,
        "cloud_pct": 100.0,
        "precip_now": "snow",
        "precip_level": 2,
    }
    return wx.make_weather(**({"temperature_c": 0.0, "apparent_c": 0.0} | base | fields))


def test_the_payload_of_a_fresh_report_with_snow(monkeypatch):
    monkeypatch.setattr(wx, "_latest", _report(wind_gust_kmh=45.0))
    out = conditions.current(NOW)
    assert out["known"] is True
    assert out["wind"] == {
        "from_deg": 315,
        "speed_ms": 9.0,
        "gust_ms": 12.5,
        "source": "metar",
        "at": "17:20",
    }
    assert out["sky"] == {"cloud_pct": 100, "source": "metar", "at": "17:20"}
    assert out["precip"] == {"kind": "snow", "level": 2, "source": "metar", "at": "17:20"}
    assert out["air"] is None
    assert out["sun"]["phase"] == "dusk"  # 17:30 on 17 October: the sun set at 17:19
    assert out["sun"]["morning"] is False


def test_nothing_known_is_not_clear_sky(monkeypatch):
    monkeypatch.setattr(wx, "_latest", None)
    out = conditions.current(NOW)
    assert out["known"] is False
    assert (out["wind"], out["sky"], out["precip"], out["air"]) == (None, None, None, None)
    assert out["sun"]["phase"]  # the sun needs no data
    monkeypatch.setattr(wx, "_latest", wx.make_weather())  # refreshed, but every request failed
    out = conditions.current(NOW)
    assert out["known"] is True
    assert (out["wind"], out["sky"], out["precip"], out["air"]) == (None, None, None, None)


def test_a_calm_or_variable_wind_draws_nothing(monkeypatch):
    for fields in ({"wind_from_deg": None}, {"wind_from_deg": 90, "wind_kmh": 0.0}):
        monkeypatch.setattr(wx, "_latest", _report(**fields))
        assert conditions.current(NOW)["wind"] is None


def test_precipitation_is_only_now_when_the_report_is_recent(monkeypatch):
    monkeypatch.setattr(wx, "_latest", _report(minutes_ago=100))
    out = conditions.current(NOW)
    assert out["precip"] is None
    assert out["wind"]["at"] == "15:50"  # a 100-minute-old report still has a wind
    monkeypatch.setattr(wx, "_latest", _report(minutes_ago=4 * 60))
    out = conditions.current(NOW)
    assert (out["wind"], out["sky"], out["precip"]) == (None, None, None)  # too old to be «now»


def test_the_forecast_gives_wind_and_sky_but_never_precipitation(monkeypatch):
    forecast = wx.make_weather(
        2.0, 2.0, 18.0, 3.0, forecast_used=True, wind_from_deg=90, cloud_pct=30.0
    )
    monkeypatch.setattr(wx, "_latest", forecast)
    out = conditions.current(NOW)
    assert out["wind"] == {
        "from_deg": 90,
        "speed_ms": 5.0,
        "gust_ms": None,
        "source": "met-no",
        "at": "",
    }
    assert out["sky"] == {"cloud_pct": 30, "source": "met-no", "at": ""}
    assert out["precip"] is None  # 3 mm of the forecast is not «falling now»


def test_the_air_flag_is_the_official_notice_or_the_stations_smoke(monkeypatch):
    monkeypatch.setattr(wx, "_latest", _report(conditions=("smog",)))
    assert conditions.current(NOW)["air"] == {"kind": "smog", "source": "metar", "at": "17:20"}
    notice = WeatherWarning(
        kind="nmu", title="НМУ", text="…", source_url="https://www.kazhydromet.kz/nmu", active=True
    )
    monkeypatch.setattr(wx, "_latest", _report(warnings=(notice,)))
    assert (
        conditions.current(NOW)["air"]
        == {
            "kind": "nmu",
            "source": "kazhydromet",
            "at": "",
            "title": "НМУ",
            "url": "https://www.kazhydromet.kz/nmu",  # the caption names the notice only together with its link
        }
    )
    tomorrow = notice.model_copy(update={"active": False})  # shown, but not the air now
    monkeypatch.setattr(wx, "_latest", _report(warnings=(tomorrow,)))
    assert conditions.current(NOW)["air"] is None
    monkeypatch.setattr(wx, "_latest", _report(conditions=("snow", "wind")))
    assert conditions.current(NOW)["air"] is None


def test_a_manual_weather_draws_nothing(monkeypatch):
    monkeypatch.setattr(wx, "_latest", wx.manual_weather(-25.0))
    out = conditions.current(NOW)
    assert (out["wind"], out["sky"], out["precip"], out["air"]) == (None, None, None, None)


# ------------------------------------------------------------------------------------------- the endpoint


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    return TestClient(create_app())


def test_the_endpoint_reads_the_refreshed_weather_and_never_the_network(client, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the endpoint went to the network")

    monkeypatch.setattr(wx, "fetch_weather", boom)
    monkeypatch.setattr(wx, "_latest", None)
    res = client.get("/api/conditions")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    assert res.json()["known"] is False
    assert set(res.json()) == {
        "known",
        "now",
        "sun",
        "wind",
        "sky",
        "precip",
        "air",
        "notice",
        "temp",
        "vis",
        "pm25",
        "hours",
    }


def test_a_scenario_is_served_only_under_the_test_switch(client, monkeypatch):
    monkeypatch.setattr(wx, "_latest", None)
    assert client.get("/api/conditions?fake=snow").json()["known"] is False
    monkeypatch.setenv("WALKS_FX_FAKE", "1")
    out = client.get("/api/conditions?fake=snow%2Bnight").json()
    assert out["precip"]["kind"] == "snow"
    assert out["wind"]["from_deg"] == 315
    assert out["sun"]["phase"] == "night"
    assert client.get("/api/conditions?fake=none").json()["wind"] is None
    assert client.get("/api/conditions?fake=haze").json()["air"]["kind"] == "nmu"


# ------------------------------------------------------------------------------------------- the weather card


def test_the_card_blocks_of_a_fresh_report(monkeypatch):
    weather = _report(
        temperature_c=-3.2, apparent_c=-7.6, visibility_m=4000, pm25=36.4, fetched_at="17:25"
    )
    monkeypatch.setattr(wx, "_latest", weather)
    out = conditions.current(NOW)
    assert out["temp"] == {"temp_c": -3, "feels_c": -8, "source": "metar", "at": "17:20"}
    assert out["vis"] == {"m": 4000, "source": "metar", "at": "17:20"}
    assert out["pm25"] == {"value": 36, "source": "open-meteo", "at": "17:25"}
    assert (out["sun"]["rise"], out["sun"]["set"]) == ("06:40", "17:19")  # computed for 17 October


def test_a_block_without_data_is_none_not_a_clear_word(monkeypatch):
    monkeypatch.setattr(wx, "_latest", wx.make_weather(forecast_used=False))
    out = conditions.current(NOW)
    assert all(out[k] is None for k in ("temp", "vis", "pm25", "hours", "wind", "sky"))
    metar_only = _report(visibility_m=None)
    monkeypatch.setattr(wx, "_latest", metar_only)
    assert conditions.current(NOW)["vis"] is None  # a report without the group says nothing


def test_the_forecast_gives_the_temperature_but_not_the_visibility(monkeypatch):
    forecast = wx.make_weather(2.0, -1.0, 18.0, 3.0, forecast_used=True, visibility_m=9999)
    monkeypatch.setattr(wx, "_latest", forecast)
    out = conditions.current(NOW)
    assert out["temp"] == {"temp_c": 2, "feels_c": -1, "source": "met-no", "at": ""}
    assert out["vis"] is None


def test_the_next_hours_come_from_the_series_in_memory_and_never_the_network(monkeypatch):
    metno.reset()
    doc = met_doc("2026-10-17T12:00:00Z", 1.0, 80.0, 3.0, 0.0)
    series = doc["properties"]["timeseries"]
    for i in range(1, 9):
        entry = json.loads(json.dumps(series[0]))
        entry["time"] = f"2026-10-17T{12 + i}:00:00Z"
        entry["data"]["instant"]["details"]["air_temperature"] = 1.0 - i
        entry["data"]["next_1_hours"] = {
            "summary": {"symbol_code": "lightsnowshowers_night" if i == 2 else "partlycloudy_day"},
            "details": {"precipitation_amount": 0.4 if i == 2 else 0.0},
        }
        series.append(entry)
    metno.forecast(0.0, NOW, 4.0, MetServer(doc))
    forecast = wx.make_weather(1.0, 1.0, 10.8, 0.0, forecast_used=True)
    monkeypatch.setattr(wx, "_latest", forecast)
    items = conditions.current(NOW)["hours"]["items"]
    assert [i["at"] for i in items] == [
        "18:00",
        "19:00",
        "20:00",
        "21:00",
        "22:00",
        "23:00",
    ]  # 12:30 UTC = 17:30
    assert items[1] == {"at": "19:00", "temp_c": -1, "precip_mm": 0.4, "sym": "snow"}
    assert items[0]["sym"] == "partly"
    assert conditions.current(NOW)["hours"]["source"] == "met-no"
    metno.reset()
    assert conditions.current(NOW)["hours"] is None  # no series, no strip


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("clearsky_day", "clear"),
        ("fair_night", "clear"),
        ("partlycloudy_night", "partly"),
        ("cloudy", "cloud"),
        ("heavyrainshowers_day", "rain"),
        ("lightrainandthunder", "thunder"),
        ("sleet", "sleet"),
        ("lightsnow", "snow"),
        ("fog", "fog"),
        ("", ""),
        (None, ""),
    ],
)
def test_the_symbols_reduce_to_what_the_card_draws(code, kind):
    assert metno.symbol_kind(code) == kind


def test_the_scenario_wind_speed_and_card_blocks(client, monkeypatch):
    monkeypatch.setenv("WALKS_FX_FAKE", "1")
    out = client.get("/api/conditions?fake=wind12%2Bday").json()
    assert out["wind"]["speed_ms"] == 12.0
    assert out["wind"]["gust_ms"] is not None
    assert client.get("/api/conditions?fake=day").json()["wind"]["speed_ms"] == 3.0
    haze = client.get("/api/conditions?fake=haze").json()
    assert haze["air"]["url"].startswith("https://www.kazhydromet.kz/")
    assert haze["pm25"]["value"] == 62
    snow = client.get("/api/conditions?fake=snow").json()
    assert (snow["temp"]["temp_c"], snow["vis"]["m"], len(snow["hours"]["items"])) == (-3, 3000, 6)
    none = client.get("/api/conditions?fake=none").json()
    assert none["temp"] is none["hours"] is None


# ------------------------------------------------------------------------------------------- what the map may draw


def test_a_wrong_precipitation_never_reaches_the_map():
    """Real nights at UACC: fog and mist (FG, BR, PRFG) under overcast, clear frosty air: none of that is rain or snow."""
    for raw in (
        "METAR UACC 180200Z 28003MPS 0800 R22/0800 PRFG OVC003 02/02 Q1029 NOSIG",
        "METAR UACC 180500Z 24003MPS 3000 BR OVC002 05/05 Q1030 NOSIG",
        "METAR UACC 180300Z 26002MPS 0800 FG VV002 03/03 Q1029 NOSIG",
        "METAR UACC 171200Z 30002MPS 9999 IC SKC M30/M32 Q1040 NOSIG",
    ):
        obs = metar.parse_metar(raw, datetime(2026, 10, 20, tzinfo=UTC))
        assert obs is not None
        assert wx._obs_fields(obs, {})["precip_now"] == "", raw


def test_a_report_of_65_minutes_is_no_longer_falling_now(monkeypatch):
    monkeypatch.setattr(wx, "_latest", _report(minutes_ago=60))
    assert conditions.current(NOW)["precip"] is not None
    monkeypatch.setattr(wx, "_latest", _report(minutes_ago=66))
    assert conditions.current(NOW)["precip"] is None


def test_the_forecast_never_makes_the_precipitation(monkeypatch):
    """3 mm in MET Norway's next hour with no observation: nothing falls on the map."""
    weather = wx.make_weather(2.0, 0.0, 18.0, 3.0, forecast_used=True, wind_from_deg=90)
    monkeypatch.setattr(wx, "_latest", weather)
    out = conditions.current(NOW)
    assert out["precip"] is None
    assert out["wind"]["source"] == "met-no"


def test_a_storm_notice_is_shown_in_its_own_words(monkeypatch):
    storm = WeatherWarning(
        kind="storm",
        title="Штормовое предупреждение ОЯ № 17 от 17 октября 2026 года",
        text="г. Астана: 18 октября ночью и утром ожидается туман.",
        source_url="https://www.kazhydromet.kz/ru/storm",
        valid_to="2026-10-18T08:00+05:00",
        active=True,
    )
    monkeypatch.setattr(wx, "_latest", _report(warnings=(storm,)))
    notice = conditions.current(NOW)["notice"]
    assert notice == {
        "text": "18 октября ночью и утром ожидается туман",
        "phenomena": ["fog"],
        "periods": ["night", "morning"],
        "until": "08:00 18.10",
        "source": "kazhydromet",
        "at": "",
        "url": "https://www.kazhydromet.kz/ru/storm",
    }
    assert conditions.current(NOW)["air"] is None  # a storm notice is not the bad-air flag
    later = storm.model_copy(update={"active": False})
    monkeypatch.setattr(wx, "_latest", _report(warnings=(later,)))
    assert conditions.current(NOW)["notice"] is None


def test_the_scenario_word_fog_is_a_storm_notice(client, monkeypatch):
    monkeypatch.setenv("WALKS_FX_FAKE", "1")
    fog = client.get("/api/conditions?fake=fog%2Bday").json()
    assert "туман" in fog["notice"]["text"]
    assert client.get("/api/conditions?fake=day").json()["notice"] is None


@pytest.mark.parametrize(
    ("text", "phenomena", "periods"),
    [
        ("18 октября ночью и утром ожидается туман", ["fog"], ["night", "morning"]),
        ("Ожидается сильный ветер 15-20 м/с, порывы до 25 м/с, днем", ["wind"], ["day"]),
        ("Гололёд и снег вечером", ["ice", "snow"], ["evening"]),
        ("В течение суток сильная жара", ["heat"], ["all"]),
        ("Ожидаются неблагоприятные метеоусловия", ["smog"], []),
        ("Грозы, град", ["thunder", "hail"], []),
        ("Сильный мороз ночью", ["cold"], ["night"]),
        ("Пыльная буря днем", ["dust"], ["day"]),
        (
            "Ожидается нечто необычное",
            [],
            [],
        ),  # no phenomenon we know: the card only names the source
        ("", [], []),
    ],
)
def test_the_notice_phenomenon_and_period_are_found_in_its_words(text, phenomena, periods):
    assert kazhydromet.classify_notice(text) == (phenomena, periods)


def test_every_phenomenon_and_period_code_has_its_words_in_three_languages():
    """The card writes the title from the codes: a code without a string would show its key to a visitor."""
    from i18n import UI

    for code, _ in kazhydromet.PHENOMENA:
        assert f"fx_ph_{code}" in UI, code
    for code, _ in kazhydromet.PERIODS:
        assert f"fx_per_{code}" in UI, code
    for key in ("fx_notice_title", "fx_notice_fmt", "fx_notice_text", "fx_and"):
        assert key in UI


def test_a_notice_of_an_unknown_phenomenon_has_no_codes(monkeypatch):
    storm = WeatherWarning(
        kind="storm",
        title="ОЯ № 4",
        text="г. Астана: ожидается нечто необычное.",
        source_url="https://www.kazhydromet.kz/ru/storm",
        valid_to="2026-10-18T08:00+05:00",
        active=True,
    )
    monkeypatch.setattr(wx, "_latest", _report(warnings=(storm,)))
    notice = conditions.current(NOW)["notice"]
    assert (notice["phenomena"], notice["periods"]) == ([], [])
    assert notice["url"] == "https://www.kazhydromet.kz/ru/storm"  # the link is what remains
