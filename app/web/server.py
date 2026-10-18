"""The Starlette app of the web UI: the static front-end (web/static: vanilla ES modules, vendored MapLibre) and the
JSON endpoints over the core. Run it with `python -m web` (web/__main__.py) or any ASGI server: `web.server:app`.

    GET  /                    the page (Ассистент, Город, Данные are client-side views of it)
    GET  /api/config          the stand's mode, the places, the starter requests      (web.turns)
    GET  /api/strings         every UI string in kk / ru / en                         (i18n.UI)
    POST /api/turn            one message of the dialogue                             (web.turns, walks.dialog)
    POST /api/report          a resident's anonymous mark of a place                  (web.memory, walks.feedback)
    GET|POST /api/profile     the opt-in profile                                      (web.memory, walks.profile)
    GET  /api/geocode         the address search of «Где вы?»: ≤ 5 points (?q=) or the house at a point (?lat=&lon=)  (web.geocode)
    GET  /api/city/{layer}    demand | quality | reports                              (web.city)
    GET  /api/city/export/{name}
    GET  /api/data            sources, coverage, measured honesty                     (web.datainfo)
    GET  /api/districts       district outlines (the map's background without the network)
    GET  /healthz
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from i18n import ui_table
from walks import conditions, weather
from walks.envcfg import load_env_file
from walks.i18n import SIGNAL, norm
from web import city, datainfo, geocode, memory, turns

STATIC = Path(__file__).resolve().parent / "static"
VERSIONED = "/static/v-"  # /static/v-<release>/js/main.js is /static/js/main.js of that release
IMMUTABLE = b"public, max-age=31536000, immutable"
MAX_BODY = 64_000
BASEMAP = "https://tiles.openfreemap.org"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    f"img-src 'self' data: blob: {BASEMAP}; connect-src 'self' {BASEMAP}; worker-src 'self' blob:; "
    "font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
SECURITY_HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"geolocation=(self), camera=(), microphone=()"),
]
log = logging.getLogger("web")
_running: set[asyncio.Task] = set()  # turns in progress (a task needs a reference until it ends)


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [*message.get("headers", []), *SECURITY_HEADERS]
                # the ES modules import each other by bare path, so a proxy must revalidate them after every release
                if scope["path"].startswith("/static/"):
                    headers = [(k, v) for k, v in headers if k.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-cache"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, with_headers)


class Release:
    """The release of the front-end the page links its assets under: a short hash of the path, size and modification
    time of every file of web/static, taken again on every page load, so an edited module gets a new address at once
    (no build step, no restart)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.current = self.take()

    def take(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(p for p in self.root.rglob("*") if p.is_file()):
            st = path.stat()
            digest.update(
                f"{path.relative_to(self.root).as_posix()}\0{st.st_size}\0{st.st_mtime_ns}\n".encode()
            )
        self.current = digest.hexdigest()[:12]
        return self.current


class VersionedStatic:
    """Serves /static/v-<release>/… as /static/…, kept for a year when <release> is the current one. A proxy in front
    keeps static files for hours whatever the server says (the Cloudflare browser-cache TTL), so the page, which is
    never cached, links every asset under its release: the ES modules import each other by relative path and stay
    inside it, and one release's page never runs another's modules."""

    def __init__(self, app: ASGIApp, release: Release) -> None:
        self.app, self.release = app, release

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(VERSIONED):
            await self.app(scope, receive, send)
            return
        release, _, rest = scope["path"][len(VERSIONED) :].partition("/")
        path = f"/static/{rest}"
        scope = {**scope, "path": path, "raw_path": path.encode()}
        if (
            release != self.release.current
        ):  # an older page's link: today's file, revalidated like any other
            await self.app(scope, receive, send)
            return

        async def immutable(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 200:
                headers = [(k, v) for k, v in message["headers"] if k.lower() != b"cache-control"]
                message["headers"] = [*headers, (b"cache-control", IMMUTABLE)]
            await send(message)

        await self.app(scope, receive, immutable)


@lru_cache(maxsize=4)
def page_html(release: str) -> str:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    return html.replace('"/static/', f'"{VERSIONED}{release}/')


async def _body[Body: BaseModel](request: Request, model: type[Body]) -> Body:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY:
        raise HTTPException(413, "too_large")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "too_large")
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, "bad_request") from exc


def _lang(request: Request) -> str:
    return norm(request.query_params.get("lang"))


def _int(request: Request, name: str) -> int | None:
    value = request.query_params.get(name, "")
    return int(value) if value.isdigit() else None


async def page(request: Request) -> Response:
    # no-transform: a Cloudflare proxy in front must not rewrite the page (it would inject its Web Analytics
    # beacon, which the strict CSP blocks and logs as a console error); the CSP itself stays as it is
    release = request.app.state.release.take()
    return HTMLResponse(page_html(release), headers={"cache-control": "no-cache, no-transform"})


async def health(_: Request) -> Response:
    return PlainTextResponse("ok")


async def config(_: Request) -> Response:
    return JSONResponse(turns.config())


async def strings(_: Request) -> Response:
    table = {key: list(entry) for key, entry in ui_table().items()}
    table |= {f"sig_{key}": list(entry) for key, entry in SIGNAL.items()}
    return JSONResponse(table)


