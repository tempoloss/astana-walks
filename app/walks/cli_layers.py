"""The CLI flags of the data layers (events afisha, mobility, OSM city layers): each prints what its layer says for a
point, a moment or a route and exits, without a dialogue. `add_flags` declares them, `run` answers the one that is set
(None when none is). The time and coordinate parsers stay with walks.cli and come in as arguments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .events import format_block, load_snapshot, nearby_events
from .hours import local_now

ParseTime = Callable[[argparse.ArgumentParser, str], datetime]
CheckCoordinates = Callable[[argparse.ArgumentParser, float | None, float | None], None]


def add_flags(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--events",
        action="store_true",
        help="афиша рядом (data/events.json): события, идущие сейчас или начинающиеся в окне --events-window; "
        "нужны --lat/--lon, --time задаёт момент (по времени Астаны)",
    )
    ap.add_argument("--events-radius", type=int, default=1500, metavar="М", help="радиус афиши, м")
    ap.add_argument("--events-window", type=int, default=180, metavar="МИН", help="окно афиши, мин")
    ap.add_argument(
        "--parking",
        action="store_true",
        help="платная парковочная зона для точки (слой ЦОДД по умолчанию выключен: WALKS_MOBILITY_PARKING=1)",
    )
    ap.add_argument(
        "--stops",
        action="store_true",
        help="ближайшие автобусные остановки (GTFS Zenodo + OSM) с минутами пешком",
    )
    ap.add_argument(
        "--airport-bus",
        action="store_true",
        help="автобусы в аэропорт: маршруты, последний рейс, тариф (факты nn-airport.kz)",
    )
    ap.add_argument(
        "--city-notes",
        metavar="LAT,LON",
        help="печать сигналов OSM Notes вокруг точки (walks.city_layers.signals_for_poi)",
    )
    ap.add_argument(
        "--city-lit",
        metavar="LAT,LON[,LAT,LON...]",
        help="доли освещённости вдоль маршрута (walks.city_layers.lit_share)",
    )
    ap.add_argument(
        "--city-construction",
        metavar="LAT,LON[,LAT,LON...]",
        help="стройки рядом с точкой/маршрутом (walks.city_layers.construction_near_route)",
    )
    ap.add_argument(
        "--city-summary",
        action="store_true",
        help="сводка слоя «Город» (walks.city_layers.city_summary)",
    )
    ap.add_argument(
        "--gov-hours",
        nargs="?",
        const="cson",
        choices=["cson", "sport"],
        help="часы гособъектов из данных (ЦОН, реестр спорта №730), без рекомендаций: --q «ЦОН в субботу» [--lat --lon]",
    )


def _mobility(ap: argparse.ArgumentParser, args: argparse.Namespace, parse_time: ParseTime) -> int:
    """--parking / --stops / --airport-bus: one mobility layer per flag, reads data/mobility only."""
    from . import mobility as mob

    when = parse_time(ap, args.time) if args.time else None
    if args.parking:
        if args.lat is None or args.lon is None:
            ap.error("--parking нужны --lat и --lon")
        zone = mob.parking_at(args.lat, args.lon, when)
        if zone is None:
            on = os.environ.get(mob.PARKING_ENABLE_ENV, "").strip() == "1"
            state = (
                "данных о зоне в этой точке нет"
                if on
                else "слой выключен (WALKS_MOBILITY_PARKING!=1)"
            )
            print(f"Парковка: данных нет ({state})")
        else:
            print(
                f"Парковка: зона {zone.name}, {zone.address or 'адрес не указан'} "
                f"({zone.source_url}; лицензия: {zone.licence})"
            )
            if (price := zone.price_text()) is not None:
                print(f"   тариф: {price}")
            if zone.is_residential:
                print("   резидентная зона")
    if args.stops:
        if args.lat is None or args.lon is None:
            ap.error("--stops нужны --lat и --lon")
        stops = mob.nearest_stops(args.lat, args.lon)
        if not stops:
            print("Остановки: данных нет (файл data/mobility/stops.json отсутствует или пуст)")
        for s in stops:
            src = "; ".join(sorted({x.get("source", "?") for x in s.sources})) or "—"
            print(
                f"Остановка: {s.name or 'название не указано'} — {s.distance_m} м, {s.walk_min} мин пешком [{src}]"
            )
    if getattr(args, "airport_bus", False):
        info = mob.airport_bus()
        if info is None:
            print("Автобусы в аэропорт: данных нет (нет снимка data/mobility/airport_bus.json)")
            return 0
        hours = (
            f", работают {info.working_hours[0]}–{info.working_hours[1]}"
            if info.working_hours
            else ""
        )
        print(
            f"Автобусы в аэропорт{hours}: билет {info.fare_card_kzt} ₸ картой / "
            f"{info.fare_cash_kzt} ₸ наличными [{info.source_url}]"
        )
        for r in info.routes:
            print(
                f"   №{r['route']} {r['direction']}: {r['first_departure']}–{r['last_departure']}, "
                f"интервал {r['headway_min']} мин"
            )
        if info.last_to_airport:
            print(
                f"   последний из города в аэропорт: №{info.last_to_airport[0]} в {info.last_to_airport[1]}"
            )
    return 0


def _print_events(
    ap: argparse.ArgumentParser,
    args: argparse.Namespace,
    parse_time: ParseTime,
    check_coordinates: CheckCoordinates,
) -> int:
    """--events: the «сегодня рядом» block for a point and a moment (Astana time), with the snapshot's freshness."""
    if args.lat is None or args.lon is None:
        ap.error("--events: нужны --lat и --lon")
    check_coordinates(ap, args.lat, args.lon)
    when = parse_time(ap, args.time) if args.time else local_now()
    if args.time and len(args.time) <= 5:  # 'HH:MM' means today in Astana, not on this machine
        when = local_now().replace(hour=when.hour, minute=when.minute, second=0, microsecond=0)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    snap = load_snapshot()
    located = sum(e["venue"].get("lat") is not None for e in snap.events)
    age = snap.age_hours(when)
    print(
        f"Афиша: точка {args.lat}, {args.lon}; {when:%Y-%m-%d %H:%M} (UTC+5); окно {args.events_window} мин; "
        f"радиус {args.events_radius} м"
    )
    print(
        f"Снимок: fetched_at={snap.fetched_at}; "
        + (
            "возраст неизвестен"
            if age is None
            else f"возраст ≈ {age:.1f} ч"
            if age >= 0
            else "снимок сделан позже заданного --time"
        )
        + ("; УСТАРЕЛ (> 36 ч)" if snap.is_stale(when) else "")
        + f"; событий в файле {len(snap.events)}, с координатами {located}"
    )
    near = nearby_events(
        args.lat,
        args.lon,
        when,
        radius_m=args.events_radius,
        window_min=args.events_window,
        snapshot=snap,
    )
    if near is None:
        print("Блок «сегодня рядом» молчит: в этом окне нечего показать.")
        return 0
    print("\n".join(format_block(near, args.lang or "ru", when)))
    for h in near.hits:
        print(f"    {h.url}")
    return 0


