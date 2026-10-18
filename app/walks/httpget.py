"""One polite HTTP request for the measured-weather sources (METAR, Kazhydromet): the project's User-Agent with a
contact, a short timeout, an injectable `opener` (tests pass a fake; production uses urllib)."""

from __future__ import annotations

import urllib.request
from urllib.parse import urlencode

USER_AGENT = "astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)"


def get_text(
    url: str,
    timeout: float,
    opener=urllib.request.urlopen,
    *,
    form: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    """GET `url` (POST when `form` is given) and return the body as text; raises on a network error."""
    data = urlencode(form).encode("ascii") if form is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    with opener(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")
