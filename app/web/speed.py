"""«Время ответа» of the «Данные» page: how long the answers took, read from the anonymous request log (walks.reqlog
`total_ms`: for a request of the page, the whole turn from the message to the ready answer on the server). The rotated
file counts too; an older record without the time, or a damaged line, is not counted. Nothing is estimated: no record
with a time, no number."""

from __future__ import annotations

import json
import math
import statistics
from functools import lru_cache
from pathlib import Path

from walks.reqlog import log_path


def _times(path: Path) -> list[int]:
    out: list[int] = []
    for file in (path.with_name(path.name + ".1"), path):
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                ms = json.loads(line).get("total_ms")
            except (ValueError, AttributeError):
                continue
            if isinstance(ms, int) and not isinstance(ms, bool) and ms >= 0:
                out.append(ms)
    return out


def _stamp(path: Path) -> tuple:
    out = []
    for file in (path, path.with_name(path.name + ".1")):
        try:
            st = file.stat()
        except OSError:
            out.append(None)
            continue
        out.append((st.st_mtime, st.st_size))
    return tuple(out)


@lru_cache(maxsize=4)
def _summary_at(path: str, _stamp: tuple) -> dict:
    times = sorted(_times(Path(path)))
    if not times:
        return {"requests": 0}
    p95 = times[
        math.ceil(0.95 * len(times)) - 1
    ]  # nearest rank: 95 % of the answers took this long or less
    return {
        "requests": len(times),
        "median_s": round(statistics.median(times) / 1000, 1),
        "p95_s": round(p95 / 1000, 1),
    }


def answer_times() -> dict:
    """{"requests": n, "median_s": x, "p95_s": y} over the logged answers; {"requests": 0} when the log holds none
    (missing, empty, logging off, or only records written before the time was logged). Re-read when the log changes."""
    path = log_path()
    if path is None:
        return {"requests": 0}
    return _summary_at(str(path), _stamp(path))
