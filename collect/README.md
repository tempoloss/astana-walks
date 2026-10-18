# collect/ — сбор и обогащение POI Астаны

> **Файлы `data/` — замороженный снимок от 16–17.10.2026; пересборка необязательна.** Всё, что читает приложение
> (`data/poi.enriched.json`, `walk_cache.json`, `population_proxy.json`, `demo_llm_cache.json`, …), лежит в
> репозитории, и `uv run poe check` collect/ не запускает. Пересборка — долгая сетевая задача (вежливые лимиты
> хостов; Overpass бывает нестабилен — 429/504, зеркала, повторы) и даёт другой снимок OSM / Overture / Wikidata, а
> значит другие числа в `data/coverage_delta.md` и в таблицах оценки. Без сети проверяется только сборщик:
> `uv run --with pytest python -m pytest collect/tests -q`.

```
uv sync
uv run python -m collect.build            # districts → osm → overture → geocheck → wiki → wiki_places → merge → sites → gov → dedupe → wikivoyage, всё через кэш и без сети для sites/gov/dedupe/wikivoyage
uv run python -m collect.build --refresh  # игнорировать кэш HTTP (перекачать всё, но вежливо)
uv run python -m collect.build --no-sites # остановиться после merge: data/poi.enriched.json без фактов сайтов, госреестров и Wikivoyage
```

Запуск — из корня репозитория. Повторный запуск идемпотентен: ответы лежат в `.local/http_cache.sqlite`
(ключ = метод + URL + хэш тела), стадия Overture пропускается, если в `data/overture_places.json` уже последний
релиз; в конце `build` печатает `Wikimedia: network_requests=0 cache_hits=…`.

Юнит-тесты сборщика (без сети): `uv run --with pytest python -m pytest collect/tests -q`.

## Стадии и файлы

| стадия | модуль | выход |
|---|---|---|
| districts | `districts.py` | `data/districts.geojson` (районы Астаны, OSM admin_level=6, MultiPolygon, ODbL) |
| osm | `overpass_poi.py` | `data/poi.osm.json`, `data/poi.osm_stats.json` |
| overture | `overture_places.py` | `data/overture_places.json` (все записи bbox + `meta`: релиз, распределение confidence) |
| geocheck | `coord_quality.py` | `data/overture_geocheck.json` (подозрительные координаты Overture и ответы Nominatim) |
| wiki | `wiki_enrich.py` | `data/wiki_enrichment.json` (матчи, сущности, запросы SPARQL, пороги) |
| wiki_places | `wiki_places.py` | `data/wiki_places.json` (места из Wikidata / Wikipedia: категории, geosearch, класс P31, координаты) |
| merge | `merge.py` (+ `wiki_merge.py`, `metrics.py`) | `data/poi.enriched.json`, `data/poi_enriched_stats.json`, `data/coverage_delta.md` |
| sites | `sites/apply.py` (+ `sites/join.py`, `sites/verify.py`) | `data/poi.enriched.json` (то же имя: набор merge + факты официальных сайтов), `data/poi_enriched_stats.json` (ключ `official_sites`, `after`/`per_source_counts` пересчитаны), секция «Official-site facts» в `data/coverage_delta.md`, `data/sites/joined.json` |
| gov | `gov/apply.py` (+ `gov/geocode.py`, `gov/verify.py`) | `data/poi.enriched.json` (на месте: + ЦОН, `admin_hours` реестра № 730), `data/poi_enriched_stats.json` (ключ `state_registry`), `data/gov/joined.json`, секции в `data/coverage_delta.md` и `data/ATTRIBUTION.md` |
| dedupe | `dedupe.py` (+ `venue_names.py`) | `data/poi.enriched.json` (на месте: по одной карточке на музей/театр/достопримечательность/парк/ТЦ), `data/poi_enriched_stats.json` (ключ `duplicates`; `per_source_counts` остаётся счёткой стадий сбора), секция «Same-venue duplicates» в `data/coverage_delta.md`, `data/duplicates_merged.json` (лог кластеров) |
| wikivoyage | `wikivoyage/apply.py` (+ `wikivoyage/editions.py`, `wikivoyage/join.py`, `wikivoyage/verify.py`) | `data/poi.enriched.json` (на месте: часы/цены/описания из путеводителя, `source: wikivoyage`), `data/poi_enriched_stats.json` (ключ `wikivoyage`), `data/wikivoyage_joined.json` (лог пар для человеческой проверки), секция «Wikivoyage» в `data/coverage_delta.md`; снимки wikitext — `collect/wikivoyage/snapshots/`, источник и лицензия — `collect/wikivoyage/README.md` |

