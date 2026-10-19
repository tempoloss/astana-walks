"""Candidate retrieval: category/keyword/flag scoring, opening-hours gating, chain duplicates, ranking. The radius a
request reaches, the minimum-stay budget and the shelter rule live in walks.radius, walks.stay, walks.shelter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .asked import info_first
from .attributes import (
    crowd_bonus,
    diet_signal,
    halal_signal,
    has_socket,
    has_wifi,
    keyword_score,
    local_food_signal,
    meat_place,
    pets_signal,
    requested_diets,
    serves_alcohol,
    wheelchair_access,
)
from .chains import collapse_duplicates
from .city_layers import lit_near
from .colocated import collapse_shared_coordinates
from .feedback import FeedbackIndex
from .holidays import holiday_name
from .hours import poi_hours, to_local_naive
from .kids import (
    KIDS_BONUS,
    KIDS_HOST_CATEGORIES,
    collapse_anonymous,
    is_member,
    keep_named,
    kids_signal,
    padding_of,
)
from .lexicon import normalize
from .marks import Marks, count_marks, supply_nearby
from .models import (
    POI,
    Candidate,
    Constraints,
    Filters,
    Intent,
    PeopleEvidence,
    Personal,
    RetrievalResult,
    WeatherInfo,
)
from .names import NAME_RATIO_MIN, best_ratio, name_keys, names_place
from .presets import PRESET_NAMES, PRESETS
from .price_kind import price_bonus, quick_bonus
from .radius import (
    ERRAND_KINDS,
    FOOD_KINDS,
    MAX_RADIUS_M,
    NEAREST_FAR,
    RADIUS_STEPS,
    SPEED_KMH,
    backfill_ok,
    declared_radius_m,
    haversine_m,
    is_stroll,
    related_kinds,
    travel_minutes,
    travel_share,
    walk_minutes,
)
from .shelter import (
    AIR_OUTDOOR_KEPT,
    LIT_NEAR,
    OUTDOOR_OFF_KIND,
    OUTDOOR_REQUESTS,
    WEATHER_OUTDOOR_KEPT,
    apply_shelter_rule,
    asks_outdoors,
    is_outdoor_place,
    is_outdoor_sport,
)
from .stay import fit_stay_budget
from .sun import is_dark, sun_for
from .weather import INDOOR_CATEGORIES, OUTDOOR_CATEGORIES
from .wish_rank import hours_rare, not_for, seen_outside, wish_bonus
from .wishes import (
    keep_requested_kinds,
    mark_unmet_wishes,
    open_first,
    round_the_clock_first,
    without_night_dead_ends,
)

TRANSIT_CATEGORY = "transit_station"
MONEY_CATEGORY = "money"
ANCHOR_RADIUS_M = 200  # a request from a starting place's own point comes from that place
ANCHOR_PLACE_M = (
    1000  # how far the record of that place may sit from the point (a mall, a park, a monument)
)


def anchor_names(lat: float, lon: float) -> frozenset[str]:
    """The names, in every language, of the stand's starting place a request comes from (within ANCHOR_RADIUS_M of its
    point), or nothing when the request starts elsewhere."""
    for key, (plat, plon) in PRESETS.items():
        if haversine_m(lat, lon, plat, plon) <= ANCHOR_RADIUS_M:
            return frozenset(normalize(n) for n in (key, *PRESET_NAMES.get(key, {}).values()))
    return frozenset()


DAYTIME_CATEGORIES = frozenset({"museum_gallery", "coworking_library"})
MIN_IN_CATEGORY = (
    3  # fewer in-category candidates than this -> fill up with other categories (flagged)
)
TOP_N = (
    20  # candidates handed to the generation step: the model narrows them to 2-3 for this request
)
HALAL_BONUS = 4.0  # a food place the record itself marks halal, for a request that asks for it
DIET_BONUS = 4.0  # a food place the record itself marks vegetarian / vegan / gluten-free / kosher, when asked
MEAT_PENALTY = 3.0  # a meat house for a vegetarian / vegan request
LANDMARK_BONUS = 3.0  # the place the user described («башня с шаром») by its name
DEEP_NIGHT_START, DEEP_NIGHT_END = 23, 6  # local hours; [23:00, 06:00)
DEEP_NIGHT_OPEN_BONUS = 2.0  # on top of the night bonus: confirmed-open beats unknown hours
SHORT_TIME_MIN = 45  # a budget up to this is «быстро»: the nearer place wins
NEAR_WEIGHT, NEAR_WEIGHT_CONSTRAINED = 1.5, 3.0  # score points lost over the whole radius
DARK_OUTDOOR_PENALTY = (
    3.0  # park / viewpoint / playground after sunset, for a request that did not ask for it
)
LIT_BONUS = 2.0  # after dark, an outdoor place beside a street the data tag lit, for a request that asked for it
GYM_OUTDOOR_PENALTY = 3.0
_GYM_WISH = re.compile(
    r"спортзал|тренажёр|тренажер|фитнес|\bgym\b|fitness|спорт залы|жаттығу", re.I
)

NIGHT_START, NIGHT_END = 21, 5  # local hours; [21:00, 05:00) counts as "night" for ranking
VISITED_PENALTY = 2.5  # a place the user's profile says they have been to
LIKED_STEP = 0.3  # per mark «понравилось» of the category, at most three
LIKED_OPEN_BONUS = 1.5  # a kind the person likes, when the request names no kind of its own

_UNKNOWN_PENALTY = 1.0
_UNKNOWN_PENALTY_NIGHT = 2.5


def is_night(intent: Intent, when: datetime) -> bool:
    h = to_local_naive(when).hour
    return intent.night or h >= NIGHT_START or h < NIGHT_END


def is_deep_night(when: datetime) -> bool:
    """23:00-06:00 local: little is open, and a place whose hours are unknown is far more likely closed."""
    h = to_local_naive(when).hour
    return h >= DEEP_NIGHT_START or h < DEEP_NIGHT_END


def distance_weight(intent: Intent, *, near: bool = False) -> float:
    """How hard the distance counts: a budget or short-time request wants the nearer of two similar places; so does
    a request kept outdoors in bad weather or air (`near`): the shorter way is the lesser exposure."""
    constrained = near or intent.budget == "low" or intent.time_budget_min <= SHORT_TIME_MIN
    return NEAR_WEIGHT_CONSTRAINED if constrained else NEAR_WEIGHT


def _score(
    poi: POI,
    intent: Intent,
    state: str,
    distance_m: float,
    radius_m: int,
    night: bool,
    categories: list[str],
    weather: WeatherInfo | None = None,
    dark: bool = False,
    people: PeopleEvidence | None = None,
    visited: bool = False,
    liked: int = 0,
    deep_night: bool = False,
    kids_band: str | None = None,
    hours_night: bool
    | None = None,  # the clock of the arrival is night: «неизвестно» is likely closed
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    s = 0.0

    if poi.category in categories or is_member(poi, set(categories), categories, intent):
        s += 3.0
        if intent.categories:
            reasons.append("category")
    elif categories:
        s -= 2.0  # only reached when too few POIs of the requested categories are in range
        reasons.append("off_category")

    kw, hits = keyword_score(poi, intent.free_text_keywords)
    if kw:
        s += kw
        reasons.append("keywords:" + ",".join(hits))

    cat = poi.category
    if intent.halal and cat in FOOD_KINDS:
        if halal_signal(poi):
            s += HALAL_BONUS
            reasons.append("halal")
        else:
            s -= 1.0
            reasons.append("halal_unverified")
    s += wish_bonus(poi, intent, reasons)
    if cat in FOOD_KINDS:
        for diet in requested_diets(intent):
            if diet_signal(poi, diet):
                s += DIET_BONUS
                reasons.append(f"diet:{diet}")
            else:
                s -= 1.0
                reasons.append(f"diet_unverified:{diet}")
                if diet in ("vegetarian", "vegan") and meat_place(poi):
                    s -= (
                        MEAT_PENALTY  # a steak house is the wrong answer, whatever the keywords say
                    )
    if names_place(poi, getattr(intent, "landmark_refs", [])):
        s += LANDMARK_BONUS
        reasons.append("landmark_ref")
    if intent.with_kids:
        s += KIDS_BONUS.get(kids_band or "", KIDS_BONUS[""]).get(cat, 0.0)
        if cat == "bar_nightlife":
            s -= 6.0
        if cat == "kids_playground" or (cat in KIDS_HOST_CATEGORIES and kids_signal(poi)):
            reasons.append("kids")
    if intent.quiet:
        delta = {
            "park_garden": 1.5,
            "coworking_library": 2.0,
            "cafe": 1.0,
            "museum_gallery": 1.0,
            "viewpoint": 1.0,
            "mall": -1.5,
            "entertainment": -1.5,
            "bar_nightlife": -2.0,
            "fast_food": -1.0,
        }.get(cat, 0.0)
        s += delta
        if delta > 0:
            reasons.append("quiet")
    if intent.quiet and people is not None and people.noise in {"quiet", "noisy"}:
        quiet_marks = people.noise == "quiet"
        s += 1.5 if quiet_marks else -2.0
        reasons.append("people_quiet" if quiet_marks else "people_noisy")
    if intent.needs_wifi_socket:
        wifi, sock = has_wifi(poi), has_socket(poi)
        crowd_wifi, crowd_sock = (people.wifi, people.socket) if people else (0, 0)
        if wifi:
            s += 2.5
            reasons.append("wifi")
        elif crowd_wifi:
            s += crowd_bonus(crowd_wifi)
            reasons.append("people_wifi")
        if sock:
            s += 2.5
            reasons.append("socket")
        elif crowd_sock:
            s += crowd_bonus(crowd_sock)
            reasons.append("people_socket")
        if not (wifi or sock or crowd_wifi or crowd_sock):
            s -= 1.5
            reasons.append("wifi_unverified")
        if cat == "coworking_library":
            s += 1.0
    if intent.accessibility:
        wc = wheelchair_access(poi)
        if wc == "yes":
            s += 3.0
            reasons.append("wheelchair")
        elif wc == "limited":
            s += 0.5
        elif wc is None:
            s -= 1.5  # a step-free need is not met by «не указано»: confirmed places come first
            reasons.append("wheelchair_unverified")
    if intent.budget == "low" or getattr(intent, "price_cap_kzt", 0):
        s += price_bonus(poi, reasons)
    s += quick_bonus(poi, intent)
    if getattr(intent, "pets", False) and pets_signal(poi):
        s += 3.0
        reasons.append("pets")
    hours_night = night if hours_night is None else hours_night
    if night and cat in {"bar_nightlife", "entertainment", "culture_theatre_cinema"}:
        s += 1.5
    if (
        hours_night
    ):  # «щас уже поздно» at 08:40 is no night for the hours: the clock of the answer is
        if state != "open" and cat in DAYTIME_CATEGORIES:
            s -= 2.0  # a museum / library without confirmed hours is unlikely to be open at night
            reasons.append("daytime_place")
        if state == "open":
            s += 2.0
            reasons.append("open_at_night")
            if deep_night:
                s += DEEP_NIGHT_OPEN_BONUS  # 23:00-06:00: «неизвестно» is usually closed

    if state == "unknown":
        s -= _UNKNOWN_PENALTY_NIGHT if hours_night else _UNKNOWN_PENALTY
        reasons.append("hours_unknown")
        if deep_night and state == "unknown":
            reasons.append("night_unknown")  # the card says it may be closed
    elif state == "open":
        s += 0.5
        reasons.append("open")

    if people is not None and people.hours is not None:
        weight = 1.0 if people.confidence == "medium" else 0.6
        if people.hours == "open" and state == "unknown":
            s += 1.0 * weight
            reasons.append("people_open")
        elif people.hours == "closed" and state != "closed":
            s -= (2.0 if state == "unknown" else 1.0) * weight
            reasons.append("people_closed")
        elif people.hours == "mixed":
            reasons.append("people_mixed")
    if visited:
        s -= VISITED_PENALTY
        reasons.append("visited")
    if liked:
        s += LIKED_STEP * min(liked, 3)
        if not intent.wished:
            s += LIKED_OPEN_BONUS
        reasons.append("liked_category")
    if poi.has_real_description():  # OSM tag or Wikipedia, not text derived from tags
        s += 0.3
    if poi.name_generated:
        s -= 0.3
    held = weather is not None and weather.indoor_preferred and asks_outdoors(intent)
    s -= distance_weight(intent, near=held) * distance_m / max(radius_m, 1)
    if weather is not None and weather.indoor_preferred:
        if held:
            # asked for the outdoors: the requested kind stays (no indoor bonus, no outdoor penalty); a place of
            # another kind is a rule violation while one of the requested kind is left; the card says why the
            # walk is better kept short
            if "off_category" in reasons:
                reasons.append(OUTDOOR_OFF_KIND)
            elif is_outdoor_place(poi):
                if weather.adverse:
                    reasons.append(WEATHER_OUTDOOR_KEPT)
                if weather.air_bad:
                    reasons.append(AIR_OUTDOOR_KEPT)
        elif cat in INDOOR_CATEGORIES or (  # a food request: fast food is eaten inside as a café is
            cat == "fast_food" and intent.categories and set(intent.categories) <= FOOD_KINDS
        ):
            s += 2.5
            if weather.adverse:
                reasons.append("weather_indoor")
            if weather.air_bad:
                reasons.append("air_indoor")
        elif is_outdoor_place(poi):
            s -= 4.0 if cat in OUTDOOR_CATEGORIES else 1.5
            if weather.adverse:
                reasons.append("weather_outdoor")
            if weather.air_bad:
                reasons.append("air_outdoor")
    if dark:
        owish = asks_outdoors(intent)
        if owish and is_outdoor_place(poi):  # asked for the outdoors: the dark only orders them
            lit = lit_near(
                poi.lat, poi.lon
            )  # lit way near; no tag is no verdict (the card says so)
            reasons.append(LIT_NEAR if lit else "dark_outdoor")
            s += LIT_BONUS if lit else 0.0
        elif not owish and (cat in OUTDOOR_CATEGORIES or is_outdoor_sport(poi)):
            s -= DARK_OUTDOOR_PENALTY
            reasons.append("dark_outdoor")
        elif cat in INDOOR_CATEGORIES:
            reasons.append("dark_indoor")
    if (
        cat == "sport"
        and _GYM_WISH.search(" ".join(intent.free_text_keywords))
        and is_outdoor_sport(poi)
    ):
        s -= GYM_OUTDOOR_PENALTY  # «спортзал» / «gym»: a stadium or a ski base is not what was asked for
    return s, reasons


# ---------------------------------------------------------------- main entry


@dataclass(frozen=True)
class _Context:
    """What the dialogue, the people's marks and the personal profile add to one retrieval."""

    constraints: Constraints
    feedback: FeedbackIndex | None
    visited: frozenset[str]
    liked: dict[str, int]
    kids_band: str | None
    shown: tuple[
        tuple[POI, frozenset[str]], ...
    ]  # places shown earlier in the dialogue, with name keys

    def excludes(self, p: POI) -> bool:
        """Shown already, or another branch of the same chain anywhere («что-то другое» must not bring Starbucks back
        under another id), or alcohol while «без алкоголя»."""
        if self.constraints.no_alcohol and serves_alcohol(p):
            return True
        if p.id in self.constraints.exclude_ids:
            return True
        keys = name_keys(p)
        return bool(keys) and any(
            s.category == p.category and best_ratio(keys, shown_keys) >= NAME_RATIO_MIN
            for s, shown_keys in self.shown
        )


