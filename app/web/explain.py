"""What the page's «Данные» view says about one answer, from the pipeline's Result (the python-only `Outcome.result` of
walks.dialog): every number and every step behind the answer, grouped as sections of lines (API readers; the page no
longer renders it). Lines may carry **bold** and `code`. The conditions of the answer (weather, air, darkness, a
holiday) are part of the dialogue's own lead sentence (`walks.dialog_lead`)."""

from __future__ import annotations

from i18n import tr
from walks.i18n import holiday_name as holiday_in
from walks.i18n import public_text
from walks.models import Result
from walks.pipeline import COORD_DECIMALS
from walks.weather import (
    BAD_PM25,
    adverse_text,
    air_driver_text,
    attribution,
    fmt_temp,
    source_details,
    warning_text,
)

# ---------------------------------------------------------------- «Какие данные использованы»


def _weather_line(res: Result, lang: str, src: str) -> str:
    """The weather and what it did: the measured numbers when there are any, always the real driver of the verdict."""
    f, w = res.retrieval.filters, res.weather
    if w is None:
        return tr("dp_wx_off", lang)
    if w.temperature_c is None and not w.adverse:
        return tr("dp_wx_unknown", lang)
    tail = tr("dp_wx_ok", lang)
    if w.adverse:
        key = "dp_wx_kept" if f.outdoor_request else "dp_wx_bad"
        tail = tr(key, lang, reason=adverse_text(w, lang), m=f.radius_declared_m)
    if w.temperature_c is None:
        return tr("dp_wx_driver", lang) + tail
    head = tr(
        "dp_wx",
        lang,
        src=src,
        t=fmt_temp(w.temperature_c),
        a=fmt_temp(w.apparent_c),
        p=f"{w.precipitation_mm:g}",
    )
    return head + tail


def _air_line(res: Result, lang: str, src: str) -> str:
    """The air and what it did: the PM2.5 value when it is known; when the air is bad, its real driver (the PM2.5
    value, smoke / haze at the station, the НМУ notice) and whether it moved the choice indoors or was only said."""
    f, w = res.retrieval.filters, res.weather
    if w is None:
        return ""
    if w.air_bad:
        key = "dp_air_kept" if f.outdoor_request else "dp_air_bad"
        tail = tr(key, lang, reason=air_driver_text(w, lang))
    else:
        tail = tr("dp_air_ok", lang, limit=f"{BAD_PM25:g}")
    if w.pm25 is None:
        return tr("dp_air_nopm", lang) + tail if w.air_bad else tr("dp_air_unknown", lang)
    head = tr("dp_air", lang, src=src, pm=f"{w.pm25:.0f}")
    return head + (tr("dp_air_aqi", lang, aqi=w.aqi) if w.aqi is not None else "") + tail


def _weather_lines(res: Result, lang: str) -> list[str]:
    f, w = res.retrieval.filters, res.weather
    if w is None:
        return [tr("dp_wx_off", lang)]
    sim = w.source == "manual"
    forecast = tr("src_sim", lang) if sim else tr("dp_src_met", lang)
    air = tr("src_sim", lang) if sim else tr("dp_src_om", lang)
    src = (
        attribution(w, lang) if w.source == "metar" else forecast
    )  # the station's own words when it is the source
    sun_src = tr("dp_sun_calc", lang) if f.sun_source == "расчёт" else f.sun_source
    dark = "dp_sun_dark_kept" if f.outdoor_request else "dp_sun_dark"
    out = [
        _weather_line(res, lang, src),
        _air_line(res, lang, air),
        tr("dp_sun", lang, rise=f.sunrise, sset=f.sunset, src=sun_src)
        + tr(dark if f.dark else "dp_sun_light", lang),
    ]
    if w.observed_at:
        out.append(source_details(lang))
    out += [warning_text(warning, lang) for warning in w.warnings]
    return out


def _parse_lines(res: Result, lang: str) -> list[str]:
    ir = res.intent
    how = tr("dp_parse_llm" if ir.parser == "rules+llm" else "dp_parse_rules", lang)
    note = f" — {public_text(ir.note, lang)}" if ir.note else ""
    out = [tr("dp_parse", lang, how=how, note=note)]
    if ir.llm_step is not None:
        cached = tr("dp_cached", lang) if ir.llm_step.cached else ""
        chain = public_text(ir.llm_step.attempts_text(), lang)
        out.append(tr("dp_chain_parse", lang, chain=chain, ms=ir.llm_step.ms) + cached)
    return out


