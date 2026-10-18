"""Measured weather: the airport METAR (walks.metar), the official Kazhydromet notices (walks.kazhydromet) and how
walks.weather combines them with the MET Norway forecast. Reports are real strings of UACC (aviationweather.gov / IEM);
the storm warning is the real answer of kazhydromet.kz/ajax_storm.php of 2026-10-17."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from conftest import MetServer, met_doc

from walks import kazhydromet as kh
from walks import metar
from walks import weather as wx
from walks.envcfg import offline
from walks.i18n_weather import WEATHER_STRINGS, tw

FIXTURES = Path(__file__).parent / "fixtures"
STORM_BODY = (FIXTURES / "kazhydromet_storm_astana.json").read_text(encoding="utf-8")

# ---- real UACC reports ---------------------------------------------------------------------------
SMOKE = "SPECI UACC 161943Z 24003MPS 4500 FU"
CLEAR = "METAR UACC 171200Z 30002MPS 9999 SCT026CB 10/05 Q1025 NOSIG RMK QFE737/0983"
SNOW_BLOWING = (
    "UACC 151900Z 21011MPS 1500 R22/P2000 SN BLSN SCT010 OVC026 M10/M12 Q1015 NOSIG RMK QFE730/0974"
)
LIGHT_DRIFT = (
    "UACC 091900Z 01006G11MPS 5000 -SN DRSN BKN011 OVC021 M22/M25 Q1030 NOSIG RMK QFE741/0988"
)
DRIFT_ONLY = "UACC 061230Z 25007MPS 9999 DRSN BKN010 OVC026 M03/M05 Q1026 NOSIG RMK QFE738/0984"
LIGHT_BLOWING = "UACC 062100Z 23009MPS 8000 -SHSN BLSN SCT026CB OVC043 M03/M07 Q1022 RESHSN NOSIG"
FREEZING_FOG = (
    "UACC 241700Z 10003MPS 0600 R04/1700N FZFG VV002 M00/M00 Q1029 TEMPO 0200 FZFG VV001 RMK QBB070"
)
MIST_TEMPO = (
    "UACC 082011Z 24007MPS 2000 R22/P2000 BR OVC002 00/00 Q1014 TEMPO 0200 FZFG VV001 RMK QBB060"
)
FREEZING_RAIN = (
    "UACC 141754Z 25011G17MPS 1800 R22/P2000 FZRA SN BKN006 OVC023 M01/M02 Q0998 NOSIG RMK QBB180"
)
MIST_SMOKE = (
    "UACC 171400Z VRB01MPS 3100 BR FU BKN009 01/M01 Q1030 TEMPO 2000 BR FU BKN005 RMK QFE740/0987"
)
THUNDER_KT = "METAR UACC 171200Z 27020G30KT 4000 +TSRA BKN020CB 25/18 Q1010"
SHALLOW_FOG = "UACC 171200Z 00000MPS 0800 MIFG SKC 05/04 Q1020"

DEC = datetime(2025, 12, 16, tzinfo=UTC)


def _obs(raw: str, now: datetime = DEC) -> metar.Observation:
    obs = metar.parse_metar(raw, now)
    assert obs is not None, raw
    return obs


# ---------------------------------------------------------------------------------------------- parsing


def test_speci_with_smoke_parses_and_counts_as_smog():
    obs = _obs(SMOKE, datetime(2026, 10, 17, 12, tzinfo=UTC))
    assert obs.observed_at == datetime(
        2026, 10, 16, 19, 43, tzinfo=UTC
    )  # the day of the month picks the date
    assert (obs.wind_ms, obs.visibility_m, obs.weather) == (3.0, 4500, ("FU",))
    assert obs.temperature_c is None
    assert metar.adverse_conditions(obs) == ("smog",)


def test_a_calm_clear_report_has_no_adverse_condition():
    obs = _obs(CLEAR, datetime(2026, 10, 17, 12, 30, tzinfo=UTC))
    assert (obs.temperature_c, obs.dew_point_c, obs.wind_ms, obs.visibility_m) == (
        10.0,
        5.0,
        2.0,
        9999,
    )
    assert obs.weather == ()
    assert metar.adverse_conditions(obs) == ()
    assert obs.station == "UACC"


def test_snow_with_blowing_snow():
    obs = _obs(SNOW_BLOWING, datetime(2025, 12, 15, 20, tzinfo=UTC))
    assert (obs.temperature_c, obs.dew_point_c) == (-10.0, -12.0)
    assert obs.weather == ("SN", "BLSN")
    assert metar.adverse_conditions(obs) == (
        "snow",
        "blowing_snow",
    )  # 11 m/s is below the wind threshold


def test_light_snow_with_drifting_snow_is_not_adverse_but_the_cold_is_measured():
    obs = _obs(LIGHT_DRIFT, datetime(2025, 12, 9, 20, tzinfo=UTC))
    assert obs.weather == ("-SN", "DRSN")
    assert obs.gust_ms == 11.0
    assert (
        metar.adverse_conditions(obs) == ()
    )  # drifting snow at 5 km visibility: low drifting, light snow
    assert metar.apparent_c(obs) == pytest.approx(-29.9, abs=0.2)  # -22 °C with a 6 m/s wind


def test_drifting_snow_counts_only_when_the_visibility_is_poor():
    assert metar.adverse_conditions(_obs(DRIFT_ONLY, datetime(2025, 12, 6, 13, tzinfo=UTC))) == ()
    poor = metar.parse_metar(
        "UACC 061230Z 25007MPS 1500 DRSN M03/M05", datetime(2025, 12, 6, 13, tzinfo=UTC)
    )
    assert poor is not None
    assert metar.adverse_conditions(poor) == ("blowing_snow",)


def test_light_shower_with_blowing_snow_is_blowing_snow_not_snow():
    obs = _obs(LIGHT_BLOWING, datetime(2025, 11, 6, 22, tzinfo=UTC))
    assert obs.weather == ("-SHSN", "BLSN")
    assert metar.adverse_conditions(obs) == ("blowing_snow",)


def test_freezing_fog_and_the_trend_group_is_not_the_present_weather():
    fog = _obs(FREEZING_FOG, datetime(2025, 11, 24, 18, tzinfo=UTC))
    assert (fog.visibility_m, fog.weather, fog.temperature_c) == (600, ("FZFG",), 0.0)
    assert metar.adverse_conditions(fog) == ("fog",)
    mist = _obs(MIST_TEMPO, datetime(2025, 11, 8, 21, tzinfo=UTC))
    assert mist.weather == ("BR",)  # the TEMPO FZFG is a forecast
    assert metar.adverse_conditions(mist) == (
        "fog",
    )  # mist at 2000 m limits the visibility as fog does


def test_mist_with_smoke_at_3_km_is_smog_not_fog_and_shallow_fog_is_ignored():
    obs = _obs(MIST_SMOKE, datetime(2025, 11, 17, 15, tzinfo=UTC))
    assert obs.weather == ("BR", "FU")
    assert obs.wind_ms == 1.0  # VRB01MPS
    assert metar.adverse_conditions(obs) == ("smog",)
    shallow = _obs(SHALLOW_FOG, datetime(2026, 10, 17, 13, tzinfo=UTC))
    assert shallow.weather == ("MIFG",)
    assert metar.adverse_conditions(shallow) == ()


def test_freezing_rain_with_snow_and_a_gust():
    obs = _obs(FREEZING_RAIN, datetime(2025, 12, 14, 18, tzinfo=UTC))
    assert (obs.wind_ms, obs.gust_ms) == (11.0, 17.0)
    assert metar.adverse_conditions(obs) == ("freezing_rain", "snow", "wind")


def test_thunderstorm_and_the_knots_unit():
    obs = _obs(THUNDER_KT, datetime(2026, 10, 17, 13, tzinfo=UTC))
    assert obs.wind_ms == pytest.approx(10.29, abs=0.01)
    assert obs.gust_ms == pytest.approx(15.43, abs=0.01)
    assert metar.adverse_conditions(obs) == ("thunder", "rain", "wind")
    assert metar.apparent_c(obs) is not None
    assert obs.temperature_c == 25.0


def test_the_day_of_the_month_rolls_over_the_month_and_never_points_at_the_future():
    obs = _obs("UACC 312350Z 00000MPS 9999 01/00", datetime(2026, 11, 1, 0, 20, tzinfo=UTC))
    assert obs.observed_at == datetime(2026, 10, 31, 23, 50, tzinfo=UTC)
    assert obs.fresh(datetime(2026, 11, 1, 0, 20, tzinfo=UTC))
    assert metar.parse_metar("UACC 321200Z 00000MPS 9999 01/00", DEC) is None  # no such day
    assert metar.parse_metar("not a report", DEC) is None


def test_a_report_is_fresh_for_three_hours():
    obs = _obs(CLEAR, datetime(2026, 10, 17, 12, 30, tzinfo=UTC))
    base = obs.observed_at
    assert obs.fresh(base + timedelta(hours=2, minutes=59))
    assert not obs.fresh(base + timedelta(hours=3, minutes=1))


def test_feed_parsers_read_the_raw_listing_and_the_iem_csv_newest_first():
    now = datetime(2026, 10, 17, 12, 30, tzinfo=UTC)
    raw = f"METAR UACC 171130Z 31004MPS 9999 SCT026CB 10/05 Q1025 NOSIG RMK QFE737/0983\n{CLEAR}\n"
    reports = metar.parse_feed(raw, now)
    assert [o.observed_at.hour * 100 + o.observed_at.minute for o in reports] == [1200, 1130]
    csv = "station,valid,metar\nUACC,2026-10-17 11:30,UACC 171130Z 31004MPS 9999 10/05 Q1025=\nUACC,2026-10-17 12:00,UACC 171200Z 30002MPS 9999 10/05 Q1025\n"
    assert next(o.raw for o in metar.parse_feed(csv, now)).startswith("UACC 171200Z")
    assert metar.parse_feed("", now) == []


def _opener(
    routes: dict[str, str | Exception], calls: list | None = None, met: MetServer | None = None
):
    ordered = sorted(routes, key=len, reverse=True)  # the longest prefix wins

    def opener(req, timeout):
        if calls is not None:
            calls.append((req.get_method(), req.full_url, req.data))
        if met is not None and "api.met.no" in req.full_url:
            return met(req, timeout)
        for prefix in ordered:
            if req.full_url.startswith(prefix):
                body = routes[prefix]
                if isinstance(body, Exception):
                    raise body
                return io.BytesIO(body.encode("utf-8"))
        raise urllib.error.URLError("no route")

    return opener


def test_iem_takes_over_when_aviationweather_is_down_or_empty():
    now = datetime(2026, 10, 17, 12, 30, tzinfo=UTC)
    csv = "station,valid,metar\nUACC,2026-10-17 12:00,UACC 171200Z 30002MPS 9999 10/05 Q1025\n"
    down = _opener({metar.AVIATION_URL: urllib.error.URLError("down"), metar.IEM_URL: csv})
    got = metar.fetch_observation(4.0, down, now_utc=now)
    assert got is not None
    assert got.source_url == metar.IEM_URL
    empty = _opener({metar.AVIATION_URL: "", metar.IEM_URL: csv})
    assert metar.fetch_observation(4.0, empty, now_utc=now) is not None
    nothing = _opener({metar.AVIATION_URL: "", metar.IEM_URL: "station,valid,metar\n"})
    assert metar.fetch_observation(4.0, nothing, now_utc=now) is None


# ---------------------------------------------------------------------------------------------- Kazhydromet

TITLE_1 = "Штормовое предупреждение ОЯ № 17 от 17 октября 2026 года с 20 ч. 17 октября до 08 ч. 18 октября 2026 г."
TITLE_2 = "Штормовое  предупреждение ОЯ № 17 от 17 октября 2026 года с 20 ч. 17 октября 2026 г до 20 ч. 18 октября 2026 г."
NMU_17 = "18&nbsp;октября неблагоприятные метеорологические условия ожидаются в городах Костанай, Павлодар, Караганда, Жезказган, Балхаш, Темиртау,&nbsp;Актобе, Алматы, Астана"
NMU_16 = "17 октября неблагоприятные метеорологические условия ожидаются в городах Актобе, Алматы, ночью в городах Костанай, Караганды, Темиртау, Астана."
NMU_NONE = "05 октября неблагоприятные метеорологические условия не ожидаются."
NMU_OTHERS = (
    "08 октября неблагоприятные метеорологические условия ожидаются в городах Алматы и Атырау."
)


def nmu_page(published: str, sentence: str) -> str:
    return (
        '<h1 class="weather-pageTitle">Ежедневный бюллетень состояния воздушного бассейна (НМУ)</h1>'
        f'<div class="nature-time"><span>Опубликовано {published} </span></div>'
        f'<div class="calendar_page_content">\n<p>{sentence}</p>\n</div>'
    )


def test_storm_window_from_the_title():
    (a,) = kh.parse_window(TITLE_1)
    assert a == (datetime(2026, 10, 17, 20), datetime(2026, 10, 18, 8))
    (b,) = kh.parse_window(TITLE_2)
    assert b == (datetime(2026, 10, 17, 20), datetime(2026, 10, 18, 20))
    assert kh.parse_window("предупреждение без периода", date(2026, 10, 17)) == (
        (datetime(2026, 10, 17), datetime(2026, 10, 18)),
    )
    assert kh.parse_window("предупреждение без периода") == ()


def test_the_real_storm_feed_of_astana():
    (notice,) = kh.parse_storm(STORM_BODY)
    assert notice.kind == "storm"
    assert notice.text == "г. Астана: 18 октября ночью и утром ожидается туман."
    assert notice.title.startswith("Штормовое предупреждение ОЯ № 17 от 17 октября 2026 года")
    assert notice.source_url == kh.STORM_PAGE
    assert notice.attachment_url.endswith(".pdf")
    assert notice.windows == ((datetime(2026, 10, 17, 20), datetime(2026, 10, 18, 8)),)
    assert kh.parse_storm('{"items": []}') == []
    other = json.dumps(
        {
            "items": [
                {
                    "name": "x",
                    "regionId": 4,
                    "regions": [{"id": 4}],
                    "myRegions": "Акмолинская область",
                }
            ]
        }
    )
    assert kh.parse_storm(other) == []


def test_nmu_of_tomorrow_lists_astana_for_the_whole_day():
    target, notice = kh.parse_nmu(nmu_page("17.10.2026", NMU_17), kh.NMU_PAGE)
    assert target == date(2026, 10, 18)
    assert notice is not None
    assert notice.windows == ((datetime(2026, 10, 18), datetime(2026, 10, 19)),)
    assert notice.issued == "17.10.2026"
    assert notice.text.startswith("18 октября неблагоприятные")
    assert notice.text.endswith(
        "Алматы, Астана"
    )  # verbatim, the no-break spaces turned into spaces


def test_nmu_named_after_night_covers_the_night_hours_only():
    target, notice = kh.parse_nmu(nmu_page("16.10.2026", NMU_16), kh.NMU_PAGE)
    assert target == date(2026, 10, 17)
    assert notice is not None
    assert notice.windows == (
        (datetime(2026, 10, 17, 0), datetime(2026, 10, 17, 8)),
        (datetime(2026, 10, 17, 20), datetime(2026, 10, 18, 0)),
    )


def test_nmu_without_astana_or_not_expected_gives_no_notice_but_the_day():
    assert kh.parse_nmu(nmu_page("04.10.2026", NMU_NONE)) == (date(2026, 10, 5), None)
    assert kh.parse_nmu(nmu_page("07.10.2026", NMU_OTHERS)) == (date(2026, 10, 8), None)
    assert kh.parse_nmu("<html>no bulletin</html>") == (None, None)
    december = nmu_page(
        "31.12.2026", "01 января неблагоприятные метеорологические условия ожидаются в Астана"
    )
    assert kh.parse_nmu(december)[0] == date(2027, 1, 1)


def test_notices_are_active_inside_their_window_and_shown_a_day_ahead():
    (storm,) = kh.parse_storm(STORM_BODY)
    assert (
        kh.warnings_at([storm], datetime(2026, 10, 17, 19, 59))[0].active is False
    )  # starts at 20:00
    assert kh.warnings_at([storm], datetime(2026, 10, 16, 19, 0)) == []  # more than a day ahead
    (w,) = kh.warnings_at([storm], datetime(2026, 10, 17, 21, 0))
    assert w.active
    assert (w.valid_from, w.valid_to) == ("2026-10-17T20:00+05:00", "2026-10-18T08:00+05:00")
    assert kh.warnings_at([storm], datetime(2026, 10, 18, 8, 0)) == []  # over


# ---------------------------------------------------------------------------------------------- weather


def _forecast(precipitation: float | None = 0.0) -> MetServer:
    """MET Norway's answer for the hour of the pinned «now» (12:00 Astana = 07:00 UTC; `evening` moves it): -22 °C,
    80 %, 5 m/s."""
    hour = (wx.local_now() - timedelta(hours=5)).strftime("%Y-%m-%dT%H:00:00Z")
    return MetServer(met_doc(hour, -22.0, 80.0, 5.0, precipitation))


FORECAST_APPARENT_C = pytest.approx(-29.2, abs=0.05)  # Steadman: -22 + 0.33 e(80 %) - 0.7 * 5 - 4
AIR_BODY = {"current": {"pm2_5": 8.0, "european_aqi": 20}}
# pinned «now» is 2026-10-14 12:00 Astana = 07:00 UTC
FRESH_SMOKE = "METAR UACC 140630Z 24003MPS 4500 FU M02/M04 Q1020 NOSIG"
STALE_SMOKE = "METAR UACC 140200Z 24003MPS 4500 FU M02/M04 Q1020 NOSIG"


def _routes(**extra: str | Exception) -> dict[str, str | Exception]:
    routes: dict[str, str | Exception] = {wx.AIR_URL: json.dumps(AIR_BODY)}
    routes.update({getattr(metar, k, None) or getattr(kh, k): v for k, v in extra.items()})
    return routes


def _fetch(routes, calls=None, clock=lambda: 0.0, met: MetServer | None = None):
    sleeps: list[float] = []
    opener = _opener(routes, calls, met or _forecast())
    w = wx.fetch_weather(opener=opener, clock=clock, sleep=sleeps.append)
    return w, sleeps


def test_a_fresh_observation_replaces_the_forecast_temperature_and_adds_the_attribution(
    monkeypatch,
):
    monkeypatch.setenv("WALKS_AIR_DEMO", "1")
    w, _ = _fetch(_routes(AVIATION_URL=FRESH_SMOKE))
    assert w.source == "metar"
    assert w.temperature_c == -2.0
    assert w.apparent_c == pytest.approx(-6.5, abs=0.5)  # not the forecast's -29.2
    assert not w.adverse  # the model's frost is not what the station measures
    assert w.conditions == ["smog"]
    assert w.air_bad
    assert w.pm25 == 8.0  # from the Open-Meteo air demo leg
    assert w.forecast_used  # the precipitation still comes from the forecast
    assert w.observed_at == "2026-10-14T11:30+05:00"
    assert w.obs_raw == FRESH_SMOKE
    assert wx.attribution(w, "ru") == "по наблюдению Казгидромета (METAR UACC), 14.10 11:30"
    assert "NOAA/NWS" in wx.source_details("ru")
    assert "NOAA" not in wx.attribution(w, "ru")


def test_smog_reads_in_the_three_languages():
    w, _ = _fetch(_routes(AVIATION_URL=FRESH_SMOKE))
    ru, kk, en = (wx.air_text(w, lang) for lang in ("ru", "kk", "en"))
    assert "дым или дымка по наблюдению метеостанции" in ru
    assert "түтін" in kk
    assert "smoke or haze" in en
    assert "Open-Meteo" not in ru
    assert "MET Norway" not in ru
    assert w.air_reason == "дым или дымка по наблюдению метеостанции"


def test_a_stale_observation_is_reported_and_the_forecast_is_used():
    w, _ = _fetch(_routes(AVIATION_URL=STALE_SMOKE))
    assert w.source == "met-no"
    assert w.obs_stale
    assert w.temperature_c == -22.0  # the forecast
    assert w.adverse  # its -29.2 °C
    assert not w.air_bad  # the smoke of five hours ago is not the air now
    assert w.observed_at == "2026-10-14T07:00+05:00"
    assert "устарело" in wx.attribution(w, "ru")
    assert "MET Norway" in wx.attribution(w, "en")


def test_no_station_report_leaves_the_forecast_untouched():
    w, _ = _fetch(_routes())
    assert (w.source, w.observed_at, w.obs_stale, w.conditions, w.warnings) == (
        "met-no",
        "",
        False,
        [],
        [],
    )
    assert w.apparent_c == FORECAST_APPARENT_C
    assert wx.attribution(w, "ru") == ""


def test_the_station_says_what_falls_the_model_how_much():
    routes = _routes(AVIATION_URL="METAR UACC 140630Z 24003MPS 9999 05/03 Q1020")
    w, _ = _fetch(routes, met=_forecast(6.0))
    assert w.source == "metar"
    assert w.precipitation_mm == 6.0  # shown
    assert not w.adverse  # but no precipitation is reported at the station


def test_rain_snow_fog_and_wind_at_the_station_are_adverse_with_their_own_words():
    rain = "METAR UACC 140630Z 24003MPS 3000 RA BKN010 08/07 Q1010"
    w, _ = _fetch(_routes(AVIATION_URL=rain))
    assert w.adverse
    assert w.reason == "дождь"
    assert wx.adverse_text(w, "en") == "rain"
    assert wx.adverse_text(w, "kk") == "жаңбыр"
    fog = "METAR UACC 140630Z 00000MPS 0400 FG VV001 01/01 Q1010"
    wx.clear_cache()
    w, _ = _fetch(_routes(AVIATION_URL=fog))
    assert w.reason == "туман"
    wind = "METAR UACC 140630Z 24012G18MPS 9999 SCT030 10/02 Q1010"
    wx.clear_cache()
    w, _ = _fetch(_routes(AVIATION_URL=wind))
    assert w.reason == "сильный ветер"
    assert w.wind_kmh == 43.2


def test_heat_is_adverse_from_35_degrees():
    assert wx.make_weather(36, 36).adverse
    assert wx.make_weather(36, 36).reason == "жара: ощущается как 36°C"
    assert not wx.make_weather(34, 34.9).adverse
    assert wx.adverse_text(wx.make_weather(36, 36), "en") == "heat: feels like 36°C"
    hot = "METAR UACC 140630Z 24003MPS CAVOK 38/10 Q1010"
    w, _ = _fetch(_routes(AVIATION_URL=hot))
    assert w.source == "metar"
    assert w.adverse
    assert "жара" in w.reason


def test_the_last_good_observation_survives_a_failing_fetch_with_its_time():
    clock = [0.0]
    routes = _routes(AVIATION_URL=FRESH_SMOKE)
    first, _ = _fetch(routes, clock=lambda: clock[0])
    clock[0] = 700.0  # the 10-minute cache has expired and the feed is down
    down = _routes(
        AVIATION_URL=urllib.error.URLError("down"), IEM_URL=urllib.error.URLError("down")
    )
    again, _ = _fetch(down, clock=lambda: clock[0])
    assert again.source == "metar"
    assert again.observed_at == first.observed_at


def test_offline_mode_makes_no_request_and_knows_no_observation(monkeypatch):
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    assert offline()

    def boom(*a, **k):
        raise AssertionError("network access in offline mode")

    w = wx.fetch_weather(opener=boom)
    assert (w.temperature_c, w.pm25, w.source, w.observed_at, w.warnings) == (
        None,
        None,
        "met-no",
        "",
        [],
    )
    assert not w.indoor_preferred


def test_a_manual_demo_weather_carries_no_observation_or_warning():
    w = wx.manual_weather(-30)
    assert (w.source, w.observed_at, w.conditions, w.warnings, w.warning) == (
        "manual",
        "",
        [],
        [],
        None,
    )
    assert w.adverse
    assert not wx.manual_weather(10, pm25=5).indoor_preferred


# ---- the warnings in the weather ----------------------------------------------------------------


@pytest.fixture
def evening(monkeypatch):
    """17 October 21:00 in Astana: the storm warning of the fixture is in force, the night НМУ too."""
    monkeypatch.setattr(wx, "local_now", lambda: datetime(2026, 10, 17, 21, 0))


def _kazhydromet_routes(**extra: str | Exception) -> dict[str, str | Exception]:
    routes = _routes(**extra)
    routes.update(
        {
            kh.ROBOTS_URL: "<html><title>404 Not Found</title></html>",
            kh.STORM_API: STORM_BODY,
            kh.NMU_PAGE: nmu_page("17.10.2026", NMU_17),
            f"{kh.NMU_PAGE}?date=2026-10-16": nmu_page("16.10.2026", NMU_16),
        }
    )
    return routes


def test_an_active_storm_warning_and_nmu_make_the_conditions_adverse(evening):
    calls: list = []
    w, sleeps = _fetch(_kazhydromet_routes(), calls)
    assert [(x.kind, x.active) for x in w.warnings] == [
        ("storm", True),
        ("nmu", True),
        ("nmu", False),
    ]
    storm = w.warning
    assert storm is not None
    assert storm.text == "г. Астана: 18 октября ночью и утром ожидается туман."
    assert storm.source_url == "https://www.kazhydromet.kz/ru/storm"
    assert w.adverse
    assert "жара" not in w.reason
    assert "штормовое предупреждение Казгидромета" in w.reason
    assert w.air_bad  # the night НМУ of 17 October
    assert "неблагоприятные метеоусловия (НМУ)" in w.air_reason
    assert w.conditions == ["storm_warning", "nmu"]
    assert len(sleeps) >= 3  # at most one request per second to Kazhydromet
    posted = [c for c in calls if c[0] == "POST"]
    assert len(posted) == 1
    assert b"region=20" in posted[0][2]
    assert wx.warning_text(storm, "en").endswith(
        "Source: Kazhydromet, https://www.kazhydromet.kz/ru/storm"
    )


def test_the_storm_warning_text_names_the_source_in_every_language(evening):
    w, _ = _fetch(_kazhydromet_routes())
    storm = w.warning
    assert storm is not None
    for lang, head in (
        ("ru", "Источник: Казгидромет"),
        ("kk", "Дереккөз: Қазгидромет"),
        ("en", "Source: Kazhydromet"),
    ):
        assert head in wx.warning_text(storm, lang)
    assert "https://www.kazhydromet.kz/ru/storm" in wx.warning_text(storm, "kk")
    assert "штормовое предупреждение" in wx.adverse_text(w, "ru")
    assert "дауыл" in wx.adverse_text(w, "kk")
    assert "storm warning" in wx.adverse_text(w, "en")
    assert "НМУ" in wx.air_text(w, "ru")


def test_tomorrows_nmu_is_shown_but_changes_nothing(monkeypatch):
    monkeypatch.setattr(wx, "local_now", lambda: datetime(2026, 10, 17, 12, 0))
    routes = _kazhydromet_routes()
    routes[kh.STORM_API] = '{"items": []}'
    w, _ = _fetch(routes)
    assert [(x.kind, x.active) for x in w.warnings] == [("nmu", False), ("nmu", False)]
    assert not w.air_bad
    assert w.conditions == []


def test_robots_txt_that_forbids_the_feed_stops_the_request(evening):
    calls: list = []
    routes = _kazhydromet_routes()
    routes[kh.ROBOTS_URL] = "User-agent: *\nDisallow: /ajax_storm.php\n"
    w, _ = _fetch(routes, calls)
    assert w.warnings == []
    assert not [c for c in calls if c[0] == "POST"]  # the disallowed page is never requested
    assert any(c[1] == kh.ROBOTS_URL for c in calls)


def test_a_dead_kazhydromet_leaves_the_weather_as_it_was(evening):
    w, _ = _fetch(_routes())
    assert w.warnings == []
    assert w.apparent_c == FORECAST_APPARENT_C
    assert w.adverse  # the forecast frost


def test_notices_are_cached_for_fifteen_minutes(evening):
    calls: list = []
    clock = [0.0]
    routes = _kazhydromet_routes()

    def kazhydromet_calls() -> int:
        return len([c for c in calls if c[1].startswith(kh.BASE)])

    _fetch(routes, calls, clock=lambda: clock[0])
    first = kazhydromet_calls()
    assert first == 4  # robots.txt, the storm feed, the bulletin, the bulletin of yesterday
    clock[0] = 800.0
    _fetch(routes, calls, clock=lambda: clock[0])
    assert kazhydromet_calls() == first
    clock[0] = 901.0
    _fetch(routes, calls, clock=lambda: clock[0])
    assert len([c for c in calls if c[1] == kh.STORM_API]) == 2


# ---- strings ---------------------------------------------------------------------------------------


def test_every_weather_string_has_the_same_fields_in_three_languages():
    import re

    for key, entry in WEATHER_STRINGS.items():
        assert len(entry) == 3, key
        assert all(entry), key
        fields = [set(re.findall(r"{(\w+)}", text)) for text in entry]
        assert fields[0] == fields[1] == fields[2], key


def test_every_token_has_wording():
    for token in (*wx.WEATHER_TOKENS, *wx.AIR_TOKENS):
        for lang in ("kk", "ru", "en"):
            assert tw(f"wx_c_{token}", lang)


def test_the_cli_prints_the_observation_and_every_notice_with_its_link(evening):
    from walks.cli import _station_lines

    routes = _kazhydromet_routes(
        AVIATION_URL="METAR UACC 171530Z 24003MPS 4500 FU M02/M04 Q1020 NOSIG"
    )
    w, _ = _fetch(routes)
    text = "\n".join(_station_lines(w))
    assert "METAR UACC 171530Z 24003MPS 4500 FU" in text
    assert "по наблюдению Казгидромета (METAR UACC), 17.10 20:30" in text
    assert "NOAA/NWS" in text
    assert "действует" in text
    assert text.count("Источник: Казгидромет, https://www.kazhydromet.kz/") == 3
    assert "ожидается" in text  # tomorrow's НМУ
