"""The Wikivoyage description (collect/wikivoyage): quoted and attributed to the guide, only in the edition's own
language, never over the place's own website text, hours never leak from it. Each behaviour in all three answer
languages."""

from __future__ import annotations

import pytest

from tests.test_official_site import (
    DESCRIPTION,
    SITE,
    cand,
    poi,
)  # reuse the official-site fixtures
from walks.i18n import t
from walks.models import Intent
from walks.reasons import template_what

VOYAGE_URL = "https://ru.wikivoyage.org/wiki/Астана"
VOYAGE = {"source": "wikivoyage", "license": "CC BY-SA 4.0", "url": VOYAGE_URL, "lang": "ru"}
VOYAGE_EN = {**VOYAGE, "lang": "en", "url": "https://en.wikivoyage.org/wiki/Astana"}
TEXT_RU = (
    "Монумент «Байтерек» — символ города: золотая сфера на высоте 97 метров. "
    "Работает ежедневно с 09:00 до 21:00."
)
SENT_RU = "Монумент «Байтерек» — символ города: золотая сфера на высоте 97 метров."
TEXT_EN = "The Baiterek monument is a symbol of the city: a golden sphere at 97 metres. Open daily from 09:00 to 21:00."
SENT_EN = "The Baiterek monument is a symbol of the city: a golden sphere at 97 metres."


def _intent(lang):
    return Intent(language=lang, time_budget_min=60)


@pytest.mark.parametrize(
    ("lang", "text", "body", "src"),
    [
        ("ru", SENT_RU, TEXT_RU, VOYAGE),
        ("en", SENT_EN, TEXT_EN, VOYAGE_EN),
    ],
)
def test_the_voyage_description_is_quoted_attributed_and_without_its_hours(lang, text, body, src):
    c = cand(description_voyage=body, field_sources={"description_voyage": src})
    what = template_what(c, _intent(lang))
    assert t("info_voyage", lang, text=text) in what
    assert "09:00" not in what  # hours are the card's own fields
    assert "21:00" not in what


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_the_voyage_credit_names_the_guide_and_the_article(lang):
    p = poi(description_voyage=TEXT_EN, field_sources={"description_voyage": VOYAGE_EN})
    assert p.voyage_description_credit(lang) == ("Wikivoyage", VOYAGE_EN["url"])
    assert poi().voyage_description_credit("ru") is None


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_the_voyage_text_is_used_only_in_its_edition_language(lang):
    # the ru edition never speaks in a kk or en answer
    c = cand(
        description_voyage=TEXT_RU,
        field_sources={"description_voyage": VOYAGE},
        address="ул. Сыганак, 1",
    )
    what = template_what(c, _intent(lang))
    if lang == "ru":
        assert SENT_RU in what
    else:
        assert "Байтерек» — символ" not in what  # fell through to the address
        assert "ул. Сыганак, 1" in what


def test_the_first_party_website_text_wins_over_the_guide():
    c = cand(
        description_official=DESCRIPTION,
        field_sources={"description_official": SITE, "description_voyage": VOYAGE},
        description_voyage=TEXT_RU,
    )
    what = template_what(c, _intent("ru"))
    assert (
        t("info_site", "ru", text="Lilou Bar — коктейльный бар-бистро с панорамным видом.") in what
    )
    assert "путеводителя Wikivoyage" not in what
