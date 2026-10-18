"""The forecast leg: MET Norway locationforecast 2.0 (walks.metno) and how walks.weather uses it. The recorded answer
(tests/fixtures/metno_locationforecast_astana.json) is a real one of 2026-10-17 15:28 UTC; the 403 / 429 refusals are
synthetic (the live API answered every request of the check with 200, see collect/weather/README.md)."""

from __future__ import annotations

import copy
import io
import re
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest
from conftest import MET_RECORDED, MetServer, met_doc

from walks import apparent, metar, metno
from walks import weather as wx
from walks.httpget import USER_AGENT

RECORDED_AT = datetime(2026, 10, 17, 15, 28, 21, tzinfo=UTC)  # the Date of the recorded answer
LAST_MODIFIED = "Sat, 17 Oct 2026 15:00:05 GMT"


def _network(met: MetServer, *, metar_text: str = "", air: str = ""):
    """The opener of fetch_weather: MET Norway, optionally the station report and the air API, nothing else."""
    seen: list[str] = []

    def opener(req, timeout):
        seen.append(req.full_url)
        if "api.met.no" in req.full_url:
            return met(req, timeout)
        if metar_text and req.full_url == metar.AVIATION_URL:
            return io.BytesIO(metar_text.encode("utf-8"))
        if air and "air-quality-api.open-meteo.com" in req.full_url:
            return io.BytesIO(air.encode("utf-8"))
        raise urllib.error.URLError("not reachable in this test")

    opener.seen = seen  # type: ignore[attr-defined]
    return opener


# ---------------------------------------------------------------------------------------------- reading


def test_the_recorded_answer_gives_the_hour_nearest_to_now():
    fc = metno.forecast(0.0, RECORDED_AT, 4.0, MetServer())
    assert fc is not None
    assert fc.time == datetime(
        2026, 10, 17, 15, 0, tzinfo=UTC
    )  # 28 min away, the next one is 32 min away
    assert fc.temperature_c == 7.0
    assert fc.wind_kmh == 10.1  # 2.8 m/s
    assert fc.precipitation_mm == 0.0  # next_1_hours of that entry
    assert fc.apparent_c == pytest.approx(4.08, abs=0.01)  # 7 + 0.33 e(92.1 %) - 0.7 * 2.8 - 4


def test_the_precipitation_is_the_next_hour_of_the_entry():
    met = MetServer(met_doc("2026-10-17T15:00:00Z", 3.0, 90.0, 4.0, 6.5))
    fc = metno.forecast(0.0, RECORDED_AT, 4.0, met)
    assert fc is not None
    assert fc.precipitation_mm == 6.5


def test_an_entry_without_next_1_hours_counts_as_no_precipitation():
    """Real: the last entry of the recorded answer (a 6-hourly step, 10 days out) has no next_*_hours at all."""
    at = datetime(2026, 10, 27, 0, 10, tzinfo=UTC)
    fc = metno.forecast(0.0, at, 4.0, MetServer())
    assert fc is not None
    assert fc.time == datetime(2026, 10, 27, 0, 0, tzinfo=UTC)
    assert fc.temperature_c == -4.8
    assert fc.precipitation_mm == 0.0
    assert fc.apparent_c == pytest.approx(-8.6, abs=0.05)
    synthetic = MetServer(met_doc("2026-10-17T15:00:00Z", 1.0, 80.0, 2.0, None))
    assert metno.forecast(0.0, RECORDED_AT, 4.0, synthetic).precipitation_mm == 0.0  # type: ignore[union-attr]


def test_a_missing_humidity_or_wind_leaves_that_term_out():
    doc = copy.deepcopy(MET_RECORDED["body"])
    details = doc["properties"]["timeseries"][0]["data"]["instant"]["details"]
    del details["relative_humidity"], details["wind_speed"]
    fc = metno.forecast(0.0, RECORDED_AT, 4.0, MetServer(doc))
    assert fc is not None
    assert fc.apparent_c == pytest.approx(7.0 - 4.0)
    assert fc.wind_kmh == 0.0


def test_the_shared_formula_gives_the_same_apparent_temperature_from_a_dew_point_or_a_humidity():
    rh = 100 * apparent.saturation_hpa(5.0) / apparent.saturation_hpa(10.0)
    by_dew_point = apparent.apparent_c(10.0, 2.0, dew_point_c=5.0)
    assert apparent.apparent_c(10.0, 2.0, humidity_pct=rh) == pytest.approx(by_dew_point)
    assert by_dew_point == pytest.approx(7.4755, abs=1e-3)


def test_a_plain_answer_is_read_as_well_as_a_gzipped_one():
    fc = metno.forecast(0.0, RECORDED_AT, 4.0, MetServer(gzipped=False))
    assert fc is not None
    assert fc.temperature_c == 7.0


