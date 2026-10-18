# Цифры для слайдов и документов

Файл генерируется `python scripts/make_figures.py` из статистики в `data/`. Не править вручную: исправьте входные файлы или скрипт и пересоберите.

Входы: `data/poi_stats.json`, `data/poi.osm_stats.json`, `data/poi_enriched_stats.json`, `data/coverage_delta.md`.

**Какой датасет что означает.** `poi.json` — замороженный OSM-only вход приложения и эталон «до» (baseline). `poi.osm.json` — пересобранный OSM-снимок; это OSM-часть shipped-базы. `poi.enriched.json` — shipped-база приложения (OSM + Overture + Wikipedia + официальные сайты), датасет по умолчанию в `app/walks/models.py`.

## 1. Размер базы

| набор | POI | источник |
|---|---|---|
| baseline `data/poi.json` (OSM, замороженный вход приложения) | 1 488 | data/poi_stats.json: total |
| OSM-снимок `data/poi.osm.json` (пересбор) | 1 501 | data/poi.osm_stats.json: total |
| shipped `data/poi.enriched.json` (OSM + Overture + Wikipedia + официальные сайты) | 2 294 | data/poi_enriched_stats.json: after.total |
| прирост shipped относительно baseline | 806 | вычислено: shipped − baseline |

## 2. Состав shipped-датасета

| источник записи | записей | доля | источник |
|---|---|---|---|
| только OSM | 1 312 | 57.2% | data/poi_enriched_stats.json: per_source_counts.osm_only |
| OSM + Overture | 189 | 8.2% | data/poi_enriched_stats.json: per_source_counts.osm_and_overture |
| только Overture (категория отображена) | 669 | 29.2% | data/poi_enriched_stats.json: per_source_counts.overture_only |
| только Wikidata / Wikipedia (места без OSM и Overture) | 13 | 0.6% | data/poi_enriched_stats.json: per_source_counts.wikidata_only |
| только официальные сайты (новые места) | 133 | 5.8% | data/poi_enriched_stats.json: per_source_counts.official_site_only |
| только госреестр (ЦОН, gov4c.kz) | 10 | 0.4% | data/poi_enriched_stats.json: per_source_counts.state_registry_only |
| слито записей об одном месте (`collect.dedupe`), корзины выше: OSM + Overture +17, только OSM −21, только Overture −27, только Wikidata −1 | −32 |  | data/poi_enriched_stats.json: duplicates.absorbed_from_bucket |
| **итого** | **2 294** | 100% | шесть строк минус слитые записи |

## 3. POI по категориям

| категория | baseline (poi_stats) | OSM-снимок (poi.osm_stats) | shipped (poi_enriched_stats) | Δ shipped − baseline |
|---|---|---|---|---|
| cafe | 328 | 329 | 580 | +252 |
| restaurant | 176 | 176 | 398 | +222 |
| fast_food | 123 | 123 | 168 | +45 |
| bar_nightlife | 109 | 109 | 243 | +134 |
| museum_gallery | 10 | 10 | 18 | +8 |
| attraction_landmark | 88 | 93 | 115 | +27 |
| viewpoint | 1 | 1 | 1 | +0 |
| park_garden | 177 | 177 | 191 | +14 |
| kids_playground | 336 | 328 | 328 | -8 |
| entertainment | 5 | 14 | 45 | +40 |
| mall | 51 | 51 | 70 | +19 |
| culture_theatre_cinema | 25 | 31 | 44 | +19 |
| coworking_library | 11 | 11 | 18 | +7 |
| sport | 23 | 24 | 36 | +13 |
| transit_station | 25 | 24 | 29 | +4 |
| other | 0 | 0 | 10 | +10 |
| **итого** | **1 488** | **1 501** | **2 294** | **+806** |

Баланс: сумма по категориям равна итогу в каждом наборе (проверено скриптом).

## 4. Атрибуты записей

| метрика | baseline | OSM-снимок | shipped | источник |
|---|---|---|---|---|
| % с часами работы (все записи) | 23.2 | 23.1 | 23.4 | data/poi_stats.json, data/poi.osm_stats.json, data/poi_enriched_stats.json: pct_opening_hours_total |
| % с часами работы (только записи из OSM) | 23.2 | — | 23.1 | data/coverage_delta.md: «OSM-origin records only» |
| % реальное описание (OSM-тег или Wikipedia) | 0.1 | 0.1 | 2.3 | pct_real_description |
| % описание, собранное из тегов (не реальное) | 99.9 | 99.9 | 97.7 | pct_derived_description |
| % с сайтом | 13.1 | 13.1 | 30.0 | pct_website |
| % с телефоном | 12.8 | — | 41.2 | baseline: data/coverage_delta.md «% with phone»; shipped: pct_phone |
| записи с тегом wheelchair | 69 | 69 | — | count_wheelchair_tag |
| имя сгенерировано из категории (name_generated) | 473 | 473 | — | count_name_generated |

