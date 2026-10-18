"""Wording of the answer to a question about the afisha («что сегодня интересного», «кино сегодня»; walks.dialog_asks):
the reply, the honest note about how few sources the afisha has, the answer when nothing is listed. An entry is a
tuple (kk, ru, en); `ta` is this table's own lookup. «Nothing listed» is never «nothing happens»."""

from __future__ import annotations

from .i18n import Entry, pick

AFISHA_STRINGS: dict[str, Entry] = {
    "reply": (
        "Жақын жердегі афишадан табылғаны — төменде.",
        "Вот что нашлось в афише рядом — ниже.",
        "Here is what the listings have nearby — below.",
    ),
    "none": (
        "Мен пайдаланатын афишада жақын жерде бұл уақытқа ештеңе жоқ, бірақ афиша толық емес: тек {sources}.",
        "В афише, которой я пользуюсь, рядом на это время ничего нет — но афиша неполная: только {sources}.",
        "The listings I use have nothing nearby for this time, but they are incomplete: only {sources}.",
    ),
    "coverage": (
        "Афиша бірнеше көзден ғана жиналған ({sources}) — бұл қаладағы барлық іс-шара емес.",
        "Афиша собрана лишь из нескольких источников ({sources}) — это не все события города.",
        "The listings come from a few sources only ({sources}); they are not every event in the city.",
    ),
    "no_data": (
        "Менде афиша деректері жоқ.",
        "Данных афиши у меня нет.",
        "I have no listings data.",
    ),
}


def ta(key: str, lang: str | None, **fields: object) -> str:
    text = pick(AFISHA_STRINGS[key], lang)
    return text.format(**fields) if fields else text
