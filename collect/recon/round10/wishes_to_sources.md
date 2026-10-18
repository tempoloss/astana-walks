# Раунд 10 — TOP-voted pedestrian wishes из трекеров движков → источники Астаны

Дата: 2026-10-19. База: §19.1/§19.3 (`recon/round9/github_wishes.md`) — по Астане трекеры пусты (0 в OsmAnd/StreetComplete/GraphHopper/Valhalla, 1 не-пожелание в Organic Maps), поэтому раунд строит **поверх**: топ wish'ей по функциональности и их маппинг на уже измеренные источники Астаны.

Метод: GitHub Search API keyless (`/search/issues`, `sort=reactions-%2B1`), UA `astana-walks-research/0.1 (an8kk.sa@gmail.com)`, ≤1 req/3s. Сырые ответы: `recon/round10/w2/*.json` (11 поисков) + точечные GET по номерам. Overpass-пробы: `recon/round10/w2/ast_*_count.json` (overpass-api.de, bbox 51.00–51.30 / 71.15–71.80, снято 2026-10-18/19; зеркало maps.mail.ru в этот день 504).

## Таблица: wish → чем закрывается в Астане → вердикт

| # | wish (repo#issue, реакции) | чем закрывается в Астане | вердикт |
|---|---|---|---|
| 1 | **Пешеходы не могут сойти с тротуаров** — `valhalla/valhalla#4419`, open, rx 4, 23 комм. Свежая проба 2026-10-19: open, updated 2025-01-16, последний комм. andrewharvey 2025-01-16 («pre-processing OSM data to insert additional topology connections is likely the best way»). Движок = наш (`app/walks/walking.py`) | Тротуарная сеть OSM Астаны уже снята: `footway=sidewalk` **2 425** (§18.1, раунд 5). Наша прямая маршрутизация ×1.25 не зависит от апстрим-бага; self-host Valhalla (§14.7-1) — если взлетит pre-processing, примем патч | **МЫ МОЖЕМ** (обход у нас уже есть) — upstream-фикс полезен, но не блокер |
| 2 | **Разные типы пешеходных переходов** — `valhalla/valhalla#6094`, open, rx 4 | OSM `highway=crossing` + `crossing:markings/signals` — теги есть в данных; в Астане дорожная разметка не публикуется отдельно (мёртвые порталы §0), Кozy- DPS `peds_new` = перс. данные, не храним | **НУЖЕН UPSTREAM** (парсер тегов в costing) + мы может дополнить теги переходов через свой вклад в OSM |
| 3 | **Роутинг вокруг pedestrian areas** — `valhalla/valhalla#3736`, open, rx 2; `organicmaps/organicmaps#4147` rx 4 (та же тема) | Хан Шатыр/набережные — `highway=pedestrian` area в OSM Астаны есть; workaround у нас — прямая маршрутизация + GeoJSON-обход | **МЫ МОЖЕМ** (обход) / upstream (для self-host) |
| 4 | **Свежесть часов работы POI** — `osmandapp/Osmand#22415`, open, rx 9; `#2610` (праздники в opening_hours) rx 7; `#15464` rx 4; `organicmaps/organicmaps#4795` (часы с перерывом) rx 8 | Часы — главная дыра продукта (84 %, §6/§14.7-8): Overture/Foursquare полей не имеют, Wikidata `P3025/P8626` в Астане = 0, Wikivoyage даёт +20 часов. «Свежесть» = OSM Notes (в проде: 300 notes, open 7, class `hours` 2, §13.6) + версионные срезы eGov §15.1 | **МЫ МОЖЕМ частично** (notes+версии как «свежесть»), полный фикс — **upstream/нет источника** |
| 5 | **Квест «вода питьевая?»** — `StreetComplete/StreetComplete#549`, **closed** (реализовано), rx 9; dog bowl #6149 open rx 4 | Overpass 2026-10-19: `amenity=drinking_water` в bbox Астаны = **8** узлов; питьевые фонтанчики = 7 (§4, `_geo/op_census.txt`); `amenity=fountain` = **129** (переснято 19.10). Покрытие OSM — мёртвая тема, drinking_water точек почти нет | **МЕРТВАЯ ТЕМА В KZ** (данных ~8-15 на город; фонтаны 129 — не drinking_water) |
| 6 | **Скамейки на остановках / бенч-квесты** — `StreetComplete/StreetComplete#200` (bus stop bench) rx 7, `#1079` rx 5, `#4167`/`#3132` rx 4 — все closed (квесты реализованы) | Overpass 19.10: `amenity=bench` в bbox Астаны = **673** (669 nodes + 4 ways) — comfort-слой, не POI (правило §4). Померено ранее как 669 — совпало | **МЫ МОЖЕМ** (слой комфорта на маршруте, данные есть) |
| 7 | **Больше инфо о туалетах** — `organicmaps/organicmaps#3192`, open, rx 6 | Overpass 19.10: `amenity=toilets` = **47** (19 nodes + 28 ways; перепроверено, round10 `walk_essentials_probe` 2 815 — артефакт битого прогона bg54, не читать); текущая shipped-база — 0 (SELECTORS без toilets, §20.1) | **МЫ МОЖЕМ** (добавить `amenity=toilets` в SELECTORS → +47 POI) |
| 8 | **Sidewalk overlay / пешеходные точечные фичи** — `StreetComplete/StreetComplete#5022`, open, rx 9 | Теги sidewalk/lighting в Астане: `lit` — 953 дороги (~2.7 %), `+363 lit footway` (§18.4); полноценной sidewalk-сети нет (480 из `walk_essentials_probe` — сырой счёт по надписи «streets_sidewalk», не валидирован) | **НУЖЕН UPSTREAM** — собираемый StreetComplete-квест закрыл бы дыру, но сам по себе это источник данных, не wish для нас |
| 9 | **Street lighting квесты** — `StreetComplete/StreetComplete#5539`/`#430`, rx 2 каждая | Спутниковый свет: street-уровень мёртв, районный defensible (§19.4); OSM `street_lamp` = **217** узлов (переснято 19.10, было 0 на mail.ru-зеркале — противоречие снять при след. сборе) | **МЫ МОЖЕМ** (бейдж «освещено» на 953+363 сегментах) / районный VIIRS-слой |
| 10 | **Двуязычная карта kk/ru** — `organicmaps/organicmaps#6798`, open, rx 1, 6 комм. (единственный KZ-близкий hit по §19.1) | RCA-реестр §15.1: 4 032 геонима Астаны (3 016 улиц) с историческими именами (Акмола/Целиноград/Нур-Султан) — это наш алиас-слой, не Organic Maps | **НЕ ПРО НАС** (апстрим-тема Organic Maps) |
| 11 | **Пешеходная навигация (voice/organicmaps)** — `organicmaps/organicmaps#2056` rx 4, `#8328` (crossing-aware voice) rx 3 | Мы не shipping mobile nav; crossing-данные Астаны — как #2 | **НЕ ПРО НАС** / нужен upstream |
| 12 | **Popularity / crowding POI** — прямых wish'ей на crowding в OsmAnd нет (`"popular times" OR crowding OR crowded` in:title,body → 7, верхний #11340 rx 3 «Open Now filter» — про часы, не толпу); соседняя тема — «Live traffic» `organicmaps/organicmaps#10062` rx 8 | Ничего хранимого о посещаемости «сейчас» не существует (§18.5) — Places API без Popular Times, FSQ hours_popular = PAYG | **МЕРТВАЯ ТЕМА В KZ** (легального источника нет) |

