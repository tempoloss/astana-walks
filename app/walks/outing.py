"""«Куда сходить?», «where should I go», «қайда барсам болады»: a request that names nothing to look for. A model reads
it when one is available (walks.dialog._model_reading); without one the answer is a sensible default instead of a
question back: a walk, a sight, a coffee and a museum nearby, ordered by the usual rules (open now, the weather, the
hour, the saved settings). The lead then names no kind: the person did not ask for one."""

from __future__ import annotations

import re
from datetime import datetime

from .intent import parse_rules
from .models import IntentResult

DEFAULT_KINDS = ("park_garden", "attraction_landmark", "cafe", "museum_gallery")
# «щас скучно»: something to do, never a café first: entertainment, a show or a film, a sight, a park, a museum
BORED_KINDS = (
    "entertainment",
    "culture_theatre_cinema",
    "attraction_landmark",
    "park_garden",
    "museum_gallery",
)
BORED_REFUSED = (
    "cafe",
    "restaurant",
    "fast_food",
)  # a bored person is not offered a place to sit and eat first
_OUTING = re.compile(
    r"\bкуда (?:бы |же |тут |здесь |можно |мне |нам )*(?:сходить|пойти|податься|выбраться|сходим|пойдем|пойдём|идти)\b|"
    r"\bчто (?:есть |тут |здесь |интересного )*(?:рядом|поблизости|вокруг|посмотреть)\b|\bчем (?:бы )?заняться\b|"
    r"\bгде (?:можно )?провести время\b|"
    r"\bқайда (?:барсам|барамыз|барайық|барсақ|баруға|бару)\b|\bжақын жерде не бар\b|\bне істесем\b|"
    r"\bwhere (?:should|can|could|shall|do) (?:i|we) go\b|\bwhere to go\b|\bwhat(?:'s| is) (?:near|nearby|around)\b|"
    r"\bwhat (?:can|should) (?:i|we) do\b|\banything (?:to do )?nearby\b",
    re.I,
)


_BORED = re.compile(
    r"\bскучно\b|\bскучаю\b|\bскука\b|\bнечего делать\b|\bзаняться нечем\b|\bbored\b|\bboring\b|\bnothing to do\b|"
    r"\bзеріктім\b|\bзеріге\w*\b|\bжалықтым\b|\bқызық\w* жоқ\b",
    re.I,
)


def is_bored(text: str) -> bool:
    """«щас скучно», «i'm bored», «зеріктім»: the person wants something to do."""
    return bool(_BORED.search(text.lower()))


def is_outing(text: str) -> bool:
    """The message asks where to go without naming a kind of place («куда сходить вечером»)."""
    return bool(_OUTING.search(text.lower()))


def is_bored_outing(text: str) -> bool:
    """«щас скучно куда сходить»: bored AND asking where to go (a bare «скучно» is still asked back)."""
    return is_bored(text) and is_outing(text)


def default_outing(text: str, when: datetime | None = None) -> IntentResult | None:
    """The default reading of a bare «куда сходить» (None: the message is not one): the rules' own reading of the time,
    the company and the evening, with the default kinds to search for. No kind becomes a wish (`wished` stays empty),
    so the conditions and the settings order them freely."""
    if not is_outing(text):
        return None
    rules = parse_rules(text, when)
    if rules.intent.categories or rules.intent.refusal != "none":
        return None
    bored = is_bored(text)
    kinds = BORED_KINDS if bored else DEFAULT_KINDS
    update: dict = {"categories": list(kinds)}
    if bored:
        update["refused"] = [*rules.intent.refused, *BORED_REFUSED]
    intent = rules.intent.model_copy(update=update)
    what = (
        "скучно → развлечения, культура, достопримечательность, парк, музей"
        if bored
        else ("куда сходить → прогулка, достопримечательность, кафе, музей")
    )
    note = "; ".join(filter(None, [rules.note, what]))
    return IntentResult(intent=intent, parser="rules", note=note)
