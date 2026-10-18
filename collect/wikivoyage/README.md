# collect/wikivoyage — часы / цены / описания достопримечательностей из Wikivoyage

## Источник

Статьи об Астане в пяти изданиях Wikivoyage (свободный путеводитель проекта Wikimedia):

| издание | страница (action=parse, prop=wikitext) | pageid | листингов | листингов see/do/eat |
|---|---|---|---|---|
| en | https://en.wikivoyage.org/wiki/Astana | 1775 | 88 | 52 |
| it | https://it.wikivoyage.org/wiki/Astana | 2233 | 71 | 51 |
| he | https://he.wikivoyage.org/wiki/אסטנה | 3339 | 51 | 39 |
| pl | https://pl.wikivoyage.org/wiki/Astana | 294 | 14 | 14 |
| ru | https://ru.wikivoyage.org/wiki/Астана | 6257 | 60 | 31 |

Снимки wikitext — `snapshots/<lang>.wikitext` с метаданными `snapshots/<lang>.meta.json` (заголовок страницы, pageid,
дата снимка). Стадия `apply` работает **только по снимкам**: сеть не нужна, повтор сборщика даёт ровно те же числа.

## Лицензия

Текст Wikivoyage распространяется под **CC BY-SA 4.0**. Дословная строка из подвала каждой статьи
(проверено живым запросом `https://en.wikivoyage.org/wiki/Astana`, 2026-10-17):

