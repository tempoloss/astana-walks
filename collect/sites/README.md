# collect/sites — первичные факты с официальных сайтов

Часы, адрес, телефон, описание **с собственных сайтов заведений** (не 2ГИС/Яндекс/Zoon/соцсети: их ToS запрещают
хранение или требуют логин). Всё запускается из корня репозитория: `uv run python -m collect.sites.<модуль>`.

| этап | модуль | выход |
|---|---|---|
| инвентарь доменов | `inventory.py` | `data/sites/inventory.json` (домены по числу POI + `manual_targets` без сайта) |
| инвентарь культуры | `culture_inventory.py` | `inventory_culture.json` + `partitions_culture/p1..p3.json` (учреждения и достопримечательности без день-квалифицированных часов; снапшоты P856/e-museum/robots в `snapshots/`) |
| раздача работы | `partition.py` | `data/sites/partitions/p1..p6.json` (p6 = ручные цели + добор до равного веса) |
| краулинг | `fetch.py`, `jsonld.py`, `hours.py`, `store.py` | `data/sites/facts/<domain>.json` |
| проверка | `verify.py [--write]` | каждый `snippet` обязан найтись в кэшированной странице, иначе факт удаляется; филиал с координатами вне коробки Астаны (`store.ASTANA_LAT/LON` = 50.98–51.25 / 71.25–71.60) удаляется целиком |
| привязка к POI | `join.py` | `data/sites/joined.json`; `poi.enriched.json` не меняется |
| применение | `apply.py` (последняя стадия `collect.build`) | shipped `data/poi.enriched.json` (на месте), `data/poi_enriched_stats.json` (ключ `official_sites`), секция в `data/coverage_delta.md` |

Эталонные краулеры (KFC `data-lat/lng`-карточки, текстовые страницы контактов): `crawl_demo.py`.

## Схема `data/sites/facts/<domain>.json`

```json
{"domain": "kfc.kz", "robots_ok": true, "fetched_at": "ISO", "pages": ["https://kfc.kz/stores"],
 "branches": [{"name", "address", "lat", "lon", "phone", "opening_hours_raw", "opening_hours_osm", "description",
               "price_text", "url",
               "evidence": [{"field", "url", "snippet", "fetched_at"}],
               "method": "jsonld|locator_json|html|agent_extract", "confidence": 0.0}],
 "notes": "что пробовали, чего нет", "source_label": "museum_register — только у записей реестра (e-museum.kz)"}
```

Правила (проверяет `store.validate_branch` при `save_facts`):

- **ни одного факта без `evidence`**: `address` ← поле `address`, `phone` ← `phone`, часы ← `opening_hours`,
  `lat/lon` ← `geo`, `description` ← `description`, `price_text` ← `price` (текст цены как на странице/в карточке,
  никогда не разбирается в число); `snippet` ≤ 300 символов — дословная (с точностью до пробелов)
  подстрока страницы `url`. `url` = ровно тот URL, что передан в `SiteFetcher.fetch` (ключ кэша).
- `opening_hours_osm` собирается **только** из `opening_hours_raw` функцией `hours.to_osm` (`make_branch` делает это
  сам); `None`, если текст не разобран однозначно. Результат валидируется парсером приложения (`opening-hours-py`).
- **часы без дней и `00:00-00:00`**: `hours.analyze(raw)` не конвертирует текст, где названо только время («с 18:00 до
  06:00», «10:00–22:00») или диапазон `00:00-00:00` без слова «круглосуточно»/«24/7» в том же тексте.
  `opening_hours_raw` остаётся, `opening_hours_osm = null`, `hours_flags = ["needs_days"]` и/или `["ambiguous_24h"]`
  (поле заполняют `make_branch`/`save_facts`/`verify`). `join.py` кладёт такие часы в `hours_unqualified` (с
  `field_sources`), не в `opening_hours`. После правок правил: `verify --write` пересчитывает все файлы.
- `robots_ok: false` ⇒ ветки не сохраняются.

## Как писать краулер домена

```python
from collect.sites import store
from collect.sites.fetch import SiteFetcher, visible_text   # robots.txt + ≤1 запрос/с на домен + кэш .local/http_cache.sqlite
f = SiteFetcher()
urls = f.discover("https://example.kz")            # ссылки stores|branches|контакт|астана... + sitemap.xml
page = f.fetch(url)                                 # Page(status, text, fetched_at, robots_blocked)
branches = f.jsonld_branches(url)                   # LocalBusiness из JSON-LD, evidence уже дословные
text = visible_text(page.text)                      # для HTML: snippet = срез этого текста (или сырого page.text)
b = store.make_branch(name, [store.evidence("opening_hours", url, snippet, page.fetched_at)], "html", 0.8,
                      opening_hours_raw="Пн-Пт 9-18", url=url)
store.save_facts(store.new_record("example.kz", robots_ok=True, pages=[url], branches=[b], notes="..."))
```

Затем `uv run python -m collect.sites.verify <domain>` и `uv run python -m collect.sites.join`.

## Привязка (`join.py`)