Записей с часами: ≈537 из 2 294 в shipped (≈ 347 из 1 501 в OSM-снимке, вычислено из процентов). Часы работы приходят из OSM и (с официальных сайтов) для записей, у которых OSM их не имел; Overture-only записи добавляют в знаменатель, но почти не добавляют часов.

## 5. Описания по источнику (shipped)

| источник описания | записей | доля | источник |
|---|---|---|---|
| OSM-тег description | 2 | 0.1% | data/poi_enriched_stats.json: description_source_counts.osm |
| Wikipedia (extract) | 50 | 2.2% | data/poi_enriched_stats.json: description_source_counts.wikipedia |
| собрано из тегов (derived) | 2 242 | 97.7% | data/poi_enriched_stats.json: description_source_counts.derived |

### Данные официальных сайтов (`collect/sites`)

| показатель | значение | источник |
|---|---|---|
| филиалов с проверенными доказательствами | 435 | official_sites.branches_verified |
| привязано к существующим POI | 133 | official_sites.pois_matched |
| новых POI (первичные координаты на странице сайта) | 133 | official_sites.new_pois |
| часы работы с днями: было → стало | 346 (15.8%) → 514 (22.2%) | official_sites.hours_day_qualified_*, hours_pct_* |
| часы добавлены существующим POI / новым POI | 41 / 127 | official_sites.hours_new_on_* |
| расхождение часов OSM и сайта (в `opening_hours` остаётся OSM) | 31 | official_sites.hours_conflicts |
| часы сайта без дней (не влияют на «открыто / закрыто») | 20 | official_sites.hours_unqualified_pois |
| описание сайта у существующих POI | 14 | official_sites.filled_on_existing |

## 6. Wikidata, Wikipedia и Overture

| показатель | значение | источник |
|---|---|---|
| Wikidata: совпадение по тегу OSM | 29 | data/poi_enriched_stats.json: wikidata_matches_by_method.tag |
| Wikidata: совпадение по SPARQL | 10 | data/poi_enriched_stats.json: wikidata_matches_by_method.sparql |
| Wikidata: совпадение по имени (fuzzy) | 5 | data/poi_enriched_stats.json: wikidata_matches_by_method.fuzzy |
| **Wikidata: всего** | **76** | per_source_counts.with_wikidata |
| Wikipedia-статья у записи | 51 | per_source_counts.with_wikipedia_article |
| Просмотры Wikimedia (популярность) | 24 | per_source_counts.with_popularity_pageviews |
| OSM ∩ Overture, 1:1 | 186 | data/poi_enriched_stats.json: osm_overture_matched |

### Воронка Overture (release 2026-09-23.1, bbox Астаны)

| шаг | значение | источник |
|---|---|---|
| мест в bbox, всего | 8 590 | data/poi_enriched_stats.json: overture.total |
| проходят порог уверенности ≥ 0.7 | 2 802 | overture.passing_cutoff |
| отброшено порогом < 0.7 | 5 788 | overture.dropped_by_cutoff |
| отброшено при сборке (dropped_unusable, из прошедших порог) | 0 | overture.dropped_unusable |
| совпало с OSM 1:1 | 186 | osm_overture_matched |
| Overture-only, категория отображена (добавлено) | 669 | overture.overture_only_added |
| Overture-only, категория other (не добавлено) | 1 914 | overture.overture_only_other_not_added |

Не-POI среди прошедших порог, понижены (по причине): residential_complex 36, historic_site_unverified 14, school_education 1 (всего 51; data/poi_enriched_stats.json: overture.non_poi_demoted).

Понижены из категории (прошедшие порог): attraction_landmark 50, coworking_library 1.

Дубликаты сетей: слиты в запись OSM 3; поглощены уже сопоставленной OSM-записью 1; по совпадению имени: 4 (`overture.chain_duplicates`).

### Доля совпадений с OSM по уверенности Overture

| уверенность | записей | совпало с OSM | доля совпадений |
|---|---|---|---|
| 0.1-0.2 | 10 | 0 | 0.0% |
| 0.2-0.3 | 78 | 2 | 2.6% |
| 0.3-0.4 | 104 | 7 | 6.7% |
| 0.4-0.5 | 160 | 12 | 7.5% |
| 0.5-0.6 | 319 | 13 | 4.1% |
| 0.6-0.7 | 309 | 27 | 8.7% |
| 0.7-0.8 | 334 | 37 | 11.1% |
| 0.8-0.9 | 265 | 41 | 15.5% |
| 0.9-1.0 | 270 | 95 | 35.2% |

Источник: `data/poi_enriched_stats.json: overture.match_rate_by_confidence`. Суммы по корзинам (1 849 записей) не равны числу прошедших порог: корзины охватывают кандидатов, а не только принятые записи; для слайда используйте доли по корзинам, а не абсолютные числа.

## 7. Транспорт

| показатель | значение | источник |
|---|---|---|
| станции LRT «Tarlan Astana» в OSM-снимке | 18 | data/poi.osm_stats.json: count_lrt_stations |
| POI категории transit_station, baseline / OSM-снимок / shipped | 25 / 24 / 29 | категории в трёх файлах статистики |

