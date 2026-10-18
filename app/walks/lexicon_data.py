"""The vocabulary of the rule-based intent parser: concepts with ru / kk / en stems and what each one means.

A concept is something the user may want or say («перекусить», «выпить и потанцевать», «переждать дождь»). Its
effect on the Intent is declared here, next to the words, and applied by walks.intent:
  categories  place categories the concept names (`tier="kind"`: always added; `tier="mood"`: only when the text
              names no place kind at all - «с ребёнком» alone implies playground / museum);
  flags       Intent flags / modifiers it sets (see FLAGS below);
  keywords    retrieval keywords it adds;
  unless      concepts that cancel it («выпить» is a bar unless the text is about coffee);
  negation_excludes  categories removed when the text negates the concept («не хочу фастфуд»).

Stem syntax (written in natural spelling, normalised by walks.lexicon: lowercase, ё→е, kk letters → ru look-alikes):
  «кофе»        a word starting with it («кофейня», «кофе»); words of 3 letters or fewer must match exactly;
  «бар=»        exactly this word;
  «торгов центр» consecutive words, each starting with the given stem.
Stems of 5+ letters also tolerate a typo (walks.lexicon, rapidfuzz). Keep stems roots of whole words: a stem that
is a prefix of an unrelated word needs the concept's `not_stems`.
"""

from __future__ import annotations

from dataclasses import dataclass

FLAGS = frozenset(
    {
        "with_kids",
        "quiet",
        "wifi",
        "night",
        "evening",
        "access",
        "unusual",
        "tourist",
        "cheap",
        "expensive",
        "fast",
        "halal",
        "no_alcohol",
        "car",
        "transit",
        "minor",
        "wx_cold",
        "wx_rain",
        "wx_heat",
        "wx_smog",
        "refuse_drugs",
        "refuse_sex",
        "refuse_weapons",
        "diet_vegetarian",
        "diet_vegan",
        "diet_gluten_free",
        "diet_kosher",
        "pets",
    }
)

# Time budgets (minutes) a concept implies when the text states none (see Concept.budget_min)
LONG_VISIT_BUDGET_MIN = 120  # with a child / a museum / a tourist: a visit needs more than an hour
QUICK_BUDGET_MIN = 30  # in a hurry
WAITING_BUDGET_MIN = 45  # waiting for a train / bus / flight: short, near, back in time
BETWEEN_CLASSES_BUDGET_MIN = 55  # a break between classes or meetings
LONG_STAY_BUDGET_MIN = 180  # «надолго», «на весь день»: a long sit-down, not a quick stop


@dataclass(frozen=True)
class Concept:
    name: str
    ru: tuple[str, ...] = ()
    kk: tuple[str, ...] = ()
    en: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    tier: str = "kind"  # "kind" | "mood" | "activity", see the module docstring
    flags: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    unless: tuple[str, ...] = ()
    not_stems: tuple[str, ...] = ()  # a token starting with one of these never matches this concept
    # categories removed when the concept is negated; None: the concept's own (kind tier only)
    negation_excludes: tuple[str, ...] | None = None
    # categories the LLM refinement may not ADD while this concept is active (the text itself may still name them);
    # indoor shelter in bad weather is decided in retrieve, not by the model
    forbids: tuple[str, ...] = ()
    # activity tier: a named place of one of these kinds already is the outing («прогулка с ребёнком, площадка»), so the
    # activity adds none of its own places
    covered_by: tuple[str, ...] = ()
    # the time budget (minutes) this concept implies when the text states none; the smallest of the active ones wins
    budget_min: int | None = None

    def stems(self) -> tuple[str, ...]:
        return (*self.ru, *self.kk, *self.en)


# Words that negate the concept they stand just before («без алкоголя», «не хочу фастфуд», «no kids»).
NEGATORS = frozenset(
    [
        "не",
        "без",
        "нет",
        "ни",
        "никаких",
        "кроме",
        "no",
        "not",
        "without",
        "dont",
        "doesnt",
        "wont",
        "cant",
        "never",
        "nothing",
        "ничего",
        "except",
        "avoid",
        "жоқ",
        "емес",
    ]
)
# «не знаю где поесть» is not a negation of eating
NEGATION_VOID = frozenset(["знаю", "знаем", "понимаю", "уверен", "помню", "know", "sure"])
# «кофе емес» - the negator of kk stands after the word
POSTFIX_NEGATORS = frozenset({"емес", "жоқ"})
# a word that is another language's word when the text is kazakh («бар» = «there is»)
KK_AMBIGUOUS = frozenset(
    {"бар", "бару", "бара"}
)  # «бару» is «to go», «бара» «going»: never the ru «to the bar»
# kk «бар» means «there is» (ойнау алаңы бар жер) unless a conjunction stands right before it: «кафе немесе бар»
KK_BAR_JOINERS = frozenset(
    {"немесе", "мен", "бен", "пен", "және", "не", "да", "или", "и", "or", "and"}
)
KK_QUESTION = frozenset({"ма", "ме", "ба", "бе", "па", "пе"})  # «бар ма?» = «is there?», not a bar