Один филиал ↔ один POI. С координатами: ≤150 м и (имя ≥75 или ключ одного имени — *начало* другого: «KFC Астана | Мега» ≈
«KFC», но не торговый центр «Керуен») либо сайт POI на том же домене (имя ≥40). Без координат: POI с сайтом на домене и
тот же дом+улица, либо явно лучшее имя. Запись реестра (`source_label: museum_register`, e-museum.kz) — без домена POI:
ветка без координат сопоставляется со всеми POI по имени+адресу (`register_name_address`), адрес не перекрывает слабого
имени (музей-заповедник «Бозоқ» и Нацмузей стоят на Тәуелсіздік 54). В `joined.json`: `fields`, `new_fields` (поля,
которых у POI не было), `conflicts` (официальное значение ≠ значение POI — не перезаписывается), `field_sources` с
`source: official_site` (или `museum_register`), `url`, `snapshot_date`, `snippet` и лицензией источника;
`official_domain` — домен, который отвечает за `official_site`-поля (на него ссылается `official_site_match`).

## Применение к датасету (`apply.py`)

`uv run python -m collect.build` запускает `apply.py` последней стадией (без сети): набор, который выдал `merge`
(`data/poi.enriched.json`), дополняется проверенными филиалами (`join.join_branches`) и записывается обратно в
`data/poi.enriched.json` — это и есть shipped-набор приложения. `python -m collect.sites.apply` отдельно запускают
только на выходе `merge`: набор, уже несущий факты сайтов, отказывается обрабатываться повторно (`already_applied`).
Статистика — в `data/poi_enriched_stats.json` (merge-статистика с пересчитанными `after` и `per_source_counts`, плюс
ключ `official_sites`).
Все поля существующих POI сохраняются; добавляются поля `opening_hours_official`, `hours_conflict`,
`hours_conflict_prefers`, `hours_unqualified`, `hours_unqualified_flags`, `description_official`,
`official_site_match` (у всех записей одна схема).

- **Часы.** `opening_hours` берётся с сайта *только если у POI его нет* (день-квалифицированная OSM-строка;
  `field_sources.opening_hours.source = official_site`, `hours_state = known`). Если часы есть у обоих и недельные
  расписания различаются (сравнение по минутам эталонной недели, `hours.same_schedule`, «12:00-00:00» = «12:00-24:00»),
  `opening_hours` остаётся OSM-ным, значение сайта лежит в `opening_hours_official`, `hours_conflict = true`.
  `hours_conflict_prefers = "official_site"`, если страница сайта получена позже снимка OSM-часов (и значение
  день-квалифицированное — иначе оно не попало бы в `opening_hours_osm`), иначе `"osm"`. Это справочный флаг:
  снимок OSM — дата скачивания, а не дата правки, поэтому `opening_hours` приложению не переключается. Совпадающие
  расписания — не конфликт (`opening_hours_official` заполнен, `hours_conflict = false`).
- **Домен говорит за POI только при согласии** (`agree.speaks_for`): домен принадлежит POI (его сайт) или первое слово
  домена входит в имя/бренд POI (`coffeeboom.kz` ~ «Coffee BOOM», `kfc.kz` ~ `kfc-kazakhstan.kz`), и категория POI
  совместима с категориями собственных POI домена (еда ↔ еда). Близость к POI сама ничего не привязывает: филиал
  кофейни внутри ТРЦ — не ТРЦ (раньше ТРЦ получали его часы, `hours_conflict` и телефон). Готовый датасет
  проверяет `verify.check_dataset` (`uv run python -m collect.sites.verify --dataset data/poi.enriched.json`; `apply`
  не пишет датасет, не прошедший проверку): любое официальное поле — с домена, согласного с POI, и URL доказательства
  на этом домене (или другом домене того же бренда), иначе платформа-вендор «не сайт POI».
- **Часы без дней** («с 10:00 до 22:00», `00:00-00:00` без «круглосуточно») — только в `hours_unqualified` (+ флаги),
  никогда в `opening_hours`; в «покрытие часов» не входят.
- `phone` / `address` заполняются только пустые (адрес с другим городом — Алматы и т. п. — не берётся: опечатка
  сайта); описание сайта — в `description_official`, `description` не трогается; `price_text` — дословный текст цены
  со страницы/карточки, заполняется только пустой. День-квалифицированные часы сайта реестр не перебивает: принятое
  сопоставление остаётся, но поля, которых у него нет, к нему добавляются (цена из реестра + часы своего сайта
  у Нацмузея).
- **Новые POI**: ветка без совпадения с POI, у которой на странице самого сайта есть `geo`-доказательство (координаты
  внутри коробки Астаны), не из сторонного бэкенда (запись `notes` начинается с «third-party»), с известной
  категорией домена (доминирующая категория его POI, доля ≥ 0,5, ничья → cafe > restaurant > …; mall/park/landmark
  — это арендаторы, не точки), без «плейсхолдер»-координат (одна точка у разных по имени веток домена = центр
  карты по умолчанию). Дубликат — POI ≤ 75 м с похожим именем (`join.name_similarity ≥ 60`) среди существующих и
  уже созданных. Имя — имя с сайта без хвоста « — адрес»/«, адрес»/«(адрес)»; имя-адрес или описание места
  («Орталық саябақтағы сағаттың жанында») заменяется на «<бренд домена>, <адрес>», нет адреса — не создаём.
  `id = site/<domain>/<sha1[:10]>`, `source = sources = official_site`, `field_sources` на каждое поле (категория —
  `derived`), `match_confidence` = уверенность ветки, `official_site_match.nearest_poi_m/_name_score` — ближайший
  существующий POI в 75 м. Ветки без своих координат POI не создают.
