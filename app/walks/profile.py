"""Personal profile: opt-in, local, editable, deletable.

Off by default (the UI toggle «запоминать мои предпочтения»). A profile is one JSON file,
app/.local/profiles/<random-uuid>.json (WALKS_PROFILE_DIR redirects it): flags {with_kids + age band, mobility,
quiet, budget, halal, no_alcohol, language, walk_pace, cold_tolerance}, the kinds of place to leave out (`avoid`),
the user's own free text for the AI (`about`), the places the user marked visited ([poi_id, day]) and how many
times each category was marked liked. The uuid is random, kept in the session (and optionally in the `?u=` query
parameter for a demo) and means nothing outside this machine.

Write path: after an answer the UI offers chips «Запомнить: с ребёнком?» derived from the parsed intent; a flag is
saved only on a click. Read path (`merge_into_intent`): flags are merged into the Intent of a NEW request and the
request itself wins; visited places are ranked lower; the answer says «вы отмечали, что …».

What leaves this module towards a model: the flags (`preferences_payload`) and the user's own text (`about`, via
`personal_view`; the UI says so next to the field). Never the visited list, the liked counts or the avoided kinds.
A request that used a profile is not written to the request log (Result.private) and nothing here ever reaches
data/city_feedback.json.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .i18n import LANG_SELF, Entry, age_label, category_name, pick, t
from .intent import kinds_named_alone
from .models import Category, Constraints, Intent, Language, Personal, WeatherInfo
from .weather import HEAVY_PRECIP_MM

DEFAULT_DIR = Path(__file__).resolve().parents[1] / ".local" / "profiles"
MAX_PROFILES = 1000  # past this the least recently written profile files are deleted
COLD_LOW_C = -5.0  # «мёрзну»: indoor places from this apparent temperature on
COLD_HIGH_C = -25.0  # «холод переношу легко»: the frost rule starts only from here
PACE_RADIUS = {"slow": 0.8, "normal": 1.0, "fast": 1.25}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_LETTER = re.compile(r"[A-Za-zА-Яа-яЁёәіңғүұқөһӘІҢҒҮҰҚӨҺ]")

AgeBand = Literal["0-3", "4-7", "8-12", "13+"]
Mobility = Literal["none", "stroller", "wheelchair"]
Pace = Literal["slow", "normal", "fast"]
Cold = Literal["low", "normal", "high"]
# «недорого» is the one budget the data can act on (a free entry, the nearer place, «цены уточняйте»); the data hold no
# prices, so a mid-range or a pricier bill is not a setting: nothing could honestly be done with it
ProfileBudget = Literal["any", "low"]
ABOUT_MAX = 500  # characters of the user's free text
_SPACES = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2060-\u206f]")


class VisitedPlace(BaseModel):
    poi_id: str
    day: str  # ISO day


def clean_about(text: object) -> str:
    """The user's free text as it is stored: control characters dropped, runs of white space made one space."""
    if not isinstance(text, str):
        return ""
    return _CONTROL.sub("", _SPACES.sub(" ", text)).strip()


class Profile(BaseModel):
    with_kids: bool = False
    kids_age_band: AgeBand | None = None
    mobility: Mobility = "none"
    quiet: bool = False
    budget: ProfileBudget = "any"
    halal: bool = False
    no_alcohol: bool = False
    language: Language | None = None
    walk_pace: Pace = "normal"
    cold_tolerance: Cold = "normal"
    avoid: list[Category] = Field(default_factory=list)
    about: str = Field("", max_length=ABOUT_MAX)
    visited: list[VisitedPlace] = Field(default_factory=list)
    liked: dict[str, int] = Field(default_factory=dict)

    @field_validator("budget", mode="before")
    @classmethod
    def _supported_budget(cls, value: object) -> object:
        return (
            value if value in ("any", "low") else "any"
        )  # a file saved with a level the form no longer offers

    @field_validator("about", mode="before")
    @classmethod
    def _clean_about(cls, value: object) -> str:
        return clean_about(value)

    @field_validator("avoid")
    @classmethod
    def _avoid_once(cls, value: list[Category]) -> list[Category]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _age_needs_kids(self) -> Profile:
        """A child's age only means something next to «с детьми»: without it the age is dropped."""
        if not self.with_kids and self.kids_age_band is not None:
            self.kids_age_band = None
        return self


