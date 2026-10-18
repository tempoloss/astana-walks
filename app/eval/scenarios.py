"""Render docs/scenarios.md from eval/cases.json and the latest eval/results: the five scenarios of the brief in
detail, the whole case matrix in short, and the limitations that the failing cases show."""

from __future__ import annotations

from pathlib import Path

from walks.intent import DEFAULT_BUDGET_MIN, LONG_VISIT_BUDGET_MIN
from walks.radius import (
    ADVERSE_WALK_CAP_M,
    CIRCUITY,
    KIDS_WALK_MAX_MIN,
    MAX_RADIUS_M,
    MIN_RADIUS_M,
    RADIUS_STEPS,
    ROUTED_DETOUR,
    SPEED_KMH,
    STROLL_TRAVEL_SHARE,
    TRAVEL_SHARE,
)
from walks.retrieve import MIN_IN_CATEGORY, NIGHT_END, NIGHT_START
from walks.stay import TIGHT_FIT_MARGIN_MIN
from walks.walking import FALLBACK_DETOUR
from walks.weather import BAD_PM25, COLD_APPARENT_C, HEAVY_PRECIP_MM

from .cases import DOCS_SCENARIOS, case_when, describe_conditions, load_cases
from .metrics import UNKNOWN_HOURS_LABEL, WHEELCHAIR_LABEL, WIFI_NEGATIVE_LABEL
from .report import (
    ABSTAIN_ONLY,
    BASE,
    CANDIDATE,
    HISTORICAL_RUNS,
    MODES,
    load_runs,
    metric_rows,
    set_roles_text,
    summarize,
)

LIMITATION_TEXT = {
    "category_not_allowed": "в радиусе доступности мало мест нужной категории, и поиск добавляет места других "
    "категорий (карточка помечена «Категория вне вашего запроса»); для просьбы «прогулка / тихое кафе / "
    "доступное место» это иногда фастфуд или ресторан",
    "category_forbidden": "то же, но категория заведомо неподходящая (фастфуд для прогулки, детская площадка "
    "для взрослой прогулки)",
    "outdoor_in_cold_or_smog": "при −15°C и ниже или PM2.5 > 35 уличные места только понижаются в рейтинге, а не "
    "исключаются: (1) для «с ребёнком» бонус за совпавшую категорию и «детское» перевешивает штраф за улицу, "
    "а помещений для детей рядом мало: в `poi.json` у EXPO музеев нет в радиусе 3 км, в `poi.enriched.json` "
    "музей у EXPO отсекается фильтром минимального времени (музей ≥ 60 мин при бюджете 60 мин по умолчанию); "
    "(2) выбор «разные категории» (pick_diverse) ставит в тройку парк даже с самым низким баллом, ради новой "
    "категории",
    "walk_too_long": "радиус считается от общего времени, а не от ограничений пользователя (например, "
    "маломобильности)",
    "closed_at_arrival": "закрытое к моменту прихода место попало в выдачу",
    "kids_unsuitable": "в выдаче для семьи оказался бар / ночное заведение",
    "not_step_free": "в выдаче для маломобильного оказалось место с wheelchair=no",
    "open_without_hours": "«открыто» без opening_hours в данных",
    "open_on_holiday": "«открыто» в праздничный день",
    "unknown_not_labeled": "неизвестные часы без пометки на карточке",
    "open_claim_in_text": "в тексте карточки утверждается «работает/открыто» при статусе «неизвестно»: описание "
    "строится из тегов OSM («Работает круглосуточно» из 24/7), а статус в праздник понижен до «неизвестно»",
    "wifi_socket_claim_unsupported": "Wi-Fi/розетки заявлены без подтверждения в данных",
    "wheelchair_unknown_not_flagged": "доступность для колясок не указана в данных и не помечена",
    "over_budget": "маршрут не укладывается во время",
    "duplicate_chain": "две точки одной сети среди рекомендаций",
    "no_recs": "нет ни одной рекомендации",
    "hallucinated_poi": "рекомендован объект, которого нет в датасете",
}