def test_the_request_identifies_the_project_and_asks_for_gzip():
    met = MetServer()
    metno.forecast(0.0, RECORDED_AT, 4.0, met)
    (request,) = met.requests
    assert request["user-agent"] == USER_AGENT
    assert "astana-walks" in USER_AGENT
    assert "@" in USER_AGENT  # a contact, as the terms ask
    assert request["accept-encoding"] == "gzip"
    assert "if-modified-since" not in request  # nothing is cached yet
    assert not re.search(r"=-?\d+\.\d{5,}", metno.URL)  # the terms: at most 4 decimals


# ---------------------------------------------------------------------------------------------- caching


def test_nothing_is_asked_before_expires_and_then_the_answer_is_revalidated():
    met = MetServer()  # Expires 15:31:34, 193 s after the answer's Date
    assert metno.forecast(0.0, RECORDED_AT, 4.0, met) is not None
    assert metno.forecast(192.0, RECORDED_AT + timedelta(seconds=192), 4.0, met) is not None
    assert len(met.requests) == 1
    later = RECORDED_AT + timedelta(seconds=194)
    assert metno.forecast(194.0, later, 4.0, met) is not None
    assert len(met.requests) == 2
    assert (
        met.requests[1]["if-modified-since"] == LAST_MODIFIED
    )  # the Last-Modified of the first answer, verbatim
    # the 304 carried no body: the series in memory is served, and an Expires already past is not hammered
    assert metno.forecast(194 + 59, later + timedelta(seconds=59), 4.0, met) is not None
    assert len(met.requests) == 2
    metno.forecast(194 + 61, later + timedelta(seconds=61), 4.0, met)
    assert len(met.requests) == 3


def test_a_new_version_replaces_the_series_and_its_validator():
    met = MetServer()
    metno.forecast(0.0, RECORDED_AT, 4.0, met)
    met.doc = met_doc("2026-10-17T15:00:00Z", -9.0, 50.0, 1.0, 0.0)
    met.last_modified = "Sat, 17 Oct 2026 15:30:05 GMT"
    later = RECORDED_AT + timedelta(minutes=5)
    fc = metno.forecast(300.0, later, 4.0, met)
    assert fc is not None
    assert fc.temperature_c == -9.0  # the old validator did not match: a full 200
    metno.forecast(600.0, later + timedelta(minutes=5), 4.0, met)
    assert met.requests[-1]["if-modified-since"] == "Sat, 17 Oct 2026 15:30:05 GMT"


def test_without_an_expires_header_ten_minutes_are_assumed():
    met = MetServer(expires="")
    metno.forecast(0.0, RECORDED_AT, 4.0, met)
    metno.forecast(599.0, RECORDED_AT + timedelta(seconds=599), 4.0, met)
    assert len(met.requests) == 1
    metno.forecast(601.0, RECORDED_AT + timedelta(seconds=601), 4.0, met)
    assert len(met.requests) == 2


def test_an_expires_in_the_past_still_waits_a_minute():
    met = MetServer(expires="Sat, 17 Oct 2026 15:00:00 GMT")
    metno.forecast(0.0, RECORDED_AT, 4.0, met)
    metno.forecast(59.0, RECORDED_AT + timedelta(seconds=59), 4.0, met)
    assert len(met.requests) == 1
    metno.forecast(61.0, RECORDED_AT + timedelta(seconds=61), 4.0, met)
    assert len(met.requests) == 2


def test_a_deprecated_version_is_logged(caplog):
    met = MetServer(status=203)
    with caplog.at_level("WARNING", logger="walks.metno"):
        assert metno.forecast(0.0, RECORDED_AT, 4.0, met) is not None
    assert "203" in caplog.text


# ---------------------------------------------------------------------------------------------- failures


@pytest.mark.parametrize("status", [403, 429])
def test_a_refusal_gives_no_forecast_and_stops_the_requests_for_a_quarter_of_an_hour(status):
    met = MetServer(fail=status)
    assert metno.forecast(0.0, RECORDED_AT, 4.0, met) is None
    assert metno.forecast(899.0, RECORDED_AT + timedelta(seconds=899), 4.0, met) is None
    assert len(met.requests) == 1
    met.fail = None
    fc = metno.forecast(901.0, RECORDED_AT + timedelta(seconds=901), 4.0, met)
    assert len(met.requests) == 2
    assert fc is not None  # the ban was lifted: it is served again


def test_a_network_error_is_retried_after_a_minute():
    met = MetServer(fail=urllib.error.URLError("down"))
    assert metno.forecast(0.0, RECORDED_AT, 4.0, met) is None
    metno.forecast(59.0, RECORDED_AT, 4.0, met)
    assert len(met.requests) == 1
    metno.forecast(61.0, RECORDED_AT, 4.0, met)
    assert len(met.requests) == 2


