"""The model's paraphrase of the wish («Вы ищете …») must stay in the person's own terms: it has to name what they asked
for. A paraphrase that names nothing of the stated wish («уютное место для отдыха» for «прогуляться») is a drift to a
substitution the system made, and the lead then uses the template composed from the parsed wish."""

from __future__ import annotations

import re

from .lexicon import match
from .lexicon_concepts import CONCEPTS
from .models import Intent

# the dataset's category said back («заведения категории бар и ночная жизнь», «places of the category …»): a log line,
# not the person's words
_ECHO = re.compile(r"категори|\bcategor|санатын|санаттағы|ночная жизнь|nightlife|түнгі өмір", re.I)


def names_the_wish(clause: str, intent: Intent) -> bool:
    """True when the clause is no echo of a category and there is no stated wish to check against, or the clause says
    (in any language) one of the kinds or activities the person named."""
    if _ECHO.search(clause):
        return False
    if not intent.wished:
        return True
    said = match(clause)
    wished = set(intent.wished)
    return any(
        said.has(c.name) and wished & set(c.categories)
        for c in CONCEPTS
        if c.tier in {"kind", "activity"} or c.name == "dog_walk"
    )
