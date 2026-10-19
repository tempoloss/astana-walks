"""Kazakh / Russian / English wording of «Мой вайб» on the page: the first-screen chip and the block of «Память»
(web/static/js/vibe-form.js). The line under a card and the lead of a vibe search are the core's (walks.vibe_data).
Merged into `UI` (i18n.py)."""

from __future__ import annotations

from walks.i18n import Entry

VIBE: dict[str, Entry] = {
    "sug_vibe": ("Менің вайбыма", "Под мой вайб", "My vibe"),
    "sug_vibe_q": ("Менің вайбыма сай", "Под мой вайб", "Match my vibe"),
    "vb_title": ("Менің вайбым", "Мой вайб", "My vibe"),
    "vb_intro": (
        "Осы бойынша орын іздеймін: «Менің вайбыма» түймесі және кәдімгі жауаптардағы рет.",
        "По нему я подбираю места: кнопка «Под мой вайб» и порядок в обычных ответах.",
        "I pick places by it: the “My vibe” button and the order of ordinary answers.",
    ),
    "vb_why": (
        "Вайбыңызға сай іздеу үшін оның қандай екенін айтыңыз: интроверт пе, экстраверт пе және не ұнайды.",
        "Чтобы искать под ваш вайб, скажите, какой он: интроверт вы или экстраверт и что вам нравится.",
        "To search for your vibe, tell me what it is: introvert or extrovert, and what you like.",
    ),
    "vb_axis": ("Сіз көбіне", "Вы скорее", "You are more of"),
    "vb_axis_calm": ("Интроверт: тыныштық", "Интроверт: тишина", "Introvert: quiet"),
    "vb_axis_any": ("Маңызды емес", "Не важно", "Does not matter"),
    "vb_axis_lively": ("Экстраверт: адамдар", "Экстраверт: люди", "Extrovert: people"),
    "vb_likes": ("Не ұнайды", "Что нравится", "What you like"),
    "vb_text": (
        "Вайбыңызды сипаттаңыз: сізге не ұнайды",
        "Опишите свой вайб: что вам нравится",
        "Describe your vibe: what you like",
    ),
    "vb_ph": (
        "Мысалы: тыныштықты, кітап пен саябақтарды жақсы көремін, көп адамды ұнатпаймын",
        "Например: люблю тишину, книги и парки, не люблю толпы",
        "For example: I love quiet, books and parks, I hate crowds",
    ),
    "vb_note": (
        "Сақтағанда мәтінді сыртқы ЖИ моделі бір рет оқиды (модель болмаса, сөздік) және жоғарыдағы белгілерді қояды. "
        "Сұраныстарыңызбен мәтін жіберілмейді.",
        "При сохранении текст один раз читает внешняя модель ИИ (без неё словарь) и отмечает вайб выше. С вашими "
        "запросами текст не уходит.",
        "On save an external AI model reads the text once (without one, a word list) and marks the vibe above. The "
        "text never goes with your requests.",
    ),
    "vb_on": (
        "Вайбты сақтау «Қалауларымды есте сақтау» дегенді қосады; «Бәрін ұмыту» оны қайта өшіреді.",
        "Сохранение вайба включает «Запоминать мои предпочтения»; «Забыть всё» снова выключает.",
        "Saving the vibe turns on “Remember my preferences”; “Forget everything” turns it off again.",
    ),
    "vb_save": ("Сақтап, вайбты белгілеу", "Сохранить и отметить вайб", "Save and mark the vibe"),
    "vb_reading": ("Оқып жатырмын…", "Читаю…", "Reading…"),
    "vb_read": ("Былай түсіндім: {facets}", "Понял так: {facets}", "I read it as: {facets}"),
    "vb_read_none": (
        "Мәтіннен не ұнайтынын таппадым: жоғарыдан өзіңіз белгілеңіз.",
        "В тексте не нашёл, что вам нравится: отметьте сами выше.",
        "I found nothing you like in the text: mark it above yourself.",
    ),
    "vb_go": ("Вайбыма сай іздеу", "Искать под мой вайб", "Search for my vibe"),
}