`collect.build` — единственная команда сборки shipped-набора: стадия `sites` идёт после `merge` и перезаписывает
`data/poi.enriched.json` на месте. Отдельно `python -m collect.sites.apply` запускают только на выходе `merge`
(набор, уже несущий факты сайтов, он отказывается обрабатывать повторно — сначала `collect.build`).

Стадия `gov` (`gov/apply.py`; `--no-sites` пропускает её вместе с `sites` и `wikivoyage`) добавляет факты гос-реестров: ЦОН Астаны
(gov4c.kz), реестр спортобъектов № 730, `source: state_registry`, координаты только сопоставлением с OSM/POI
(`data/gov/`, `data/gazetteer/`, `collect/gov/catalog.json`); сетевые шаги (`collect.gov.cons|sport|catalog|gazetteer|osm`)
запускаются отдельно, сама стадия работает по файлам без сети. Источники, лицензии, правила области часов —
`collect/gov/README.md`.

Стадия `dedupe` (`dedupe.py`, offline, после `gov` и до `wikivoyage`) схлопывает записи об одном месте: правила —
общий `wikidata_id`; совпадение имён на ru/kk/en/транслитерации (`venue_names`: родающие слова «музей/мечеть/парк»,
«Республика Казахстан», «Астана» и описательные «национальный/исторический» вынесены отдельно, цифры решают) в 120 м
(парки 300 м; тот же адрес с домом — 300 м); ≤20 м + общее знающее слово; храмы одной веры ≤30 м; «голый» Overture-пин,
названный только родом («Historical Museum Astana»), ≤250 м от записи того же рода. Не сливаются: разные `wikidata_id`,
ветки сети (общий `brand`), имя, которое носят ≥3 места в разных концах города, сгенерированные имена («Парк / сквер»),
разные категории; кластер не растягивается дальше 350 м. Переживает слияние самая богатая запись: она берёт все чужие факты, которых у неё
нет (с их `field_sources`), несёт чужие id в `aliases` и описывает поглощённую запись в `merged_from` — по этим id
работают `collect.dedupe.resolve_alias` и `collect.events.venues.VenueIndex.by_id` (джойны событий и закреплённые
демо-ключи не ломаются). Конфликтующие значения остаются у выжившей, но записаны в `values_not_taken`. Стадия
одноразовая: набор с `aliases` отвергается.

Стадия `wikivoyage` (`wikivoyage/apply.py`, последняя; `--no-sites` пропускает её) добавляет часы/цены/описания
достопримечательностей из статей об Астане в en/it/he/pl/ru Wikivoyage (CC BY-SA 4.0): листинги see/do (eat/drink —
только часы и цены), джойн по `wikidata`, затем координаты ≤150 м с именем-гейтом; день-квалифицированные часы —
в пустой `opening_hours`, иначе `opening_hours_voyage`, текст без дней — `hours_unqualified`; цены — текстом в общее
поле `price_text` (факт с сайта имеет приоритет: стадия пишет только в пустое); описания — в `description_voyage`
со ссылкой на статью и издание. Стадия offline: по снимкам `collect/wikivoyage/snapshots/`; пересъёмка снимков —
ручный шаг (`collect/wikivoyage/README.md`), лог пар для человеческой проверки — `data/wikivoyage_joined.json`. Набор, уже несущий факты путеводителя,
пересобирается на месте: `strip` снимает ровно те поля, чей `field_sources` указывает на стадию, и джойн проходит
заново — поэтому смену правил джойна видно одним `uv run python -m collect.wikivoyage.apply`.

`data/poi_enriched_v1_stats.json` — замороженная сводка обогащённого набора от 2026-10-16 (2178 записей, до расширения
релевантности); «до» в разделе «Relevance expansion» файла `coverage_delta.md` берётся оттуда
(`python -m collect.metrics --freeze <poi.json>` пишет его; запускать только на наборе, собранном до расширения).