def test_a_body_that_is_not_a_forecast_is_a_failure_not_a_crash():
    for doc in (
        {"properties": {}},
        {"properties": {"timeseries": []}},
        {"properties": {"timeseries": [{}]}},
    ):
        metno.reset()
        assert metno.forecast(0.0, RECORDED_AT, 4.0, MetServer(doc)) is None


def test_the_last_series_is_served_for_three_hours_after_its_last_confirmation_and_then_dropped():
    met = MetServer()
    assert metno.forecast(0.0, RECORDED_AT, 4.0, met) is not None
    met.fail = urllib.error.URLError("down")
    two_fifty = RECORDED_AT + timedelta(hours=2, minutes=50)
    fc = metno.forecast(10000.0, two_fifty, 4.0, met)
    assert fc is not None
    assert fc.time == datetime(2026, 10, 17, 18, 0, tzinfo=UTC)  # the older forecast for that hour
    assert metno.forecast(20000.0, RECORDED_AT + timedelta(hours=3, minutes=10), 4.0, met) is None


def test_a_series_that_no_longer_covers_now_is_not_the_weather_now():
    met = MetServer(met_doc("2026-10-17T10:00:00Z", 1.0, 50.0, 1.0, 0.0))
    assert metno.forecast(0.0, RECORDED_AT, 4.0, met) is None  # the only entry is 5 h away


# ---------------------------------------------------------------------------------------------- in fetch_weather


@pytest.fixture
def at_recording(monkeypatch):
    """The weather module's «now» is the moment of the recorded answer (20:28:21 Astana = 15:28:21 UTC)."""
    monkeypatch.setattr(wx, "local_now", lambda: datetime(2026, 10, 17, 20, 28, 21))


def test_fetch_weather_takes_the_forecast_from_met_norway_and_credits_it(at_recording):
    opener = _network(MetServer())
    w = wx.fetch_weather(opener=opener, clock=lambda: 0.0, sleep=lambda s: None)
    assert (w.source, w.forecast_used) == ("met-no", True)
    assert (w.temperature_c, w.wind_kmh, w.precipitation_mm) == (7.0, 10.1, 0.0)
    assert w.apparent_c == pytest.approx(4.08, abs=0.01)
    assert not w.adverse
    assert wx.credit_lines(w, "ru") == ["прогноз: MET Norway (CC BY 4.0)"]
    assert wx.credit_lines(w, "kk") == ["болжам: MET Norway (CC BY 4.0)"]
    assert wx.credit_lines(w, "en") == ["forecast: MET Norway (CC BY 4.0)"]
    # no PM2.5 without the demo switch: Open-Meteo's free API is for non-commercial use only
    assert w.pm25 is None
    assert not any("open-meteo" in url for url in opener.seen)  # type: ignore[attr-defined]


def test_the_open_meteo_air_leg_is_a_demo_switch_and_says_so(at_recording, monkeypatch):
    monkeypatch.setenv("WALKS_AIR_DEMO", "1")
    air = '{"current": {"pm2_5": 41.0, "european_aqi": 90}}'
    w = wx.fetch_weather(
        opener=_network(MetServer(), air=air), clock=lambda: 0.0, sleep=lambda s: None
    )
    assert (w.pm25, w.aqi, w.air_bad) == (41.0, 90, True)
    forecast_credit, air_credit = wx.credit_lines(w, "ru")
    assert forecast_credit == "прогноз: MET Norway (CC BY 4.0)"
    assert "Open-Meteo" in air_credit
    assert "демо" in air_credit
    assert "некоммерческ" in air_credit


def test_a_refused_forecast_leaves_the_weather_unknown_and_changes_no_ranking(at_recording):
    w = wx.fetch_weather(
        opener=_network(MetServer(fail=403)), clock=lambda: 0.0, sleep=lambda s: None
    )
    assert w.temperature_c is None
    assert not w.forecast_used
    assert not w.indoor_preferred
    assert wx.credit_lines(w, "ru") == []


def test_a_refused_forecast_does_not_silence_the_station():
    fresh = "METAR UACC 140630Z 24003MPS 9999 05/03 Q1020"  # 11:30 Astana, the pinned now is 12:00
    w = wx.fetch_weather(
        opener=_network(MetServer(fail=403), metar_text=fresh),
        clock=lambda: 0.0,
        sleep=lambda s: None,
    )
    assert w.source == "metar"
    assert w.temperature_c == 5.0
    assert w.precipitation_mm == 0.0  # nothing says otherwise
    assert not w.forecast_used
    assert wx.credit_lines(w, "ru") == []


def test_a_manual_demo_weather_has_no_remote_credit():
    assert wx.credit_lines(wx.manual_weather(-30), "ru") == []


def test_offline_mode_asks_nobody(monkeypatch):
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    met = MetServer()
    w = wx.fetch_weather(opener=met)
    assert met.requests == []
    assert (w.temperature_c, w.pm25, w.forecast_used) == (None, None, False)