## 8. Сверка и расхождения

Внутренняя арифметика проверена при генерации (сбой → скрипт завершается с кодом 1). Ниже — сравнение между файлами. Расхождение не скрыто: указаны оба значения и канонический источник.

| проверка | значение A (источник) | значение B (источник) | статус | канон |
|---|---|---|---|---|
| OSM-снимок: total | 1 501 (data/poi.osm_stats.json) | 1 501 (data/coverage_delta.md «OSM POI in the re-collected snapshot») | OK | poi.osm_stats.json |
| Overture-only в категориях | 669 (data/poi_enriched_stats.json per_source_counts) | 669 (data/coverage_delta.md «Overture-only, mapped category») | OK | poi_enriched_stats.json |
| Overture-only: overture.overture_only_added | 669 (data/poi_enriched_stats.json) | 669 (per_source_counts.overture_only) | OK | poi_enriched_stats.json |
| Wikidata-совпадения | 76 (data/poi_enriched_stats.json with_wikidata) | 76 (data/coverage_delta.md «Wikidata matched POI») | OK | poi_enriched_stats.json |
| OSM ∩ Overture 1:1 | 186 (data/poi_enriched_stats.json osm_overture_matched) | 186 (data/coverage_delta.md «OSM ∩ Overture matched») | OK | poi_enriched_stats.json |
| Итого после обогащения (без новых POI с официальных сайтов и из госреестра, до слияния дублей) | 2 183 (data/poi_enriched_stats.json after.total − official_site_only − state_registry_only + merged) | 2 183 (data/coverage_delta.md «total» after (merge)) | OK | data/poi_enriched_stats.json: per_source_counts, duplicates |
| Итого до обогащения | 1 488 (data/poi_stats.json) | 1 488 (data/coverage_delta.md «total» before) | OK | poi_stats.json |
| Итого до обогащения vs OSM-снимок | 1 488 (data/poi_stats.json) | 1 501 (data/poi.osm_stats.json) | РАСХОЖДЕНИЕ | baseline: poi_stats.json; OSM-часть shipped: poi.osm_stats.json |
| Категории до/после (16 строк) | совпадает (data/coverage_delta.md) | совпадает (data/poi_stats.json / data/poi_enriched_stats.json) | OK | poi_stats.json, poi_enriched_stats.json |

Арифметика, проверенная при генерации (все OK, иначе скрипт не завершился бы):

- shipped = OSM-only + OSM+Overture + Overture-only + Wikidata-only + только официальные сайты + только госреестр (корзины стадий сбора) − слитые записи: 1 312 + 189 + 669 + 13 + 133 + 10 − 32 = 2 294 (корзины при слиянии: OSM + Overture +17, только OSM −21, только Overture −27, только Wikidata −1);
- OSM-часть shipped = OSM-снимок: 1 312 + 189 = 1 501;
- чистый прирост = Overture-only + Wikidata-only + официальные сайты + госреестр + (OSM-снимок − baseline) − слитые записи: 806 = 669 + 13 + 133 + 10 + (13) − 32;
- OSM+Overture (корзины стадий сбора) = 1:1 + слияния сетей: 189 = 186 + 3; из них 17 карточек после слияния дублей несут ещё и Overture-ид поглощённой записи;
- слито записей об одном месте: 32 (attraction_landmark — 12, culture_theatre_cinema — 1, mall — 5, museum_gallery — 7, park_garden — 7);
- Overture: всего − отброшено порогом = прошедшие: 8 590 − 5 788 = 2 802.

- baseline (`poi.json`, 1 488) и OSM-снимок пересбора (1 501) различаются по категориям: cafe: 328 vs 329; attraction_landmark: 88 vs 93; kids_playground: 336 vs 328; entertainment: 5 vs 14; culture_theatre_cinema: 25 vs 31; sport: 23 vs 24; transit_station: 25 vs 24. Канон для «до» — `poi_stats.json` (замороженный вход приложения); для OSM-части shipped — `poi.osm_stats.json`.
- чистый прирост 806 ≠ Overture-only 669: в нём ещё 13 мест только из Wikidata / Wikipedia, 133 мест только с официальных сайтов и 13 — добавки OSM-снимка пересбора относительно baseline (второй запрос Overpass и расхождение снимков). В слайдах прирост писать с этой расшифровкой.

## 9. Вывод для слайда

- База: 2 294 POI в Астане (OSM + Overture + Wikipedia + официальные сайты) против 1 488 в OSM-only baseline.
- Часы работы: 23.4% записей по всей базе; у записей из OSM — 23.1%; официальные сайты добавили часы с днями в 168 записей (было 15.8%, стало 22.2%).
- Реальные описания (OSM-тег или Wikipedia): 2.3% против 0.1% в baseline.
- Сайт: 30.0% (было 13.1%); телефон: 41.2% (было 12.8%).