def _retrieval_lines(res: Result, lang: str) -> list[str]:
    f = res.retrieval.filters
    out = [
        tr(
            "dp_filters",
            lang,
            mode=tr(f"mode_{f.mode}", lang),
            v=f"{f.speed_kmh:g}",
            b=f.time_budget_min,
            s=int(f.travel_share * 100),
            r=f.radius_text(lang),
            cats=", ".join(f.categories_requested) or tr("dp_any", lang),
            relaxed=tr("dp_relaxed", lang) if f.categories_relaxed else "",
            night=tr("yes" if f.night_mode else "no", lang),
            kw=", ".join(f.keywords) or "—",
        ),
        tr(
            "dp_candidates",
            lang,
            total=f.pois_total,
            inr=f.in_radius,
            closed=f.excluded_closed,
            n=f.candidates_returned,
            unk=f.hours_unknown,
        ),
    ]
    if f.excluded_min_stay or f.clustered_away:
        out.append(tr("dp_time_cut", lang, n=f.excluded_min_stay, chains=f.clustered_away))
    out += [
        tr("dp_merged", lang, name=m.kept_name, id=m.kept_id, items="; ".join(m.merged))
        for m in f.merged
    ]
    return out


def _memory_lines(res: Result, lang: str) -> list[str]:
    f, c = res.retrieval.filters, res.constraints
    out: list[str] = []
    if res.continued:
        out.append(
            tr("mem_dialogue", lang, note=res.follow_up_note or tr("mem_dialogue_default", lang))
        )
    if c.radius_cap_m or c.radius_factor != 1.0 or c.exclude_ids or c.no_alcohol:
        out.append(
            tr(
                "mem_constraints",
                lang,
                f=f"{c.radius_factor:g}",
                cap=tr("mem_cap", lang, m=c.radius_cap_m) if c.radius_cap_m else "",
                n=len(c.exclude_ids),
                alc=tr("yes" if c.no_alcohol else "no", lang),
                ex=f.excluded_followup,
            )
        )
    if res.profile_applied:
        items = ", ".join(tr(f"profile_code_{code}", lang) for code in res.profile_applied)
        out.append(tr("mem_profile", lang, items=items))
    if f.people_marks:
        out.append(tr("mem_marks", lang, n=f.people_marks))
    return out


def _generation_lines(res: Result, lang: str) -> list[str]:
    gs = res.generation_step
    if res.generation == "llm":
        out = [tr("dp_text_llm", lang, model=public_text(res.model, lang))]
    else:
        out = [tr("dp_text_tpl", lang, note=public_text(res.generation_note, lang))]
    if gs is not None:
        cached = tr("dp_cached", lang) if gs.cached else ""
        chain = public_text(gs.attempts_text(), lang)
        out.append(tr("dp_chain_gen", lang, chain=chain, ms=gs.ms) + cached)
    if res.generation_retry:
        out.append(tr(f"dp_retry_{res.generation_retry}", lang))
    if tm := res.timings_ms:
        out.append(
            tr(
                "dp_timing",
                lang,
                i=tm["intent"],
                r=tm["retrieve"],
                g=tm["generation"],
                rt=tm["route"],
                total=tm["total"],
            )
        )
    if res.unbacked_claims_removed:
        out.append(tr("dp_unbacked", lang, n=res.unbacked_claims_removed))
    if res.llm_payload is None and res.intent.parser == "rules+llm":
        out.append(tr("dp_payload_none", lang))
    if res.intent.parser == "rules+llm":
        out.append(tr("dp_parse_sent", lang))
    return out


def _candidates(res: Result, lang: str) -> dict:
    keys = ("col_poi", "col_cat", "col_m", "col_min", "col_hours", "col_score", "col_reasons")
    return {
        "columns": [tr(k, lang) for k in keys],
        "rows": [
            [
                c.poi.name,
                c.poi.category,
                c.distance_m,
                c.travel_min,
                c.hours_state,
                c.score,
                ", ".join(c.reasons),
            ]
            for c in res.retrieval.candidates
        ],
    }


def explain(res: Result, lang: str, *, manual_time: bool) -> dict:
    """Every number and step behind one answer, grouped as the «Данные» page shows it."""
    f = res.retrieval.filters
    setting = [
        tr("dp_location", lang, lat=res.lat, lon=res.lon, n=COORD_DECIMALS),
        tr("dp_time", lang, t=f.checked_at) + (tr("dp_time_manual", lang) if manual_time else ""),
        *_weather_lines(res, lang),
    ]
    if f.holiday:
        setting.append(tr("dp_holiday", lang, name=holiday_in(f.holiday, lang)))
    stats = ", ".join(f"{k}: {v}" for k, v in res.walk_stats.items()) or "—"
    setting.append(tr("dp_walk", lang, stats=stats))
    if res.lrt_note:
        setting.append(tr("dp_lrt", lang, note=res.lrt_note))
    ir = res.intent
    return {
        "query": res.query,
        "sections": [
            {"id": "setting", "lines": setting},
            {"id": "parse", "lines": _parse_lines(res, lang)},
            {"id": "search", "lines": _retrieval_lines(res, lang)},
            {"id": "memory", "lines": _memory_lines(res, lang)},
            {"id": "text", "lines": _generation_lines(res, lang)},
        ],
        "candidates": _candidates(res, lang),
        "json": {
            "rules": ir.rules.model_dump(mode="json") if ir.rules is not None else None,
            "ai": ir.llm.model_dump(mode="json") if ir.llm is not None else None,
            "intent": ir.intent.model_dump(mode="json"),
            "payload": res.llm_payload,
        },
    }