def _short(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def when_text(case: dict) -> str:
    w = case_when(case)
    days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    return f"{w:%d.%m.%Y} ({days[w.weekday()]}) {w:%H:%M}"


def rec_table(run: dict | None, *, llm: bool = False) -> list[str]:
    if run is None:
        return ["_нет прогона_"]
    if not run["recs"]:
        return ["_рекомендаций нет_"]
    viol = run["verdict"]["constraint_violations"]
    lines = [
        "| # | место | категория | источник | часы | пешком, мин | почему |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(run["recs"], 1):
        mark = f" ⚠ {', '.join(viol[r['poi_id']])}" if r["poi_id"] in viol else ""
        why = r["why"] if not llm else f"{r['why']} {r['what_to_do']}"
        lines.append(
            f"| {i} | {_cell(r['name'])} | {r['category']} | {r['source']} | {r['hours_state']} | "
            f"{r['walk_min']} | {_cell(_short(why))}{mark} |"
        )
    return lines


def verdict_text(run: dict | None) -> str:
    if run is None:
        return "нет прогона"
    v = run["verdict"]
    if v["all_ok"]:
        return "✅ все ограничения и проверки честности выполнены"
    return "❌ " + ", ".join(v["violations"])


def _google_answer(run: dict) -> bool:
    """True when a Google link wrote the text of this run: the AI-mode tables show nothing else."""
    return run["model_link"].startswith("gemini:")


def incomplete_data_line(run: dict | None, case: dict) -> str:
    """What the system did about missing data in this answer, from the facts of the run (no free text)."""
    if run is None or not run["recs"]:
        return ""
    recs, parts = run["recs"], []
    unknown = [r for r in recs if r["hours_state"] == "unknown"]
    if unknown:
        parts.append(
            f"у {len(unknown)} из {len(recs)} рекомендаций часов работы нет в данных или неприменимы: статус "
            f"«неизвестно» и пометка «{UNKNOWN_HOURS_LABEL.rstrip('.')} — уточните перед выходом», "
            "«открыто» не утверждается"
        )
    if run["filters"]["holiday"]:
        parts.append(
            f"праздник ({run['filters']['holiday']}): «открыто» по OSM понижено до «неизвестно» с пометкой"
        )
    if run["filters"]["categories_relaxed"]:
        parts.append(
            "мест нужной категории в радиусе меньше трёх: добавлены другие категории с пометкой "
            "«Категория вне вашего запроса»"
        )
    if case["expected"].get("needs_wifi_socket"):
        bad = sum(WIFI_NEGATIVE_LABEL in (r["notes"] or "") for r in recs)
        parts.append(
            f"Wi-Fi/розетки: подтверждены в данных у {len(recs) - bad} из {len(recs)}, для остальных — пометка "
            "«Wi-Fi/розетки в данных не подтверждены»"
        )
    if case["expected"].get("step_free"):
        bad = sum(WHEELCHAIR_LABEL in (r["notes"] or "") for r in recs)
        parts.append(
            f"доступность: у {bad} из {len(recs)} не указана в данных, помечено «{WHEELCHAIR_LABEL}»; "
            "места с wheelchair=no исключаются"
        )
    text = "; ".join(parts)
    return f"{text[0].upper()}{text[1:]}." if parts else ""


def _expected_text(case: dict) -> str:
    e = case["expected"]
    bits = []
    if e.get("allowed_categories"):
        bits.append("категории: " + ", ".join(e["allowed_categories"]))
    if e.get("forbidden_categories"):
        bits.append("нельзя: " + ", ".join(e["forbidden_categories"]))
    if e.get("max_walk_min_one_way") is not None:
        bits.append(f"дорога в одну сторону ≤ {e['max_walk_min_one_way']} мин")
    if e.get("budget_min") is not None:
        bits.append(f"маршрут туда-обратно ≤ {e['budget_min']} мин")
    if e.get("indoor_preferred"):
        bits.append("только помещения (непогода / плохой воздух)")
    if e.get("kids_ok"):
        bits.append("подходит детям")
    if e.get("must_flag_unknown_hours"):
        bits.append("неизвестные часы обязательно помечены")
    return "; ".join(bits)


def _case_section(case: dict, runs: dict[tuple[str, str], dict[str, dict]]) -> list[str]:
    cid, o = case["id"], case["origin"]
    base, cand = (
        runs.get((BASE, "offline"), {}).get(cid),
        runs.get((CANDIDATE, "offline"), {}).get(cid),
    )
    lines = [
        f"### {cid}: «{case['query']}»",
        "",
        f"- **Вход:** {o['name']} ({o['lat']}, {o['lon']}); {when_text(case)}; {describe_conditions(case)}; "
        f"запрос: «{case['query']}».",
        f"- **Ожидаемый тип ответа:** {case['expected']['notes']} Проверяется: {_expected_text(case)}.",
        "",
        f"**Система, `{BASE}.json`, офлайн (шаблон):** {verdict_text(base)}",
        "",
        *rec_table(base),
        "",
    ]
    if cand is not None:
        same = (
            base is not None
            and base["recs"][:1]
            and cand["recs"][:1]
            and base["recs"][0]["poi_id"] == cand["recs"][0]["poi_id"]
        )
        lines += [
            f"**С `{CANDIDATE}.json`, офлайн:** {verdict_text(cand)}"
            + (" (top-1 тот же)" if same else " (top-1 изменился)"),
            "",
            *rec_table(cand),
            "",
        ]
    for ds in (BASE, CANDIDATE):
        for mode in ("llm", "llm-public"):
            llm = runs.get((ds, mode), {}).get(cid)
            if llm is not None and _google_answer(llm):
                lines += [
                    f"**ИИ-режим, `{ds}.json`, звено `{llm['model_link']}`:** {verdict_text(llm)}"
                    + (f" _({llm['generation_note']})_" if llm["generation_note"] else "")
                    + (
                        f" Цепочка: {llm['generation_trace']}."
                        if llm.get("generation_trace")
                        else ""
                    ),
                    "",
                    *rec_table(llm, llm=True),
                    "",
                ]
    line = incomplete_data_line(base, case)
    if line:
        lines += [f"**Как система обрабатывает неполные данные:** {line}", ""]
    return lines


def _matrix(cases: list[dict], runs: dict[tuple[str, str], dict[str, dict]]) -> list[str]:
    base = runs.get((BASE, "offline"), {})
    lines = ["| кейс | вход | top-1 (`poi.json`) | вердикт |", "|---|---|---|---|"]
    for c in cases:
        run = base.get(c["id"])
        top = "—"
        if run and run["recs"]:
            r = run["recs"][0]
            top = f"{r['name']} ({r['category']}, {r['hours_state']}, {r['walk_min']} мин)"
        lines.append(
            f"| `{c['id']}` | {_cell(c['label'])}; «{_short(c['query'], 60)}» | {_cell(top)} | {_cell(verdict_text(run))} |"
        )
    return lines


def _limitations(cases: list[dict], runs: dict[tuple[str, str], dict[str, dict]]) -> list[str]:
    base = runs.get((BASE, "offline"), {})
    by_code: dict[str, list[str]] = {}
    for c in cases:
        run = base.get(c["id"])
        if run:
            for code in run["verdict"]["violations"]:
                by_code.setdefault(code, []).append(c["id"])
    if not by_code:
        return ["Среди проверенных кейсов нарушений не найдено."]
    lines = []
    for code, ids in sorted(by_code.items(), key=lambda kv: -len(kv[1])):
        shown = ", ".join(f"`{i}`" for i in ids[:6]) + (" …" if len(ids) > 6 else "")
        lines.append(
            f"- **{code}** — {len(ids)} из {len(base)} кейсов ({shown}): {LIMITATION_TEXT.get(code, '')}."
        )
    return lines


def _assumptions() -> list[str]:
    """The defaults and constants the answers and the numbers above rest on, read from the code so that the
    text cannot drift from it."""
    steps = ", ".join(f"×{s:g}" for s in RADIUS_STEPS)
    return [
        "Часть значений выведена из внешних нормативов и публикаций (ссылки в строках ниже), часть "
        "остаётся продуктовым допущением и помечена так; оценка и ответы определяются ими в обоих случаях. "
        "Проверка источников — `collect/SOURCES.md` §18.7.",
        "",
        f"- **Время не указано.** Бюджет по умолчанию {DEFAULT_BUDGET_MIN} мин (прогулка / кофе / вечер); "
        f"{LONG_VISIT_BUDGET_MIN} мин, если в запросе ребёнок, музей или турист: визит в музей или на "
        "площадку не укладывается в час вместе с дорогой. Выбор записывается в примечание разбора.",
        "- **Рейс.** При фразе «до вылета / до поезда» 60 мин резервируются на аэропорт, на прогулку "
        "остаётся остальное (не меньше 30 мин).",
        f"- **Дорога.** Скорость пешком {SPEED_KMH['walk']:g} км/ч — нижняя граница мета-анализа обычного "
        "темпа (Murtagh et al., 35 исследований, 14 015 взрослых: 1.31 м/с, т. е. 4.57–4.86 км/ч) с зимней "
        f"поправкой на снег/лёд (Ryeng: −6.5…−17 %, Comeau: −15.9 %). Расстояние по прямой × {CIRCUITY:g} "
        f"(радиус поиска) и × {FALLBACK_DETOUR:g} (время пешком без Valhalla, так считает и оценка) — "
        "**допущение** транспортной практики, валидируется на кэше Valhalla. "
        f"На дорогу туда и обратно уходит {TRAVEL_SHARE:.0%} бюджета ({STROLL_TRAVEL_SHARE:.0%} для чистой "
        f"прогулки) — **допущение**; радиус от {MIN_RADIUS_M} до {MAX_RADIUS_M} м; в мороз, ливень и смог "
        f"пешком не дальше {ADVERSE_WALK_CAP_M} м — **допущение** (порог −15 °C мягче казахстанских "
        "нормативов опасного явления, цитируемого основания ровно на −15 нет).",
        f"- **Расширение радиуса и добор.** Если нужной категории в радиусе нет, радиус растёт ступенями "
        f"({steps}), если после этого мест нужной категории меньше {MIN_IN_CATEGORY} — добираются другие "
        "категории (кроме фастфуда, баров днём и «прочего»; для прогулки — только парк, достопримечательность, "
        "смотровая, кафе, музей). Добор берёт места только внутри заявленного радиуса (по бюджету времени), "
        "расширенный радиус на него не распространяется. Такие места получают поле `padding` "
        "(`expanded` / `backfill`) и метку на карточке; доля таких рекомендаций — метрика padding.",
        f"- **С ребёнком.** Бюджет по умолчанию {LONG_VISIT_BUDGET_MIN} мин (см. выше); в одну сторону пешком "
        f"не дальше {KIDS_WALK_MAX_MIN} мин (`KIDS_WALK_MAX_MIN`, считается с коэффициентом дороги "
        f"×{ROUTED_DETOUR:g}, чтобы место, прошедшее фильтр, не показывало на карточке больше). "
        f"Значение {KIDS_WALK_MAX_MIN} введено в caf7692, после того как два детских кейса main не проходили "
        "по пешему лимиту. По внешним числам оно **мягче** норматива, а не консервативно: СН РК 3.01-01-2013 "
        "задаёт доступность школы ≤ 500 м и детсада ≤ 300 м, а наш лимит 15 мин = `kids_walk_radius_m()` = 865 м "
        "по прямой (4.5 км/ч) и ≈1125 м с коэффициентом дороги — намеренно выше школьного норматива, чтобы не "
        "отсекать легальные дальние площадки; для дошкольника норматив жёстче, ужесточение под детский пресет — "
        "после 22.10. Введено как продуктовое допущение («детская "
        "выносливость пешком около 15 мин в одну сторону», `walks/radius.py`) и выбрано в диапазоне пределов "
        "кейсов (с ребёнком: 12 или 15 мин в `cases.json`, 15 или 20 в `holdout_cases.json`), поэтому main "
        "и holdout в этой части не полностью независимы. Независимая проверка — holdout3 (написан после "
        "исправлений по одному `eval/SCHEMA.md`, без доступа к коду); holdout2 слепым был только до "
        "исправлений. Данных горожан, которые задавали бы порог, нет.",
        f"- **Минимальное время на месте.** Место, где обычно нужно больше времени, чем осталось после дороги "
        f"туда и обратно, отбрасывается; превышение до {TIGHT_FIT_MARGIN_MIN} мин остаётся с пометкой "
        "«впритык».",
        f"- **Непогода.** Ощущаемая температура ≤ {COLD_APPARENT_C:g}°C, осадки ≥ {HEAVY_PRECIP_MM:g} мм/ч "
        f"или PM2.5 > {BAD_PM25:g} мкг/м³ — предпочтение помещениям (парки, смотровые, площадки "
        "исключаются, пока есть помещение). Порог PM2.5 = ПДК среднесуточная РК (Приказ МЗ РК "
        "№ ҚР ДСМ-70 от 02.08.2022, 0.035 мг/м³; руководство ВОЗ 2021 строже — 15 мкг/м³, выбор в пользу "
        "РК-норматива осознан). Пороги температуры и осадков — **допущение**.",
        f"- **Ночь.** С {NIGHT_START}:00 до {NIGHT_END:02d}:00; часы работы неизвестны → статус «неизвестно» "
        "с пометкой, «открыто» не утверждается. В государственный праздник «открыто» по OSM понижается до "
        "«неизвестно».",
        "- **Оценка.** Погода, воздух и время берутся из кейса. Наборы кейсов: "
        + set_roles_text()
        + " "
        "Честное число обобщения даёт holdout3, не holdout2. Ожидаемые ограничения кейсов (допустимые "
        "категории, предел пешком, бюджет времени) написаны вручную; смысл полей — в `app/eval/SCHEMA.md`.",
    ]


def _public_ai_run(label: str, s: dict) -> bool:
    """A non-offline run that may be shown: not a historical stress run and not one whose text came from a link
    outside Google (the answers are Gemini's or the template's)."""
    return label not in HISTORICAL_RUNS and all(
        k == "template" or k.startswith("gemini:") for k in s["model_link"]
    )


def _summary_columns(summaries: dict[tuple[str, str], dict]) -> list[tuple[str, str]]:
    return [
        (ds, m)
        for m in MODES
        for ds in (BASE, CANDIDATE)
        if (ds, m) in summaries and (m == "offline" or _public_ai_run(m, summaries[(ds, m)]))
    ]


def _ai_mode_lines(summaries: dict[tuple[str, str], dict]) -> list[str]:
    if any(m != "offline" for _, m in _summary_columns(summaries)):
        return [
            "Колонки `llm*`: пять сценариев задания через публичную цепочку Gemini, кэш ответов выключен; "
            "если звено не ответило, текст шаблонный, и такая строка не считается ответом ИИ (см. `model_link` "
            "в `app/eval/results/summary_*_llm-public.md` и раздел «ИИ-режим» в `app/eval/results/canonical.md`)."
        ]
    return ["ИИ-режим измерен отдельно."]


def render(
    cases: list[dict],
    runs: dict[tuple[str, str], dict[str, dict]],
    summaries: dict[tuple[str, str], dict],
) -> str:
    out = [
        "# Сценарии и оценка качества",
        "",
        "> Файл сгенерирован командой `cd app && uv run poe eval` (`eval/report.py` → `eval/scenarios.py`) из "
        "`app/eval/cases.json` и `app/eval/results/`. Вручную не править.",
        "",
        f"Кейсов: {len(cases)}. Время, погода и воздух подставляются из кейса (не живой Open-Meteo), дорога "
        "считается по прямой × 1.3 (без Valhalla), чтобы датасеты сравнивались в одинаковых условиях. Основной "
        f"датасет — `{BASE}.json` (текущий), кандидат — `{CANDIDATE}.json`. Офлайн-режим: тот же поиск, текст из "
        "шаблона.",
        "",
        *_ai_mode_lines(summaries),
        "",
        "## Сводка метрик",
        "",
    ]
    cols = _summary_columns(summaries)
    out += [
        "| метрика | "
        + " | ".join(f"{ds} / {m} ({summaries[(ds, m)]['cases']})" for ds, m in cols)
        + " |"
    ]
    out += ["|---|" + "---|" * len(cols)]
    out += [
        f"| {label} | " + " | ".join(cells) + " |"
        for label, cells in metric_rows([summaries[c] for c in cols], skip=ABSTAIN_ONLY)
    ]
    out += ["", "Подробности: `app/eval/results/summary_*.md`, `comparison_*.md`.", ""]
    out += ["## Пять сценариев задания", ""]
    for c in cases:
        if c.get("tz"):
            out += _case_section(c, runs)
    out += ["## Все кейсы (матрица: место × время × погода × запрос)", ""]
    out += _matrix(cases, runs)
    out += ["", "## Ограничения (по кейсам с нарушениями, `poi.json`, офлайн)", ""]
    out += _limitations(cases, runs)
    out += ["", "## Допущения", "", *_assumptions()]
    return "\n".join(out) + "\n"


def write_scenarios(path: Path = DOCS_SCENARIOS) -> Path:
    cases = load_cases()
    runs: dict[tuple[str, str], dict[str, dict]] = {}
    summaries: dict[tuple[str, str], dict] = {}
    for ds in (BASE, CANDIDATE):
        for mode in MODES:
            rs = load_runs(ds, mode)
            if rs:
                runs[(ds, mode)] = {r["case_id"]: r for r in rs}
                summaries[(ds, mode)] = summarize(rs, cases)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(cases, runs, summaries), encoding="utf-8", newline="\n")
    return path
