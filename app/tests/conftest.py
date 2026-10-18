import gzip
import io
import json
import os
import sys
import urllib.error
from datetime import datetime
from email.message import Message
from pathlib import Path

import pytest

from walks import cli, feedback, hours

PINNED_NOW = datetime(2026, 10, 14, 12, 0)  # a Wednesday noon, Astana local time
_LOCAL_NOW = hours.local_now  # the real clock source, before any test patches it


@pytest.fixture(autouse=True)
def pin_clock(monkeypatch):
    """No test depends on the wall clock: every place where the app reads it (`hours.local_now` and its importers,
    the CLI's «HH:MM» and the time of a mark) answers `PINNED_NOW`. Returns `pin(now)` for a test that needs another
    instant (a CLI test that stores marks and asks at a fixed time must store them at that time too)."""

    clock = [PINNED_NOW]  # the instant every patched module answers; a later pin moves it

    def pin(now: datetime) -> None:
        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return now.replace(tzinfo=tz)

        clock[0] = now
        for name, module in list(sys.modules.items()):
            if (
                name.startswith(("walks.", "web."))
                and getattr(module, "local_now", None) is _LOCAL_NOW
            ):
                monkeypatch.setattr(module, "local_now", lambda: clock[0])
        monkeypatch.setattr(cli, "datetime", Frozen)
        monkeypatch.setattr(feedback, "datetime", Frozen)

    pin(PINNED_NOW)
    return pin


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Tests never touch the network or the real app/.local files unless they inject their own fakes."""
    from walks import llm, llm_providers, walking, weather

    monkeypatch.setenv("WALKS_REQUEST_LOG", "off")  # app/.local/requests.jsonl
    monkeypatch.setenv("WALKS_WALKING", "off")  # Valhalla: straight-line fallback only
    monkeypatch.setenv("WALKS_WALK_CACHE", "off")  # app/.local/walk_cache.json
    monkeypatch.setenv("WALKS_LLM_CACHE", "off")  # app/.local/llm_cache.json
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # no key unless a test installs a fake one
    monkeypatch.setenv("GEMINI_KEY_FILE", str(tmp_path / "no-key"))
    for name in list(os.environ):  # chains, profiles and demo switches of the developer's shell
        if name.startswith(
            (
                "LLM_",
                "OPENAI_",
                "WALKS_ENV",
                "WALKS_OFFLINE",
                "WALKS_SIMULATE",
                "WALKS_DEMO",
                "WALKS_CACHE_PIN",
                "WALKS_VALHALLA",
                "WALKS_AIR",
            )
        ):
            monkeypatch.delenv(name)
    monkeypatch.setenv(
        "WALKS_FEEDBACK", str(tmp_path / "marks.json")
    )  # app/.local/city_feedback.json
    llm_providers._no_json_mode.clear()
    monkeypatch.setattr(walking, "_default", None)
    monkeypatch.setattr(
        weather, "start_refresher", lambda: None
    )  # the server's background thread is not a test's
    weather.clear_cache()
    llm.reset_breakers()
    yield
    weather.clear_cache()
    llm.reset_breakers()


_skipped: list[str] = []


def pytest_runtest_logreport(report):
    if report.skipped and not hasattr(report, "wasxfail"):
        _skipped.append(report.nodeid)


def pytest_sessionfinish(session):
    """A skipped test is a hidden failure (e.g. missing data/poi.json): fail the run."""
    if _skipped:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


# ---- api.met.no as a fake opener ---------------------------------------------------------------------

MET_RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "metno_locationforecast_astana.json").read_text(
        encoding="utf-8"
    )
)  # a real answer of 2026-10-17 15:28 UTC, see its `_recorded` block


def met_header(**fields: str) -> Message:
    headers = Message()
    for key, value in fields.items():
        headers[key.replace("_", "-")] = value
    return headers


def met_doc(
    utc: str, temperature: float, humidity: float, wind: float, precipitation: float | None
):
    """A minimal `compact` answer: one entry at `utc` ("2026-10-14T07:00:00Z"); `precipitation=None` leaves out
    next_1_hours, as the real answer does beyond its first ~60 hours."""
    data: dict = {
        "instant": {
            "details": {
                "air_temperature": temperature,
                "relative_humidity": humidity,
                "wind_speed": wind,
            }
        }
    }
    if precipitation is not None:
        data["next_1_hours"] = {
            "summary": {"symbol_code": "clearsky_day"},
            "details": {"precipitation_amount": precipitation},
        }
    return {"type": "Feature", "properties": {"timeseries": [{"time": utc, "data": data}]}}


class MetServer:
    """api.met.no behind the `opener` of walks.weather / walks.metno. Everything else is unreachable (URLError), as
    in a test that has no network. `fail` is an HTTP status (403, 429, ...) or an exception to raise; a request with
    `If-Modified-Since` equal to `last_modified` gets a 304, like the real server."""

    def __init__(
        self,
        doc: dict | None = None,
        *,
        expires: str = "Sat, 17 Oct 2026 15:31:34 GMT",
        last_modified: str = "Sat, 17 Oct 2026 15:00:05 GMT",
        gzipped: bool = True,
        fail: int | Exception | None = None,
        status: int = 200,
    ):
        self.doc = doc if doc is not None else MET_RECORDED["body"]
        self.expires, self.last_modified = expires, last_modified
        self.gzipped, self.fail, self.status = gzipped, fail, status
        self.requests: list[dict[str, str]] = []  # the lower-cased headers of every request

    def __call__(self, req, timeout):
        if not req.full_url.startswith(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact?"
        ):
            raise urllib.error.URLError("not reachable in this test")
        self.requests.append({k.lower(): v for k, v in req.header_items()})
        if isinstance(self.fail, Exception):
            raise self.fail
        if isinstance(self.fail, int):
            raise urllib.error.HTTPError(req.full_url, self.fail, "refused", met_header(), None)
        if req.get_header("If-modified-since") == self.last_modified:
            raise urllib.error.HTTPError(
                req.full_url,
                304,
                "Not Modified",
                met_header(Expires=self.expires, Last_Modified=self.last_modified),
                None,
            )
        body = json.dumps(self.doc).encode("utf-8")
        fields = {"Expires": self.expires, "Last_Modified": self.last_modified}
        if self.gzipped:
            body = gzip.compress(body)
            fields["Content_Encoding"] = "gzip"
        resp = io.BytesIO(body)
        resp.headers = met_header(**fields)  # type: ignore[attr-defined]
        resp.status = self.status  # type: ignore[attr-defined]
        return resp


@pytest.fixture
def met_server():
    """The MetServer class: `met_server(doc, expires=..., fail=403)` builds one."""
    return MetServer
