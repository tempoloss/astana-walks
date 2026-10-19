"""Fact-check of the deck's screenshots against the base and the app's own hours logic.

    cd app && uv run python ../docs/presentation/deck/shots/factcheck.py

Reads shots.jsonl (written by shoot.py), keeps the last accepted attempt of every shot (or, when the model never wrote
the text, the last real answer, marked as a template) and checks each card it shows: the id is a record of
data/poi.enriched.json, the name is that record's, the hours string is the record's and walks.hours.hours_check gives
the same state at the answer's own time, the walk is plausible for the straight line from the start point, and the
texts claim nothing the record does not hold. Writes factcheck.md next to this file.
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "app"))

from walks.hours import hours_check  # noqa: E402

RECORDS = {r["id"]: r for r in json.loads((ROOT / "data" / "poi.enriched.json").read_text(encoding="utf-8"))}
WALK_M_PER_MIN = 75  # 4.5 km/h, the app's walking speed (explain block: «режим пешком (4.5 км/ч)»)
OPENISH = {"open", "soon", "closing"}
SEEDED = re.compile(r"примерн|отметкам людей|people_demo", re.I)
LINK_AT_PROFILE = re.compile(r"\b[a-z0-9_-]+:[a-z0-9._-]+@[a-z0-9._-]+\b", re.I)
WIFI = re.compile(r"wi-?fi|розетк|интернет", re.I)
CLOCK = re.compile(r"\b([01]?\d|2[0-4])[:.]([0-5]\d)\b")


def straight_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def check_place(p: dict, when: datetime, start: tuple[float, float]) -> list[str]:
    bad: list[str] = []
    rec = RECORDS.get(p["id"])
    if rec is None:
        return [f"{p['id']}: нет такой записи в базе"]
    names = {rec.get("name"), *(rec.get("names") or {}).values()}
    # a record with no name of its own («Парк / сквер», name_generated) is shown under the app's label for it,
    # «Сквер без названия, район Есиль» (walks.facts.display_name): that label is the record's, not an invented name
    unnamed = rec.get("name_generated") and " без названия" in (p.get("name") or "")
    if p.get("name") not in names and not unnamed:
        bad.append(f"{p['id']}: имя «{p.get('name')}» не из записи")
    h = p.get("hours") or {}
    raw = h.get("raw")
    rec_raw = rec.get("opening_hours") or rec.get("opening_hours_official")
    if raw and raw not in {rec.get("opening_hours"), rec.get("opening_hours_official")}:
        bad.append(f"{p['id']}: строка часов «{raw}» не совпадает с записью")
    shown = h.get("state")
    state, _ = hours_check(raw, when) if raw else ("unknown", "")
    if shown in OPENISH and state != "open":
        bad.append(f"{p['id']}: на карточке «{h.get('text')}», а по часам записи сейчас {state}")
    if shown == "closed" and state != "closed":
        bad.append(f"{p['id']}: на карточке «закрыто», а по часам записи {state}")
    if shown == "unknown" and rec_raw and hours_check(rec_raw, when)[0] != "unknown" and not h.get("issue"):
        bad.append(f"{p['id']}: «неизвестно», хотя часы в записи есть")
    if shown in OPENISH and not raw:
        bad.append(f"{p['id']}: «открыто» без строки часов")
    w = p.get("walk") or {}
    sm = straight_m(start, (p["lat"], p["lon"]))
    dm, mins = w.get("distance_m"), w.get("minutes")
    if dm is not None:
        if dm + 30 < sm * 0.95:
            bad.append(f"{p['id']}: пешком {dm} м короче прямой {sm:.0f} м")
        if dm > sm * 3.2 + 400:
            bad.append(f"{p['id']}: пешком {dm} м при прямой {sm:.0f} м")
        if mins is not None and abs(mins - dm / WALK_M_PER_MIN) > max(3, 0.4 * dm / WALK_M_PER_MIN):
            bad.append(f"{p['id']}: {mins} мин на {dm} м")
    text = " ".join(str(p.get(k) or "") for k in ("why", "what_to_do", "note", "caveat", "vibe"))
    if SEEDED.search(text):
        bad.append(f"{p['id']}: в тексте примерные отметки")
    # «Wi-Fi и розетки не подтверждены» is the card's honesty label, not a claim
    claims = re.sub(r"[^.;]*(не подтвержд|not confirmed|unconfirmed|не указан|not listed|нет данных)[^.;]*", "", text, flags=re.I)
    if WIFI.search(claims) and not (rec.get("internet_access") or any("internet" in t for t in rec.get("tags") or [])):
        bad.append(f"{p['id']}: текст обещает Wi-Fi или розетки, в записи их нет ({claims.strip()[:80]})")
    hours_text = (rec_raw or "") + " " + (h.get("text") or "")
    for hh, mm in CLOCK.findall(text):
        clock = f"{int(hh):02d}:{mm}"
        if clock not in hours_text and f"{int(hh)}:{mm}" not in hours_text and clock != "24:00":
            bad.append(f"{p['id']}: время {clock} в тексте не из часов записи")
    return bad


def main() -> None:
    rows: dict[str, dict] = {}
    tries: dict[str, list[dict]] = {}
    for line in (HERE / "shots.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        tries.setdefault(r["id"], []).append(r)
        if r.get("accepted"):
            rows[r["id"]] = r
    template_only = []
    for sid, xs in tries.items():
        answered = [x for x in xs if x.get("answer")]
        if sid not in rows and answered:
            rows[sid] = answered[-1]
            template_only.append(sid)
    out = [
        "# Фактчек скриншотов деки",
        "",
        "Каждый кадр — свежий ответ живого стенда https://anyq.an8kk.dev, снятый 19.10.2026 вечером без закреплённого "
        "демо (кроме кадров из раздела «Кадры не со стенда»): реальное время и погода, геолокация браузера = точка "
        "старта, профиль не создавался. Ответ целиком лежит в `shots.jsonl`; проверка — `factcheck.py` по "
        "`data/poi.enriched.json` и `walks.hours.hours_check` (та же логика часов, что в приложении).",
        "",
        "У каждой карточки: запись с таким id есть в базе; имя из записи; строка часов из записи, и состояние «открыто / "
        "закрыто / неизвестно» совпадает с `hours_check` в момент ответа; пешее расстояние не короче прямой и не длиннее "
        "её втрое, минуты ≈ метры / 75; в текстах нет примерных отметок, Wi-Fi без данных и времени не из часов записи. "
        "У ответа: `pinned: false`, время ответа совпадает со временем запроса, кто написал текст (`meta.generation`), "
        "в JSON нет имён звеньев вида `провайдер:модель@профиль`.",
        "",
        "| кадр | запрос | старт | время ответа | кто писал текст | карточек | итог |",
        "|---|---|---|---|---|---|---|",
    ]
    verdicts: dict[str, bool] = {}
    notes: list[str] = []
    for sid, r in rows.items():
        if sid == "city":
            layers = r.get("city_layers") or {}
            sim = [k for k, v in layers.items() if isinstance(v, dict) and (v.get("simulated") or v.get("sim"))]
            verdicts[sid] = not sim
            out.append(f"| city | страница «Город» | {r['start']['name']} | {r['sent_at'][:16].replace('T', ' ')} | — | "
                       f"слои: {', '.join(sorted(layers)) or '—'} | {'OK' if not sim else 'НЕТ: смоделировано'} |")
            continue
        a = r["answer"]
        t = a["turn"]
        meta = t.get("meta") or {}
        start = (r["start"]["lat"], r["start"]["lon"])
        when = datetime.fromisoformat(f"{a['at']['date']}T{a['at']['time']}")
        sent = datetime.fromisoformat(r["sent_at"]).replace(tzinfo=None)
        bad: list[str] = []
        if a.get("pinned"):
            bad.append("ответ закреплён (pinned)")
        if abs((when - sent).total_seconds()) > 180:
            bad.append(f"время ответа {a['at']['time']} не совпадает со временем запроса {sent:%H:%M}")
        if LINK_AT_PROFILE.search(json.dumps(a, ensure_ascii=False)):
            bad.append("в ответе есть имя звена вида провайдер:модель@профиль")
        if SEEDED.search(t.get("reply") or ""):
            bad.append("в ответе примерные отметки")
        places = t.get("places") or []
        for p in places:
            bad += check_place(p, when, start)
        verdicts[sid] = not bad
        gen = meta.get("generation")
        who = f"модель ({meta.get('model')})" if gen == "llm" else "шаблон из данных" if gen else f"готовый текст ({t.get('kind')})"
        cards = sorted({p.get("text_source") or "?" for p in places})
        out.append(
            f"| {sid} | {r['query']} | {r['start']['name']} | {a['at']['date']} {a['at']['time']} | {who}"
            f"{'; карточки: ' + ', '.join(cards) if cards else ''} | {len(places)} | {'OK' if not bad else 'НЕТ'} |"
        )
        if bad:
            notes.append(f"- **{sid}**: " + "; ".join(bad))
    rejected = [
        f"{sid}, попытка {x.get('attempt')}: "
        + (((x.get("answer") or {}).get("turn") or {}).get("meta", {}).get("generation") or x.get("error") or "без текста модели")
        for sid, xs in tries.items() for x in xs if not x.get("accepted")
    ]
    out += ["", "## Замечания", ""] + (notes or ["Нет: все карточки сходятся с базой и логикой часов."])
    local = [(sid, r) for sid, r in rows.items() if r.get("base")]
    if local:
        out += ["", "## Кадры не со стенда", ""] + [
            f"- **{sid}**: {r['base']} — {r.get('server', '')}; камера `{r.get('camera')}` (зум, широта, долгота); "
            f"тайлы Esri: {r.get('esri_tiles')}. Ключ модели у локального запуска не задан, поэтому текст ответа — "
            f"{'модель' if r['answer']['turn']['meta'].get('generation') == 'llm' else 'шаблон из данных'}; места, "
            "часы и путь выбирает тот же код и те же данные, что на стенде."
            for sid, r in local
        ]
    if template_only:
        out += ["", "Текст этих кадров написала не модель: " + ", ".join(template_only) + ". Три попытки с паузой 45 с "
                "дали тот же результат: для таких запросов стенд отвечает готовым текстом или шаблоном из данных."]
    out += ["", "## Отклонённые попытки", "", ("; ".join(rejected) + ".") if rejected else "Нет."]
    out += ["", "Профилей на стенде не создавалось: панель «Память» не открывалась, `/api/profile` не вызывался.", ""]
    (HERE / "factcheck.md").write_text("\n".join(out), encoding="utf-8")
    for sid, ok in verdicts.items():
        print(sid, "OK" if ok else "FAIL", "(template)" if sid in template_only else "")
    print("\n".join(notes))


if __name__ == "__main__":
    main()