class _Pool:
    """Candidates scored inside one radius, with what was left out on the way."""

    def __init__(self) -> None:
        self.scored: list[Candidate] = []
        self.closed_in = 0  # closed POIs inside the requested categories; closed_out: outside them
        self.closed_out = 0
        self.other = 0
        self.excluded_stay = 0
        self.stay_kinds: list[str] = []  # categories the time-fit rule dropped places of
        self.followup = 0
        self.alcohol_removed = (
            0  # places of the requested kinds left out by the profile's «без алкоголя»
        )
        self.avoided = 0  # places left out by the profile's «не показывать»
        self.marks = (
            Marks()
        )  # what the records say about halal / step-free (honest counts for the lead)


def _gather(
    in_radius: list[tuple[POI, float]],
    radius: int,
    intent: Intent,
    local: datetime,
    night: bool,
    weather: WeatherInfo | None,
    ctx: _Context,
    deep_night: bool = False,
) -> _Pool:
    requested = list(intent.categories)
    out = _Pool()
    for p, d in in_radius:
        if p.category == "other" and ("other" not in requested or not p.is_state_service()):
            continue  # `other` holds the ЦОН only: a place for an explicit state-service request, never a walk
        if p.category in ctx.constraints.avoid or p.category in intent.refused:
            out.avoided += 1  # «не показывать» or «не хочу в кафе»: a hard exclusion, no backfill path brings it back
            continue
        if ctx.constraints.no_alcohol and serves_alcohol(p):
            out.alcohol_removed += not requested or p.category in requested
            continue
        if ctx.excludes(p):
            out.followup += 1
            continue
        travel = travel_minutes(d, intent.mode)
        arrival = local + timedelta(minutes=travel)
        hours = poi_hours(p, arrival)
        state = hours.state
        if state == "closed" and not seen_outside(p, intent):
            if not requested or p.category in requested:
                out.closed_in += 1
            else:
                out.closed_out += 1
            continue
        if (
            (intent.accessibility and wheelchair_access(p) == "no")
            or (intent.with_kids and p.category == "bar_nightlife")
            or (intent.minor and p.category == "bar_nightlife")
            or not_for(p, intent)
        ):
            out.other += 1
            continue
        people = ctx.feedback.evidence(p.id, arrival) if ctx.feedback else None
        score, reasons = _score(
            p,
            intent,
            state,
            d,
            radius,
            night,
            requested,
            weather,
            is_dark(weather, arrival),
            people,
            p.id in ctx.visited,
            ctx.liked.get(p.category, 0),
            deep_night,
            ctx.kids_band,
            hours_night=night and not NIGHT_END <= arrival.hour < NIGHT_START,
        )
        out.scored.append(
            Candidate(
                poi=p,
                distance_m=round(d),
                walk_min=walk_minutes(d),
                travel_min=travel,
                hours_state=state,
                hours_note=hours.note,
                hours_issue=hours.issue,
                score=round(score, 3),
                reasons=reasons,
                people=people,
            )
        )
    before = out.scored
    out.scored, out.excluded_stay = fit_stay_budget(
        before, intent.time_budget_min, frozenset(intent.wished)
    )
    kept = {c.poi.id for c in out.scored}
    out.stay_kinds = sorted({c.poi.category for c in before if c.poi.id not in kept})
    out.marks = count_marks(out.scored, intent)
    return out


