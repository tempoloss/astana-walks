# Культурные учреждения и достопримечательности без часов — инвентарь и сбор первичных фактов

Снимок 2026-10-17, `data/poi.enriched.json` (2326 POI). Генератор: `uv run python -m collect.sites.culture_inventory`
(офлайн, снапшоты в `collect/sites/snapshots/`); выход: `inventory_culture.json` + `partitions_culture/p1..p3.json`.
Домены, отданные другим партициям (`data/sites/inventory.json` → `partitions/p1..p6`), исключены (кроме фактов этой
ветки — они помечены `status: collected`). Собрано: e-museum.kz (WP-REST коллектор), akorda.kz, museumgold.kz →
`data/sites/facts/`; в датасете: `price_text` + `hours_unqualified` трёх музеев. Часы реестра без дней недели —
только `hours_unqualified` (день-квалифицированных этот источник не даёт).

## 1. Замер: доля день-квалифицированных часов по категориям

| категория | POI | с `opening_hours` | доля |
|---|---:|---:|---:|
| museum_gallery | 25 | 2 | 8.0 % |
| culture_theatre_cinema | 45 | 8 | 17.8 % |
| attraction_landmark | 127 | 3 | 2.4 % |
| viewpoint | 1 | 0 | 0.0 % |
| coworking_library | 18 | 8 | 44.4 % |
| park_garden | 198 | 2 | 1.0 % |
| entertainment | 45 | 3 | 6.7 % |
| kids_playground | 328 | 1 | 0.3 % |
| **итого 8 категорий** | **787** | **27** | **3.4 %** |

По всем категориям — `data/poi_enriched_stats.json`; худшие по доле: kids_playground 0.3 %, park_garden 1.0 %,
attraction_landmark 2.4 %.

## 2. Проверка утверждений

- **«POI с сайтом, но без часов = 320» — подтверждено**: 692 POI с непустым `website`, из них 320 без
  день-квалифицированных `opening_hours` (по категориям: restaurant 103, cafe 64, bar_nightlife 46, fast_food 19,
  mall 18, culture_theatre_cinema 18, entertainment 15, attraction_landmark 12, museum_gallery 9, sport 8,
  coworking_library 3, park_garden 3, transit_station 2 — совпадает с разведкой round7).
- **«museum_gallery ~8 %» — подтверждено** (8.0 %, 2/25); **«attraction_landmark ~2.4 %» — подтверждено** (3/127).
- **«~150 некцепных учреждений» — опровергнуто** при любых прочтениях: POI 8 культурных категорий без
  день-квалифицированных часов и с краулируемым доменом = **60** (все 53 домена уже в facts/partitions);
  + 16 с `wikidata=Q…` без сайта → P856 даёт 3 новых домена; + e-museum-карточки. Максимум достижимого пула ~76–80
  POI, а не 150. Ближайшее число 150 в данных не воспроизводится.
- **e-museum.kz «WordPress REST, Астана = 4 музея, work_hours + ticket_price заполнены» — подтверждено с уточнением**:
  `GET https://e-museum.kz/wp-json/wp/v2/museum?region=3952&lang=ru` → 5 уникальных карточек (keyless, HTTP 200,
  снято 2026-10-17 в `collect/sites/snapshots/e-museum_region3952_2026-10-17.json`); 4 музея `addresscity = Астана қаласы`
  (Нацмузей, Сейфуллин, ВИМ ВС РК, «Бозоқ») + 1 утечка фильтра — «Алжир» (`Ақмол ауылы`, Акмолинский район).
  У всех 5 заполнены `work_hours` и `ticket_price`. `/wp-json/wp/v2/region` → «г. Астана» count=15 (5 × 3 языка).

## 3. e-museum.kz: карточки → факты датасета (собрано)

Коллектор `collect/sites/crawlers/e-museum.kz.py` читает REST-эндпоинт; сниппеты — дословные подстроки сырого
JSON (с `\uXXXX`-escape), card URL = evidence URL. Карточки без координат — привязка к POI по имени + адресу
(`register_name_address`, join не меняет день-квалифицированные часы сайта на бездневные часы реестра; поля
реестра, которых у сайта нет, добавляются). В датасет вошли `price_text` и `hours_unqualified` (needs_days):