# A category word that says WHERE the user is, not what they want («возле парка Момышулы», «at the mall»): it is not
# added as a category. Written in natural spelling, normalised by walks.lexicon.
LOCATIVE_BEFORE = (
    "возле", "около", "рядом с", "рядом со", "недалеко от", "неподалеку от", "поблизости от", "вблизи", "близ", "напротив", "у", "в районе", "в двух шагах от",
    "по соседству с", "near", "next to", "close to", "by", "at", "opposite", "across from", "beside", "outside", "in front of", "around",
)  # fmt: skip
DETERMINERS = frozenset(
    {"the", "a", "an", "этого", "этой", "того", "той"}
)  # may stand between «near» and the place
NAME_LINKS = frozenset(
    {"имени", "им", "named", "called", "after", "названием"}
)  # «парк имени Момышулы»
# kk postpositions after the place: «Момышулы паркі жанында», «музей қасында», «паркке жақын»
KK_POSTPOSITIONS = (
    "жанында", "жанына", "жанынан", "жанымда", "қасында", "қасына", "қасынан", "маңында", "маңына", "маңынан", "қарсысында", "айналасында", "жақын",
)  # fmt: skip
KK_POSSESSIVE_ENDINGS = ("і", "ы", "сі", "сы")  # kk «парк+і»: the park OF a name, «Момышулы паркі»

# multi-word spellings joined before matching so that each has one token (hyphens are spaces by then)
JOINS = {
    "fast food": "fastfood",
    "street food": "streetfood",
    "фаст фуд": "фастфуд",
    "стрит фуд": "стритфуд",
    "wi fi": "wifi",
    "co working": "coworking",
    "step free": "stepfree",
    "alcohol free": "alcoholfree",
    "non alcoholic": "nonalcoholic",
    "gluten free": "glutenfree",
    "глютен фри": "глютенфри",
    "party of": "group of",
}

# Fuzzy matching must never turn a word into its opposite: a word and the lexicon stem it would be read as a typo
# of may not be one of these pairs («надолго» is not a typo of «недолго»). Normalised spelling, both directions.
ANTONYM_PAIRS = (
    ("надолго", "недолго"),
    ("дорого", "недорого"),
    ("далеко", "недалеко"),
    ("близко", "неблизко"),
    ("долго", "недолго"),
)  # fmt: skip
# A word that starts with a negating prefix is never read as a typo of a stem that has none («небыстро» is not a typo
# of «быстр»): that rule lives in walks.lexicon.

# A place kind named right after one of these says where the user has just BEEN, not what they want
# («только из мечети, где поесть», «just left the mall»): it is excluded from the answer. Normalised tokens.
VISITED_BEFORE = (
    "только из", "только что из", "только с", "вышел из", "вышла из", "вышли из", "вышел с", "выхожу из", "выходим из", "прямо из", "вернулся из", "вернулись из",
    "пришел из", "пришли из", "иду из", "идем из", "уже был в", "уже была в", "уже были в", "уже был на", "уже была на", "уже были на", "уже посетил", "уже посетила",
    "уже посетили", "только что был в", "только что была в", "только что были в", "только что был на", "только что были на", "только что посетил", "только что посетили",
    "just left", "just came from", "just came out of", "just got out of", "just visited", "already visited", "already been to", "just been to", "just finished at",
    "coming from", "came from", "just walked out of",
)  # fmt: skip
# kk: «мешіттен шықтым», «мұражайдан келдім» - the place in the ablative, then one of these verbs
KK_VISITED_AFTER = frozenset(
    {
        "шыктым",
        "шыктык",
        "шыгып",
        "шыккан",
        "келдим",
        "келдик",
        "келе",
        "шыгамын",
        "шыгамыз",
        "кайттым",
        "кайттык",
    }
)

