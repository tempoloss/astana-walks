"""Input hygiene and the age guard of the rule parser.

`clean_text` cuts the spans of a message that are not natural language (a pasted JSON object, a code block, tags,
base64 / hex noise): the lexicon would read their words («with_kids», «night», «cheap») as the user's wishes, and the
model would read them as instructions. What is left is the text every later step works on.

`minor_age` says whether the text names someone under 18 by a number («15-летних», «мне 16», «she is 14 years old»,
«15 жаста»); the words («подросток», «школьники», «teenager») are concepts of walks.lexicon_concepts.
"""

from __future__ import annotations

import re
from functools import lru_cache

ADULT_AGE = 18
MAX_TEXT_CHARS = 2000  # a request is a sentence or two; the tail of a longer one is never read

_FENCE = re.compile(r"```.*?(?:```|$)", re.S)
_JSON_BLOCK = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]")
_JSON_OPEN = re.compile(r"[{\[]\s*\"[^\"]*\"\s*:.*$", re.S)  # a cut-off object: «{"a": 1, "b"…»
_JSON_PAIR = re.compile(r"\"[A-Za-z_][\w ]*\"\s*:\s*(?:\"[^\"]*\"|[\w.+-]+)")
_TAG = re.compile(r"</?[A-Za-z][^<>\n]{0,60}>")
_PLACEHOLDER = re.compile(r"\$\{[^}]*\}|\{\{[^}]*\}\}")
_BASE64 = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_UPPER_INSIDE = re.compile(r"(?<=[a-z0-9])[A-Z]")


def _json_like(span: str) -> bool:
    return '"' in span or ":" in span or "=" in span


def _noise_token(tok: str) -> bool:
    """base64 / hex / a token: 16+ characters of one alphabet that mix digits and letters or case inside the word
    (a long plain word has neither)."""
    if not _BASE64.fullmatch(tok):
        return False
    letters = any(c.isalpha() for c in tok)
    digits = any(c.isdigit() for c in tok)
    return (letters and digits) or len(_UPPER_INSIDE.findall(tok)) >= 2 or tok.endswith("==")


def _strip_blocks(text: str) -> str:
    for _ in range(4):  # nested objects: peel from the inside
        new = _JSON_BLOCK.sub(lambda m: " " if _json_like(m.group()) else m.group(), text)
        if new == text:
            break
        text = new
    return text


@lru_cache(maxsize=512)
def clean_text(text: str) -> str:
    """The message without its non-natural-language spans (see the module docstring); whitespace is collapsed."""
    t = text[:MAX_TEXT_CHARS]
    t = _FENCE.sub(" ", t)
    t = _strip_blocks(t)
    t = _JSON_OPEN.sub(" ", t)
    t = _JSON_PAIR.sub(" ", t)
    t = _TAG.sub(" ", t)
    t = _PLACEHOLDER.sub(" ", t)
    return " ".join(tok for tok in t.split() if not _noise_token(tok.strip(".,;:!?()\"'")))


_N = r"(\d{1,2})"
_PERSON = (
    r"(?:мне|ему|ей|им|нам|сыну|сын|дочке|дочери|дочь|внуку|внучке|ребенку|ребёнку|мальчику|девочке|подростку|"
    r"подросткам|детям|дети|парню|девушке|ученику|ученице|школьнику|школьнице)"
)
_AGE_PATTERNS = (
    re.compile(rf"(?<![\d.,]){_N}\s*-?\s*летн", re.I),  # «15-летних», «15 летний»
    re.compile(rf"(?<![\d.,]){_N}\s*(?:лет|года|год)\b\s+{_PERSON}", re.I),  # «15 лет сыну»
    re.compile(rf"\b{_PERSON}\s+(?:всего\s+|уже\s+)?{_N}\s*(?:лет|года|год)\b", re.I),  # «мне 16 лет»
    re.compile(rf"\bмне\s+{_N}(?![\d\s]*(?:час|мин|ч\b|км|м\b|₸|тенге|тг))", re.I),
    re.compile(rf"(?<![\d.,]){_N}\s*жас", re.I),  # kk «15 жаста», «15 жастамын»
    re.compile(rf"(?<![\d.,]){_N}[\s-]*(?:years?|yrs?)[\s-]*olds?\b", re.I),
    re.compile(rf"(?<![\d.,]){_N}[\s-]*(?:y/?o|yo)\b", re.I),
    re.compile(rf"\b(?:aged?|i'?m|i am|he'?s|she'?s|he is|she is|they are)\s+{_N}\b(?!\s*(?:min|hour|h\b|km|m\b))", re.I),
    re.compile(
        r"\b(?:до|младше|моложе|меньше|under|below|younger than)\s*18\b"
        r"(?![:.]\d)(?!\s*(?:час|ч\b|h\b|pm|am|вечера|утра|дня|сағат))",
        re.I,
    ),
)  # fmt: skip


def minor_age(text: str) -> bool:
    """True when the text states an age below 18 for someone."""
    for rx in _AGE_PATTERNS:
        for m in rx.finditer(text):
            if not m.groups():
                return True
            if int(m.group(1)) < ADULT_AGE:
                return True
    return False