| музей | карточка | POI | что дало |
|---|---|---|---|
| Нацмузей РК | `…/68da379b4b4fb9d59-ru/` | node/4894937300 | `price_text` 1000 тг. (часы — свои, Tu-Su из nmrk.kz) |
| Музей Сакена Сейфуллина | `…/68da37a0228ab7ad4-ru/` | way/240376692 | `price_text` 500 тг + `hours_unqualified` |
| ВИМ ВС РК | `…/68da379da9894247d-ru/` | overture/d2f834c2… | `price_text` 500 тг. + `hours_unqualified`; дубли way/240391776, overture/7972273c…, way/1239171353 — другие POI того же места, не подключены |
| «Бозоқ» | `…/68da37a2c72b30113-ru/` | node/11968737470 (Городище Бозок) | не подключено: имя карточки ↔ «Городище Бозок» = 38 < 40; поле `site` карточки даёт домен **bozok.kz** (allowed) — открытая цель |
| «Алжир» | `…/68da37ac132046063-ru/` | — | Ақмол ауылы — не Астана (утечка region=3952); отброшен коллектором по city |

## 4. akorda.kz, museumgold.kz (собрано, фактов нет)

- **akorda.kz** (P856 Q413579, `Allow: /`): сайт Президента публикует только «График приёма граждан»
  Администрации — служебные часы приёма, не посещение резиденции; по правилам `collect/sites` административные
  часы в `opening_hours` не попадают ⇒ запись фактов пустая, вердикт в notes.
- **museumgold.kz** (P856 Q4146879, `Allow: /`): домен припаркован (заглушка регистратора, «Новый сайт успешно
  создан…», HTTP 503 на повторных запросах) — сайта музея нет ⇒ пустая запись, вердикт в notes.

## 5. robots.txt по доменам (снято 2026-10-17, UA `astana-walks/0.1 (…)`; снапшот `collect/sites/snapshots/robots_culture_2026-10-17.json`)

| домен | вердикт |
|---|---|
| e-museum.kz | allowed — только `Disallow: /wp-admin/`, REST открыт |
| akorda.kz | allowed — `User-agent: * Allow: /` |
| museumgold.kz | allowed — `User-agent: * Allow: /` |
| bozok.kz | allowed — только `Disallow: /wp-admin/`, sitemap открыт |
| museum-alzhir.kz | **denied** — robots.txt отдаёт 403 (Cloudflare) |
| astanamuseums.kz | unreachable — connect timeout (поле `site` карточки Сейфуллина) |
| botsad-nursultan.kz | unreachable — DNS не резолвится (P856; OSM-домен POI astanabotsad.kz уже в partitions) |

## 6. Итоговые счётчики

- Culture-POI всего: **787**; без день-квалифицированных часов: **760**.
- Доменов в инвентаре: **7**, POI в них: **10**; из них `collected` (факты в `data/sites/facts/`): **3**
  (e-museum.kz 5 POI, akorda.kz 1, museumgold.kz 1); `open` (следующий краулинг): **1** (bozok.kz, 1 POI);
  `dead`: **2** (astanamuseums.kz, botsad-nursultan.kz); `denied`: **1** (museum-alzhir.kz, 0 POI).
- robots: allowed **4**, denied **1**, unreachable **2** (`counts.robots` в `inventory_culture.json`).
- Партиции (`partitions_culture/p1..p3.json`, вес = 1 домен + 1 за POI, раздача «тяжёлый → самый лёгкий»):
  p1 — e-museum.kz (5 POI); p2 — akorda.kz, botsad-nursultan.kz, museumgold.kz (3 POI);
  p3 — astanamuseums.kz, bozok.kz, museum-alzhir.kz (2 POI).
- Датасет до → после: `price_text` 0 → **3** POI; `hours_unqualified` 18 → **20**; день-квалифицированные часы
  без изменений (реестр их не даёт).

## Лицензии/условия

- Wikidata P856: CC0-1.0 (`collect/wiki_enrich.py::LICENSES`), запрос `wbgetentities` 2026-10-17,
  `collect/sites/snapshots/wikidata_p856_targets_2026-10-17.json` (24 QID, 10 с P856, 3 новых домена).
- e-museum.kz: страницы `terms`/ToS нет (`/ru/about/` прочитан целиком — только проза; footer «© Музеи Казахстана»);
  robots/sitemap/REST открыты, хранение фактов + url + snapshot_date с атрибуцией портала — как в round7-вердикте.
  Данные карточек ведут сами музеи (Министерство культуры РК).
- akorda.kz / bozok.kz / museumgold.kz: robots открыты; лицензионных страниц не публиковалось — факты с собственных
  сайтов учреждения храним с evidence по правилам `collect/sites/README.md`.