FAR_LOOKUP = (
    8  # nearest records of the absent kind that are checked for hours / stay (some may be closed)
)


def _nearest_requested(
    pois: list[POI],
    lat: float,
    lon: float,
    intent: Intent,
    local: datetime,
    night: bool,
    weather: WeatherInfo | None,
    ctx: _Context,
    member_cats: set[str],
    declared_m: int,
    deep_night: bool,
) -> list[Candidate]:
    """The nearest open-or-unknown place of the requested kinds (at most MAX_RADIUS_M away), as the one card of a
    request whose kind has no candidate in range. Beyond `declared_m` it carries NEAREST_FAR, so the card says «рядом
    нет X; ближайшее — N км»; nearer ones (they did not fit the time) carry the minimum-stay note instead. Empty when
    the dataset has none."""
    requested = list(intent.categories)
    far = sorted(
        (
            (p, d)
            for p in pois
            if p.category != TRANSIT_CATEGORY
            and is_member(p, member_cats, requested, intent)
            and (d := haversine_m(lat, lon, p.lat, p.lon)) <= MAX_RADIUS_M
        ),
        key=lambda pd: (pd[1], pd[0].id),
    )[:FAR_LOOKUP]
    if not far:
        return []
    pool = _gather(far, round(far[-1][1]), intent, local, night, weather, ctx, deep_night)
    if not pool.scored:
        return []
    best = min(pool.scored, key=lambda c: (c.distance_m, c.poi.id))
    if best.distance_m <= declared_m:
        return [best]
    return [best.model_copy(update={"reasons": [*best.reasons, NEAREST_FAR]})]


