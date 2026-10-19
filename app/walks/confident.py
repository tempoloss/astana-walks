"""When the rules' reading of a new request is the answer's reading, so the intent model is not asked.

The model may only narrow what the rules read (walks.intent.merge_intents). Measured live (results/intent_skip.md),
it changes nothing in a message that only names one kind of place by its noun («кофе рядом», «аптека», «хочу в
парк», «банкомат рядом», «coffee nearby»), and it widens a mood, an outing, a wish with a modifier or a verb
(«что посмотреть» gets cinemas, «с ребёнком» parks, «поужинать» the keyword «ужин», «выпить и потанцевать» more
kinds). So the rules are confident when:

* the text names exactly one kind of place, by the word whose negation would rule that kind out («не кофе»), with no
  flag of its own: no mood, no activity, no modifier (cheap, quiet, evening, Wi-Fi …);
* that word is a noun, not a verb («поужинать», «выпить», «dine»: the model adds the noun as a keyword);
* no word was negated, read through a typo, read as where the person is («возле парка») or has just been;
* every other word only asks (want / where / near …: `_ASKS`), so nothing is left for a model to read;
* nothing else is said: no named place, no stated time or deadline, no budget, no plan, no weather, no age, no group.

The proof on the evaluation sets is `python -m eval.intent_skip` (results/intent_skip.md)."""

from __future__ import annotations

import re

from .lexicon import CONCEPTS, Hit, Matches, match, normalize
from .models import Intent, IntentResult
from .safety import clean_text

CONFIDENT_NOTE = "правила прочли каждое слово запроса — ИИ не спрашивали"
_BY_NAME = {c.name: c for c in CONCEPTS}
# Words that only ask for what the kind word names (normalised as the lexicon reads them: ё→е, kk letters → ru). No
# preposition that attaches a modifier («с видом», «на крыше»): those words go to the model.
_ASK_WORDS = (
    "я мне мы нам хочу хочется хотим хотел хотела бы где куда тут здесь рядом поблизости недалеко близко "
    "найти найди найдите покажи покажите подскажи подскажите посоветуй посоветуйте нужен нужна нужно надо "
    "есть ли можно какой какая какое какие ближайший ближайшая ближайшее ближайшие и в ну пожалуйста "
    "мен маған біз бізге қайда жақын жерде маңда маңайда осы осында мұнда бар ма ме керек келеді "
    "іздеймін тап табу көрсет қай қандай ең "
    "i me we us want wanna need where wheres is are there a an the some any nearby near close "
    "around here please can could find show get"
)
_ASKS = frozenset(normalize(w) for w in _ASK_WORDS.split())
# A verb of the kind's own words: a russian infinitive, a kazakh verb ending (normalised letters), an english verb.
_RU_VERB = re.compile(r"(?:ть|ться|тись|чь|ти)$")
_KK_VERB = re.compile(r"(?:у|ю|уге|юге|гим|гым|ким|кым|йик|йык|мын|мин)$")
_EN_VERB_WORDS = (
    "dine drink drinks drinking dance dancing swim swimming skate skating jog jogging run running climb climbing "
    "buy sleep exercise training cycling skiing partying clubbing stay eat"
)
_EN_VERBS = frozenset(_EN_VERB_WORDS.split())


def _names_a_kind(name: str) -> bool:
    c = _BY_NAME[name]
    return c.tier == "kind" and bool(c.categories) and bool(c.negation_excludes) and not c.flags


def _a_verb(hit: Hit, language: str) -> bool:
    words = hit.text.split()
    if language == "en":
        return any(w in _EN_VERBS for w in words)
    verb = _KK_VERB if language == "kk" else _RU_VERB
    return any(verb.search(w) for w in words)


def _words_read(m: Matches, text: str) -> bool:
    """One concept that names a kind by a noun, every hit a plain one, and every word a hit's or one of `_ASKS`."""
    if any(h.negated or h.fuzzy or h.location or h.visited for h in m.hits):
        return False
    if len(m.active) != 1 or not all(_names_a_kind(n) for n in m.active):
        return False
    if any(_a_verb(h, m.language) for hits in m.active.values() for h in hits):
        return False
    read = {w for h in m.hits for w in h.text.split()}
    return all(w in read or w in _ASKS for w in re.findall(r"\w+", normalize(clean_text(text))))


def _says_nothing_else(intent: Intent) -> bool:
    return not (
        intent.landmark_refs
        or intent.info_about
        or intent.plan_order
        or intent.time_stated
        or intent.price_cap_kzt
        or intent.budget != "any"
        or intent.weather_hint != "none"
        or intent.minor
        or intent.group_size
        or intent.exclude_categories
        or intent.refused
        or intent.diets
        or intent.mode_explicit
    )


def rules_confident(text: str, rules: IntentResult, about: str = "") -> bool:
    """The model would read `text` as the rules did (see the module docstring). The person's own notes (`about`) go to
    the model with the message, so with notes the model is always asked."""
    intent = rules.intent
    if intent.refusal != "none" or not intent.categories or about.strip():
        return False
    m = match(text)
    named = {cat for n in m.active for cat in _BY_NAME[n].categories}
    return _says_nothing_else(intent) and _words_read(m, text) and set(intent.categories) == named


def confident_reading(rules: IntentResult) -> IntentResult:
    """The rules' reading as the request's reading, with the note saying why no model was asked."""
    note = "; ".join(x for x in (rules.note, CONFIDENT_NOTE) if x)
    return rules.model_copy(update={"note": note})


def _stem4(word: str) -> str:
    return normalize(word)[:4]


def _restates(keyword: str, text: str) -> bool:
    """Does every word of the model's keyword only repeat a word of the user's own message («кофе» for «хочу кофе»)?"""
    said = {_stem4(w) for w in re.findall(r"\w+", text)}
    return all(_stem4(w) in said for w in re.findall(r"\w+", keyword))


def same_reading(rules: Intent, final: Intent, text: str) -> bool:
    """The model's reading adds nothing the rules' reading did not have, apart from keywords that restate the user's
    own words: the answer prepared for the rules' intent is then the answer."""
    skip = {"free_text_keywords"}
    if rules.model_dump(exclude=skip) != final.model_dump(exclude=skip):
        return False
    added = [k for k in final.free_text_keywords if k not in rules.free_text_keywords]
    return all(_restates(k, text) for k in added)
