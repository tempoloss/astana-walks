"""AssistantQA3 matrix runner: POSTs every dialogue of matrix_cases.py to /api/turn (NDJSON), keeps `state` across
follow-ups, applies the memory form through /api/profile, checks every answer and writes one JSON line per step.

Run from `app/` (needs httpx and opening-hours-py, both in the app's environment):

    uv run python ../docs/fuzz/AssistantQA3/run_matrix.py --base http://127.0.0.1:8755 --label offline
    uv run python ../docs/fuzz/AssistantQA3/run_matrix.py --base http://127.0.0.1:8751 --label live --live-only --min-interval 4

Servers:  powershell -NoProfile -File ../docs/fuzz/AssistantQA3/serve.ps1 offline 8755   (WALKS_OFFLINE=1)
          powershell -NoProfile -File ../docs/fuzz/AssistantQA3/serve.ps1 live 8751       (model key from GEMINI_KEY_FILE)

Output: results.<label>.jsonl (one line per step: request, answer digest, findings) and findings.<label>.jsonl
(one line per finding, with a minimal repro). Read-only against the product; the only write is under this directory.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matrix_cases as mc  # noqa: E402

DATA = HERE.parents[2] / "data"
S1, S2, S3, S4 = "S1", "S2", "S3", "S4"

# --------------------------------------------------------------------------------------------------- dataset
_POIS: dict[str, dict] = {}
_NAMES: set[str] = set()
_BIG_TEXT = ""


def load_dataset() -> None:
    global _BIG_TEXT
    pois = json.loads((DATA / "poi.enriched.json").read_text(encoding="utf-8"))
    for p in pois:
        _POIS[p["id"]] = p
        _NAMES.add(norm(p["name"]))
        for v in (p.get("names") or {}).values():
            _NAMES.add(norm(v))
    parts = []
    for f in ("gov/joined.json", "gov/osm_candidates.json"):
        path = DATA / f
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    for f in (DATA / "sites").glob("*.json") if (DATA / "sites").exists() else []:
        parts.append(f.read_text(encoding="utf-8"))
    _BIG_TEXT = "\n".join(parts)


def norm(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").casefold().replace("ё", "е")).strip()


def hav(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def near_count(cats: list[str] | None, origin: tuple[float, float], radius: float = 1200) -> int:
    if not cats:
        return 0
    return sum(1 for p in _POIS.values() if p["category"] in cats and hav(origin, (p["lat"], p["lon"])) <= radius)


# --------------------------------------------------------------------------------------------------- text helpers
KK_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
RU_ONLY = set("ыэёъщ")
RU_WORDS = {"и", "в", "на", "с", "для", "что", "это", "как", "или", "рядом", "мин", "пешком", "ниже", "ещё", "еще", "места",
            "место", "открыто", "сначала", "советую", "вы", "ищете", "поближе", "уже", "темно", "часы", "неизвестны", "не", "по",
            "из", "до", "от", "нет", "есть", "можно", "ничего", "найдено", "данных", "данные", "хотите", "хочу"}
KK_WORDS = {"және", "мен", "үшін", "жақын", "ашық", "минут", "жаяу", "іздейсіз", "орын", "жер", "бар", "жоқ", "бұл", "не", "қайда",
            "керек", "сізге", "ұсынамын", "төмен", "тағы", "сағат"}
TECH = re.compile(
    r"\b(llm|gemini|gemma|openai|json|api|http|template|шаблон\w*|кэш\w*|cache|offline|офлайн\w*|replay|demo|демо|парсер\w*|"
    r"parser|traceback|exception|stack ?trace|poi[_ ]?id|node/|way/|relation/|token|токен\w*|промпт\w*|prompt|embedding|retrieval|"
    r"fallback|walks_\w+|undefined|nan|null|none|\[object|ai studio|нейросет\w*|языков\w+ модел\w*|language model)\b",
    re.I,
)
PLACEHOLDER = re.compile(r"[{}]|%s|%\(|\$\{|\bNone\b|\bnull\b|undefined|\\n|\\u[0-9a-f]{4}|&[a-z]+;")
QUOTED = re.compile(r"«([^»]{1,80})»")
TIME_RE = re.compile(r"\b([01]?\d|2[0-4]):([0-5]\d)\b")


GENERIC_NAMES = {"парк сквер", "детская площадка", "парк", "сквер", "площадка", "кафе", "ресторан", "магазин", "памятник", "фонтан"}


def msg_lang(text: str) -> str | None:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return None
    if any(c in KK_LETTERS for c in letters):
        return "kk"
    words = set(re.findall(r"\w+", text.casefold()))
    if words & {"және", "мен", "қайда", "керек", "бар", "жоқ", "ма", "ме", "ба", "бе"}:
        return "kk"
    cyr = sum(1 for c in letters if "а" <= c.casefold() <= "я" or c in "ёЁ")
    if cyr >= 3 or cyr / len(letters) > 0.5:
        return "ru"
    return "en"


def strip_names(text: str, names: list[str]) -> str:
    out = QUOTED.sub(" ", text)
    for n in sorted({n for n in names if n}, key=len, reverse=True):
        out = out.replace(n, " ")
    return out


def reply_lang_problem(text: str, expected: str, names: list[str]) -> str | None:
    body = strip_names(text, names)
    toks = re.findall(r"[^\W\d_]+", body.casefold())
    if len(toks) < 3:
        return None
    cyr = [t for t in toks if re.search(r"[а-яёәғқңөұүһі]", t)]
    lat = [t for t in toks if re.fullmatch(r"[a-z]+", t)]
    kk_tok = [t for t in toks if any(c in KK_LETTERS for c in t) or t in KK_WORDS]
    ru_tok = [t for t in toks if t in RU_WORDS or any(c in RU_ONLY for c in t)]
    if expected == "en":
        if len(cyr) >= 1:
            return f"Cyrillic in an English answer: {cyr[:6]}"
    elif expected == "ru":
        if len(lat) >= 3 and len(lat) > 0.3 * len(toks):
            return f"mostly Latin in a Russian answer: {lat[:6]}"
        if sum(1 for t in kk_tok if any(c in KK_LETTERS for c in t)) >= 2:
            return f"Kazakh letters/words in a Russian answer: {kk_tok[:6]}"
    elif expected == "kk":
        if len(lat) >= 4 and len(lat) > 0.3 * len(toks):
            return f"mostly Latin in a Kazakh answer: {lat[:6]}"
        if len(ru_tok) >= 3 and len(ru_tok) > len(kk_tok) + 1:
            return f"Russian words in a Kazakh answer: {ru_tok[:8]}"
        if not kk_tok and len(toks) >= 6:
            return "no Kazakh markers in a Kazakh answer"
    return None


# --------------------------------------------------------------------------------------------------- hours
try:
    from opening_hours import OpeningHours, State
except Exception:  # pragma: no cover
    OpeningHours = None  # type: ignore[assignment]
    State = None  # type: ignore[assignment]
_UNTRUSTED = ("||", "sunrise", "sunset", "dawn", "dusk", "easter", "week ", "unknown")


def calc_state(raw: str, when: datetime) -> str:
    if OpeningHours is None or not raw or any(m in raw.lower() for m in _UNTRUSTED):
        return "unknown"
    try:
        st, _ = OpeningHours(raw).state(when)
    except Exception:
        return "unknown"
    return {State.CLOSED: "closed", State.OPEN: "open"}.get(st, "unknown")


def is_24_7(raw: str | None) -> bool:
    t = (raw or "").strip()
    return t == "24/7" or bool(re.fullmatch(r"(?:mo-su\s+)?00:00-24:00", t, re.I))


# --------------------------------------------------------------------------------------------------- the check
class Finding(dict):
    pass


def digest_place(p: dict) -> dict:
    h = p.get("hours") or {}
    w = p.get("walk") or {}
    return {
        "id": p["id"], "name": p["name"], "category": p["category"], "primary": p["primary"], "lat": p["lat"], "lon": p["lon"],
        "walk_min": w.get("minutes"), "dist_m": w.get("distance_m"), "walk_mode": w.get("mode"), "walk_method": w.get("method"),
        "hours_state": h.get("state"), "hours_text": h.get("text"), "hours_raw": h.get("raw"), "hours_source": h.get("source"),
        "hours_issue": h.get("issue"), "hours_note": h.get("note"),
        "price": p.get("price"), "padding": p.get("padding"), "why": p.get("why"), "what_to_do": p.get("what_to_do"),
        "note": p.get("note"), "caveat": p.get("caveat"), "text_source": p.get("text_source"), "ai_idea": p.get("ai_idea"),
        "stop": (p.get("stop") or {}).get("name"), "stop_min": (p.get("stop") or {}).get("minutes"),
    }


def visible_texts(turn: dict) -> list[tuple[str, str]]:
    out = [("reply", turn.get("reply") or ""), ("notice", turn.get("notice") or "")]
    out += [(f"notices[{i}]", n if isinstance(n, str) else str(n.get("text", n))) for i, n in enumerate(turn.get("notices") or [])]
    for i, a in enumerate(turn.get("answers") or []):
        out.append((f"answers[{i}]", a if isinstance(a, str) else str(a.get("text", ""))))
    for p in turn.get("places") or []:
        for f in ("why", "what_to_do", "note", "caveat"):
            if p.get(f):
                out.append((f"place[{p['name']}].{f}", p[f]))
        h = p.get("hours") or {}
        for f in ("text", "note"):
            if h.get(f):
                out.append((f"place[{p['name']}].hours.{f}", h[f]))
    for c in turn.get("chips") or []:
        out.append(("chip", c.get("label", "")))
    return out


class Ctx:
    """Everything a step check reads."""

    def __init__(self, case, idx, step, body, ans, wall, prev, base_origin):
        self.case, self.idx, self.step, self.body, self.ans, self.wall, self.prev = case, idx, step, body, ans, wall, prev
        self.turn = ans["turn"] if ans else None
        self.origin = (round(body["lat"], 3), round(body["lon"], 3))  # the core rounds the point to ~100 m on input
        self.exp = step["expect"]
        self.places = (self.turn or {}).get("places") or []
        self.primary = next((p for p in self.places if p["primary"]), self.places[0] if self.places else None)


def check_step(ctx: Ctx, live: bool) -> list[dict]:
    F: list[dict] = []

    def add(sev, code, msg, **extra):
        F.append({"sev": sev, "code": code, "msg": msg, **extra})

    c, exp, turn, body = ctx.case, ctx.exp, ctx.turn, ctx.body
    if ctx.ans is None:
        return F  # transport findings are added by the caller
    kind = turn["kind"]
    reply = turn["reply"] or ""
    places = ctx.places
    when_s = ctx.ans["at"]
    when = datetime.fromisoformat(f"{when_s['date']}T{when_s['time']}")
    names = [p["name"] for p in places]
    pdig = [digest_place(p) for p in places]

    # ---- kinds
    allowed_kinds = exp.get("kinds") or ["places", "none_found", "place_answer"]
    if kind not in allowed_kinds:
        sev = S2 if (exp.get("cats") and kind in ("clarify", "refusal")) else S3
        if not any(ch.isalpha() for ch in body["text"]):
            sev = S3  # emoji-only: a nicety
        add(sev, "kind_unexpected", f"kind={kind}, expected one of {allowed_kinds}")
    if exp.get("none") and places:
        sev = S1 if c["id"].startswith("edge-") and any(k in c["id"] for k in ("drugs", "weapons", "sex")) else S2
        add(sev, "places_for_non_place_request", f"{len(places)} place cards for a request that should have none: {names}")
    if kind == "none_found" and exp.get("cats") and near_count(exp["cats"], ctx.origin) >= 3 and not exp.get("none"):
        add(S2, "recall_none_found", f"none_found although the data holds {near_count(exp['cats'], ctx.origin)} places of {exp['cats']} within 1.2 km")
    if kind == "clarify" and exp.get("cats") and ctx.prev is not None:
        add(S2, "lost_context", "a follow-up got a clarifying question instead of using the dialogue so far")

    # ---- answer time honours `at`
    if body.get("at") and when_s["time"] != body["at"] and not ctx.ans.get("pinned"):
        add(S2, "at_ignored", f"asked at {body['at']}, the answer is about {when_s['time']}")

    # ---- wish / category fit
    cats = exp.get("cats")
    hard = bool(exp.get("hard"))
    if cats and places:
        for p in places:
            if p["category"] not in cats:
                prim = p["primary"]
                if not hard:
                    sev = S3
                elif p["padding"] in ("substituted", "backfill") and ctx.exp.get("follow") != "insist":
                    sev = S2  # a padding pick, disclosed on the card (shelter rule / too few places of the kind), not the wish
                else:
                    sev = S1 if prim else S2
                add(sev, "category_misfit", f"{'primary ' if prim else ''}place «{p['name']}» is {p['category']} (padding={p['padding']}); wanted {cats}",
                    place=p["name"], category=p["category"], padding=p["padding"])
        meta_cats = (turn["meta"].get("intent") or {}).get("categories") or []
        if hard and meta_cats and not set(meta_cats) <= set(cats):
            add(S1, "intent_drift", f"intent categories {meta_cats} are outside the wish {cats}", categories=meta_cats)
        pads = Counter(p["padding"] for p in places)
        if hard and (pads.get("substituted") or pads.get("backfill")) and not any(p["category"] in cats for p in places):
            add(S2, "padding_without_wish_kind", f"every card is padding ({dict(pads)}) for a hard wish")
    if exp.get("no_cat"):
        bad = [p["name"] for p in places if p["category"] in exp["no_cat"]]
        if bad:
            sev = S1 if "bar_nightlife" in exp["no_cat"] and ("minor" in c["id"] or "noalc" in c["id"]) else S2
            add(sev, "excluded_category_shown", f"{exp['no_cat']} must not appear, shown: {bad}")
    pr0 = ctx.primary
    if pr0 and kind == "places":
        mc_ = (turn["meta"].get("intent") or {}).get("categories") or []
        if mc_ and pr0["category"] not in mc_ and re.search(r"вы ищете|you.re looking|you are looking|іздейсіз", reply, re.I):
            add(S2, "lead_contradiction", f"the lead says what you look for ({mc_}) and then recommends «{pr0['name']}» ({pr0['category']}, padding={pr0['padding']})",
                place=pr0["name"])
    if re.search(r"темно|dark|қараңғы", reply, re.I) and 8 <= when.hour <= 16:
        add(S2, "dark_at_daytime", f"the lead says it is dark at {when_s['time']}")
    if not live and body.get("weather", "now") == "now" and re.search(r"мороз|дожд|снег|смог|ветер|жар[аы]|frost|rain|snow|smog|wind|-?\d+\s*°", reply, re.I):
        add(S1, "weather_claim_without_data", f"offline with no weather data, the lead speaks about weather: «{reply[:140]}»")
    if exp.get("intent"):
        got = turn["meta"].get("intent") or {}
        for k, v in exp["intent"].items():
            if got.get(k) != v:
                add(S2, "memory_not_applied", f"intent.{k}={got.get(k)!r}, expected {v!r}", field=k)

    # ---- hours honesty
    for p in places:
        h = p.get("hours") or {}
        raw, st = h.get("raw"), h.get("state")
        poi = _POIS.get(p["id"])
        if st in ("open", "closed") and not raw and not h.get("source"):
            add(S1, "hours_without_data", f"«{p['name']}» state={st} but no raw hours and no source", place=p["name"])
        if raw:
            calc = calc_state(raw, when)
            if st in ("open", "closed") and calc in ("open", "closed") and calc != st and "праздник" not in (h.get("note") or ""):
                add(S1, "hours_mismatch", f"«{p['name']}» says {st}, hours '{raw}' at {when:%a %H:%M} compute {calc}", place=p["name"])
            if st == "unknown" and calc in ("open", "closed") and not h.get("issue") and "праздник" not in (h.get("note") or ""):
                add(S4, "hours_known_but_unknown", f"«{p['name']}»: raw '{raw}' computes {calc}, card says unknown", place=p["name"])
            if poi is not None and raw not in {poi.get("opening_hours"), poi.get("opening_hours_official")} and raw not in _BIG_TEXT:
                add(S3, "hours_raw_unmatched", f"«{p['name']}» raw hours '{raw}' not found in the shipped record", place=p["name"])
        if "круглосуточно" in (h.get("text") or "").casefold() and not is_24_7(raw):
            add(S1, "round_the_clock_unbacked", f"«{p['name']}» is shown round-the-clock, raw='{raw}'", place=p["name"])
        if poi is None and not p["id"].startswith(("gov/", "city/")):
            add(S1, "unknown_poi_id", f"place id {p['id']} («{p['name']}») is not in the shipped dataset", place=p["name"])
        elif poi is not None:
            if hav((p["lat"], p["lon"]), (poi["lat"], poi["lon"])) > 30:
                add(S2, "coords_differ_from_data", f"«{p['name']}» coordinates differ from data by {hav((p['lat'], p['lon']), (poi['lat'], poi['lon'])):.0f} m")
            if norm(p["name"]) not in _NAMES and not any(n.startswith(norm(p["name"])) for n in _NAMES):
                add(S2, "name_not_in_data", f"«{p['name']}» is not a name of any record")
            if poi.get("name_generated") or norm(p["name"]) in GENERIC_NAMES:
                add(S3, "generic_name", f"«{p['name']}» is a generated/generic name (no real name in the data)" + ("; shown as the pick" if p["primary"] else ""), place=p["name"])
    prim = ctx.primary
    claim = re.search(r"(?<!не )(?<!не\s)\b(открыт[оы]?|работает|open until|is open|opens until|ашық|круглосуточно|round the clock|24/7)", reply, re.I)
    if prim and claim and kind == "places":
        if (prim["hours"] or {}).get("state") != "open":
            add(S1, "open_claim_without_open_state", f"reply says «{claim.group(0)}» but «{prim['name']}» hours state = {(prim['hours'] or {}).get('state')}", place=prim["name"])
    if prim and kind == "places" and (prim["hours"] or {}).get("state") == "closed" and not re.search(r"закрыт|closed|жабық|не работает", reply, re.I):
        add(S2, "closed_primary_recommended", f"the recommended «{prim['name']}» is closed now and the lead does not say so", place=prim["name"])

    # ---- prices / times only from data
    data_times = {"24:00"}
    for p in places:
        h = p.get("hours") or {}
        blob = " ".join(str(x) for x in (h.get("text"), h.get("raw"), h.get("today"), h.get("note")) if x)
        data_times |= {f"{int(a):02d}:{b}" for a, b in TIME_RE.findall(blob)}
    for a in turn.get("answers") or []:
        poi_a = _POIS.get(a.get("place_id", "")) if isinstance(a, dict) else None
        if poi_a:
            blob = " ".join(str(poi_a.get(k) or "") for k in ("opening_hours", "opening_hours_official"))
            data_times |= {f"{int(x):02d}:{y}" for x, y in TIME_RE.findall(blob)}
    for a, b in TIME_RE.findall(reply):
        t = f"{int(a):02d}:{b}"
        if t not in data_times and t != body.get("at") and t != when_s["time"] and kind in ("places", "place_answer"):
            if not re.search(r"восход|закат|sunrise|sunset|афиш|сеанс|начал", reply, re.I):
                add(S2, "time_not_from_data", f"reply mentions {t} which no card's hours state", time=t)
    price_blob = json.dumps([p.get("price") for p in places] + [turn.get("answers")], ensure_ascii=False)
    asked_digits = set(re.findall(r"\d+", body["text"]))
    for m in re.finditer(r"(\d[\d\s]{0,8})\s*(₸|тг|тенге|kzt|tenge)", reply, re.I):
        digits = re.sub(r"\D", "", m.group(1))
        if digits and digits not in asked_digits and digits not in re.sub(r"\D", "", price_blob) and digits not in price_blob:
            add(S1, "price_not_from_data", f"price «{m.group(0)}» in the reply is on no card", price=m.group(0))
    for p in places:
        for f in ("why", "what_to_do", "note"):
            for m in re.finditer(r"(\d[\d\s]{1,8})\s*(₸|тг|тенге|kzt|tenge)", p.get(f) or "", re.I):
                digits = re.sub(r"\D", "", m.group(1))
                if digits not in asked_digits and not (p.get("price") and digits in re.sub(r"\D", "", json.dumps(p["price"]))):
                    add(S1, "price_not_from_data", f"«{p['name']}».{f}: «{m.group(0)}» but the card has no such price", place=p["name"])

    # ---- invented places
    for q in QUOTED.findall(reply):
        qn = norm(q)
        if qn and qn not in {norm(n) for n in names} and qn not in _NAMES and not any(qn in n or n in qn for n in _NAMES if len(n) > 4) \
                and q not in (c.get("bookmarks") and [b["name"] for b in c["bookmarks"]] or []):
            add(S1, "invented_name", f"«{q}» in the reply is not a place of the answer nor of the dataset", name=q)
    seen: dict[tuple, str] = {}
    for p in places:
        key = (norm(p["name"]),)
        if key in seen and hav((p["lat"], p["lon"]), next((q["lat"], q["lon"]) for q in places if norm(q["name"]) == key[0])) < 150:
            add(S2, "duplicate_place", f"«{p['name']}» is shown twice (≤150 m apart)", place=p["name"])
        seen[key] = p["id"]
    if len({p["id"] for p in places}) != len(places):
        add(S2, "duplicate_place_id", "the same place id twice in one answer")
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            if a["category"] == b["category"] and hav((a["lat"], a["lon"]), (b["lat"], b["lon"])) < 15 and norm(a["name"]) != norm(b["name"]):
                add(S4, "same_spot_two_names", f"«{a['name']}» and «{b['name']}» are {hav((a['lat'], a['lon']), (b['lat'], b['lon'])):.0f} m apart (one place, two records?)")

    # ---- minutes
    bm_pts = [(b["lat"], b["lon"]) for b in c["bookmarks"]]
    for p in places:
        w = p.get("walk") or {}
        mins, dist = w.get("minutes"), w.get("distance_m")
        if mins is None or dist is None:
            continue
        starts = [ctx.origin, *bm_pts]
        hmin = min(hav(s, (p["lat"], p["lon"])) for s in starts)
        hmax = max(hav(s, (p["lat"], p["lon"])) for s in starts[:1])
        if w.get("mode") == "walk" and mins > 0:
            speed = dist / mins
            if not (40 <= speed <= 140) and dist > 150:
                add(S2, "minutes_vs_distance", f"«{p['name']}»: {mins} min for {dist} m ({speed:.0f} m/min)", place=p["name"])
        if dist + 30 < 0.9 * hmin:
            add(S2, "distance_below_straight", f"«{p['name']}»: {dist} m but straight line is {hmin:.0f} m", place=p["name"])
        if dist > 2.6 * hmax + 300 and not bm_pts:
            add(S3, "detour_huge", f"«{p['name']}»: {dist} m for a straight line of {hmax:.0f} m", place=p["name"])
        if hmin > 8000 and w.get("mode") == "walk":
            add(S1, "far_place_as_walk", f"«{p['name']}» is {hmin/1000:.0f} km away but shown with a walk of {mins} min", place=p["name"])
        elif mins > 45 and w.get("mode") == "walk" and c["family"] not in ("origin",):
            add(S3, "walk_over_45", f"«{p['name']}» is {mins} min on foot", place=p["name"])
    if prim and kind == "places":
        m = re.search(r"(\d+)\s*(?:мин|min|минут)", reply)
        pm = (prim.get("walk") or {}).get("minutes")
        if m and pm is not None and int(m.group(1)) != pm and int(m.group(1)) not in {(p.get("walk") or {}).get("minutes") for p in places} \
                and not re.search(r"на\s*\d+\s*мин|for\s*\d+\s*min|budget", reply[max(0, m.start() - 6):m.end() + 4], re.I):
            add(S2, "reply_minutes_mismatch", f"reply says {m.group(1)} min, the primary card says {pm}")
    rt = turn.get("route")
    if rt:
        if rt.get("fits") and rt.get("budget_min") and rt.get("total_min", 0) > rt["budget_min"] + 1:
            add(S2, "route_over_budget", f"route total {rt['total_min']} min > budget {rt['budget_min']} but fits=true")
        if rt.get("legs_min") and abs(sum(rt["legs_min"]) - rt.get("walk_min_total", 0)) > 2:
            add(S3, "route_legs_sum", f"legs {rt['legs_min']} sum != walk_min_total {rt.get('walk_min_total')}")

    # ---- language
    exp_lang = exp.get("lang")
    if "lang_expect" in exp and body.get("profile_on"):
        exp_lang = exp["lang_expect"]
    if exp_lang is None and "lang" not in exp:
        ml = msg_lang(body["text"])
        exp_lang = body["lang"] if body.get("lang_fixed") else (ml or None)
        if ml == "en" and any(t in c.get("tags", []) for t in ("lang:translit", "lang:mixed")):
            exp_lang = "ru|en"
    if body.get("lang_fixed") and "lang" not in exp:
        exp_lang = body["lang"]
    if exp_lang:
        alts = exp_lang.split("|")
        if turn["lang"] not in alts:
            add(S2, "turn_lang_wrong", f"turn.lang={turn['lang']} expected {exp_lang} (request lang={body['lang']}, fixed={body['lang_fixed']})")
        use = turn["lang"] if turn["lang"] in alts else alts[0]
        prob = reply_lang_problem(reply, use, names)
        if prob and kind != "clarify" or (prob and kind == "clarify"):
            add(S2, "reply_language", prob, expected=use)
        for ch in turn.get("chips") or []:
            lab = ch.get("label", "")
            if use == "en" and re.search(r"[а-яёәғқңөұүһі]", lab, re.I):
                add(S3, "chip_language", f"chip «{lab}» is not English")
            if use == "ru" and re.search(r"[әғқңөұүһі]", lab, re.I):
                add(S3, "chip_language", f"chip «{lab}» is not Russian")

    # ---- lead grammar
    flat = reply
    prose = [("reply", reply)] + [(w, t) for w, t in visible_texts(turn) if w.startswith(("notice", "answers"))]
    for where, ptxt in prose:
        for m in re.finditer(r"(?<!\w)([^\W\d_]{3,})([\s:,;—–-]+)\1(?!\w)", ptxt, re.I):
            add(S2, "lead_doubled_word", f"«{m.group(0)}» in {where}: «{ptxt[:140]}»", where=where)
        for m in re.finditer(r"(?<!\w)([^\W\d_]{4,})\s*[:—–-]\s*([^\W\d_]{4,})", ptxt):
            a, b = m.group(1).casefold(), m.group(2).casefold()
            if a != b and len(a) >= 5 and a[:5] == b[:5] and a[-1:] != b[-1:]:
                add(S2, "lead_doubled_stem", f"«{m.group(0)}» repeats a stem in {where}: «{ptxt[:160]}»", where=where)
    pats = [(r"[.!?]{2,}(?<!\.\.\.)", "double sentence punctuation"), (r",\s*,", "double comma"), (r"\s[,.;:!?]", "space before punctuation"),
            (r"«\s*»", "empty quotes"), (r"\(\s*\)", "empty brackets"), (r"[:;,—–-]\s*[:;,—–-]", "double separator"),
            (r"\s{2,}", "double space"), (r"\bот «", "name in nominative after «от» (declension)"), (r"^[a-zа-яёәғқңөұүһі]", "lowercase start")]
    for pat, what in pats:
        mm = re.search(pat, flat)
        if mm:
            add(S3 if what.startswith(("space", "double space", "lowercase", "name in")) else S2, "lead_punct", f"{what}: «{flat[max(0, mm.start()-20):mm.end()+20]}»")
    if flat.count("«") != flat.count("»") or flat.count("(") != flat.count(")"):
        add(S2, "lead_unbalanced", f"unbalanced quotes/brackets: «{flat[:140]}»")
    if kind == "places" and flat and flat.rstrip()[-1] not in ".!?»)…":
        add(S3, "lead_no_final_stop", f"reply does not end with a stop: «…{flat[-40:]}»")
    if PLACEHOLDER.search(flat):
        add(S1, "placeholder_in_reply", f"leftover placeholder in «{flat[:160]}»")
    if kind == "places" and prim:
        quoted = QUOTED.findall(reply)
        if quoted and norm(prim["name"]) not in {norm(q) for q in quoted}:
            add(S2, "lead_names_other_place", f"lead recommends «{quoted[0]}» but the primary card is «{prim['name']}»")
        if not quoted and norm(prim["name"]) not in norm(reply):
            add(S3, "lead_without_pick", "kind=places and the lead names no place")
    if kind == "places" and not places:
        add(S1, "places_kind_without_places", "kind=places with no cards")
    if kind == "places" and prim is None:
        add(S1, "no_primary", "kind=places and no primary card")

    # ---- technical / demo words in anything the user reads
    for where, text in visible_texts(turn):
        t = strip_names(text, names)
        mm = TECH.search(t)
        if mm:
            add(S2, "technical_word", f"«{mm.group(0)}» in {where}: «{text[:140]}»", where=where, word=mm.group(0))
        if where != "reply" and PLACEHOLDER.search(text):
            add(S2, "placeholder_visible", f"leftover placeholder in {where}: «{text[:140]}»", where=where)

    # ---- latency
    lat = ctx.wall
    if live:
        if lat > 25:
            add(S2, "latency", f"{lat:.1f} s", seconds=round(lat, 1))
        elif lat > 12:
            add(S3, "latency", f"{lat:.1f} s", seconds=round(lat, 1))
    elif lat > 3:
        add(S3, "latency", f"offline {lat:.1f} s", seconds=round(lat, 1))

    # ---- follow-ups
    fol = exp.get("follow")
    pv = ctx.prev
    if fol and pv is not None and pv.get("turn"):
        pt = pv["turn"]
        pplaces = pt.get("places") or []
        pids = {p["id"] for p in pplaces}
        if fol == "more":
            if places and kind == "places":
                rep = [p["name"] for p in places if p["id"] in pids]
                if rep:
                    add(S2, "repeat_after_more", f"«ещё» repeats already shown places: {rep}", places=rep)
                pc = {p["category"] for p in pplaces}
                drift = [p["name"] for p in places if pc and p["category"] not in pc and p["padding"] == "none"]
                if drift and len(drift) == len(places):
                    add(S2, "topic_drift_after_more", f"«ещё» changed the kind: {sorted(pc)} -> {sorted({p['category'] for p in places})}")
        elif fol == "closer" and places and pplaces:
            far_prev = max((p.get("walk") or {}).get("distance_m", 0) or 0 for p in pplaces)
            far_new = max((p.get("walk") or {}).get("distance_m", 0) or 0 for p in places)
            if far_new > far_prev + 50:
                add(S2, "closer_is_farther", f"«поближе»: farthest was {far_prev} m, now {far_new} m")
            if [p["id"] for p in places] == [p["id"] for p in pplaces] and not re.search(r"ближе|closer|жақын|больше нет|ничего", reply + " ".join(turn.get("notices") or []), re.I):
                add(S3, "closer_changes_nothing", "«поближе» returns the same cards in the same order and says nothing about it")
        elif fol == "longer":
            nb = (turn["meta"].get("intent") or {}).get("time_budget_min")
            ob = (pt["meta"].get("intent") or {}).get("time_budget_min")
            if nb is not None and ob is not None and nb <= ob:
                add(S2, "longer_not_longer", f"time budget {ob} -> {nb} after «на час дольше»")
            if cats and places and any(p["category"] not in cats for p in places):
                pass
        elif fol == "kids":
            if not (turn["meta"].get("intent") or {}).get("with_kids"):
                add(S2, "kids_not_applied", "«с ребёнком» did not set with_kids")
        elif fol == "insist":
            ppri_ = next((p for p in pplaces if p["primary"]), pplaces[0] if pplaces else None)
            if cats and ppri_ and ppri_["category"] not in cats and places and [p["id"] for p in places] == [p["id"] for p in pplaces] and reply == pt["reply"]:
                add(S1, "wish_repeat_ignored", "the user repeats the wish and gets exactly the same answer back (same cards, same lead), still not what they asked")
        elif fol == "open":
            ppri = next((p for p in pplaces if p["primary"]), pplaces[0] if pplaces else None)
            if ppri is not None:
                pst = (ppri.get("hours") or {}).get("state")
                if kind != "place_answer":
                    add(S3, "open_followup_not_answered", f"«а он открыт?» gave kind={kind}")
                if pst == "unknown" and re.search(r"(?<!не\s)\b(открыт[оы]?\b|open\b|ашық)", reply, re.I) and not re.search(r"неизвестн|нет данных|не указан|unknown|no hours|жоқ|белгісіз|уточн", reply, re.I):
                    add(S1, "open_claim_unknown_hours", f"«{ppri['name']}» hours unknown but the answer says open: «{reply[:140]}»")
                if pst == "closed" and re.search(r"(?<!не\s)\bоткрыт[оы]?\b", reply, re.I) and not re.search(r"закрыт", reply, re.I):
                    add(S1, "open_claim_closed", f"«{ppri['name']}» is closed but the answer says open: «{reply[:140]}»")
                if ppri["name"] not in reply and kind == "place_answer":
                    add(S3, "open_followup_no_name", "the answer does not name the place it speaks about")
        elif fol == "howlong":
            ppri = next((p for p in pplaces if p["primary"]), pplaces[0] if pplaces else None)
            if ppri is not None and (ppri.get("walk") or {}).get("minutes") is not None:
                if str((ppri["walk"])["minutes"]) not in reply and (ppri["walk"] or {}).get("text", "~") not in reply:
                    add(S2, "howlong_wrong", f"«сколько идти?»: card says {ppri['walk']['minutes']} min, reply «{reply[:120]}»")
        elif fol == "bus":
            ppri = next((p for p in pplaces if p["primary"]), pplaces[0] if pplaces else None)
            if ppri is not None and kind == "place_answer":
                stop = (ppri.get("stop") or {}).get("name")
                if stop and stop not in reply and not re.search(r"автобус|bus|маршрут|остановк|stop|тоқтауыш|көлік", reply, re.I):
                    add(S3, "bus_followup_vague", f"«а на автобусе?» says nothing about transit: «{reply[:140]}»")

    # ---- bookmarks
    if exp.get("near") and c["bookmarks"] and prim and kind == "places":
        bms = [b for b in c["bookmarks"] if b["kind"] == exp["near"] or exp["near"] == "other"]
        if bms:
            d = min(hav((prim["lat"], prim["lon"]), (b["lat"], b["lon"])) for b in bms)
            if d > 900:
                add(S2, "not_near_bookmark", f"«рядом с {exp['near']}»: the primary «{prim['name']}» is {d:.0f} m from the bookmark")
            if not re.search("|".join(re.escape(b["name"]) for b in bms) + r"|дом|работ|школ|универ|home|work|school|үй", reply, re.I):
                add(S3, "bookmark_not_visible", f"the answer does not say it searched near the bookmark: «{reply[:140]}»")
    if exp.get("toward") and c["bookmarks"] and prim and kind == "places":
        bms = [b for b in c["bookmarks"] if b["kind"] == exp["toward"]]
        if bms:
            b = bms[0]
            own = hav(ctx.origin, (b["lat"], b["lon"]))
            there = hav((prim["lat"], prim["lon"]), (b["lat"], b["lon"]))
            if own > 300 and there > own - 20:
                add(S2, "not_toward_bookmark", f"the primary «{prim['name']}» is {there:.0f} m from {b['name']}, the user is {own:.0f} m")
            elif not re.search(r"домой|по пути|по дороге|к дому|home|on the way|үйге|жолда|работ|work", reply, re.I):
                add(S3, "toward_not_visible", f"the pick lies toward the bookmark but the answer does not say so: «{reply[:140]}»")
    if c["bookmarks"]:
        for b in c["bookmarks"]:
            if "<" in b["name"] and b["name"] in reply:
                add(S2, "markup_in_reply", f"bookmark name with markup echoed raw into the reply: «{reply[:140]}»")

    # ---- halal claims
    if c.get("memory") and (c["memory"] or {}).get("halal") and kind == "places":
        blob_all = " ".join(t for _, t in visible_texts(turn))
        mentions = re.search(r"халал|халяль|halal", blob_all, re.I)
        for p in places:
            txt = " ".join(str(p.get(f) or "") for f in ("why", "note", "caveat", "what_to_do"))
            poi = _POIS.get(p["id"]) or {}
            backed = bool(re.search(r"halal|халал|халяль", " ".join([p["name"], *(poi.get("tags") or []), poi.get("description") or ""]), re.I))
            says_ok = re.search(r"(халяль|халал|halal)[^.]{0,40}(учтен|учтён|taken into account|ескерілді|принят)", txt, re.I)
            if says_ok and not backed:
                add(S1, "halal_claim_unbacked", f"«{p['name']}» ({p['category']}) says halal is taken into account; no halal mark in its record: «{txt[:160]}»", place=p["name"])
            if p["category"] == "bar_nightlife" and says_ok:
                add(S1, "halal_on_bar", f"a bar «{p['name']}» is shown as «halal учтено»", place=p["name"])
        if not mentions and any(p["category"] in ("restaurant", "cafe", "fast_food") for p in places):
            add(S2, "halal_silent", "halal is on in the profile, food places are shown, and the answer says nothing about halal (neither a mark nor «не указан»)")
    return F


# --------------------------------------------------------------------------------------------------- I/O
class Limiter:
    def __init__(self, interval: float):
        self.interval, self.lock, self.next = interval, threading.Lock(), 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next)
            self.next = slot + self.interval
        if slot > now:
            time.sleep(slot - now)


def post_turn(client: httpx.Client, base: str, body: dict, timeout: float = 120) -> tuple[dict | None, list, float, str | None]:
    t0 = time.monotonic()
    stages: list[str] = []
    try:
        with client.stream("POST", f"{base}/api/turn", json=body, timeout=timeout) as r:
            if r.status_code != 200:
                return None, stages, time.monotonic() - t0, f"HTTP {r.status_code}: {r.read().decode('utf-8', 'replace')[:200]}"
            ans = None
            err = None
            for line in r.iter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if "stage" in obj:
                    stages.append(obj["stage"])
                elif "answer" in obj:
                    ans = obj["answer"]
                elif "error" in obj:
                    err = f"stream error: {obj['error']}"
            return ans, stages, time.monotonic() - t0, err if ans is None else None
    except Exception as exc:
        return None, stages, time.monotonic() - t0, f"{type(exc).__name__}: {exc}"


def save_profile(client: httpx.Client, base: str, form: dict) -> tuple[str | None, str | None]:
    f = {"with_kids": False, "kids_age_band": None, "mobility": "none", "quiet": False, "budget": "any", "halal": False, "no_alcohol": False,
         "language": None, "walk_pace": "normal", "cold_tolerance": "normal", "liked": [], "avoid": [], "about": ""}
    f.update(form)
    r = client.post(f"{base}/api/profile", json={"action": "save", "form": f, "id": None, "lang": "ru"}, timeout=30)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    view = r.json()
    # the form must come back as saved
    back = view.get("form", {})
    diff = {k: (form[k], back.get(k)) for k in form if back.get(k) != form[k] and k != "about"}
    if "about" in form and form["about"].strip() != (back.get("about") or ""):
        diff["about"] = (form["about"], back.get("about"))
    return view["id"], (f"profile round-trip differs: {diff}" if diff else None)


def run_case(client, base, case, limiter, live, results_by_id) -> list[dict]:
    rows: list[dict] = []
    pid, perr = (None, None)
    if case["memory"]:
        pid, perr = save_profile(client, base, case["memory"])
    state, prev, repro = None, None, []
    for idx, step in enumerate(case["steps"]):
        lat, lon = mc.ORIGINS[case["origin"]]
        body = {"text": step["say"], "lat": lat, "lon": lon, "lang": case["lang"], "lang_fixed": case["lang_fixed"],
                "weather": step.get("weather") or case["weather"]}
        if (step.get("at") or case["at"]):
            body["at"] = step.get("at") or case["at"]
        if case["budget_min"]:
            body["budget_min"] = case["budget_min"]
        if case["company"]:
            body["company"] = case["company"]
        if case["bookmarks"]:
            body["bookmarks"] = case["bookmarks"]
        if pid:
            body |= {"profile_on": True, "profile_id": pid}
        repro.append({k: v for k, v in body.items() if k not in ("profile_id",)} | ({"state": "<state of the previous answer>"} if idx else {}))
        send = dict(body, state=state) if state else body
        if live:
            limiter.wait()
        ans, stages, wall, err = post_turn(client, base, send)
        ctx = Ctx(case, idx, step, body, ans, wall, prev, None)
        if ans is not None:
            fnd = []
        elif err and err.startswith("HTTP 422") and 422 in (step["expect"].get("http") or []):
            fnd = [{"sev": S3, "code": "over_limit_rejected", "msg": f"the server answers 422 to a {len(step['say'])}-char message: {err}; the page must stop the input at the limit"}]
        else:
            fnd = [{"sev": S1, "code": "transport", "msg": err or "no answer"}]
        if perr and idx == 0:
            fnd.append({"sev": S2, "code": "profile_roundtrip", "msg": perr})
        if ans is not None:
            try:
                fnd += check_step(ctx, live)
            except Exception as exc:  # a checker bug must be visible, not silent
                fnd.append({"sev": S4, "code": "checker_error", "msg": f"{type(exc).__name__}: {exc}"})
            state = ans["state"]
            prev = {"turn": ans["turn"]}
        for f in fnd:
            f["repro"] = list(repro)
            f["case"] = case["id"]
            f["step"] = idx
        turn = ans["turn"] if ans else None
        row = {
            "label": None, "case": case["id"], "family": case["family"], "step": idx, "say": step["say"][:200], "tags": case["tags"],
            "origin": case["origin"], "at": body.get("at"), "weather": body["weather"], "lang_req": case["lang"], "memory": case["memory"],
            "bookmarks": [b["name"] for b in case["bookmarks"]], "wall_s": round(wall, 2), "stages": stages, "error": err,
            "request": {k: v for k, v in body.items() if k != "profile_id"},
            "kind": turn["kind"] if turn else None, "lang": turn["lang"] if turn else None,
            "reply": turn["reply"] if turn else None, "notice": turn["notice"] if turn else None,
            "notices": turn["notices"] if turn else None, "answers": turn["answers"] if turn else None,
            "chips": [c["label"] for c in turn["chips"]] if turn else None,
            "places": [digest_place(p) for p in turn["places"]] if turn else None,
            "route": turn["route"] if turn else None,
            "meta": ({k: turn["meta"].get(k) for k in ("parser", "generation", "model", "ms", "continued", "change", "radius_m", "note")}
                     | {"intent": turn["meta"].get("intent")}) if turn else None,
            "findings": fnd,
        }
        rows.append(row)
        results_by_id[(case["id"], idx)] = row
    return rows


def ab_findings(rows_by_key: dict, cases: list[dict]) -> list[dict]:
    out = []
    for c in cases:
        if not c["ab_base"] or c["steps"][0]["expect"].get("ab") != "differ":
            continue
        a, b = rows_by_key.get((c["id"], 0)), rows_by_key.get((c["ab_base"], 0))
        if not a or not b or a["kind"] is None or b["kind"] is None:
            continue
        sig = lambda r: (r["kind"], tuple(p["id"] for p in r["places"] or []), r["reply"], tuple((p["why"] or "") for p in r["places"] or []))  # noqa: E731
        if sig(a) == sig(b):
            f = {"sev": S2, "code": "memory_no_effect", "case": c["id"], "step": 0,
                 "msg": f"the setting {c['memory']} changes nothing visible: same kind, same cards, same lead, same reasons as without it ({b['case']})",
                 "repro": [a["request"] | {"profile_on": True, "profile_id": "<id from POST /api/profile action=save form=" + json.dumps(c["memory"], ensure_ascii=False) + ">"}]}
            a["findings"].append(f)
            out.append(f)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--label", required=True, help="offline | live")
    ap.add_argument("--only", default="", help="regex on case id")
    ap.add_argument("--live-only", action="store_true", help="only cases flagged live=True")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--min-interval", type=float, default=0.0, help="seconds between turns across workers (live: quota)")
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    load_dataset()
    cases = [c for c in mc.CASES if re.search(args.only, c["id"]) and (c["live"] or not args.live_only)]
    if args.limit:
        cases = cases[: args.limit]
    ids = {c["id"] for c in cases}
    for c in list(cases):  # an A/B twin needs its base
        if c["ab_base"] and c["ab_base"] not in ids:
            cases.append(next(x for x in mc.CASES if x["id"] == c["ab_base"]))
            ids.add(c["ab_base"])
    live = args.label == "live"
    limiter = Limiter(args.min_interval)
    rows_by_key: dict = {}
    all_rows: list[dict] = []
    done = [0]
    lock = threading.Lock()
    t0 = time.monotonic()

    def work(case):
        with httpx.Client() as client:
            try:
                rows = run_case(client, args.base, case, limiter, live, rows_by_key)
            except Exception as exc:
                rows = [{"case": case["id"], "family": case["family"], "step": 0, "say": "<runner crash>", "findings": [
                    {"sev": S1, "code": "runner_crash", "msg": f"{type(exc).__name__}: {exc}", "case": case["id"], "step": 0, "repro": []}]}]
        with lock:
            all_rows.extend(rows)
            done[0] += 1
            if done[0] % 10 == 0:
                print(f"[{args.label}] {done[0]}/{len(cases)} dialogues, {time.monotonic() - t0:.0f}s", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, cases))
    ab_findings(rows_by_key, cases)
    all_rows.sort(key=lambda r: (r["case"], r["step"]))
    out = Path(args.out)
    with (out / f"results.{args.label}.jsonl").open("w", encoding="utf-8") as fh:
        for r in all_rows:
            r["label"] = args.label
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    findings = [f | {"label": args.label, "family": next((r["family"] for r in all_rows if r["case"] == f["case"]), None),
                     "say": next((r["say"] for r in all_rows if r["case"] == f["case"] and r["step"] == f["step"]), None)}
                for r in all_rows for f in r["findings"]]
    with (out / f"findings.{args.label}.jsonl").open("w", encoding="utf-8") as fh:
        for f in findings:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    by_sev = Counter(f["sev"] for f in findings)
    print(f"[{args.label}] {len(cases)} dialogues, {len(all_rows)} steps, {len(findings)} findings {dict(sorted(by_sev.items()))}, {time.monotonic() - t0:.0f}s")
    codes = Counter((f["sev"], f["code"]) for f in findings)
    for (sev, code), n in sorted(codes.items()):
        print(f"  {sev} {code}: {n}")


if __name__ == "__main__":
    main()
