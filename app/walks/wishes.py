"""Post-ranking rules of the wishes a record can only partly confirm: the night (what is confirmed open comes first),
an errand (the nearest that is confirmed open first), and the honest «no place found has it» for halal and the diets."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime, time, timedelta

from .hours import is_24_7, poi_hours
from .lexicon import match
from .models import Candidate
from .supply import UTILITY_KINDS

# A person goes to one of these to do one thing: the nearest one that works is the answer, not the best rated one.
ERRANDS = UTILITY_KINDS | {"lodging", "public_toilet"}
NIGHT_PROBE = time(2, 0)  # «ночной магазин» asked by day: open at 02:00 of the coming night
DAY_START, DAY_END = 5, 21  # [05:00, 21:00) is day, as retrieve.NIGHT_END / NIGHT_START
_GROUP = {"open": 0, "unknown": 1}  # what the data confirm open, then unknown hours, then the rest
# From this many minutes on foot a place is far: its walk is said as a distance and the transport, never the minutes
# (about 2 km by the streets; «как дойти» suggests a vehicle), and the sub-kind asked does not lead from there
FAR_WALK_MIN = 25
# the sub-kinds whose absence nearby is said, with the nearest one as a card: a dentist, a children's clinic, an ATM
GAP_SUBKINDS = frozenset({"atm", "dentist", "kids_doctor"})

# unknown hours at 23:00-06:00 are as good as closed for these
UNLIKELY_AT_NIGHT = frozenset({"mall", "museum_gallery", "coworking_library"})


def open_first(ranked: list[Candidate], wished: frozenset[str] = frozenset()) -> list[Candidate]:
    """23:00-06:00: places whose opening hours the data confirm come before every place with unknown hours (a stable
    partition: the rank order holds inside each group): at 3 a.m. a night shift wants what is open, not what is
    nearest and probably closed. A kind the person named («погулять с собакой») keeps its place before everything
    else: the night orders the places of that kind, it never replaces them with a café that happens to be open."""
    return sorted(
        ranked,
        key=lambda c: (bool(wished) and c.poi.category not in wished, c.hours_state != "open"),
    )


def errand(categories: Sequence[str]) -> bool:
    """Is this a request for errands only (a pharmacy, a shop, an ATM, a bed, a toilet)."""
    return bool(categories) and set(categories) <= ERRANDS


# A kind inside a category that only a record's tags or name tell apart, asked by the person's words (walks.intent):
#   atm          a cash machine among the banks (a branch's hours are not the machine's)
#   dentist      a dentist among the clinics (a laboratory is no dentist)
#   kids_doctor  a children's clinic first, never a dentist («балалар емханасы», a child is ill: Intent.sick)
#   doctor       a doctor for an illness, never a dentist («где врач», «емхана», somebody is ill)
#   kazpost      a post office of Kazpost, never a courier's pickup point (СДЭК) unless a courier is asked
#   play         a place to play (PS, bowling, a cinema), never a concert or congress hall (walks.dialog_unmapped)
_ATM_TAGS = frozenset({"amenity=atm", "atm=yes"})
_DENTIST_TAGS = frozenset({"amenity=dentist", "healthcare=dentist"})
_DENTIST_NAME = re.compile(
    r"\bdent|\bдент|стомат|\bstom", re.I
)  # «Doctor Dent», «Доктор Дент», «Uni Stom»
_KIDS_CLINIC = re.compile(r"детск|педиатр|pediatr|paediatr|child|балалар", re.I)
_COURIER_NAME = re.compile(
    r"сдэк|cdek|dhl|exline|\bксэ\b|\bym\b|beepost|jana post|пункт\w* выдачи|pickup|ozon|wildberries|kaspi",
    re.I,
)
_PLAY_TAGS = frozenset(
    {"leisure=bowling_alley", "leisure=amusement_arcade", "leisure=escape_game", "amenity=cinema"}
    | {"tourism=theme_park", "leisure=trampoline_park"}
    | {
        f"overture_category={c}"
        for c in ("bowling_alley", "pool_billiards", "arcade", "amusement_park", "movie_theater")
    }
    | {"overture_category=arts_and_entertainment"}
)
_PLAY_NAME = re.compile(
    r"боулинг|bowling|бильярд|billiard|снукер|караоке|karaoke|батут|trampolin|\bps ?[3-5]\b|playstation|"
    r"кибер|cyber|квест|\bquest|escape|кино|cinema|развлекательн|entertainment",
    re.I,
)
_KIDS_NAME = re.compile(r"детск|\bkids?\b|kid[a-z]|кидбург|балалар", re.I)
# the words: (sub-kind, the category they must name, words, True: the sub-kind holds unless the words are said)
_COURIER = r"курьер|доставк|посылк|сдэк|cdek|dhl|exline|пункт\w* выдачи|pickup|parcel|courier|deliver|сәлемдеме"
_SUBKIND_WORDS = (
    (
        "atm",
        "money",
        r"банкомат|налич|налик|\bнал\b|\batms?\b|cash machine|cashpoint|ақша ал|ақша шеш",
        False,
    ),
    (
        "dentist",
        "clinic",
        r"стоматолог|зубн\w* (?:врач|клиник|кабинет)|дантист|тіс (?:дәрігер|емхана)|dentist|dental",
        False,
    ),
    (
        "kids_doctor",
        "clinic",
        r"детск|педиатр|pediatr|child|\bkids?\b|балалар|\bбала\w*|ребен|ребён",
        False,
    ),
    ("doctor", "clinic", r"емхан|поликлиник|врач|дәрігер|терапевт|doctor|\bgp\b|polyclinic", False),
    ("kazpost", "post", _COURIER, True),
)
_WORD_RX = [(sub, cat, re.compile(rx), negated) for sub, cat, rx, negated in _SUBKIND_WORDS]


def asked_subkind(text: str, categories: Sequence[str]) -> str:
    """The sub-kind the words ask for inside a category they name ('' for none): «банкомат», «стоматолог», a doctor;
    a post office is Kazpost's unless a courier is said."""
    low = text.lower()
    return next(
        (
            s
            for s, cat, rx, negated in _WORD_RX
            if cat in categories and bool(rx.search(low)) != negated
        ),
        "",
    )