async def turn(request: Request) -> Response:
    """NDJSON: one `{"stage": …}` line per step the core enters (parse, search, write, route), then `{"answer": …}`
    (or `{"error": …}`): the page shows the real steps while the answer is being made."""
    req = await _body(request, turns.TurnRequest)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def stage(name: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"stage": name})

    async def work() -> None:
        try:
            await queue.put({"answer": await run_in_threadpool(turns.answer, req, stage)})
        except Exception:
            log.exception("turn failed")
            await queue.put({"error": "failed"})
        await queue.put(None)

    task = asyncio.create_task(work())
    _running.add(task)
    task.add_done_callback(_running.discard)

    async def lines() -> AsyncIterator[str]:
        while (item := await queue.get()) is not None:
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


async def report(request: Request) -> Response:
    req = await _body(request, memory.Report)
    try:
        ok = await run_in_threadpool(memory.report, req)
    except OSError as exc:
        raise HTTPException(503, "marks_off") from exc
    if not ok:
        raise HTTPException(422, "unknown_place")
    return JSONResponse({"ok": True})


async def profile(request: Request) -> Response:
    if request.method == "GET":
        uid = request.query_params.get("id")
        return JSONResponse(await run_in_threadpool(memory.view, uid, _lang(request)))
    act = await _body(request, memory.ProfileAction)
    out = await run_in_threadpool(memory.apply, act)
    if out is None:
        raise HTTPException(422, "nothing_to_change")
    return JSONResponse(out)


async def city_layer(request: Request) -> Response:
    layer, q, lang = request.path_params["layer"], request.query_params, _lang(request)
    if layer == "demand":
        args = (q.get("source"), _int(request, "k"), q.get("category"), q.get("bucket"), lang)
        return JSONResponse(await run_in_threadpool(city.demand, *args))
    if layer == "quality":
        return JSONResponse(await run_in_threadpool(city.quality, q.get("metric"), lang))
    if layer == "reports":
        return JSONResponse(await run_in_threadpool(city.reports, lang))
    raise HTTPException(404, "no_such_layer")


async def geocode_view(request: Request) -> Response:
    """The address search of «Где вы?»: up to five points of Astana for what was typed (`q`), or the house under a
    point (`lat`, `lon`). Neither the text nor the point is logged (web.geocode also strips them from uvicorn's access
    line) or kept."""
    q = request.query_params
    try:
        point = (float(q["lat"]), float(q["lon"])) if "lat" in q and "lon" in q else None
    except ValueError:
        raise HTTPException(422, "bad_point") from None
    if point:
        found = await run_in_threadpool(geocode.reverse, *point, _lang(request))
    else:
        found = await run_in_threadpool(geocode.search, q.get("q", ""), _lang(request))
    return JSONResponse({"results": found}, headers={"cache-control": "no-store"})


async def city_export(request: Request) -> Response:
    name = request.path_params["name"]
    args = (name, request.query_params.get("source"), _int(request, "k"))
    out = await run_in_threadpool(city.export, *args)
    if out is None:
        raise HTTPException(404, "no_such_export")
    body, media = out
    return Response(
        body,
        media_type=media,
        headers={"content-disposition": f'attachment; filename="{name}"'},
    )


async def data(request: Request) -> Response:
    return JSONResponse(await run_in_threadpool(datainfo.data_info, _lang(request)))


async def conditions_view(request: Request) -> Response:
    """The weather the map effects draw: what the refresh thread last read, never a network call (walks.conditions)."""
    body = conditions.current(fake=request.query_params.get("fake", ""))
    return JSONResponse(body, headers={"cache-control": "no-store"})


async def districts(_: Request) -> Response:
    return JSONResponse(
        await run_in_threadpool(city.districts_geojson), media_type="application/geo+json"
    )


async def http_error(_: Request, exc: HTTPException) -> Response:
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@contextlib.asynccontextmanager
async def lifespan(_: Starlette) -> AsyncIterator[None]:
    """The weather is refreshed in the background from the start: a request never waits for it (walks.weather)."""
    weather.start_refresher()
    yield


def create_app() -> Starlette:
    load_env_file()  # WALKS_ENV=demo -> app/.env.demo, before the first request reads the LLM / offline settings
    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/", page),
            Route("/healthz", health),
            Route("/api/config", config),
            Route("/api/strings", strings),
            Route("/api/turn", turn, methods=["POST"]),
            Route("/api/report", report, methods=["POST"]),
            Route("/api/profile", profile, methods=["GET", "POST"]),
            Route("/api/geocode", geocode_view),
            Route("/api/city/export/{name}", city_export),
            Route("/api/city/{layer}", city_layer),
            Route("/api/data", data),
            Route("/api/conditions", conditions_view),
            Route("/api/districts", districts),
            Mount("/static", StaticFiles(directory=STATIC), name="static"),
        ],
        exception_handlers={HTTPException: http_error},
    )
    app.state.release = Release(STATIC)
    app.add_middleware(SecurityHeaders)
    app.add_middleware(VersionedStatic, release=app.state.release)
    return app


app = create_app()
