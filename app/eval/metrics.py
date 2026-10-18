"""Per-case verdict: one pipeline answer judged against `expected` of a case.

Everything is recomputed here from the dataset and the case, independently of the pipeline's own filters
(opening hours are re-evaluated with walks.hours, hallucination is checked against the dataset ids), so a bug in
retrieval cannot hide itself. A record that went through `judge_case` carries the verdict into the JSONL run file;
report.py only aggregates verdicts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta

from rapidfuzz import fuzz

from walks.holidays import holiday_name
from walks.hours import poi_hours
from walks.i18n import LANGS, STRINGS, pick
from walks.models import POI
from walks.names import NAME_RATIO_MIN, name_key
from walks.weather import OUTDOOR_CATEGORIES

from .cases import case_when, indoor_required

# --- violation codes (rec level, "constraints")
CATEGORY_NOT_ALLOWED = "category_not_allowed"
CATEGORY_FORBIDDEN = "category_forbidden"
WALK_TOO_LONG = "walk_too_long"
CLOSED_AT_ARRIVAL = "closed_at_arrival"
OUTDOOR_IN_BAD_AIR_OR_COLD = "outdoor_in_cold_or_smog"
KIDS_UNSUITABLE = "kids_unsuitable"
NOT_STEP_FREE = "not_step_free"
# --- violation codes (rec level, "honesty")
OPEN_WITHOUT_HOURS = "open_without_hours"
OPEN_ON_HOLIDAY = "open_on_holiday"
UNKNOWN_NOT_LABELED = "unknown_not_labeled"
OPEN_CLAIM_IN_TEXT = "open_claim_in_text"
WIFI_CLAIM_UNSUPPORTED = "wifi_socket_claim_unsupported"
ACCESS_NOT_FLAGGED = "wheelchair_unknown_not_flagged"
# --- case level
OVER_BUDGET = "over_budget"
DUPLICATE_CHAIN = "duplicate_chain"
NO_RECS = "no_recs"
HALLUCINATED = "hallucinated_poi"

CONSTRAINT_CODES = {
    CATEGORY_NOT_ALLOWED,
    CATEGORY_FORBIDDEN,
    WALK_TOO_LONG,
    CLOSED_AT_ARRIVAL,
    OUTDOOR_IN_BAD_AIR_OR_COLD,
    KIDS_UNSUITABLE,
    NOT_STEP_FREE,
}
HONESTY_CODES = {
    OPEN_WITHOUT_HOURS,
    OPEN_ON_HOLIDAY,
    UNKNOWN_NOT_LABELED,
    OPEN_CLAIM_IN_TEXT,
    WIFI_CLAIM_UNSUPPORTED,
    ACCESS_NOT_FLAGGED,
}


def _per_lang(key: str, cut: Callable[[str], str]) -> dict[str, str]:
    """The text of a note of walks.i18n in each answer language, cut down to its fixed part (the part before the
    numbers and names that the card fills in), so the labels cannot drift away from what the app writes."""
    return {lang: cut(pick(STRINGS[key], lang)) for lang in LANGS}


def _lead(text: str) -> str:
    """Up to the first «:» or dash that opens the explanation: «Категория вне вашего запроса: ...»."""
    return re.split(r":|\s[—-]\s", text, maxsplit=1)[0]


def _clause_after_colon(text: str) -> str:
    """«Государственный праздник ({name}): часы работы могут отличаться, уточните.» -> the clause in the middle."""
    return text.split("): ", 1)[1].split(",", 1)[0]


def _without_final_dot(text: str) -> str:
    return text.removesuffix(".")


# the labels of an honest card, in each answer language (a query in English gets English notes, ...)
UNKNOWN_HOURS = _per_lang("note_hours_unknown", _lead)
HOLIDAY = _per_lang("note_holiday", _clause_after_colon)
CONFLICT = _per_lang(
    "note_hours_conflict", _lead
)  # OSM and the website differ: also explains an unknown state
WHEELCHAIR = _per_lang("note_wheelchair", _without_final_dot)
WIFI_NEGATIVE = _per_lang("note_wifi", str)
UNKNOWN_HOURS_LABEL, UNKNOWN_HOURS_LABEL_EN, UNKNOWN_HOURS_LABEL_KK = (
    UNKNOWN_HOURS["ru"],
    UNKNOWN_HOURS["en"],
    UNKNOWN_HOURS["kk"],
)
HOLIDAY_LABEL, HOLIDAY_LABEL_EN, HOLIDAY_LABEL_KK = HOLIDAY["ru"], HOLIDAY["en"], HOLIDAY["kk"]
# every note that explains why hours are not confirmed, in each answer language
UNKNOWN_HOURS_LABELS = (*UNKNOWN_HOURS.values(), *HOLIDAY.values(), *CONFLICT.values())
WHEELCHAIR_LABEL, WHEELCHAIR_LABEL_EN, WHEELCHAIR_LABEL_KK = (
    WHEELCHAIR["ru"],
    WHEELCHAIR["en"],
    WHEELCHAIR["kk"],
)
WIFI_NEGATIVE_LABEL, WIFI_NEGATIVE_LABEL_EN, WIFI_NEGATIVE_LABEL_KK = (
    WIFI_NEGATIVE["ru"],
    WIFI_NEGATIVE["en"],
    WIFI_NEGATIVE["kk"],
)

# "открыто" as a statement about the place now; «на открытом воздухе» (a different word) does not match.
_OPEN_CLAIM = re.compile(r"\bоткрыт[оаы]?\b|\bработает\b|\bopen now\b", re.I)
_WIFI_CLAIM = re.compile(r"wi-?fi|вай-?фай|розетк|socket|outlet", re.I)
# a sentence that says the data does NOT confirm it is a label, not a claim
_NOT_CONFIRMED = re.compile(
    r"не подтвержд|не указан|нет данных|неизвестн|unverified|not confirmed|расталмаған|көрсетілмеген|белгісіз",
    re.I,
)
_WIFI_VALUES = {"wlan", "yes", "wifi", "wi-fi", "terminal"}


def dataset_index(pois: list[POI]) -> dict[str, POI]:
    return {p.id: p for p in pois}


def _wheelchair(poi: POI) -> str | None:
    return (poi.wheelchair or poi.tag_dict().get("wheelchair") or "").lower() or None


def has_wifi_or_socket(poi: POI) -> bool:
    td = poi.tag_dict()
    wifi = (poi.internet_access or td.get("internet_access") or "").lower() in _WIFI_VALUES
    socket = td.get("power_supply", "").lower() in {"yes", "true"} or any(
        k.startswith("socket") and v not in {"no", "0", ""} for k, v in td.items()
    )
    return wifi or socket


def _text(rec: dict) -> str:
    return " ".join(rec.get(k) or "" for k in ("why", "what_to_do", "notes"))


def _honesty(rec: dict, poi: POI, expected: dict, arrival: datetime) -> list[str]:
    out: list[str] = []
    state, notes = rec["hours_state"], rec.get("notes") or ""
    oracle = poi_hours(poi, arrival).state
    if state == "open":
        if not (poi.opening_hours or "").strip():
            out.append(OPEN_WITHOUT_HOURS)
        if holiday_name(arrival.date()) and not (
            (poi.opening_hours or "").strip()
            == "24/7"  # round the clock: open, but only with the holiday caveat
            and any(label in notes for label in (HOLIDAY_LABEL, HOLIDAY_LABEL_EN, HOLIDAY_LABEL_KK))
        ):
            out.append(OPEN_ON_HOLIDAY)
    if oracle == "unknown" and state == "unknown":
        if not any(label in notes for label in UNKNOWN_HOURS_LABELS):
            out.append(UNKNOWN_NOT_LABELED)
    elif oracle == "unknown" and state != "unknown":
        out.append(UNKNOWN_NOT_LABELED)  # the data cannot tell, the card claims it can
    if state != "open" and _OPEN_CLAIM.search(_text(rec)):
        out.append(OPEN_CLAIM_IN_TEXT)
    if expected.get("needs_wifi_socket") and not has_wifi_or_socket(poi):
        sentences = re.split(r"(?<=[.!?])\s+", _text(rec))
        if any(_WIFI_CLAIM.search(s) and not _NOT_CONFIRMED.search(s) for s in sentences):
            out.append(WIFI_CLAIM_UNSUPPORTED)
    if (
        expected.get("step_free")
        and _wheelchair(poi) is None
        and WHEELCHAIR_LABEL not in notes
        and WHEELCHAIR_LABEL_EN not in notes
        and WHEELCHAIR_LABEL_KK not in notes
    ):
        out.append(ACCESS_NOT_FLAGGED)
    return out


def _constraints(
    rec: dict, poi: POI, expected: dict, arrival: datetime, *, indoor: bool
) -> list[str]:
    out: list[str] = []
    cat = poi.category
    allowed, forbidden = expected.get("allowed_categories"), expected.get("forbidden_categories")
    if allowed and cat not in allowed:
        out.append(CATEGORY_NOT_ALLOWED)
    if forbidden and cat in forbidden:
        out.append(CATEGORY_FORBIDDEN)
    limit = expected.get("max_walk_min_one_way")
    if limit is not None and rec["walk_min"] > limit:
        out.append(WALK_TOO_LONG)
    if poi_hours(poi, arrival).state == "closed":
        out.append(CLOSED_AT_ARRIVAL)
    if indoor and cat in OUTDOOR_CATEGORIES:
        out.append(OUTDOOR_IN_BAD_AIR_OR_COLD)
    if expected.get("kids_ok") and cat == "bar_nightlife":
        out.append(KIDS_UNSUITABLE)
    if expected.get("step_free") and _wheelchair(poi) == "no":
        out.append(NOT_STEP_FREE)
    return out


def _duplicate_chains(recs: list[dict], index: dict[str, POI]) -> list[tuple[str, str]]:
    pairs = []
    for i, a in enumerate(recs):
        pa = index.get(a["poi_id"])
        for b in recs[i + 1 :]:
            pb = index.get(b["poi_id"])
            if pa is None or pb is None or pa.name_generated or pb.name_generated:
                continue
            if fuzz.ratio(name_key(pa.name), name_key(pb.name)) >= NAME_RATIO_MIN:
                pairs.append((a["poi_id"], b["poi_id"]))
    return pairs


def _route_closed(route: dict | None, index: dict[str, POI], when: datetime) -> list[str]:
    """Informational: stops that are closed at the time the mini-route actually reaches them (retrieval checks
    opening hours only for a direct trip from the origin)."""
    if not route:
        return []
    closed, t = [], when
    for stop, leg, stay in zip(route["stops"], route["legs_min"], route["stay_min"], strict=False):
        t += timedelta(minutes=leg)
        poi = index.get(stop)
        if poi is not None and poi_hours(poi, t).state == "closed":
            closed.append(stop)
        t += timedelta(minutes=stay)
    return closed


def judge_case(case: dict, recs: list[dict], route: dict | None, index: dict[str, POI]) -> dict:
    """Verdict of one answer. `recs` are the JSONL rec records (poi_id, category, hours_state, walk_min, why,
    what_to_do, notes, ...), `route` the JSONL route record or None."""
    expected, when = case["expected"], case_when(case)
    indoor = bool(expected.get("indoor_preferred", indoor_required(case)))
    hallucinated = [r["poi_id"] for r in recs if r["poi_id"] not in index]
    constraint_viol: dict[str, list[str]] = {}
    honesty_viol: dict[str, list[str]] = {}
    wifi_verified = 0
    for r in recs:
        poi = index.get(r["poi_id"])
        if poi is None:
            continue
        arrival = when + timedelta(minutes=r["walk_min"])
        if v := _constraints(r, poi, expected, arrival, indoor=indoor):
            constraint_viol[r["poi_id"]] = v
        if v := _honesty(r, poi, expected, arrival):
            honesty_viol[r["poi_id"]] = v
        wifi_verified += has_wifi_or_socket(poi)

    budget = expected.get("budget_min")
    over_budget = bool(route and budget is not None and route["total_min"] > budget)
    dups = _duplicate_chains(recs, index)
    ok_recs = [
        r["poi_id"] for r in recs if r["poi_id"] in index and r["poi_id"] not in constraint_viol
    ]
    violations = sorted(
        {c for v in constraint_viol.values() for c in v}
        | {c for v in honesty_viol.values() for c in v}
        | ({OVER_BUDGET} if over_budget else set())
        | ({DUPLICATE_CHAIN} if dups else set())
        | ({NO_RECS} if not recs else set())
        | ({HALLUCINATED} if hallucinated else set())
    )
    return {
        "n_recs": len(recs),
        "hallucinated": hallucinated,
        "constraint_violations": constraint_viol,
        "honesty_violations": honesty_viol,
        "ok_recs": len(ok_recs),
        "over_budget": over_budget,
        "duplicate_chains": [list(p) for p in dups],
        "coverage_ok": bool(ok_recs) and not over_budget,
        "honest_ok": bool(recs) and not honesty_viol,
        "all_ok": bool(recs) and not violations,
        "route_closed_stops": _route_closed(route, index, when),
        "wifi_socket_in_data": wifi_verified,
        "violations": violations,
    }


# ---------------------------------------------------------------- padding and abstention

# Labels the card carries when it is a compromise (the notes of walks.i18n, in the answer language).
OFF_CATEGORY_LABELS = tuple(_per_lang("note_off_category", _lead).values())
TIGHT_FIT_LABELS = tuple(_per_lang("note_tight", _lead).values())
OVER_BUDGET_LABELS = tuple(_per_lang("budget_over", _lead).values())
_RADIUS_LABEL = re.compile(
    "|".join(re.escape(label) for label in _per_lang("note_expanded", _lead).values()), re.I
)


def declared_radius_m(filters: dict) -> float | None:
    """The radius the time budget allows, from a run's `filters` record (older runs: effective / factor);
    None when the record has neither."""
    if filters.get("radius_declared_m") is not None:
        return filters["radius_declared_m"]
    if filters.get("radius_m") is not None:
        return filters["radius_m"] / (filters.get("radius_factor") or 1.0)
    return None


def padding_missing_fields(run: dict, rec: dict) -> list[str]:
    """The fields a record lacks for its padding: `padding` itself (a run from before the pipeline wrote it),
    and, then, what the derivation needs (`distance_m`, a radius in `filters`)."""
    if rec.get("padding"):
        return []
    missing = ["recs[].padding"]
    if rec.get("distance_m") is None:
        missing.append("recs[].distance_m")
    if declared_radius_m(run.get("filters") or {}) is None:
        missing.append("filters.radius_declared_m")
    return missing


def rec_padding(run: dict, rec: dict) -> tuple[str, bool]:
    """(padding, derived) of one recommendation: "none" (requested kind inside the declared radius),
    "expanded" (requested kind, found only after the radius was widened), "backfill" (another category added
    because too few requested ones were in range) or "substituted" (an indoor place instead of the requested
    outdoor kind, by the shelter rule in frost / smog). Read from the record's `padding` (written by the pipeline);
    a run recorded before that field existed gets it derived (derived=True) from the card's off-category note
    and from distance_m vs the declared radius, as far as those fields exist (see padding_missing_fields); such a
    derivation cannot tell a weather substitution from a back-fill and reports "backfill"."""
    if rec.get("padding"):
        return rec["padding"], False
    if any(label in (rec.get("notes") or "") for label in OFF_CATEGORY_LABELS):
        return "backfill", True
    declared, distance = declared_radius_m(run.get("filters") or {}), rec.get("distance_m")
    expanded = declared is not None and distance is not None and distance > declared
    return ("expanded" if expanded else "none"), True


def compromise_labels(rec: dict) -> list[str]:
    """Which compromise labels the card carries: badge_expanded / badge_backfill / badge_substituted (the record's
    `padding`, shown as a badge by the UI and the CLI), then the notes' off_category, expanded_radius, tight_fit,
    over_budget."""
    text = _text(rec)
    found = []
    if rec.get("padding") in ("expanded", "backfill", "substituted"):
        found.append(f"badge_{rec['padding']}")
    if any(x in text for x in OFF_CATEGORY_LABELS):
        found.append("off_category")
    if _RADIUS_LABEL.search(text):
        found.append("expanded_radius")
    if any(x in text for x in TIGHT_FIT_LABELS):
        found.append("tight_fit")
    if any(x in text for x in OVER_BUDGET_LABELS):
        found.append("over_budget")
    return found


def _poi_text(poi: POI) -> str:
    """Name, names in other languages, tags and the human-written descriptions: what a wish for something
    specific («бассейн») can be matched against; the category alone ("sport") cannot tell a pool from a gym."""
    return " ".join([poi.name, *poi.names.values(), *poi.tags, poi.real_text()])


def silent_mismatches(case: dict, run: dict, index: dict[str, POI]) -> dict[str, list[str]]:
    """poi_id -> kinds of mismatch the card presents without saying so. Kinds: backfill_unlabeled /
    expanded_unlabeled (a padding derived for an old run, with no label in its text), off_category_unlabeled (a
    category outside expected.wanted_categories that the pipeline treats as a plain match, whatever the intent
    parser understood), specific_unlabeled (a place whose name / tags do not match expected.wanted_pattern,
    e.g. a gym for «бассейн», shown as a plain match), hours_unlabeled, wifi_unlabeled, access_unlabeled (a
    requirement the data cannot confirm, without the «в данных не указано» label). A pipeline `padding` of
    expanded / backfill / substituted is itself the label: the UI and the CLI show it on the card."""
    expected, out = case["expected"], {}
    wanted = expected.get("wanted_categories") or []
    for rec in run["recs"]:
        poi, kinds, labels = index.get(rec["poi_id"]), [], compromise_labels(rec)
        notes = rec.get("notes") or ""
        padding, derived = rec_padding(run, rec)
        if derived and padding == "backfill" and "off_category" not in labels:
            kinds.append("backfill_unlabeled")
        if derived and padding == "expanded" and "expanded_radius" not in labels:
            kinds.append("expanded_unlabeled")
        if (
            wanted
            and rec["category"] not in wanted
            and padding == "none"
            and "off_category" not in labels
        ):
            kinds.append("off_category_unlabeled")
        if rec["hours_state"] == "unknown" and not any(x in notes for x in UNKNOWN_HOURS_LABELS):
            kinds.append("hours_unlabeled")
        if poi is not None:
            pattern = expected.get("wanted_pattern")
            if (
                pattern
                and padding == "none"
                and "off_category" not in labels
                and not re.search(pattern, _poi_text(poi), re.I)
            ):
                kinds.append("specific_unlabeled")
            if (
                expected.get("needs_wifi_socket")
                and not has_wifi_or_socket(poi)
                and WIFI_NEGATIVE_LABEL not in notes
                and WIFI_NEGATIVE_LABEL_KK not in notes
                and WIFI_NEGATIVE_LABEL_EN not in notes
            ):
                kinds.append("wifi_unlabeled")
            if (
                expected.get("step_free")
                and _wheelchair(poi) is None
                and WHEELCHAIR_LABEL not in notes
                and WHEELCHAIR_LABEL_EN not in notes
                and WHEELCHAIR_LABEL_KK not in notes
            ):
                kinds.append("access_unlabeled")
        if kinds:
            out[rec["poi_id"]] = kinds
    return out


def judge_abstain(case: dict, run: dict, index: dict[str, POI]) -> dict:
    """Honest abstention of one answer in a sparse / impossible situation: it passes when there are no
    recommendations (an honest «рядом ничего подходящего нет») or no recommendation is a silent mismatch, i.e.
    every card that is not a plain match says what is off (outside the request, beyond the radius, unverified).
    A card without any compromise to flag passes as a genuine match."""
    silent = silent_mismatches(case, run, index)
    labelled = sum(bool(compromise_labels(r)) for r in run["recs"])
    return {
        "abstained": not run["recs"],
        "labelled_recs": labelled,
        "silent_mismatches": silent,
        "honest_abstain": not silent,
    }


# ---------------------------------------------------------------- intent gaps (eval/intent_compare.py)

_FLAG_EXPECTED = (  # (expected key, intent flag)
    ("kids_ok", "with_kids"),
    ("needs_wifi_socket", "needs_wifi_socket"),
    ("step_free", "accessibility"),
)


def intent_gaps(case: dict, intent: dict) -> list[str]:
    """What an intent (dict with categories / with_kids / needs_wifi_socket / accessibility) misses against the
    case's `expected`: "categories" when none of its categories is an allowed (or wanted) one, or it holds a
    forbidden one; "with_kids" / "needs_wifi_socket" / "accessibility" for a flag the case needs and it lacks."""
    expected, gaps = case["expected"], []
    allowed = set(expected.get("allowed_categories") or expected.get("wanted_categories") or [])
    forbidden = set(expected.get("forbidden_categories") or [])
    cats = set(intent["categories"])
    if (allowed and not cats & allowed) or cats & forbidden:
        gaps.append("categories")
    gaps += [flag for key, flag in _FLAG_EXPECTED if expected.get(key) and not intent[flag]]
    return gaps