# what a work wish names (Intent.work_needs): a socket («с розеткой», «зарядить»), Wi-Fi («вайфай», «интернет»), or both
_SOCKET_WORDS = re.compile(r"розетк|заряд|sockets?\b|outlets?\b|\bplugs?\b|charg")
_WIFI_WORDS = re.compile(r"wi-?fi|вай-?фа|интернет|internet")


def asked_work_needs(text: str) -> str:
    """«socket», «wifi» or «both» of a request that asks for Wi-Fi or sockets (the `work_laptop` concept): «both» when
    it names both, neither («поработать с ноутбуком»), or another word of work next to one («с розеткой, поработать»)."""
    low = text.lower()
    sock, wifi = bool(_SOCKET_WORDS.search(low)), bool(_WIFI_WORDS.search(low))
    rest = _WIFI_WORDS.sub(" ", _SOCKET_WORDS.sub(" ", low))
    if sock == wifi or match(rest).has("work_laptop"):
        return "both"
    return "socket" if sock else "wifi"


def _dentist(poi) -> bool:
    specialities = poi.tag_dict().get("healthcare:speciality", "").split(";")
    tagged = bool(_DENTIST_TAGS & set(poi.tags)) or "dentist" in (s.strip() for s in specialities)
    return tagged or (poi.category == "clinic" and bool(_DENTIST_NAME.search(poi.name)))


def _kazpost(poi) -> bool:
    """A post office, not a courier's pickup point: its operator, brand or name is no courier's (СДЭК, CDEK, DHL, a
    marketplace's pickup point); a record that names no one stays a post office."""
    d = poi.tag_dict()
    said = " ".join((poi.name, d.get("operator", ""), d.get("brand", "")))
    return poi.category == "post" and not _COURIER_NAME.search(said)


def _play(poi) -> bool:
    """A place to play with friends: bowling, billiards, an arcade, a quest, a cinema, an entertainment centre; not a
    kids' play room (an adult's PS evening is not «Детская площадка в помещении»)."""
    places = bool(_PLAY_TAGS & set(poi.tags)) or bool(_PLAY_NAME.search(poi.name))
    return places and not _KIDS_NAME.search(poi.name)


def _doctor(poi) -> bool:
    return poi.category == "clinic" and not _dentist(poi)


_SUBKIND_TESTS = {
    "atm": lambda poi: bool(_ATM_TAGS & set(poi.tags)),
    "dentist": _dentist,
    "kids_doctor": lambda poi: _doctor(poi) and bool(_KIDS_CLINIC.search(poi.name)),
    "doctor": _doctor,
    "kazpost": _kazpost,
    "play": _play,
}
# what a sub-kind keeps out of its categories whatever the score: a courier, a dentist, anything but a place to play
_OFF = {
    "kazpost": (frozenset({"post"}), lambda poi: not _kazpost(poi)),
    "doctor": (frozenset({"clinic"}), _dentist),
    "kids_doctor": (frozenset({"clinic"}), _dentist),
    "play": (frozenset({"entertainment", "culture_theatre_cinema"}), lambda poi: not _play(poi)),
}


def of_subkind(poi, sub: str) -> bool:
    """Is the record of the sub-kind `sub` ('' never is)."""
    test = _SUBKIND_TESTS.get(sub)
    return test is not None and test(poi)