# ---------------------------------------------------------------- storage


def profiles_dir() -> Path:
    v = os.environ.get("WALKS_PROFILE_DIR", "").strip()
    return Path(v) if v else DEFAULT_DIR


def new_profile_id() -> str:
    return str(uuid.uuid4())


def valid_id(uid: object) -> bool:
    """Only canonical lowercase uuids name a file: a `?u=` value can never point outside the profiles folder."""
    return isinstance(uid, str) and bool(_UUID.match(uid))


def profile_path(uid: str) -> Path:
    if not valid_id(uid):
        raise ValueError("не идентификатор профиля")
    return profiles_dir() / f"{uid}.json"


def load_profile(uid: str) -> Profile | None:
    """The stored profile, or None when there is no file (or it is unreadable)."""
    if not valid_id(uid):
        return None
    path = profile_path(uid)
    try:
        return Profile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_profile(uid: str, profile: Profile) -> Path:
    path = profile_path(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _evict_oldest(path.parent, MAX_PROFILES - 1)
    path.write_text(profile.model_dump_json(indent=1), encoding="utf-8")
    return path


def _evict_oldest(folder: Path, keep: int) -> None:
    """Delete the least recently written profile files until at most `keep` remain."""
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in files[: max(0, len(files) - keep)]:
        old.unlink(missing_ok=True)


def delete_profile(uid: str) -> bool:
    """«Забыть всё»: the file is deleted. True when there was one."""
    if not valid_id(uid):
        return False
    path = profile_path(uid)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed


# ---------------------------------------------------------------- what is stored


@dataclass(frozen=True)
class ProfileItem:
    key: str  # what forget_item takes
    label: str


# the stored-item lines of the free text and of the kinds left out (the older lines live in walks.i18n)
_ITEM: dict[str, Entry] = {
    "liked_once": ("ұнады: {cat}", "понравилось: {cat}", "liked: {cat}"),
    "avoid": ("көрсетпеу: {cat}", "не показывать: {cat}", "leave out: {cat}"),
    "about": ("сіздің мәтініңіз: «{text}»", "ваш текст: «{text}»", "your text: “{text}”"),
}


def _item(key: str, lang: str, **fields: object) -> str:
    return pick(_ITEM[key], lang).format(**fields)


def _liked_label(cat: str, n: int, lang: str) -> str:
    """«понравилось: кафе» for one like, «понравилось: кафе ×3» from the second on."""
    name = category_name(cat, lang)
    return t("item_liked", lang, cat=name, n=n) if n > 1 else _item("liked_once", lang, cat=name)


def list_items(
    profile: Profile, names: dict[str, str] | None = None, lang: str = "ru"
) -> list[ProfileItem]:
    """Every stored item, one line each, so that the panel can show it and delete it."""
    names = names or {}
    out: list[ProfileItem] = []
    if profile.with_kids:
        band = f" ({age_label(profile.kids_age_band, lang)})" if profile.kids_age_band else ""
        out.append(ProfileItem("with_kids", t("item_with_kids", lang) + band))
    if profile.mobility != "none":
        out.append(ProfileItem("mobility", t(f"item_mobility_{profile.mobility}", lang)))
    if profile.quiet:
        out.append(ProfileItem("quiet", t("item_quiet", lang)))
    if profile.budget != "any":
        out.append(ProfileItem("budget", t(f"item_budget_{profile.budget}", lang)))
    if profile.halal:
        out.append(ProfileItem("halal", t("item_halal", lang)))
    if profile.no_alcohol:
        out.append(ProfileItem("no_alcohol", t("item_no_alcohol", lang)))
    if profile.language:
        out.append(
            ProfileItem("language", t("item_language", lang, language=LANG_SELF[profile.language]))
        )
    if profile.walk_pace != "normal":
        out.append(ProfileItem("walk_pace", t(f"item_pace_{profile.walk_pace}", lang)))
    if profile.cold_tolerance != "normal":
        out.append(ProfileItem("cold_tolerance", t(f"item_cold_{profile.cold_tolerance}", lang)))
    for v in profile.visited:
        name = names.get(v.poi_id, v.poi_id)
        out.append(
            ProfileItem(f"visited:{v.poi_id}", t("item_visited", lang, name=name, day=v.day))
        )
    for cat, n in sorted(profile.liked.items()):
        out.append(ProfileItem(f"liked:{cat}", _liked_label(cat, n, lang)))
    for cat in profile.avoid:
        out.append(ProfileItem(f"avoid:{cat}", _item("avoid", lang, cat=category_name(cat, lang))))
    if profile.about:
        text = profile.about if len(profile.about) <= 60 else profile.about[:59].rstrip() + "…"
        out.append(ProfileItem("about", _item("about", lang, text=text)))
    return out


def forget_item(profile: Profile, key: str) -> Profile:
    """The profile without one stored item (a key of `list_items`)."""
    if key.startswith("visited:"):
        poi_id = key.split(":", 1)[1]
        return profile.model_copy(
            update={"visited": [v for v in profile.visited if v.poi_id != poi_id]}
        )
    if key.startswith("liked:"):
        cat = key.split(":", 1)[1]
        return profile.model_copy(
            update={"liked": {c: n for c, n in profile.liked.items() if c != cat}}
        )
    if key.startswith("avoid:"):
        cat = key.split(":", 1)[1]
        return profile.model_copy(update={"avoid": [c for c in profile.avoid if c != cat]})
    defaults = Profile()
    update = {key: getattr(defaults, key)}
    if key == "with_kids":
        update["kids_age_band"] = None
    return profile.model_copy(update=update)


# ---------------------------------------------------------------- write path


@dataclass(frozen=True)
class Chip:
    key: str  # what `remember` takes
    label: str


def suggest_chips(
    intent: Intent, constraints: Constraints, profile: Profile, text: str = "", lang: str = "ru"
) -> list[Chip]:
    """«Запомнить: с ребёнком?» for what this request asked and the profile does not hold yet."""
    out: list[Chip] = []
    if intent.with_kids and not profile.with_kids:
        out.append(Chip("with_kids", t("chip_with_kids", lang)))
    if intent.quiet and not profile.quiet:
        out.append(Chip("quiet", t("chip_quiet", lang)))
    if intent.accessibility and profile.mobility == "none":
        if intent.with_kids or "коляск" in text.lower():
            out.append(Chip("mobility:stroller", t("chip_stroller", lang)))
        else:
            out.append(Chip("mobility:wheelchair", t("chip_wheelchair", lang)))
    if intent.budget == "low" and profile.budget == "any":
        out.append(Chip("budget:low", t("chip_budget", lang)))
    if constraints.no_alcohol and not profile.no_alcohol:
        out.append(Chip("no_alcohol", t("chip_no_alcohol", lang)))
    if (intent.halal or "халяль" in intent.free_text_keywords) and not profile.halal:
        out.append(Chip("halal", t("chip_halal", lang)))
    if intent.language != "ru" and profile.language != intent.language:
        out.append(
            Chip(
                f"language:{intent.language}",
                t("chip_language", lang, language=LANG_SELF[intent.language]),
            )
        )
    return out


def remember(profile: Profile, key: str) -> Profile:
    """The profile with the flag of a chip key saved ('with_kids', 'mobility:stroller', 'budget:low', ...)."""
    name, _, value = key.partition(":")
    if name in ("mobility", "budget", "language", "kids_age_band", "walk_pace", "cold_tolerance"):
        return profile.model_copy(update={name: value})
    return profile.model_copy(update={name: True})


def record_visit(profile: Profile, poi_id: str, day: date) -> Profile:
    if any(v.poi_id == poi_id for v in profile.visited):
        return profile
    visited = [*profile.visited, VisitedPlace(poi_id=poi_id, day=day.isoformat())]
    return profile.model_copy(update={"visited": visited})


def record_like(profile: Profile, category: str) -> Profile:
    """A like for a kind of place also lifts it off the «avoid» list: the two never hold the same kind."""
    liked = dict(profile.liked)
    liked[category] = liked.get(category, 0) + 1
    return profile.model_copy(
        update={"liked": liked, "avoid": [c for c in profile.avoid if c != category]}
    )


# ---------------------------------------------------------------- read path


def merge_into_intent(intent: Intent, profile: Profile, text: str) -> tuple[Intent, list[str]]:
    """The intent of a new request with the profile's flags under it: the request wins (a budget or language it
    states stays), a flag the profile adds is OR-ed in. Returns (intent, codes of the flags that changed it)."""
    update: dict = {}
    applied: list[str] = []
    if profile.with_kids and not intent.with_kids:
        update["with_kids"] = True
        applied.append("with_kids")
    if profile.mobility != "none" and not intent.accessibility:
        update["accessibility"] = True
        applied.append("mobility")
    if profile.quiet and not intent.quiet:
        update["quiet"] = True
        applied.append("quiet")
    if profile.budget == "low" and intent.budget == "any":
        update["budget"] = "low"
        applied.append("budget")
    if profile.halal:
        kws = list(dict.fromkeys([*intent.free_text_keywords, "халяль", "halal"]))[:8]
        if kws != intent.free_text_keywords or not intent.halal:
            update["free_text_keywords"] = kws
            update["halal"] = (
                True  # the ranking's halal rule (tagged first, the rest honestly unverified)
            )
            applied.append("halal")
    if profile.language and not _LETTER.search(text):
        update["language"] = profile.language  # the request has no words to read the language from
        applied.append("language")
    return intent.model_copy(update=update), applied


def avoided_kinds(intent: Intent, profile: Profile, text: str) -> list[str]:
    """The kinds the profile leaves out of this request: a hard exclusion in retrieval (`Constraints.avoid`), lifted
    only for a kind the person NAMES in this very message by its own word («хочу в бар», «хочу кофе»). A word for a
    family («поесть») does not lift it (the avoided café leaves, the restaurants stay), nor does a mood or the model."""
    named = set(kinds_named_alone(text)) & set(intent.wished)
    return [c for c in profile.avoid if c not in named]


def constraints_for(profile: Profile) -> tuple[Constraints, list[str]]:
    """Profile flags that narrow retrieval instead of changing the intent: no alcohol, walking pace."""
    applied: list[str] = []
    if profile.no_alcohol:
        applied.append("no_alcohol")
    if profile.walk_pace != "normal":
        applied.append("walk_pace")
    return (
        Constraints(radius_factor=PACE_RADIUS[profile.walk_pace], no_alcohol=profile.no_alcohol),
        applied,
    )


def adapt_weather(weather: WeatherInfo | None, profile: Profile) -> tuple[WeatherInfo | None, bool]:
    """Cold tolerance moves the frost threshold of the indoor rule for this user. Returns (weather, changed)."""
    if weather is None or weather.apparent_c is None:
        return weather, False
    cold = weather.apparent_c
    if profile.cold_tolerance == "low" and not weather.adverse and cold <= COLD_LOW_C:
        reason = f"ощущается как {cold:.0f}°C, вы отмечали, что мёрзнете"
        return weather.model_copy(update={"adverse": True, "reason": reason}), True
    precip = weather.precipitation_mm or 0.0
    if (
        profile.cold_tolerance == "high"
        and weather.adverse
        and cold > COLD_HIGH_C
        and precip < HEAVY_PRECIP_MM
    ):
        return weather.model_copy(update={"adverse": False, "reason": ""}), True
    return weather, False


def personal_view(profile: Profile) -> Personal:
    """What retrieval reads: visited ids and liked counts, and `about`, the user's own text the core hands to the
    intent and generation prompts (the one profile field that may reach a model besides the flags)."""
    return Personal(
        visited=[v.poi_id for v in profile.visited],
        liked=dict(profile.liked),
        about=profile.about,
        kids_age_band=profile.kids_age_band if profile.with_kids else None,
    )


def preferences_payload(profile: Profile) -> dict:
    """The only part of a profile that may go to the LLM: the flags that are set. No visited list, no liked
    counts, no ids."""
    out: dict = {}
    if profile.with_kids:
        out["with_kids"] = True
        if profile.kids_age_band:
            out["kids_age_band"] = profile.kids_age_band
    if profile.mobility != "none":
        out["mobility"] = profile.mobility
    for flag in ("quiet", "halal", "no_alcohol"):
        if getattr(profile, flag):
            out[flag] = True
    if profile.budget != "any":
        out["budget"] = profile.budget
    if profile.language:
        out["language"] = profile.language
    if profile.walk_pace != "normal":
        out["walk_pace"] = profile.walk_pace
    if profile.cold_tolerance != "normal":
        out["cold_tolerance"] = profile.cold_tolerance
    return out
