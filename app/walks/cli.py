"""CLI smoke runner: python -m walks.cli --lat 51.0890 --lon 71.4160 --q "..." """

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import cli_layers
from .demo_pin import pins, recommend_pinned, setup_for
from .dialog import TurnEnv, new_state, take_turn
from .envcfg import load_env_file, replay_only
from .feedback import SIGNALS, add_feedback, hours_label, load_feedback
from .followup import conversation_after
from .i18n import padding_label, public_text, source_label
from .llm import chain_text, generation_models, intent_models
from .models import Conversation, WeatherInfo
from .pipeline import recommend
from .profile import (
    Profile,
    delete_profile,
    load_profile,
    new_profile_id,
    remember,
    save_profile,
    valid_id,
)
from .reasons import hours_state_text
from .walking import METHOD_LABEL, default_router, offline_router
from .weather import (
    adverse_text,
    air_driver_text,
    attribution,
    credit_lines,
    fetch_weather,
    fmt_temp,
    manual_weather,
    source_details,
    warning_text,
)

STATE_PATH = Path(__file__).resolve().parents[1] / ".local" / "conversation.json"


def _state_path() -> Path:
    v = os.environ.get("WALKS_STATE_FILE", "").strip()
    return Path(v) if v else STATE_PATH


def _load_state() -> Conversation:
    """The dialogue of the previous CLI call (a file the user asked for with --keep-state / --follow-up)."""
    try:
        return Conversation.model_validate_json(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit("нет сохранённого диалога: сначала запрос с --keep-state") from None


def _save_state(conv: Conversation) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(conv.model_dump_json(), encoding="utf-8")


def _mark(spec: str) -> int:
    poi_id, _, signal = spec.rpartition(":")
    if signal not in SIGNALS:
        print(f"сигнал должен быть одним из: {', '.join(SIGNALS)}")
        return 2
    entry = add_feedback(poi_id, signal)
    print(
        f"Отметка сохранена: {entry.poi_id} · {SIGNALS[signal]} · {entry.date} ({entry.hour_bucket})"
    )
    return 0


def _open_profile(arg: str | None) -> tuple[str, Profile | None]:
    """(uuid, stored profile) for --profile; an unknown uuid is a new empty profile; no --profile: no profile."""
    if arg is None:
        return "", None
    uid = new_profile_id() if arg == "new" else arg
    if not valid_id(uid):
        raise SystemExit("--profile: нужен uuid или new")
    return uid, load_profile(uid) or Profile()


def _weather(args: argparse.Namespace) -> WeatherInfo | None:
    if args.weather == "auto":
        return fetch_weather()
    if args.weather == "off":
        return None
    return manual_weather(float(args.weather), pm25=args.pm25, force_dark=args.dark)


def _station_lines(w: WeatherInfo) -> list[str]:
    """The airport observation (with its time, and the METAR verbatim) and the Kazhydromet notices of Astana."""
    lines = []
    if w.observed_at:
        lines.append(f"Наблюдение: {attribution(w, 'ru')}; METAR: {w.obs_raw}")
        lines.append(f"  {source_details('ru')}")
    if w.source == "metar" and w.conditions:
        lines.append(f"  по станции: {w.reason or w.air_reason}")
    for warn in w.warnings:
        state = "действует" if warn.active else "ожидается"
        lines.append(
            f"Казгидромет, {state} ({warn.valid_from} — {warn.valid_to}): {warning_text(warn, 'ru')}"
        )
    return lines


def _check_coordinates(ap: argparse.ArgumentParser, lat: float | None, lon: float | None) -> None:
    """--lat/--lon: both or none (none only with --follow-up), finite and on the globe."""
    if (lat is None) != (lon is None):
        ap.error("--lat и --lon задаются вместе")
    if lat is None or lon is None:
        return
    if not (math.isfinite(lat) and math.isfinite(lon)):
        ap.error(f"--lat/--lon: нужны конечные числа, получено {lat}, {lon}")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        ap.error(f"--lat/--lon вне диапазона (широта -90..90, долгота -180..180): {lat}, {lon}")


def _check_weather(ap: argparse.ArgumentParser, value: str) -> None:
    if value in ("auto", "off"):
        return
    try:
        ok = math.isfinite(float(value))
    except ValueError:
        ok = False
    if not ok:
        ap.error(f"--weather: 'auto', 'off' или число (°C), получено {value!r}")


def _parse_time(ap: argparse.ArgumentParser, value: str) -> datetime:
    """--time 'YYYY-MM-DD HH:MM' or 'HH:MM' (today); anything else is a usage error, not a traceback."""
    fmt = "%Y-%m-%d %H:%M" if len(value) > 5 else "%H:%M"
    try:
        when = datetime.strptime(value, fmt)
    except ValueError:
        ap.error(f"--time: нужно 'ГГГГ-ММ-ДД ЧЧ:ММ' или 'ЧЧ:ММ' (00:00-23:59), получено {value!r}")
    if fmt == "%H:%M":
        when = datetime.now().replace(hour=when.hour, minute=when.minute, second=0, microsecond=0)
    return when


def _dialog_main(
    ap: argparse.ArgumentParser, args: argparse.Namespace, profile: Profile | None
) -> int:
    """--dialog: every message of the dialogue (stdin lines or the --script list) through `walks.dialog.take_turn`;
    one JSON object per turn: {"say", "turn", "state"}, so a fuzzer can replay a dialogue and read every field."""
    if args.lat is None or args.lon is None:
        ap.error("--dialog: нужны --lat и --lon")
    _check_coordinates(ap, args.lat, args.lon)
    _check_weather(ap, args.weather)
    if args.offline:
        os.environ["WALKS_OFFLINE"] = "1"
    load_env_file()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.script:
        steps = json.loads(Path(args.script).read_text(encoding="utf-8"))
    else:
        steps = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    env = TurnEnv(
        when=_parse_time(ap, args.time) if args.time else None,
        weather=_weather(args),
        use_llm=not args.no_llm,
        router=default_router() if args.walking else offline_router(),
        profile=profile,
        feedback=load_feedback(),
        language=args.lang,
    )
    state = new_state(args.lat, args.lon, args.lang or "ru")
    for step in steps:
        say, turn_env = (step, env) if isinstance(step, str) else _scripted(ap, step, env)
        out = take_turn(state, say, turn_env)
        state = out.state
        print(
            json.dumps(
                {
                    "say": say,
                    "turn": out.turn.model_dump(mode="json"),
                    "state": state.model_dump(mode="json"),
                },
                ensure_ascii=False,
            )
        )
    return 0


def _scripted(ap: argparse.ArgumentParser, step: dict, env: TurnEnv) -> tuple[str, TurnEnv]:
    """A script step {"say", "lang"?, "time"?}: the message and the environment of this turn only."""
    when = _parse_time(ap, step["time"]) if step.get("time") else env.when
    return step["say"], replace(env, when=when, language=step.get("lang") or env.language)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Astana walking assistant (CLI)")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--q", help="free-text request")
    ap.add_argument("--time", help="override local time, 'YYYY-MM-DD HH:MM' or 'HH:MM' (today)")
    ap.add_argument("--no-llm", action="store_true", help="force rule parser + template text")
    ap.add_argument(
        "--weather",
        default="auto",
        help="'auto' (airport station + Kazhydromet warnings + MET Norway forecast), 'off', or a number = simulated apparent temperature in °C",
    )
    ap.add_argument(
        "--pm25", type=float, default=10.0, help="simulated PM2.5 (only with a numeric --weather)"
    )
    ap.add_argument(
        "--dark",
        action="store_true",
        help="simulate 'after sunset' (only with a numeric --weather)",
    )
    ap.add_argument(
        "--no-walking",
        dest="walking",
        action="store_false",
        help="do not call Valhalla: straight-line estimates only",
    )
    ap.add_argument(
        "--offline",
        action="store_true",
        help="zero network calls: template text, unknown weather, walking legs from the disk cache or straight line",
    )
    ap.add_argument(
        "--simulate-google-down",
        action="store_true",
        help="every gemini link fails (demo of the failover to the other providers)",
    )
    ap.add_argument(
        "--follow-up",
        action="store_true",
        help="--q уточняет прошлый запрос (состояние диалога app/.local/conversation.json, WALKS_STATE_FILE)",
    )
    ap.add_argument(
        "--keep-state",
        action="store_true",
        help="сохранить состояние диалога после ответа (иначе диалог не хранится)",
    )
    ap.add_argument(
        "--mark",
        metavar="POI_ID:СИГНАЛ",
        help=f"анонимная отметка места в app/.local/city_feedback.json ({', '.join(SIGNALS)})",
    )
    ap.add_argument(
        "--profile",
        metavar="UUID|new",
        help="личный профиль app/.local/profiles/<uuid>.json (по умолчанию выключен); new создаёт идентификатор",
    )
    ap.add_argument(
        "--remember",
        action="append",
        metavar="ФЛАГ",
        help="сохранить флаг в профиль после ответа: with_kids, quiet, mobility:stroller, budget:low, no_alcohol ...",
    )
    ap.add_argument("--forget", action="store_true", help="удалить файл профиля (--profile UUID)")
    ap.add_argument(
        "--base-q",
        help="демо-пресет, с --follow-up: текст сценария, с которого начался диалог (от него время и погода)",
    )
    ap.add_argument(
        "--dialog",
        action="store_true",
        help="диалог на walks.dialog: по реплике на строку stdin (или --script), на каждый ход одна JSON-строка",
    )
    ap.add_argument(
        "--script",
        metavar="FILE",
        help='с --dialog: JSON-список реплик (строки или {"say": ..., "lang": ..., "time": ...})',
    )
    ap.add_argument(
        "--lang",
        choices=("ru", "kk", "en"),
        help="с --dialog и --events: язык ответов (по умолчанию ru)",
    )
    cli_layers.add_flags(ap)
    args = ap.parse_args(argv)
    if args.mark:
        return _mark(args.mark)
    layer_exit = cli_layers.run(
        ap, args, parse_time=_parse_time, check_coordinates=_check_coordinates
    )
    if layer_exit is not None:
        return layer_exit
    if (args.forget or args.remember) and not args.profile:
        ap.error("--forget и --remember работают с профилем: укажите --profile UUID")
    uid, profile = _open_profile(args.profile)
    if args.forget:
        print(f"Профиль {uid}: {'удалён' if delete_profile(uid) else 'файла не было'}")
        return 0
    if args.dialog:
        return _dialog_main(ap, args, profile)
    if args.q is None or (args.lat is None and not args.follow_up):
        ap.error("нужны --q и --lat/--lon (с --follow-up координаты берутся из состояния)")
    if not args.q.strip():
        ap.error("--q: пустой запрос, напишите, что вы ищете")
    _check_coordinates(ap, args.lat, args.lon)
    _check_weather(ap, args.weather)
    if profile is not None:
        print(f"Профиль: {uid} (включён: личные флаги читаются из app/.local/profiles)")
    if (env_file := load_env_file()) is not None:
        print(f"Окружение: {env_file.name} (WALKS_ENV={os.environ.get('WALKS_ENV')})")
    if args.offline:
        os.environ["WALKS_OFFLINE"] = "1"
    if args.simulate_google_down:
        os.environ["WALKS_SIMULATE_GOOGLE_DOWN"] = "1"

    when = _parse_time(ap, args.time) if args.time else None

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    conv = _load_state() if args.follow_up else None
    lat, lon = (conv.lat, conv.lon) if conv and args.lat is None else (args.lat, args.lon)
    if replay_only():
        print("ИИ: только записанные ответы демо (WALKS_REPLAY_ONLY=1), модели не вызываются")
    else:
        print(f"Цепочка ИИ, текст: {public_text(chain_text(generation_models()))}")
        print(f"Цепочка ИИ, разбор: {public_text(chain_text(intent_models()))}")
    if pins(args.q, args.base_q):
        s = setup_for(args.q, args.base_q)
        print(
            f"Демо-пресет (WALKS_DEMO_PIN=1): {s.describe()}; --time/--weather/--no-walking не действуют"
        )
        res = recommend_pinned(
            args.q,
            lat,
            lon,
            base_text=args.base_q,
            use_llm=not args.no_llm,
            conversation=conv,
            profile=profile,
        )
    else:
        res = recommend(
            args.q,
            lat,
            lon,
            when,
            use_llm=not args.no_llm,
            weather=_weather(args),
            router=default_router() if args.walking else offline_router(),
            conversation=conv,
            profile=profile,
            feedback=load_feedback(),
        )
    if args.follow_up or args.keep_state:
        _save_state(conversation_after(conv, res))
    for chip in args.remember or []:
        save_profile(uid, remember(profile or Profile(), chip))
    f = res.retrieval.filters
    print(f"Локация (округлена до ~100 м): {res.lat}, {res.lon}; время: {f.checked_at}")
    ir = res.intent
    print(f"Разбор запроса: {ir.parser}" + (f" ({public_text(ir.note)})" if ir.note else ""))
    if ir.rules is not None:
        print(f"  правила: {ir.rules.model_dump_json()}")
    if ir.llm is not None:
        print(f"  ИИ:      {ir.llm.model_dump_json()}")
    if ir.llm_step is not None:
        print(f"  цепочка разбора: {public_text(ir.llm_step.attempts_text())}; {ir.llm_step.ms} мс")
        print(
            f"  ответило звено: {public_text(ir.llm_step.model) or '—'}; cached={ir.llm_step.cached}"
        )
    print(f"Intent: {ir.intent.model_dump_json()}")
    if res.refusal != "none":
        print(f"\nОтказ: {res.generation_note}")
        return 0
    if res.follow_up_note:
        print(f"Диалог: {res.follow_up_note}")
    if res.profile_applied:
        print(f"Профиль: учтено {', '.join(res.profile_applied)}")
    cap = res.constraints.radius_cap_m
    if f.excluded_followup or f.shrink != 1.0 or cap or f.people_marks:
        print(
            f"Память: отсеяно диалогом {f.excluded_followup}, радиус ×{f.shrink:g}"
            + (f", не дальше {cap} м" if cap else "")
            + f", кандидатов с отметками людей {f.people_marks}"
        )
    print(
        f"Радиус: {f.radius_text()}, в радиусе POI: {f.in_radius}, закрытых исключено: {f.excluded_closed}, "
        f"не по времени: {f.excluded_min_stay}, слито сетей: {f.clustered_away}, кандидатов: {f.candidates_returned}"
    )
    for m in f.merged:
        print(f"  объединено: {m.kept_name} ({m.kept_id}) ← {'; '.join(m.merged)}")
    w = res.weather
    effect = (
        "вы просили место на улице: оставлено, прогулку лучше сократить"
        if f.outdoor_request
        else "приоритет помещениям"
    )
    if w is None:
        print("Погода и воздух: не учитываются")
    else:
        if w.temperature_c is None:
            print(
                f"Погода: {adverse_text(w, 'ru')} → {effect}"
                if w.adverse
                else "Погода: неизвестна (не адаптируем)"
            )
        else:
            print(
                f"Погода ({w.source}): {fmt_temp(w.temperature_c)}°C, ощущается {fmt_temp(w.apparent_c)}°C, осадки "
                f"{w.precipitation_mm} мм"
                + (
                    f" → неблагоприятная ({adverse_text(w, 'ru')}): {effect}, "
                    f"радиус пешком ≤ {f.radius_declared_m} м"
                    if w.adverse
                    else ""
                )
            )
        if w.pm25 is None:
            print(
                f"Воздух: PM2.5 неизвестен → {air_driver_text(w, 'ru')}: {effect}"
                if w.air_bad
                else "Воздух: неизвестен (не адаптируем)"
            )
        else:
            print(
                f"Воздух: PM2.5 {w.pm25:.0f} мкг/м³"
                + (f", AQI {w.aqi}" if w.aqi is not None else "")
                + (f" → {air_driver_text(w, 'ru')}: {effect}" if w.air_bad else "")
            )
        for line in _station_lines(w):
            print(line)
        if credits := credit_lines(w, "ru"):
            print("Данные погоды: " + "; ".join(credits))
        if f.sunset:
            dark = (
                "вы просили место на улице: оставлено, освещение в данных неизвестно"
                if f.outdoor_request
                else "парки/площадки/смотровые ниже в рейтинге"
            )
            print(
                f"Солнце: восход {f.sunrise}, закат {f.sunset} ({f.sun_source})"
                + (f" → уже темно: {dark}" if f.dark else "")
            )
    if f.holiday:
        print(f"Праздник: {f.holiday} — «открыто» по OSM понижено до «неизвестно»")
    gstep = res.generation_step
    label = (
        "ИИ " + public_text(res.model) if res.generation == "llm" else "без ИИ (шаблон из данных)"
    )
    print(
        f"Текст рекомендаций: {label}"
        + (f" [{public_text(res.generation_note)}]" if res.generation_note else "")
    )
    if gstep:
        print(f"  цепочка генерации: {public_text(gstep.attempts_text())}; {gstep.ms} мс")
        print(f"  ответило звено: {public_text(gstep.model) or '—'}; cached={gstep.cached}")
    t = res.timings_ms
    print(
        f"Время: разбор {t['intent']} мс, поиск {t['retrieve']} мс, генерация {t['generation']} мс, "
        f"маршрут {t['route']} мс; всего {t['total']} мс"
    )
    if not res.recs:
        print("Ничего не найдено в радиусе доступности — увеличьте время.")
        return 0
    for i, r in enumerate(res.recs, 1):
        poi = r.poi
        lang = res.intent.intent.language
        credit = poi.wikipedia_credit(lang) or poi.official_description_credit(lang)
        print(
            f"\n{i}. {poi.name} [{poi.category}]  источник: данные {poi.data_label()}"
            + (f"; описание: {credit[0]}" if credit else "")
            + f"; данные на {(poi.collected_at or '?')[:10]}"
            + ("; что делать — совет ИИ" if r.generated_idea else "")
            + (f"; [{padding_label(r.padding, lang)}]" if r.padding != "none" else "")
        )
        hours = hours_state_text(r.hours_state, r.hours_source, lang) + (
            f" ({r.hours_note})" if r.hours_note else ""
        )
        if r.hours_source_url:
            hours += f" [{r.hours_source_url}]"
        if r.people is not None and (label := hours_label(r.people, lang)):
            hours += f"; {label} [{source_label(r.people.demo, lang)}]"
        print(
            f"   {r.distance_m} м, {r.travel_min} мин в пути [{METHOD_LABEL[r.walk_method]}]; "
            f"часы: {hours}; уверенность: {r.confidence}"
        )
        print(f"   Почему: {r.why}")
        print(f"   На месте ~{r.time_on_site_min} мин: {r.what_to_do}")
        if r.notes:
            print(f"   Заметки: {r.notes}")
        if r.lrt_hint:
            print(f"   {r.lrt_hint}")
    if res.route:
        rt = res.route
        names = {r.poi.id: r.poi.name for r in res.recs}
        print(
            "\nМини-маршрут: "
            + " → ".join(names[s] for s in rt.stops)
            + f"; в пути {rt.walk_min_total}+{rt.return_min} мин [{METHOD_LABEL[rt.method]}], "
            f"на месте {rt.on_site_min_total} мин "
            f"({'сокращено под бюджет: ' if rt.shrunk else ''}{'+'.join(map(str, rt.stay_min))}), "
            f"итого {rt.total_min} из {rt.budget_min} мин: {'укладывается' if rt.fits else 'НЕ укладывается'}"
            + (f"; не вошло в маршрут: {len(rt.dropped)}" if rt.dropped else "")
        )
    print(f"Пешие отрезки: {dict(res.walk_stats)}; LRT: {res.lrt_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