> "Text is available under the Creative Commons Attribution-ShareAlike License"
> (https://wikivoyage.org/wiki/Wikivoyage:Creative_Commons_Attribution-ShareAlike_License)

STORE = да: текст скачан, храним и используем в платном продукте с атрибуцией (ссылка на статью + издание + лицензия).
Описания — сторонний путеводителейый текст: приложение показывает его **только** с формулировкой
«по данным путеводителя Wikivoyage (CC BY-SA 4.0)» и ссылкой на статью (`walks.reasons._voyage_info`), никогда как
наш собственный текст; в ответе используется текст того издания, чей язык совпадает с языком ответа.
Производный текст под share-alike: при публикацию описаний вне приложения сохранять атрибуцию и ту же лицензию.

## Вежливость и сеть

Только `fetch` (ручный шаг, не часть `collect.build`): GET к `https://{lang}.wikivoyage.org/w/api.php`,
UA `astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)` (Wikimedia банит безымянные UA), не чаще 1 запроса/с
(политика Wikimedia ≤5 req/s; стадия делает ровно 5 запросов на город), ответы проходят через общий кэш `collect/net.py`.

## Обновление

Режим: по требованию, ориентировочно раз в квартал (статьи правят редко; ru-статья обновлялась в 2024-м). Порядок:
1. переснять wikitext пяти страниц (см. `fetch` ниже) и положить в `snapshots/`;
2. `uv run python -m collect.build` — полная пересборка: стадии merge → sites → gov заново пишут
   `data/poi.enriched.json`, затем `wikivoyage` добавляет свои поля; offline (кэш HTTP + снимки) воспроизводима.

```
# переснять снимки (сеть; из корня репозитория):
uv run python - <<'PY'
import json, pathlib, urllib.parse, urllib.request
UA = "astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)"
out = pathlib.Path("collect/wikivoyage/snapshots")
for lang, title in (("en", "Astana"), ("it", "Astana"), ("he", "אסטנה"), ("pl", "Astana"), ("ru", "Астана")):
    url = f"https://{lang}.wikivoyage.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": title, "prop": "wikitext", "format": "json", "formatversion": "2"})
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read())["parse"]
    wt = d["wikitext"] if isinstance(d["wikitext"], str) else d["wikitext"]["*"]
    (out / f"{lang}.wikitext").write_text(wt, encoding="utf-8", newline="\n")
```

## Что берётся и куда

Поля листингов — алиасы одних и тех же фактов (`editions.py`): часы `hours|orari|שעות|godziny`, цены
`price|prezzo|מחיר|ceny`, описания `content|descrizione|תיאור|opis|description`, wdid `wikidata|ויקינתונים|wdid`.

* листинги только из секций see/do (en See/Do, it Cosa vedere/Cosa fare, he מוקדי עניין/פעילויות,
  pl Warto zobaczyć, ru Достопримечательности/Чем заняться); eat/drink (en Eat/Drink, it Dove mangiare/Come
  divertirsi, he אוכל/שתייה וחיי לילה, ru Еда/Ночная жизнь) дают **только часы и цены**, buy/sleep не дают ничего;
* джойн (`join.py`): сначала `wikidata` листинга = `wikidata_id` записи; затем координаты ≤150 м с именем-гейтом:
  `name_score ≥ 60`, либо ≤40 м + совместимая категория + общий токен названия (транслитерационно-нечувствительный
  `collect.names.skeleton`; родное название из `alt` учитывается). **Правило ложных пар**: листинг eat/drink
  требует plain name-score — низкий скор это другое заведение рядом, а не перевод; see/do-пара со скором <60
  принимается только близкой, category-совместимой и с общим токеном. Общий токен должен **называть** место: род
  заведения («мечеть», «музей», `collect.venue_names`), boilerplate («Республика Казахстан», «Астана») и слово,
  которое носят заведения ещё ≥2 категорий («expo»: паб, кафе и зал — это район, а не название), токеном не считаются.
  Листинг, у которого есть `wikidata`, не джойнится с записью с другим `wikidata`. Так отбрасываются арендаторы
  («Пинта»←Ak Orda, «Gold Mine Coaster»←Chan Szatyr, «Kulanshi»←Дворец мира, «Duman»→«Ailand») и пары «комплекс ↔ один
  павильон» («Expo 2017 buildings»←Q19858174 больше не вешает часы на «SML EXPO Energy Hall»), а переводные пары
  остаются: «Assumption Cathedral»→«Свято-Успенский кафедральный собор», «Museo storico delle Forze Armate»→
  военно-исторический музей (общие kk-слова «әскери-тарихи»), «Сфера Nur Alem»→«Nur Alem Museum of Future Energy».
  Листинг, который говорит только о роде места («Центральная мечеть», «Grand Mosque of Astana»), джойнится правилом
  `kind+near`: тот же род и ≤40 м — одного слова «мечеть» для пары больше достаточно не считается; после стадии
  `dedupe` карточка стоит на всех точках поглощённых записей и отвечает на все их имена (`merged_from`, `alt_names`),
  поэтому такие пары ловятся и на 5 м. Все пары по координатам
  логируются в `data/wikivoyage_joined.json` (`radius_pairs`) для человеческой проверки, вместе с unmatched-листингами;
* часы: конвертер `collect/sites/hours.py` (расширен днями it/pl: «Lun-Dom 10:00-18:00» → `Mo-Su 10:00-18:00`;
  ivrit-часы he остаются непереводимыми) — в `opening_hours` попадает **только** день-квалифицированная строка и
  только если у записи своих часов нет; есть свои → `opening_hours_voyage` (рядом, ничего не перезаписывает);
  текст без дней → `hours_unqualified` (никогда не `opening_hours`);
* цены: дословный текст с валютой → `price_text` (общее поле; первичный источник — сайт заведения — имеет приоритет:
  стадия пишет только в пустое); числами не парсим;
* описания → `description_voyage` + `field_sources.description_voyage = {source: wikivoyage, license: CC BY-SA 4.0,
  lang: издание, url: статья, snapshot_date}`; описание из Википедии/сайта не перезаписывается;
* новых записей стадия не создаёт: несовпавший листинг остаётся в логе `unmatched`.

## Проверка

`verify.check_dataset` — каждое поле со `source: wikivoyage` обязано ссылаться на статью своего издания
(`{lang}.wikivoyage.org`), иметь лицензию, дату снимка и издание; `opening_hours` из Wikivoyage обязан быть
валидной OSM-строкой **с днями** (без дней — только в `hours_unqualified`); пустой текст цены/описания — ошибка.
Стадия `collect.build` останавливается до записи при любой проблеме. Тесты: `collect/tests/test_wikivoyage.py`
(парсинг, секции, джойн, ложные пары), `app/tests/test_wikivoyage.py` (показ с атрибуцией, только язык издания).
