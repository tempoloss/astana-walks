"""The two stored memory layers of the page (the dialogue itself lives only in the browser tab):

* residents' marks - POST /api/report: one anonymous mark of a place into the city feedback store (walks.feedback:
  no user id, no coordinates, a day and a part of the day); the «Город» page shows them;
* the opt-in profile - /api/profile: «Что я о вас знаю», each item deletable, «Забыть всё», the
  «Запомнить: …?» chips, «Был здесь» / «Понравилось», «Мой вайб» (walks.vibe: the axis and the chips are saved at once,
  the free text is read into facets on save, walks.vibe_judge). The browser keeps only the random id of the profile file."""

from __future__ import annotations

from datetime import date
from functools import cache
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from walks.feedback import SIGNALS, add_feedback
from walks.i18n import category_name
from walks.models import Category, Language
from walks.pipeline import get_pois
from walks.profile import (
    ABOUT_MAX,
    AgeBand,
    Cold,
    Mobility,
    Pace,
    Profile,
    ProfileBudget,
    clean_about,
    delete_profile,
    forget_item,
    list_items,
    load_profile,
    new_profile_id,
    record_like,
    record_visit,
    remember,
    save_profile,
    valid_id,
)
from walks.vibe import facet_name
from walks.vibe_data import FACETS, VIBE_TEXT_MAX, Facet
from walks.vibe_judge import read_vibe

Lang = Literal["kk", "ru", "en"]
FLAGS = ("with_kids", "quiet", "halal", "no_alcohol")
CHOICES: dict[str, tuple[str, ...]] = {  # the `remember` keys «name:value»
    "mobility": get_args(Mobility),
    "budget": get_args(ProfileBudget),
    "language": get_args(Language),
    "kids_age_band": get_args(AgeBand),
    "walk_pace": get_args(Pace),
    "cold_tolerance": get_args(Cold),
}
# The kinds of place the form offers for «нравится / не показывать», in the order a person thinks of them
# (food and drink, then outdoors, sights, culture, fun, the rest). «other» is no kind a person can pick.
FORM_CATEGORIES: tuple[Category, ...] = (
    "cafe",
    "restaurant",
    "fast_food",
    "bar_nightlife",
    "park_garden",
    "viewpoint",
    "attraction_landmark",
    "museum_gallery",
    "culture_theatre_cinema",
    "entertainment",
    "kids_playground",
    "sport",
    "mall",
    "coworking_library",
)


@cache
def _places() -> dict[str, tuple[str, str]]:
    """poi id -> (name, category)."""
    return {p.id: (p.name, p.category) for p in get_pois()}


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poi_id: str = Field(min_length=1, max_length=200)
    signal: str


def report(req: Report) -> bool:
    """False for an unknown place or signal: nothing is written then."""
    if req.poi_id not in _places() or req.signal not in SIGNALS:
        return False
    add_feedback(req.poi_id, req.signal)
    return True


class ProfileForm(BaseModel):
    """«Изменить вручную»: what a person can set by hand. The visited places are not edited here; the liked kinds
    are (the counts the like button keeps stay for the kinds that stay). Contradictions are refused, not mended:
    a child's age without «с детьми», a kind both liked and left out, a text over the limit."""

    model_config = ConfigDict(extra="forbid")

    with_kids: bool = False
    kids_age_bands: list[AgeBand] = Field(default_factory=list, max_length=len(get_args(AgeBand)))
    mobility: Mobility = "none"
    quiet: bool = False
    budget: ProfileBudget = "any"
    halal: bool = False
    no_alcohol: bool = False
    language: Language | None = None
    walk_pace: Pace = "normal"
    cold_tolerance: Cold = "normal"
    liked: list[Category] = Field(default_factory=list, max_length=len(FORM_CATEGORIES))
    avoid: list[Category] = Field(default_factory=list, max_length=len(FORM_CATEGORIES))
    about: str = Field("", max_length=ABOUT_MAX)
    vibe: dict[Facet, Annotated[float, Field(ge=0.0, le=1.0)]] = Field(default_factory=dict)
    vibe_text: str = Field("", max_length=VIBE_TEXT_MAX)

    @field_validator("about", "vibe_text", mode="before")
    @classmethod
    def _clean_about(cls, value: object) -> str:
        return clean_about(value)

    @field_validator("kids_age_bands")
    @classmethod
    def _ages_once(cls, value: list[AgeBand]) -> list[AgeBand]:
        return list(dict.fromkeys(value))

    @field_validator("liked", "avoid")
    @classmethod
    def _offered_kinds(cls, value: list[Category]) -> list[Category]:
        if any(c not in FORM_CATEGORIES for c in value):
            raise ValueError("not a kind of place the form offers")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _consistent(self) -> ProfileForm:
        if self.kids_age_bands and not self.with_kids:
            raise ValueError("the age of a child needs «with kids»")
        if set(self.liked) & set(self.avoid):
            raise ValueError("a kind of place cannot be both liked and left out")
        return self


class ProfileAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    lang: Lang = "ru"
    action: Literal["remember", "forget", "visit", "like", "save", "forget_all"]
    key: str | None = Field(default=None, max_length=240)
    poi_id: str | None = Field(default=None, max_length=200)
    form: ProfileForm | None = None


def _form_of(profile: Profile) -> dict:
    """The form's values of a stored profile."""
    values = profile.model_dump(include=set(ProfileForm.model_fields) - {"liked"})
    values["liked"] = [c for c in FORM_CATEGORIES if profile.liked.get(c)]
    values["avoid"] = [c for c in FORM_CATEGORIES if c in profile.avoid]
    return ProfileForm.model_validate(values).model_dump()


def view(uid: str | None, lang: str) -> dict:
    """What the «Память» panel shows: the id (None: nothing stored), every item, the form's values and what the
    form's pickers offer (kinds of place and the vibe's facets named in the language, the length limits of the texts)."""
    profile = (load_profile(uid) if valid_id(uid) else None) or Profile()
    names = {pid: name for pid, (name, _cat) in _places().items()}
    return {
        "id": uid if valid_id(uid) and load_profile(uid) is not None else None,
        "items": [{"key": i.key, "label": i.label} for i in list_items(profile, names, lang)],
        "form": _form_of(profile),
        "categories": [{"key": c, "name": category_name(c, lang)} for c in FORM_CATEGORIES],
        "about_max": ABOUT_MAX,
        "vibe_facets": [{"key": f, "name": facet_name(f, lang).capitalize()} for f in FACETS],
        "vibe_text_max": VIBE_TEXT_MAX,
    }


def _remember_key(key: str) -> bool:
    name, _, value = key.partition(":")
    return (name in FLAGS and not value) or value in CHOICES.get(name, ())


def _changed(profile: Profile, act: ProfileAction) -> Profile | None:
    """The profile after the action; None when the action names something that is not there."""
    if act.action == "remember" and act.key and _remember_key(act.key):
        return remember(profile, act.key)
    if act.action == "forget" and act.key:
        names = {pid: name for pid, (name, _cat) in _places().items()}
        if act.key in {i.key for i in list_items(profile, names)}:
            return forget_item(profile, act.key)
        return None
    if act.action in ("visit", "like") and act.poi_id in _places():
        if act.action == "visit":
            return record_visit(profile, act.poi_id, date.today())
        return record_like(profile, _places()[act.poi_id][1])
    if act.action == "save" and act.form is not None:
        form = act.form.model_dump()
        liked = {c: n for c, n in profile.liked.items() if c not in FORM_CATEGORIES}
        liked |= {c: max(profile.liked.get(c, 0), 1) for c in form.pop("liked")}
        if form["vibe_text"] and form["vibe_text"] != profile.vibe_text:
            form["vibe"] = read_vibe(
                form["vibe_text"]
            ).weights  # new words: what they ask for replaces the chips
        # the form's age groups replace the stored ones: the single youngest age is derived from them again
        return profile.model_copy(update={**form, "liked": liked, "kids_age_band": None})
    return None


def apply(act: ProfileAction) -> dict | None:
    """Run one action and return the new view; None for an action that names nothing that exists."""
    uid = act.id if valid_id(act.id) else None
    if act.action == "forget_all":
        if uid:
            delete_profile(uid)
        return view(None, act.lang)
    profile = (load_profile(uid) if uid else None) or Profile()
    changed = _changed(profile, act)
    if changed is None:
        return None
    try:
        changed = Profile.model_validate(changed.model_dump())
    except ValidationError:
        return None
    uid = uid or new_profile_id()
    save_profile(uid, changed)
    return view(uid, act.lang)