`data/poi.json` и `data/poi_stats.json` — замороженный вход тестов/кэша маршрутов `app/`; ни одна стадия их не
перезаписывает (`overpass_poi` отказывается писать в файл с именем `poi.json`). «До» в статистике берётся оттуда.

## net.py — вежливый сетевой слой (общий для всех коллекторов)

- UA `astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)` (Wikimedia банит безымянные UA).
- Token bucket на хост: WDQS 1 параллельный и ≥1 с между запросами; Wikipedia/Wikidata/Wikimedia API — один общий
  bucket ≤5 req/s; Overpass 1 параллельный, ≥5 с; Nominatim 1 req/s.
- `Retry-After` соблюдается; экспоненциальный backoff с джиттером на 429/5xx/таймауты, максимум 5 повторов.
- Кэш ответов (`200`, для pageviews ещё `404`), checkpoint для батч-задач (`wbgetentities`, pageviews) в том же sqlite.
- **Failover через VPS** (SOCKS5, `WALKS_SOCKS=socks5://127.0.0.1:1081`, нужен `httpx[socks]`): сначала домашний IP;
  хост переводится на прокси только после 3 подряд 429/403 от него и на 15 минут (cool-down), после чего возврат на
  прямой маршрут. Это резерв, а не ротация для обхода лимитов; каждое переключение пишется в stderr
  (`[net] FAILOVER host=… direct->socks …`). `WALKS_FORCE_SOCKS=1` — принудительно через прокси (для проверки).
  Туннель поднимать одним постоянным соединением:
  `ssh -N -D 127.0.0.1:1081 -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -o BatchMode=yes <user>@<vps-host>`
  (на VPS ufw LIMIT на 22: не переподключаться в цикле).

## OSM (`overpass_poi.py`)

Селекторы и категории прежние; дополнительно сохраняются теги `wikidata`, `wikipedia`, `name:kk`, `name:en`,
`brand`, `brand:wikidata`. Дедупликация по имени (50 м) как раньше; **станции (`transit_station`)** дедуплицируются
по (network, тип станции) в радиусе 150 м независимо от имени — предпочитается way, затем более заполненная запись
(пара node/way «Дворец Единоборств» схлопывается). В stats: `count_lrt_stations` (Tarlan Astana = 18),
`count_with_wikidata_tag`, `count_with_wikipedia_tag`, `count_with_name_kk/en`, `count_with_brand*`.

## Wikidata / Wikipedia (`wiki_enrich.py`)

Q1520 проверяется label-запросом (ru/en/kk = «Астана»/Astana). Кандидаты: SPARQL «`P131* wd:Q1520` + `P625`» и
SPARQL по bbox (`wikibase:box`); запросы записаны в `wiki_enrichment.json -> queries`. Методы матча
(`match_method`):

- `tag` — OSM `wikidata=Q…` (confidence 1.0) или `wikipedia=lang:Title` через pageprops (0.95);
- `sparql` — кандидат из множества «located in Астана (P131*)» + схожесть имени (ru/kk/en, нечувствительна к
  транслитерации, rapidfuzz ≥ 88) + расстояние ≤ 150 м;
- `fuzzy` — то же, но элемент нашёлся только bbox-запросом (цепочки P131 до Астаны в Wikidata нет).

`match_confidence` для sparql/fuzzy = `score/100 · (1 − 0.25·d/150)`. Неоднозначные (второй кандидат в пределах
5 баллов) отбрасываются, один элемент достаётся лучшему из претендентов. Далее: `wbgetentities` (50 id/запрос; labels,
descriptions, sitelinks ru/kk/en), Wikipedia action API (`extracts|pageprops`, 50 заголовков/запрос, ru/kk/en),
Wikimedia pageviews за последний полный месяц как `popularity_pageviews`. Лицензии: Wikidata CC0,
Wikipedia CC BY-SA 4.0.

## Overture (`overture_places.py`)

DuckDB + `httpfs` (`s3_region='us-west-2'`, анонимно), последний релиз определяется листингом `release/`.
bbox 50.98–51.25 / 71.25–71.60. В релизе 2026-09-23.1 колонки `categories` нет — используется `taxonomy`
(`primary`, `hierarchy`, `alternates`); `names.common` пуст для Астаны (только `names.primary`).
Маппинг taxonomy → наши категории: `TAXONOMY_MAP` + любые `*_restaurant`; остальное → `other` (в рекомендации не
попадает; в `poi.enriched.json` такие Overture-only записи не добавляются, остаются в `overture_places.json`).

