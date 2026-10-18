"""Airport bus facts from the airport's own page nn-airport.kz/pages/bus (STORE-facts).

The page names the city↔airport routes with their first/last departure and headway, the fare and the
 buses' working hours. The page is Kazakh by default; the Russian wording (our evidence snippets) is
served after GET /lang/ru sets the session language. Licence: not stated on the site — stored as
dated FACTS (route numbers, times, fare) with verbatim evidence snippets from the page itself, per
ГК РК ст. 974 п. 4 (facts, not texts); the full page text is never copied.

Output: data/mobility/airport_bus.json
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from collect.net import default_net
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from collect.net import default_net

from collect.mobility.common import OUT_DIR, clip_snippet, norm_ws, now_iso, write_json

BUS_URL = "https://nn-airport.kz/pages/bus"
LANG_RU_URL = "https://nn-airport.kz/lang/ru"

SOURCE_URL = BUS_URL
LICENCE = "none stated (facts from the airport's own website; source dated, quotes ≤ 300 chars)"

# Facts are read from the *Russian* rendering of the page (one language version of the same source).
# Each regex captures the sentence the stored fact came from; the matched text itself is the evidence.
# The schedule sentence separates the times with em dashes (« — », «–» or «-»), so allow any of them.
_ROUTE_RE = (
    r"Выезд из (города в аэропорт|аэропорта в город) маршрута №(\d{2,3})\s*[—–-]\s*"
    r"(\d{1,2}[.:]\d{2})\s*[—–-]\s*(\d{1,2}[.:]\d{2}), интервал между рейсами ([\d\-]+) минут"
)
_FARE_RE = r"Стоимость проезда - (\d+) тенге при оплате транспортной картой, (\d+) тенге наличными"
_HOURS_RE = r"Время работы автобусов с (\d{1,2}[:.]\d{2}) до (\d{1,2}[:.]\d{2})"


def _visible(text: str) -> str:
    import re

    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&mdash;", "—").replace("&ndash;", "–").replace("&nbsp;", " ")
    text = text.replace("&laquo;", "«").replace("&raquo;", "»").replace("&ldquo;", "“")
    text = text.replace("&rdquo;", "”").replace("&quot;", '"')
    return norm_ws(text)


def _first(pattern: str, text: str) -> tuple[str, tuple[str, ...]] | None:
    import re

    m = re.search(pattern, text)
    return (m.group(0), m.groups()) if m else None


def _evidence(field: str, snippet: str, fetched_at: str) -> dict:
    return {
        "field": field,
        "url": BUS_URL,
        "snippet": clip_snippet(snippet),
        "fetched_at": fetched_at,
    }


def collect(net) -> dict:
    """Fetch the bus page (Russian session) and turn the matched sentences into dated facts."""
    net.get(LANG_RU_URL)  # sets the language cookie; the page itself is fetched below
    resp = net.get(BUS_URL, timeout=60)
    text = _visible(resp.text)
    fetched_at = now_iso()

    routes: list[dict] = []
    import re

    for m in re.finditer(_ROUTE_RE, text):
        direction, number, first, last, headway = m.groups()
        routes.append(
            {
                "route": number,
                "direction": direction,  # "города в аэропорт" | "аэропорта в город"
                "first_departure": first.replace(".", ":"),
                "last_departure": last.replace(".", ":"),
                "headway_min": headway,
                "evidence": [_evidence("schedule", m.group(0), fetched_at)],
            }
        )
    routes.sort(key=lambda r: (r["route"], r["direction"]))

    fare = None
    if hit := _first(_FARE_RE, text):
        card, cash = hit[1]
        fare = {
            "by_transport_card_kzt": int(card),
            "cash_kzt": int(cash),
            "evidence": [_evidence("fare", hit[0], fetched_at)],
        }
    hours = None
    if hit := _first(_HOURS_RE, text):
        hours = {
            "from": hit[1][0].replace(".", ":"),
            "to": hit[1][1].replace(".", ":"),
            "evidence": [_evidence("working_hours", hit[0], fetched_at)],
        }
    if not routes or fare is None:
        raise RuntimeError(
            f"nn-airport.kz/pages/bus: expected route schedule and fare sentences, "
            f"got routes={len(routes)}, fare={fare is not None}"
        )

    doc = {
        "source_url": BUS_URL,
        "licence": LICENCE,
        "fetched_at": fetched_at,
        "routes": routes,
        "fare": fare,
        "buses_working_hours": hours,
        "notes": (
            "Факты со страницы автобусов аэропорта (№10 и №12 с первым/последним рейсом и интервалом, "
            "№201 — тариф и часы работы автобусов). Полные тексты не хранятся — только датированные "
            "факты с дословными сниппетами. Последний автобус из города в аэропорт — из самого позднего "
            "диапазона маршрутов город→аэропорт."
        ),
    }
    write_json(OUT_DIR / "airport_bus.json", doc)
    return doc


def last_departure_to_airport(doc: dict) -> tuple[str, str] | None:
    """The latest «city → airport» departure among the routes: (route, HH:MM) or None."""
    best: tuple[str, str] | None = None
    for r in doc.get("routes", []):
        if r["direction"] != "города в аэропорт":
            continue
        if best is None or r["last_departure"] > best[1]:
            best = (r["route"], r["last_departure"])
    return best


def main(argv: list[str] | None = None) -> int:
    doc = collect(default_net())
    print(
        f"[airport_bus] routes={len(doc['routes'])} fare={doc['fare']} -> {OUT_DIR / 'airport_bus.json'}"
    )
    last = last_departure_to_airport(doc)
    if last:
        print(f"[airport_bus] последний из города в аэропорт: №{last[0]} в {last[1]}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