# A vague description of a well-known place -> the names the dataset knows it by (Intent.landmark_refs; they also
# become retrieval keywords). Phrases are consecutive words, each a prefix of the user's word; the first matching
# alias wins and its words are not read again, so «башня с шаром» is the Baiterek and not the Nur Alem sphere.
LANDMARK_ALIASES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("башн с шар", "башн с золот шар", "шар на башн", "мұнара шар", "үстінде шар бар мұнара", "шар бар мұнара", "tower with a ball", "tower with a sphere", "tower with a globe", "tower with a golden ball", "golden ball tower", "tall tower with a ball"),
        ("Байтерек", "Baiterek"),
    ),
    (
        ("дерево жизни", "дерева жизни", "дереву жизни", "tree of life", "өмір ағашы"),
        ("Дерево жизни", "Tree of Life"),
    ),
    (
        ("большой шатер", "большой шатр", "огромный шатер", "шатер", "шатр", "big tent", "huge tent", "giant tent", "large tent", "tent shaped", "үлкен шатыр", "шатыр"),
        ("Хан Шатыр", "Khan Shatyr"),
    ),
    (
        ("здание шар", "здание сфер", "шар здание", "сфера", "сферическ", "sphere building", "sphere shaped", "the sphere", "big sphere", "glass sphere", "шар тәрізді ғимарат", "сфера ғимарат"),
        ("Nur Alem", "Нур Алем"),
    ),
)  # fmt: skip

# A well-known place named DIRECTLY («какие часы у Хан Шатыра», «стоит ли идти в Национальный музей»): the names the
# dataset knows it by. Phrases are consecutive words, each a prefix of the user's word (normalised spelling).
# Unlike LANDMARK_ALIASES (a description of a place) these are its names: they become `Intent.landmark_refs` when the
# place is the goal («хочу в Байтерек») and `Intent.info_about` when the text asks about it; a place that only says
# where the user is («возле Хан Шатыра») is neither.
DIRECT_PLACES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("хан шатыр", "хан шатр", "khan shatyr", "khan shatir", "ханшатыр"), ("Хан Шатыр", "Khan Shatyr")),
    (("байтерек", "baiterek", "bayterek", "baterek"), ("Байтерек", "Baiterek")),
    (("нур алем", "нұр әлем", "nur alem", "nur alyem"), ("Nur Alem", "Нур Алем")),
    (("хазрет султан", "әзірет сұлтан", "азрет султан", "hazrat sultan", "hazret sultan"), ("Хазрет Султан", "Hazrat Sultan")),
    (("национальн музей", "нацмузей", "national museum", "ұлттық музей", "ұлт музей"), ("Национальный музей", "National Museum")),
    (("астана опера", "astana opera"), ("Астана Опера", "Astana Opera")),
    (("ак орда", "акорда", "akorda", "ақорда"), ("Ак орда", "Akorda")),
    (("дерево жизни", "tree of life", "өмір ағашы"), ("Дерево жизни", "Tree of Life")),
)  # fmt: skip
# words that may stand between «возле / near» and a place name without changing what the user says about it
PLACE_WORDS = frozenset(
    {
        "тц",
        "трц",
        "тоц",
        "мечеть",
        "мечети",
        "мечетью",
        "mall",
        "mosque",
        "the",
        "a",
        "an",
        "музей",
        "музея",
        "музею",
        "museum",
        "комплекс",
        "ск",
        "сквер",
    }
)
# a question ABOUT a place (hours, worth a visit, what it is, can one go in): normalised spelling, regexes
INFO_QUESTIONS = (
    r"\bкакие\s+час", r"\bчас\w*\s+работ", r"\bграфик\w*\s+работ", r"\bрежим\w*\s+работ", r"\bдо\s+скольки\b", r"\bво\s+сколько\s+(?:откр|закр|работ)",
    r"\b(?:открыт|открыто|работает|закрыт|закрыто)\s+ли\b", r"\bстоит\s+ли\b", r"\bчто\s+это\b", r"\bчто\s+за\b", r"\bможно\s+ли\b", r"\bво\s+сколько\b",
    r"\bhours?\b", r"\bopening\b", r"\bwhat\s+time\b", r"\bis\s+(?:it|\w+(?:\s+\w+){0,3})\s+open\b", r"\bworth\s+(?:it|visiting|going|a\s+visit|seeing)\b",
    r"\bshould\s+i\s+(?:go|visit)\b", r"\bwhat\s+is\b", r"\bwhat\s+are\s+the\b", r"\bcan\s+(?:i|we)\s+(?:go|walk|get|enter)\b", r"\bis\s+it\s+(?:open|closed)\b",
    r"\bжумис\s+уакыт", r"\bжумыс\s+уакыт", r"\b(?:ашык|ачык|жабык)\s+(?:па|пе|ба|бе)\b", r"\bбару\s+керек\s+(?:пе|па)\b", r"\bбара\s+ма\b", r"\bбаруга\s+бола\b",
    r"\bболама\b", r"\bбола\s+ма\b", r"\bне\s+деген\b", r"\bкай\s+уакыт\w*\s+(?:ашыл|жабыл)", r"\bканша\s+уакыт\b",
)  # fmt: skip
