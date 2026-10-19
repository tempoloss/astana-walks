"""What the assistant is NOT for, and the part of a message it will not do: a request for code, homework, maths, a
translation, a joke, sports results, news or trivia gets one short scope line (which says what it CAN do), and no place unless the message also asks for one; a message of several steps
(«… и потом пиццу») whose one step is refused (sexual services) is refused in that step, in one sentence, and the other
steps are answered. Rules only, offline."""

from __future__ import annotations

import re

from .dialog_nlu import tokens
from .dialog_strings import s
from .intent import named_categories, parse_rules
from .outing import is_outing

# a task for a text or code machine, not a walk: code, homework, maths, a translation, an essay
_OFF_TOPIC = re.compile(
    r"\bскрипт\w*|\bна (?:питоне|python|пайтоне|js|javascript|джаве|java|си|c\+\+)\b|\bpython\b|\bjavascript\b|\bsql\b|\bкод(?:а|у|ом)? на\b|"
    r"\bнапиши(?:те)? (?:мне )?(?:код|программ\w*|функци\w*|скрипт\w*|эссе|реферат\w*|сочинени\w*|стих\w*|письм\w*|резюме|текст)\b|"
    r"\bреши(?:те)? (?:мне )?(?:задач\w*|уравнени\w*|пример\w*|интеграл\w*|домашк\w*)\b|\bдомашн\w* (?:задани\w*|работ\w*)\b|"
    r"\bпосчитай(?:те)? (?:мне )?(?:процент\w*|сумм\w*|интеграл\w*|ипотек\w*|кредит\w*)\b|\bпроцент\w* (?:для|по) ипотек\w*|"
    r"\bпереведи(?:те)?\b|\bперевод(?:и|ы)? (?:на|с) (?:английск|русск|казахск)\w*|\btranslate\b|\bwrite (?:me )?(?:a )?(?:script|code|program|function|essay|poem)\b|"
    r"\bsolve (?:this|the|my) (?:equation|problem|homework)\b|\bобъясни(?:те)? (?:мне )?(?:тему|теорему|формулу)\b|"
    r"\bкод жаз\w*|\bесеп шыгар\w*|\bаударып бер\w*|\bскрипт жаз\w*"
)
# chit-chat and general knowledge: a joke, a story, sports results, news, trivia, the assistant itself. A kind in
# the message does not save it («кто выиграл в футбол»): only a request for a place does
_CHAT = re.compile(
    r"\bанекдот\w*|\bрасскажи(?:те)? (?:мне )?(?:шутк\w*|сказк\w*|историю|что нибудь|про себя|о себе)\b|\bтоны? шутк\w*|"
    r"\btell me (?:a )?(?:joke|story|something funny|about yourself)\b|\bjokes?\b|\bmake me laugh\b|\bwho are you\b|"
    r"\bwho (?:won|wins|scored|is winning|plays|played)\b|\bwhat(?:'?s| is) the score\b|\b(?:champions|europa) league (?:final|result|score)\w*\b|"
    r"\bкто (?:выиграл|победил|выигра\w*|забил)\b|\bкакой счет\b|\bрезультат\w* (?:матч\w*|игр\w*|лиг\w*)\b|\bновости\b|\bnews\b|"
    r"\b(?:what|who) is (?:the )?(?:capital|president|prime minister|population|meaning)\b|\bcapital of\b|\bстолица\b|"
    r"\bсколько (?:лет|людей|жителей) (?:в|у|населени\w*)\b|\bкурс (?:доллара|евро|валют\w*|биткоин\w*)\b|\bexchange rate\b|\bbitcoin\b|"
    r"\bкак тебя зовут\b|\bты кто\b|\bwhat(?:'s| is) your name\b|\bкакой сегодня день\b|\bwhat day is it\b|"
    r"\bәзіл\w*|\bәңгіме айт\w*|\bкім жеңді\b|\bжаңалықтар\b"
)
# a message that also wants a place: a kind, an outing, «где», «рядом»
_WANTS_PLACE = re.compile(
    r"\bгде\b|\bкуда\b|\bрядом\b|\bпоблизости\b|\bwhere\b|\bnearby\b|\bnear me\b|\bқайда\b|\bжақын\b|\bжакын\b"
)
_STEPS = re.compile(
    r"\s+(?:и\s+)?(?:потом|затем|после\s+этого|далее|а\s+потом)\s+|\s+(?:and\s+)?(?:then|after\s+that|afterwards)\s+|[;]",
    re.I,
)


def off_topic(text: str) -> bool:
    """A request for code, homework, maths or a translation that asks for no place, or chit-chat, sports results, news
    and trivia that ask for no place."""
    low = text.lower()
    if _CHAT.search(low) and not (_WANTS_PLACE.search(low) or is_outing(text)):
        return True
    if not _OFF_TOPIC.search(" ".join(tokens(text))) and not _OFF_TOPIC.search(low):
        return False
    return not (named_categories(text) or is_outing(text) or _WANTS_PLACE.search(low))


def out_of_data_reply(missing: str, lang: str) -> str:
    """«В моих данных нет больниц …»; for a hospital or an ambulance the number to call comes with it."""
    reply = s("not_in_data", lang, what=s(f"ood_{missing}", lang))
    return f"{reply} {s('emergency_103', lang)}" if missing == "hospital" else reply


def scope_line(lang: str) -> str:
    return s("scope_line", lang)


def split_refusal(text: str) -> tuple[str, bool]:
    """(the message without its refused steps, whether one was cut): «массаж с окончанием и потом пиццу» keeps the pizza
    and cuts the massage. A message that is refused as a whole (one step, or every step refused) is left to the plain
    refusal."""
    steps = [x.strip(" ,.") for x in _STEPS.split(text) if x.strip(" ,.")]
    if len(steps) < 2:
        return text, False
    refused = [parse_rules(x).intent.refusal != "none" for x in steps]
    if not any(refused) or all(refused):
        return text, False
    kept = [x for x, bad in zip(steps, refused, strict=True) if not bad]
    return " ".join(kept), True


def refused_part_line(lang: str) -> str:
    return s("refused_part", lang)