**Порог confidence = 0.7** (`CONFIDENCE_CUTOFF`). Обоснование и таблицы — в `data/coverage_delta.md`: ниже 0.7 все
записи наших категорий — одиночные Meta без подтверждения другими датасетами, доля совпадений с OSM плоская (0–8 %),
с 0.7 появляются записи других датасетов (Microsoft/Foursquare/AllThePlaces), растёт доля сайтов и match-rate с OSM. Ложный «призрак» в маршруте
дороже пропущенного места.

## Merge (`merge.py`)

Все прежние поля записи сохранены, добавлены: `sources[]`, `field_sources{field:{source,license,snapshot_date,…}}`,
`overture_id`, `overture_match`, `overture_confidence`, `hours_state`, `brand`, `brand_wikidata`, `wikidata_id`,
`wikipedia{lang:{title,url,extract}}`, `labels{ru,kk,en}`, `popularity_pageviews`, `wiki_match{method,confidence}`.

- OSM↔Overture: расстояние ≤75 м и сходство имён ≥75, либо ≤150 м и ≥92 (для Overture-записей вне наших категорий —
  всегда ≥92); 1:1 жадно по лучшему score.
- Дубли сетей Overture↔OSM (второй проход, для Overture-only записей любой категории и любой пары категорий
  cafe/fast_food/restaurant/…): тот же `name_key` (`names.name_key` — копия `name_key` из `app/walks/retrieve.py`:
  casefold → кириллица incl. kk → латиница → без не-алфавитно-цифровых; названия из одних слов-типов вроде «Кафе» не
  считаются) либо равные `brand` / `brand:wikidata`, ≤150 м; при полностью совпадающем названии — до 250 м (один
  киоск в аэропорту OSM и Overture ставят на 240 м). Запись входит в OSM-запись (`overture_match.method =
  "chain:<name|brand|brand_wikidata>"`), а если у OSM-записи уже есть пара из Overture — отбрасывается. Счётчик и
  примеры — в `data/coverage_delta.md`.
- Не-POI из Overture (`nonpoi.py`): имена/таксономия жилых комплексов («ЖК», «Жилой комплекс», `тұрғын кешені`),
  офисов/БЦ, недвижимости и стройки, школ, клиник, госорганов, банков/банкоматов, автосервисов, юрлиц («ТОО», «ИП») →
  категория `other` (в `poi.enriched.json` не попадают). Overture `historic_site` без слова-наследия в имени
  (памятник, мечеть, парк, …) тоже → `other`: в Астане этим ярлыком в основном размечены ЖК и адреса. Разбивка по
  причинам и примеры — в `data/coverage_delta.md`.
- Конфликты: OSM побеждает по `opening_hours`, координатам и имени; Overture заполняет пустые `phone`, `website`,
  `brand`, `brand_wikidata`.
- Overture-only записи (id `overture/<id>`, `source: "overture"`) входят с `hours_state: "unknown"` и
  описанием `derived`.
- `description` из Википедии (первые 1–2 предложения, ru → en → kk) подставляется, если нет описания из OSM;
  `description_source: "wikipedia"` (и в `description_auto`).
- Лицензия поля из Overture — лицензия вкладчика записи (`overture_fs`: из `sources[].license` записи; Foursquare — Apache-2.0, AllThePlaces — CC0, остальные — CDLA-Permissive-2.0), в `field_sources` пишется ещё `contributor`; запись без лицензии — ошибка, не умолчание.
- Атрибуция источников — `data/ATTRIBUTION.md`; ведётся вручную, `merge` её не пишет (иначе пересборка стёрла бы разделы остальных стадий). Лицензия файлов `data/` — `data/NOTICE.md`, таблица с цитатами — `docs/licensing.md`.

## Расширение релевантности (2026-10-17)

Результаты «до/после», проверки часов работы и 10 новых записей — в `data/coverage_delta.md` (раздел «Relevance
expansion»), источники и отказы — в `collect/SOURCES.md` §10.