def _without_visited_kinds(chosen: list[Candidate], intent: Intent) -> list[Candidate]:
    """The kinds the user has just been to («только из мечети, где поесть») are left out, unless nothing else is left."""
    left = [c for c in chosen if c.poi.category not in intent.exclude_categories]
    return left or chosen


def retrieve(
    pois: list[POI],
    lat: float,
    lon: float,
    intent: Intent,
    when: datetime,
    top_n: int = TOP_N,
    weather: WeatherInfo | None = None,
    *,
    constraints: Constraints | None = None,
    feedback: FeedbackIndex | None = None,
    personal: Personal | None = None,
) -> RetrievalResult:
    """Rank POIs for (lat, lon) at time `when`. `when` may be naive (Astana local) or aware."""
    local = to_local_naive(when)
    indoor = bool(weather and weather.indoor_preferred)
    outdoor_request = asks_outdoors(intent)
    swap_indoor = (
        indoor and not outdoor_request
    )  # a named outdoor wish stays outdoors (advice, not a swap)
    stroll = is_stroll(intent)
    constraints = constraints or Constraints()
    base_radius = declared_radius_m(intent, indoor, constraints)
    by_id = {p.id: p for p in pois}
    ctx = _Context(
        constraints=constraints,
        feedback=feedback,
        visited=frozenset(personal.visited) if personal else frozenset(),
        liked=dict(personal.liked) if personal else {},
        kids_band=personal.kids_age_band if personal else None,
        shown=tuple(
            (by_id[i], frozenset(name_keys(by_id[i])))
            for i in constraints.exclude_ids
            if i in by_id
        ),
    )
    night = is_night(intent, when)
    deep_night = is_deep_night(when)
    sun_info = sun_for(local.date()) if weather is not None else None

    # the widening steps stop where the time's own circle would (a wider search for an unstated time widens no further)
    own = declared_radius_m(intent, indoor, constraints.model_copy(update={"radius_floor_m": None}))
    widest = max(base_radius, own * RADIUS_STEPS[-1])
    here = (
        set() if "attraction_landmark" in intent.wished else anchor_names(lat, lon)
    )  # «что посмотреть» at Байтерек
    reachable: list[tuple[POI, float]] = []
    for p in pois:
        if p.category == TRANSIT_CATEGORY:
            continue  # stations are never recommended; they only feed the LRT hint (walks.transit)
        if p.category == MONEY_CATEGORY and MONEY_CATEGORY not in intent.categories:
            continue  # money points are used, not strolled: only an explicit request («где банкомат») brings them in
        d = haversine_m(lat, lon, p.lat, p.lon)
        if here and d <= ANCHOR_PLACE_M and normalize(p.name) in here:
            continue  # the place the user is at («рядом с Mega Silk Way») is where the walk starts, not where it goes
        if d <= widest:
            reachable.append((p, d))

    requested = list(intent.categories)
    member_cats = set(requested)
    substitutes: frozenset[str] = frozenset()
    if swap_indoor and member_cats & OUTDOOR_REQUESTS:
        # asked for outdoor places in bad weather / air: indoor alternatives count as matches, but a card of one
        # is "substituted" (a visible compromise), not a plain match
        substitutes = frozenset(INDOOR_CATEGORIES - member_cats)
        member_cats |= INDOOR_CATEGORIES

    # Widen the radius stepwise while no place of the requested kind is in range (for «другие места» while fewer than
    # MIN_IN_CATEGORY: more of the same kind first); «поближе» never widens. Only then back-fill.
    enough = MIN_IN_CATEGORY if constraints.exclude_ids else 1
    first = (
        "fast_food" if intent.wished[:1] == ["fast_food"] else None
    )  # «шаурму или бургер»: a café is no answer
    capped = constraints.radius_cap_m is not None
    for factor in RADIUS_STEPS[:1] if capped else RADIUS_STEPS:
        radius = round(min(base_radius * factor, widest))
        in_radius = [
            (p, d)
            for p, d in reachable
            if d <= radius
            or (intent.local_food and capped and d <= widest and local_food_signal(p))
        ]  # «поближе» after «бешбармак»: the cap cuts the rest, the Kazakh place stays
        pool = _gather(in_radius, radius, intent, local, night, weather, ctx, deep_night)
        if not requested or (
            sum(is_member(c.poi, member_cats, requested, intent) for c in pool.scored) >= enough
            and (first is None or any(c.poi.category == first for c in pool.scored))
            and (not intent.local_food or any("local_food" in c.reasons for c in pool.scored))
            and (  # «музей?»: a museum proper, not only a gallery in a mall
                intent.wished != ["museum_gallery"]
                or any("museum" in c.reasons for c in pool.scored)
            )
        ):
            break

    wished = frozenset(intent.wished)

    def rank(c: Candidate) -> tuple:
        # a kind the person named comes before anything the system added next to it (padding, a substitute)
        named = c.poi.category in wished or (
            not outdoor_request and is_member(c.poi, member_cats, requested, intent)
        )
        return (bool(wished) and not named, -c.score, c.distance_m, c.poi.id)

    daytime = (
        NIGHT_END <= local.hour < NIGHT_START
    )  # a meal by day: the nearer place, not the one with hours
    scored, merged_log = collapse_duplicates(hours_rare(pool.scored, daytime and intent.eat))
    scored, shared_log = collapse_shared_coordinates(scored)
    merged_log += shared_log
    clustered_away = len(pool.scored) - len(scored)
    scored = collapse_anonymous(
        sorted(scored, key=rank)
    )  # one card per kind of anonymous OSM record

    # A non-stroll kind with no candidate left in range (none exists, or every one is closed / does not fit the time):
    # the back-fill is limited to kinds that still answer the wish (RELATED_KINDS); when none is in range either, show
    # the nearest place of the kind itself, saying how far it is, instead of filling the list with unrelated places (a
    # church for a cinema). A stroll keeps its back-fill: a park / landmark answers it.
    strict = [
        c for c in scored if not requested or is_member(c.poi, member_cats, requested, intent)
    ]
    absent = bool(requested) and (not stroll or outdoor_request) and not strict
    # the anonymous records one card stands for count as places of the kind: collapsing them is not a shortage
    plenty = len(strict) + sum(c.nearby_anon for c in strict)
    relaxed = bool(requested) and plenty < MIN_IN_CATEGORY
    chosen = strict
    if relaxed:
        chosen = [
            c
            for c in scored
            if is_member(c.poi, member_cats, requested, intent)
            or (
                backfill_ok(c.poi.category, intent, stroll)
                and (  # «ещё»: the same kind; «без алкоголя» after it rules the bars out, not the answer
                    not constraints.exclude_ids or (constraints.no_alcohol and not strict)
                )
                and c.distance_m <= base_radius
                and (
                    not outdoor_request or c.poi.category in OUTDOOR_REQUESTS
                )  # never a café for a walk
            )
        ]
        if absent:
            related = related_kinds(requested)
            chosen = [c for c in chosen if c.poi.category in related]
            if not chosen:
                relaxed = False
                chosen = _nearest_requested(
                    pois,
                    lat,
                    lon,
                    intent,
                    local,
                    night,
                    weather,
                    ctx,
                    member_cats,
                    base_radius,
                    deep_night,
                )
                if chosen:
                    radius = max(radius, chosen[0].distance_m)
    closed = pool.closed_in + (pool.closed_out if relaxed else 0)
    excluded_outdoor = 0
    if swap_indoor:
        chosen, excluded_outdoor = apply_shelter_rule(chosen)
    chosen = _without_visited_kinds(chosen, intent)
    if deep_night:
        chosen = without_night_dead_ends(chosen, wished)

    cands = sorted(chosen, key=rank)
    if night and ERRAND_KINDS & set(
        requested
    ):  # an errand at night: open first, round the clock next
        cands = round_the_clock_first(cands, wished)
    elif deep_night:
        cands = open_first(cands, wished)
    top = keep_named(cands, keep_requested_kinds(cands, requested, top_n, rank))
    top = [
        c.model_copy(
            update={
                "padding": padding_of(c, requested, member_cats, base_radius, intent, substitutes)
            }
        )
        for c in top
    ]
    top = mark_unmet_wishes(top)
    if intent.info_about:
        top = info_first(top, pois, lat, lon, intent, local, ctx.feedback, base_radius)

    nearby, nearby_with_hours = supply_nearby(pois, lat, lon, intent, local, stroll)
    filters = Filters(
        mode=intent.mode,
        speed_kmh=SPEED_KMH[intent.mode],
        time_budget_min=intent.time_budget_min,
        travel_share=travel_share(stroll),
        radius_declared_m=base_radius,
        radius_effective_m=radius,
        radius_factor=factor,
        categories_requested=requested,
        categories_applied=requested,
        categories_relaxed=relaxed,
        night_mode=night,
        keywords=list(intent.free_text_keywords),
        checked_at=local.strftime("%Y-%m-%d %H:%M") + " Asia/Almaty",
        pois_total=len(pois),
        in_radius=len(in_radius),
        excluded_closed=closed,
        excluded_other=pool.other,
        candidates_returned=len(top),
        excluded_min_stay=pool.excluded_stay,
        excluded_stay_kinds=pool.stay_kinds,
        excluded_outdoor=excluded_outdoor,
        clustered_away=clustered_away,
        merged=merged_log,
        hours_unknown=sum(1 for c in top if c.hours_state == "unknown"),
        weather_adapted=indoor,
        outdoor_request=outdoor_request,
        air_bad=bool(weather and weather.air_bad),
        dark=is_dark(weather, local),
        sunrise=sun_info[0].strftime("%H:%M") if sun_info else None,
        sunset=sun_info[1].strftime("%H:%M") if sun_info else None,
        sun_source=sun_info[2] if sun_info else None,
        holiday=holiday_name(local.date()),
        excluded_followup=pool.followup,
        shrink=constraints.radius_factor,
        people_marks=sum(1 for c in top if c.people is not None),
        requested_nearby=nearby,
        requested_nearby_with_hours=nearby_with_hours,
        **pool.marks._asdict(),  # halal / step-free counts of the records in range
        excluded_alcohol=pool.alcohol_removed,
        excluded_avoid=pool.avoided,
    )
    return RetrievalResult(candidates=top, filters=filters)