## Сводка по вердиктам

- **МЫ МОЖЕМ (данные есть, закрываем сами):** #4419 (обход), #3736/#4147, bench #200/#1079 (673 шт.), toilets #3192 (47 шт.), street lighting #5539/#430 (953+363 lit)
- **НУЖЕН UPSTREAM (наш вклад в OSM + патч движка):** #6094 (crossings), #5022 (sidewalk overlay), #22415/2610/15464/4795 (часы — частично)
- **МЕРТВАЯ ТЕМА В KZ:** #549 (drinking_water — 8 точек), crowding/popularity (нет источника)
- **НЕ ПРО НАС:** #6798 (bilingual Organic Maps), #2056/#8328 (mobile voice nav)

## Цифры Overpass 2026-10-19 (bbox 51.00,71.15,51.30,71.80, overpass-api.de; сырьё `w2/ast_*_count.json`)

| тег | значение |
|---|---|
| `amenity=bench` | 673 (669 nodes + 4 ways) |
| `amenity=toilets` | 47 (19 nodes + 28 ways) |
| `amenity=fountain` | 129 |
| `amenity=drinking_water` | 8 |
| `highway=street_lamp` | 217 |

## Особый пункт: valhalla#4419 — свежая проба 2026-10-19

- `GET api.github.com/repos/valhalla/valhalla/issues/4419` → HTTP 200, **state: open**, created 2023-11-28, updated 2025-01-16, comments 23, reactions +1 = 4, closed_at null, milestone null (сырьё `w2/wishes_gh4419_fresh.json`).
- Последний комментарий 2025-01-16 (andrewharvey): «pre-processing OSM data to insert additional topology connections is likely the best way to handle this».
- Кейс живой, но апстрим не двигался ~21 мес. Для self-host Valhalla — кандидат на собственный pre-process-шаг (вставка топологии sidewalk↔road), а не ожидание патча.