def off_subkind(poi, sub: str) -> bool:
    """Is the record one the sub-kind `sub` keeps out (a courier for a post office, a dentist for a sick child)."""
    cats, test = _OFF.get(sub, (frozenset(), None))
    return poi.category in cats and test is not None and test(poi)


def subkind_of(intent) -> str:
    """The sub-kind a search ranks by: the words' own (Intent.subkind); for an illness (Intent.sick) a doctor, a
    children's one when a child is ill, never a dentist unless one is asked."""
    sub = intent.subkind
    if intent.sick and "clinic" in intent.categories and sub in ("", "doctor"):
        return "kids_doctor" if intent.sick == "child" else "doctor"
    return sub


def subkind_missing(intent, first) -> str:
    """The sub-kind asked (GAP_SUBKINDS) that the first card is not: the answer then says so with the nearest one
    (walks.dialog_facts.subkind_gap), which is a card of its own (walks.chains.far_subkind); '' otherwise."""
    sub = subkind_of(intent)
    return sub if sub in GAP_SUBKINDS and not of_subkind(first, sub) else ""


def errand_order[
    P
](  # P: a Candidate or a Recommendation, both carry poi, hours_state and distance_m
    places: list[P], wished: frozenset[str], local: datetime, night: bool, *, sub: str = ""
) -> list[P]:
    """An errand: distance leads. What the data confirm open comes first, then unknown hours, then the rest; the
    nearest first inside each group (the walking metres of the card when `places` are routed). At night a
    round-the-clock place comes first in its group. «Ночной магазин» asked by day: confirmed open at 02:00 of the
    coming night is what counts as open. A kind the person named keeps its place before everything else; the
    sub-kind asked for (`sub`: a cash machine, a dentist), its records next when they are within a walk
    (FAR_WALK_MIN), and last when they are not: a children's clinic 7 km away is the far option, whatever its hours,
    the general clinic 1 km away the answer."""
    by_day = DAY_START <= local.hour < DAY_END
    probe = None
    if night and by_day:
        probe = datetime.combine(local.date() + timedelta(days=1), NIGHT_PROBE)

    def key(p) -> tuple:
        state = poi_hours(p.poi, probe).state if probe else p.hours_state
        own = bool(sub) and of_subkind(p.poi, sub)
        far = own and sub in GAP_SUBKINDS and p.walk_min >= FAR_WALK_MIN
        return (
            bool(wished) and p.poi.category not in wished,
            2 if far else 0 if own else 1,
            _GROUP.get(state, 2),
            night and not is_24_7(p.poi.opening_hours),
            p.distance_m,
        )

    return sorted(places, key=key)


def without_night_dead_ends(
    chosen: list[Candidate], wished: frozenset[str] = frozenset()
) -> list[Candidate]:
    """A mall, a museum or a library with unknown hours at 23:00-06:00 is closed in all likelihood: out, unless nothing
    else is left or the person named that kind (the card then says its hours are unknown)."""
    left = [
        c
        for c in chosen
        if c.hours_state == "open"
        or c.poi.category not in UNLIKELY_AT_NIGHT
        or c.poi.category in wished
    ]
    return left or chosen


def mark_unmet_wishes(top: list[Candidate]) -> list[Candidate]:
    """A wish the record can be checked for (halal, a diet): when no returned card carries the mark, each card's
    «unverified» becomes «none», and the card says that no place found has it, instead of leaving it to be assumed."""
    met = {r for c in top for r in c.reasons}
    out = []
    for c in top:
        reasons = []
        for r in c.reasons:
            if r == "halal_unverified" and "halal" not in met:
                r = "halal_none"
            elif r.startswith("diet_unverified:") and f"diet:{r.split(':', 1)[1]}" not in met:
                r = f"diet_none:{r.split(':', 1)[1]}"
            reasons.append(r)
        out.append(c.model_copy(update={"reasons": reasons}) if reasons != c.reasons else c)
    return out


def keep_requested_kinds(
    cands: list[Candidate], requested: list[str], top_n: int, rank: Callable[[Candidate], tuple]
) -> list[Candidate]:
    """The first `top_n` of `cands`, except that the best candidate of every requested category that has any
    stays in the list: «playground or museum» must not be answered with ten playgrounds only. It takes the
    place of the lowest-ranked entry of a category that is listed more than once."""
    top = cands[:top_n]
    for cat in requested:
        if any(c.poi.category == cat for c in top):
            continue
        best = next((c for c in cands if c.poi.category == cat), None)
        if best is None:
            continue
        counts = Counter(c.poi.category for c in top)
        for i in range(len(top) - 1, -1, -1):
            if counts[top[i].poi.category] > 1:
                top = sorted([*top[:i], *top[i + 1 :], best], key=rank)
                break
    return top
