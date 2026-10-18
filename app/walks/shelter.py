"""The shelter rule: in frost, heavy precipitation or smog, while a place to wait it out is a candidate, the outdoor
places are dropped (not just down-weighted) and the card says why.

Outdoor places are the categories of OUTDOOR_CATEGORIES (park, viewpoint, playground) and the `attraction_landmark`
records that carry no indoor signal. A landmark is judged by the record's fields only, never by its name or fame: a
monument, memorial, statue or fountain is outdoors; a mosque or church (a place of worship you can enter), a museum-
tagged record, anything tagged `indoor=*` / `building=*` or classed by Wikidata as a mosque / church / theatre /
cinema / museum is indoors and stays. Байтерек is `historic=monument` with no indoor tag in the data: the shelter rule
treats it as outdoors even though the tower has an observation deck (the data do not say so)."""

from __future__ import annotations

import re

from .models import POI, Candidate, Intent
from .weather import INDOOR_CATEGORIES, OUTDOOR_CATEGORIES

OUTDOOR_EXCLUDED = "outdoor_excluded"  # reason code: outdoor places were dropped (frost, smog)
# Places a person can wait out frost / smog in: while one of them is a candidate, outdoor places are dropped.
SHELTER_CATEGORIES = INDOOR_CATEGORIES | {"restaurant", "fast_food", "bar_nightlife"}
LANDMARK = "attraction_landmark"
# Requested categories that make indoor places stand in for them in frost / smog: the outdoor categories and landmarks
# (a landmark without an indoor signal is outdoors, see has_indoor_signal).
OUTDOOR_REQUESTS = OUTDOOR_CATEGORIES | {LANDMARK}
# The walking family a named wish keeps outdoors in any weather: a park, a square, an embankment (a landmark), a
# viewpoint. A children's playground is not in it: a child's health and the recorded demo answers keep the shelter rule.
WALKING_KINDS = frozenset({"park_garden", "attraction_landmark", "viewpoint"})
# Reason codes of an outdoor request kept outdoors in bad weather / air (see asks_outdoors): the place itself keeps
# its kind, the card says why the walk is better kept short; a candidate of another kind is shown only when nothing
# of the requested kind is left.
WEATHER_OUTDOOR_KEPT = "weather_outdoor_kept"
AIR_OUTDOOR_KEPT = "air_outdoor_kept"
OUTDOOR_OFF_KIND = "outdoor_off_kind"
LIT_NEAR = "lit_near"  # reason code: a way tagged lit=yes passes by (OpenStreetMap); no tag is never «unlit»


def outdoor_wish(intent: Intent) -> bool:
    """Did the person NAME a place to walk («погулять», «в парк», «на набережную», «на смотровую»)?
    Only their own words count (`Intent.wished`), never what a mood, the weather or the system added."""
    return bool(set(intent.wished) & WALKING_KINDS)


def asks_outdoors(intent: Intent) -> bool:
    """Is the request answered outdoors whatever the weather, the air or the darkness? A stated outdoor wish is: what
    the person asked for beats the system's shelter rule, the conditions only order the places inside the kind
    (nearer, lit first), shorten the stay and are said in the lead as advice. So is a request that brings a pet (a dog
    has to be walked outside), unless it names only indoor kinds («кафе с собакой»). A request with no stated wish
    («куда сходить») keeps the indoor substitution, with the reason in the note."""
    kinds = set(intent.categories)
    return outdoor_wish(intent) or (intent.pets and (not kinds or bool(kinds & OUTDOOR_REQUESTS)))


# Wikidata classes (`wikidata_class=` tag, from the Wikipedia link) of buildings that people enter: mosque, church
# building, cathedral, synagogue, theatre, cinema, museum.
INDOOR_WIKIDATA_CLASSES = frozenset(
    {"Q32815", "Q16970", "Q2977", "Q34627", "Q24354", "Q41253", "Q33506"}
)
_INDOOR_VALUES = frozenset({"yes", "room", "area"})  # OSM `indoor=`: inside a building
_ENTERED_TOURISM = frozenset({"museum", "gallery", "aquarium"})


def has_indoor_signal(poi: POI) -> bool:
    """Do the record's own fields say one goes inside? `indoor=yes|room|area`, any `building=*` (except "no"), a
    place of worship (OSM `amenity=place_of_worship` or an Overture `*_place_of_worship` category), a museum / gallery
    / aquarium tag (an open-air museum, `museum=open_air`, is outdoors), or an indoor Wikidata class."""
    tags = poi.tag_dict()
    if tags.get("indoor") in _INDOOR_VALUES or tags.get("building", "no") != "no":
        return True
    if tags.get("amenity") == "place_of_worship" or any(
        t.startswith("overture_category=") and t.endswith("_place_of_worship") for t in poi.tags
    ):
        return True
    if tags.get("museum") == "open_air":
        return False
    if tags.get("tourism") in _ENTERED_TOURISM or "museum" in tags:
        return True
    return tags.get("wikidata_class") in INDOOR_WIKIDATA_CLASSES


_OUTDOOR_SPORT_TAGS = frozenset(
    {
        "leisure=pitch",
        "leisure=track",
        "leisure=stadium",
        "leisure=golf_course",
        "overture_category=stadium_arena",
        "overture_category=race_track",
        "overture_category=tennis_court",
        "overture_category=hockey_field",
        "overture_category=golf_course",
        "overture_category=ski_area",
    }
)
# The sport records are thin (a ski base is `club=sport` + `building=yes`), so for this one category the name decides
# too: a stadium, a ski / roller-ski base or track, a golf course is played outdoors.
_OUTDOOR_SPORT_NAME = re.compile(r"лыж|\bski\b|стадион|stadium|трасс|\btrack\b|гольф|golf", re.I)


def is_outdoor_sport(poi: POI) -> bool:
    """A `sport` record played outdoors (stadium, pitch, ski base, roller-ski track): dark and frost rules treat it
    like a park; a gym or a pool is not one."""
    if poi.category != "sport":
        return False
    return bool(_OUTDOOR_SPORT_TAGS & set(poi.tags)) or bool(
        _OUTDOOR_SPORT_NAME.search(" ".join([poi.name, *poi.names.values()]))
    )


def is_outdoor_place(poi: POI) -> bool:
    """Does the shelter rule drop it in frost / smog: a park, viewpoint or playground, an outdoor sport ground, or a
    landmark without an indoor signal."""
    return (
        poi.category in OUTDOOR_CATEGORIES
        or is_outdoor_sport(poi)
        or (poi.category == LANDMARK and not has_indoor_signal(poi))
    )


def apply_shelter_rule(chosen: list[Candidate]) -> tuple[list[Candidate], int]:
    """Frost / smog: while at least one indoor place (SHELTER_CATEGORIES) is a candidate, outdoor places
    (is_outdoor_place) are removed outright - a category bonus must not bring them back. Returns (candidates,
    number removed); candidates keep a reason code that the card turns into an explanation."""
    if not any(c.poi.category in SHELTER_CATEGORIES for c in chosen):
        return chosen, 0
    kept = [c for c in chosen if not is_outdoor_place(c.poi)]
    removed = len(chosen) - len(kept)
    if removed:
        kept = [c.model_copy(update={"reasons": [*c.reasons, OUTDOOR_EXCLUDED]}) for c in kept]
    return kept, removed