def _coords(arg: str) -> list[tuple[float, float]]:
    """'LAT,LON' or 'LAT,LON,LAT,LON,...' (a polyline) -> [(lat, lon), ...]; anything else exits with usage."""
    nums = [p.strip() for p in arg.split(",")]
    if len(nums) % 2 or not nums:
        raise SystemExit("координаты: LAT,LON или LAT,LON,LAT,LON,... (чётное число чисел)")
    try:
        vals = [float(v) for v in nums]
    except ValueError:
        raise SystemExit(f"координаты: нужны числа, получено {arg!r}") from None
    pts = [(vals[i], vals[i + 1]) for i in range(0, len(vals), 2)]
    for lat, lon in pts:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise SystemExit(f"координаты вне диапазона: {lat}, {lon}")
    return pts


def _city_data_dir() -> Path:
    from .city_layers import DATA_DIR

    v = os.environ.get("WALKS_CITY_DIR", "").strip()
    return Path(v) if v else DATA_DIR


def _read_nearby_notes(lat: float, lon: float) -> list[dict]:
    """Open notes within NOTE_RADIUS_M of the point, read straight from the collected file."""
    from .city_layers import NOTE_RADIUS_M, dist_m

    try:
        rows = json.loads((_city_data_dir() / "osm_notes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [
        n
        for n in rows
        if n.get("status") == "open"
        and dist_m(lat, lon, float(n["lat"]), float(n["lon"])) <= NOTE_RADIUS_M
    ]


def _city_flags(args: argparse.Namespace) -> int:
    """--city-*: печатает сигналы слоя «город» для точки/маршрута и завершает работу (без диалога)."""
    from .city_layers import (
        city_summary,
        construction_near_route,
        lit_share,
    )
    from .models import POI

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.city_summary:
        s = city_summary()
        if s is None:
            print("Слоя «Город» нет в данных (data/city/ пуст) — ничего не утверждаем.")
            return 0
        d = s.as_dict()
        print(f"Город (снапшот {d['snapshot_date']}; {d['attribution']}):")
        print(
            f"  Заметки OSM: всего {d['notes_total']}, открытых {d['notes_open']}, закрытых (в снапшоте) "
            f"{d['notes_closed_kept']}; по классификации: {d['by_classification']}"
        )
        print(
            f"  Освещение: lit=yes {d['lit_yes']}, lit=no {d['lit_no']} отрезков (остальные — данных нет)"
        )
        print(f"  Стройки (highway=construction): {d['construction']}")
        for n in d["open_notes"][:10]:
            print(
                f"  - #{n['id']} [{n['classification']}] от {n['date_created']}: {n['snippet']} {n['url']}"
            )
        if len(d["open_notes"]) > 10:
            print(f"  … ещё {len(d['open_notes']) - 10} открытых заметок")
        return 0
    if args.city_notes:
        pts = _coords(args.city_notes)
        if len(pts) != 1:
            raise SystemExit("--city-notes: нужна одна точка LAT,LON")
        lat, lon = pts[0]
        # The app signal filters notes to those that mention the place's name or its kind; on the CLI the point
        # is not a POI, so show the same matching twice: unnamed (nothing to match on -> all open notes nearby)
        # and, for reference, the strict app view for a generic cafe at the same point.
        from .city_layers import dist_m
        from .city_layers import signals_for_poi as _sig

        notes = _read_nearby_notes(lat, lon)
        sigs = _sig(POI(id="point", name="кафе", lat=lat, lon=lon, category="cafe"))
        print(
            f"OSM Notes в радиусе 50 м от {lat}, {lon}: {len(notes)} (совпадающих по названию/типу: {len(sigs)})"
        )
        for n in notes:
            print(
                f"  - #{n['id']} [{n.get('classification')}] от {n.get('date_created')}, "
                f"{round(dist_m(lat, lon, n['lat'], n['lon']))} м: {n.get('snippet')}"
            )
            print(f"    {n.get('url')}")
        return 0
    route = _coords(args.city_lit or args.city_construction or "")
    if args.city_lit:
        ls = lit_share(route)
        if ls is None:
            print("Освещённость: данных нет (data/city/lit.json пуст или маршрут не задан).")
            return 0
        d = ls.as_dict()
        print(
            f"Освещённость маршрута (коридор 15 м): освещено {d['lit_yes'] * 100:.0f}%, "
            f"освещение отсутствует (тег lit=no) {d['lit_no'] * 100:.0f}%, данных нет {d['unknown'] * 100:.0f}%"
        )
        if d["known_share"] < 0.2:
            print("  Известных данных мало — честнее считать освещённость неизвестной.")
        return 0
    near = construction_near_route(route)
    print(f"Стройки в коридоре 15 м: {len(near)}")
    for w in near[:10]:
        print(
            f"  - way/{w['id']} [{w.get('construction') or 'construction'}] {w.get('name') or ''}"
        )
    return 0


def run(
    ap: argparse.ArgumentParser,
    args: argparse.Namespace,
    *,
    parse_time: ParseTime,
    check_coordinates: CheckCoordinates,
) -> int | None:
    """The exit code of the layer flag that is set, None when the command line has none."""
    if args.events:
        return _print_events(ap, args, parse_time, check_coordinates)
    if args.parking or args.stops or args.airport_bus:
        return _mobility(ap, args, parse_time)
    if any([args.city_notes, args.city_lit, args.city_construction, args.city_summary]):
        return _city_flags(args)
    if args.gov_hours:
        from . import gov_hours

        when = parse_time(ap, args.time) if args.time else None
        for line in gov_hours.run_cli(args.gov_hours, args.q, args.lat, args.lon, when):
            print(line)
        return 0
    return None