- **OSM, второй запрос** (`overpass_poi.EXTRA_SELECTORS`): по одному маленькому запросу на селектор, чтобы закэшированный
  ответ первого запроса и все собранные из него записи остались прежними (`ids` не меняются; новые записи проходят
  `add_extra`: существующая запись всегда побеждает при совпадении имени в 50 м). `overpass()` сначала ищет ответ в кэше
  под любым зеркалом и только потом идёт в сеть. `leisure=playground` + `indoor=yes` (8 записей) — теперь `entertainment`
  «Детская площадка в помещении»: `kids_playground` приложение считает уличной и убирает в мороз/смог.
- **Overture**: расширен `TAXONOMY_MAP` (музеи всех видов, планетарий, `indoor_playcenter`, картинг, скалодром,
  мини-гольф, `memorial_site`, `water_feature`, …) и введены **правила по названию** только для «общих корзин»
  (`arts_and_entertainment`, `sports_and_recreation`, `sport_or_fitness_facility`, `party_and_event_planning`, …;
  школы и центры развития исключены): батут/KANGO/«Планета Икс»/квест/боулинг/аквапарк → `entertainment`,
  ТРЦ/торговый дом с `shopping` → `mall`, «музей» → `museum_gallery`. Запись помечается тегом `category_rule=…`,
  `field_sources.category.basis = name_rule:…`; для детских — тег `for_kids=yes` и описание «Детский …».
  Порог confidence 0.7 не менялся. Смена маппинга меняет `taxonomy_map_hash` → стадия перезапрашивает релиз.
- **Координаты Overture** (`coord_quality.py`, только Overture-only записи, OSM не трогается): (1) `collapsed_point` —
  ≥8 записей на одной точке (5 знаков) с несогласованными адресами (на 3 правило срабатывало на реальный ТРЦ и театр);
  (2) `address_far` — улица адреса дальше 2 км от всех остальных записей этой улицы → адрес геокодируется Nominatim
  (адресная часть строки, 1 req/s, кэш); запись отбрасывается, если геокодер тоже ставит адрес дальше 2 км, и остаётся с
  `coord_quality.status = "suspect_unverified"`, если геокодер ничего не нашёл.
- **Wikidata / Wikipedia** (`wiki_places.py` → `wiki_merge.py`): кандидаты из SPARQL (`P131*` + класс P31/P279* из
  `CLASS_MAP`), geosearch ru/en и категорий ru/en (глубина 2); класс определяется по Wikidata, координаты — P625 >
  координаты статьи > Nominatim по названию (порог схожести 0.75); точка должна лежать в полигонах районов. Совпадение
  с существующей записью (одна категория ≤150 м и схожесть ≥60, либо любая категория ≤300 м и ≥75) **не создаёт
  дубль**; уверенное совпадение дописывает Wikidata-QID и выдержку Википедии (`wiki_match.method = wikipedia_list`),
  остальное — новая запись `wikidata/Q…` (`source: "wikidata"`).

## Файлы `data/`, которые collect/ не пишет

| файл | как получен | лицензия | пересборка |
|---|---|---|---|
| `walk_cache.json` | пешие отрезки (расстояние `m`, время `s`, дата `d` = 2026-10-16/17) публичного сервера Valhalla FOSSGIS поверх OSM и форма пути `g` (уличная линия для карты; достроена своим Valhalla скриптом `app/scripts/backfill_shapes.py`); `app/scripts/precompute_walks.py` греет `app/.local/walk_cache.json`, а отслеживаемый снимок в `data/` читает демо-режим (`WALKS_DEMO_PIN`) | ODbL 1.0 (© OpenStreetMap contributors); условия сервиса https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/ (страница `wiki.openstreetmap.org/wiki/FOSSGIS/Server/Policy` — лишь заглушка со ссылкой на них) | необязательна; ~1 запрос/с, уже посчитанное пропускается; нужна сеть |
| `population_proxy.json` | относительный вес жилья по ячейкам 500 м из зданий OSM (Overpass, снимок 2026-10-16); `app/scripts/fetch_population_proxy.py` | ODbL 1.0 (© OpenStreetMap contributors) | необязательна; один запрос Overpass через кэш `collect.net` |
| `demo_llm_cache.json`, `demand_sim.jsonl` (+ `.meta.json`) | записанные ответы ИИ и симуляция спроса (`app/scripts/warm_cache.py`, `simulate_demand.py`); `city_feedback.json` — сид отметок жителей | собственные данные проекта | см. `app/README.md` |

Атрибуция всех источников — `data/ATTRIBUTION.md`.
