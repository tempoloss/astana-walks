"""The head of a refined answer («Поближе: …», «Другие места: …»): the change in plain words, and never a claim the
answer cannot keep — «поближе» with nothing nearer says so, «без алкоголя» says how many places it left out, «с Wi-Fi»
only of a place whose record or people's marks say Wi-Fi or sockets. Also the plain parts of a search turn built from
the pipeline's result: its route, its meta and the one voice of a refined AI answer."""

from __future__ import annotations

from .attributes import has_socket, has_wifi, local_food_signal
from .dialog_strings import s
from .dialog_types import Meta, Route, ShownPlace
from .followup import FollowUp
from .generate import template_rec
from .i18n import category_name, public_text
from .models import Recommendation, Result


def route_of(res: Result, ids: set[str]) -> Route | None:
    rt = res.route
    if rt is None or not set(rt.stops) <= ids:
        return None
    return Route(
        stops=rt.stops,
        legs_min=rt.legs_min,
        legs_m=rt.legs_m,
        stay_min=rt.stay_min,
        walk_min_total=rt.walk_min_total,
        return_min=rt.return_min,
        total_min=rt.total_min,
        budget_min=rt.budget_min,
        fits=rt.fits,
        method=rt.method,
        kind="plan" if len(rt.stops) > 1 and res.intent.intent.plan_order else "nearest",
    )


def meta_of(res: Result, change: str) -> Meta:
    cached = bool(res.generation_step and res.generation_step.cached) or bool(
        res.intent.llm_step and res.intent.llm_step.cached
    )
    return Meta(
        parser=res.intent.parser,
        generation=res.generation,
        model=public_text(res.model) or None,
        cached=cached,
        generation_retry=res.generation_retry,
        ms=res.timings_ms.get("total", 0),
        continued=res.continued,
        change=change,
        intent=res.intent.intent.model_dump(mode="json"),
        note=public_text(res.intent.note),
        radius_m=res.retrieval.filters.radius_effective_m,
    )


def one_voice(
    recs: list[Recommendation], generation: str, fu: FollowUp | None
) -> list[Recommendation]:
    """After «ещё / другое» an answer written by the AI never carries a back-filled card written from a template
    (another voice, another badge): the template cards are left out. A first answer keeps its cards, each one
    says by `text_source` whose words it has."""
    if fu is None or not fu.more or generation != "llm":
        return recs
    voiced = [r for r in recs if r.text_source == "llm"]
    return voiced or recs


def _wifi_backed(r: Recommendation) -> bool:
    return (
        has_wifi(r.poi)
        or has_socket(r.poi)
        or bool(r.people and (r.people.wifi or r.people.socket))
    )


def _label(fu: FollowUp, lang: str) -> str:
    parts = [
        *([s("ch_closer", lang)] if fu.closer else []),
        *([s("ch_more", lang)] if fu.more else []),
        *([s("ch_no_alcohol", lang)] if fu.no_alcohol else []),
        *({"low": [s("ch_cheaper", lang)], "high": [s("ch_pricier", lang)]}.get(fu.budget, [])),
        *([s(f"ch_kids_{fu.with_kids}", lang)] if fu.with_kids != "keep" else []),
        *([s("ch_quiet", lang)] if fu.quiet == "yes" else []),
        *([s("ch_wifi", lang)] if fu.wifi_socket == "yes" else []),
        *([s("ch_longer" if fu.extra_min > 0 else "ch_shorter", lang)] if fu.extra_min else []),
        *([s("ch_mode", lang)] if fu.mode != "keep" else []),
    ]
    text = ", ".join(parts)
    return text[:1].upper() + text[1:]


def closer_order(
    recs: list[Recommendation], shown: list[ShownPlace], res: Result, lang: str
) -> list[Recommendation]:
    """«поближе»: the nearest of the kind the answer led with first, as the word promises; after «бешбармак» the
    places whose record says Kazakh food first, never a nearer sushi bar. When nothing new of that kind is nearer, the
    nearest place of the last answer stays first (its card as it was shown), never a farther one under «ближайшее»."""
    first_kind = shown[0].kind if shown else ""
    local = res.intent.intent.local_food
    out = sorted(
        recs,
        key=lambda r: (
            local and not local_food_signal(r.poi),
            category_name(r.poi.category, lang) != first_kind,
            r.distance_m,
        ),
    )
    near = min((p for p in shown if p.kind == first_kind), key=lambda p: p.distance_m, default=None)
    if (
        near is None
        or any(r.poi.id == near.id for r in out)
        or (out and out[0].distance_m < near.distance_m)
    ):
        return out
    cand = next((c for c in res.retrieval.candidates if c.poi.id == near.id), None)
    if cand is None:
        return out
    kept = template_rec(cand, res.intent.intent, res.weather, res.retrieval.candidates)
    kept = kept.model_copy(update={"distance_m": near.distance_m, "travel_min": near.minutes})
    return [kept, *out][: max(len(out), 1)]


def change_label(
    fu: FollowUp, res: Result, recs: list[Recommendation], shown: list[ShownPlace], lang: str
) -> str:
    """The head of the refined answer `recs` (the nearest first after «поближе»)."""
    lead = (
        shown[0].kind if shown else ""
    )  # «поближе» keeps the kind the answer led with («Al-Shawarma», not desserts)
    nearest = min((p.distance_m for p in shown if p.kind == lead), default=None)
    if fu.closer and recs and nearest is not None and recs[0].distance_m >= nearest:
        return s(
            "ch_closer_none", lang
        )  # nothing new is nearer: said so, the nearest shown stays first
    if fu.no_alcohol and (left := res.retrieval.filters.excluded_alcohol):
        return s("ch_no_alcohol_n", lang, n=left)
    if fu.wifi_socket == "yes" and recs and not _wifi_backed(recs[0]):
        return s("ch_wifi_none", lang)
    return _label(fu, lang)
