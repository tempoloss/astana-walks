# eGov data.egov.kz full-catalogue sweep — 2026-10-17

**Probed 3944 / 3944 published apiUris (100% of the catalogue).** Catalogue enumerated keyless at `https://data.egov.kz/datasets/getdatasetsre?page=<N>&count=10&byGovAgencyId=&categoryId=&statusType=&datasetSortSelect=&status=PUBLISHED` (395 pages; **the five empty params are mandatory — `?page=1&count=10&status=PUBLISHED` returns HTTP 500**). Each apiUri got an `api/detailed/<uri>` probe + a `datasets/exportjson?index=<uri>&from=1&count=100` fallback. Cache: `_geo/egov_catalog.jsonl` (3944), `_geo/egov_sweep.jsonl` (3944), slices in `_geo/astana_slice_final.json`.

Outcome classes: **2309 datasets with rows**, 626 empty (`{"data":[],"totalCount":0}`), 641 HTTP 404, 368 HTTP 456 (empty body — schema-only, no servable data).

**§15.1 version rule validated at catalogue scale, with a correction**: 2294 of the 2309 data-carrying datasets return **0 bare** and serve rows only through `exportjson` **without** a `version` param. **0 datasets needed `/vN`** — even `sporttyk_keshender_turaly_dere1` (currentVersion='v14') serves identical rows bare via exportjson; `api/detailed/<uri>/v14` works too but `currentVersion` HTML-scraping (5 s/page) is never required. So the operative keyless rule is: `api/detailed` for the fast totalCount, `exportjson?index=&from=&count=` for data and true counts (100 rows/page, hard cap; verified by paging `state_schools` to exhaustion: exactly 7094 rows, page 7101+ empty).

Licence: **no licence string of any kind** in any of the 3944 catalogue records or getmeta payloads (the 90 «лицензия» mentions are dataset *subject matter*, e.g. issued-licenses registers). Only legal basis is the KZ open-data regime (free reuse, no attribution formula) — quoted in recon round 4 from `data.egov.kz/pages/faq`.

## Ranked list A — datasets carrying COORDINATES (113 with lat/lon-ish field; Astana-verified ones first)

| # | apiUri | exact rows (measured) | Astana rows (verified) | how filtered |
|---|---|---|---|---|
| 1 | `state_schools` (АО НИТ, mod 2026-04-27) | **7094** | **106** (104 inside city bbox 51.0–51.3/71.2–71.6) | `region_nam == "г.Астана"` — admin field, no token-false-positives |
| 2 | `private_schools` (АО НИТ, 2026-04-27) | 717 | **64** (all in bbox) | same |
| 3 | `higher_education_org1` (АО НИТ, 2026-04-27) | 132 | **23** (all in bbox) | same |
| 4 | `ps_centers` (ЦОН, Мин-во AI, 2026-08-06) | 555 | **11** | `Region` contains `710000000; Г.АСТАНА` |
| 5 | `diagnostic_inspection_centers` (техосмотр) | totalCount 355 bare, but exportjson pull = **0 rows** → schema+count, no data | 0 | — |
| 6-20 | Акимат Акмолинской обл. family (~20 sets): `konak_uileri` (гостиницы, 66), `sport_keshenderi_turaly_derekt` (спорт, 51), `madeniet_mekemeleri_sarailar2` (культура, 249, **Геопозиция + режим работы**), `perzenthanalary`, `dispanserleri`, `avtovokzal_turaly__derekter`, `auezhai_turaly__derekter`, `production_of_meat2` (78), `tauar_ondirushi_kasiporyndar` (80), `gazben_kamsyzdandyru_obektile` (32), `sumen_kamsyzdandyru_obektiler5/7`, `mektepke_deiingi_bilim_beru_ui1` (47), `balalar_uileri`, `akmola_oblysy_karttar_uiler_tu`… | 3–249 each | **0** — zero Astana-token rows in culture/sport sets; the 3 «Астана» hits in `konak_uileri` are трасса Астана-Петропавловск false positives (verified `district_/_city_ru`=Шортанды ауданы) | full-row token scan |
| 21-45 | Акимат ВКО family (`*_vko`, 25 sets): `pgso_vko` спорт 100+, `prmo_vko`, `poak_vko`, `psio_vko`, `posi_vko`, `soov_vko` 54+, `dosiki_vko` 68+, `doszhd_vko` 60+, `gpuk_vko` культура 32+, `ipf_vko` фонтаны 7… | 4–100+ each | 0 | fields `long`/`geo_coordi`-style |
| 46+ | Кызылординская (`emkhanalar`, `aurukhanalar`, `gibadat_gimarattary1` 23…), Карагандинская (`t*`), Жамбылская `culture30`, Мангистауская, БҚО, Абайская — same schema family | 1–100+ | 0 | — |
| + | `tirkelgen_dini_birlestikteri_z` / `dini_imarattary` (Акмола, культовые сооружения, 100+ pages, mod 2026-10-01), `reestr_zemuchastkov6` (МСХ, 100+, 2026-10-12), `koliktik_bakylau_beketterinde_1` (Минтранс, 100+, 2026-10-14) | 100+ | 0 (регион Акмола) | — |

**Sum of new Astana POIs with real lat/lon: 204** (106 schools + 64 private schools + 23 universities + 11 ЦОН).

## Ranked list B — datasets carrying OPENING-HOURS fields (80 hits; all regional except one)

| apiUri | agency | rows | real hours? |
|---|---|---|---|
| `sporttyk_keshender_turaly_dere1` | **Акимат города Астана** (№730) | 7 | **YES — `rrk`/`rrr` (режим работы)**, e.g. «08:30-18:00». The only Astana hours source on the whole portal |
| `nur-sultan_kalasy_boiynsha_isk` (№124) | Акимат г. Астана | 8 | **NO** — `ptrurrk` is object *type* («Спортивный комплекс»), not hours (regex false positive, corrected) |
| `pgso_vko`, `gpuk_vko`, `pgp_vko`, `pgd_vko`, `grd_vko`, `pgdi_vko`, `psio_vko`, `posi_vko`, `popp_vko` (+9 more `*_vko`) | Акимат ВКО | 5–100+ | YES (` режим работы`-shaped fields), Восточный Казахстан only |
| `t562` (спорт 46+), `t212` (поликлиники 45+), `t555` (культура 31+), `t202`, `t263`, `t12` | Акимат Карагандинской обл. | 7–63 | YES, Караганда only |
| `madeniet_mekemeleri_sarailar2` (культура, Геопозиция + режим работы) | Акимат Акмолинской обл. | 249 | YES — but **0 Astana rows** (checked all 249) |
| БКО (`batys_kazakstan_oblysynyn_*` ~10), Алматинская singles (`msoc_museum_of_applied_arts_n`, `gkkp_gallery_of_fine_arts`…), Жетісу | регион. | 1–34 | YES, региональные |

**Conclusion for hole #1 (opening_hours): museums/theatres/culture hours for Astana do NOT exist on data.egov.kz at catalogue scale. Only #730 спорт (7 objects) fills hours; fill culture via OSM/Wikidata.**

## Per-dataset table (top rows, all live-verified; DATA-verified unless marked SCHEMA-only)

| source | endpoint (exact) | licence + verbatim quote + URL fetched | fields (row 0) | live proof (HTTP + snippet/count) | Astana yield | verdict |
|---|---|---|---|---|---|---|
| Государственные школы (АО НИТ) | `https://data.egov.kz/datasets/exportjson?index=state_schools&from=1&count=100` (+ `api/detailed/state_schools` bare → 0) | лицензия: не указана; record keys = `id,apiUri,nameRu,descriptionRu,keyWords,govAgency,owner,categories,status,createdDate,modifiedDate,views,downloads` (no licence field); basis: KZ open-data regime, `data.egov.kz/pages/faq` | `area_name,district_i,district_n,address,student_co,region_id,region_nam,area_id,sdu_load_i,education_,establish_,geo_coordi,lat,long,id` | HTTP 200, paged to **7094** exact; verbatim row: `{"address":"Алии Молдагуловой 35","region_nam":"г.Астана","district_n":"район Сарыарка","lat":"51.187232675730996","long":"71.4182932828207","education_":"ОСО",...}` | **106 школ с lat/lon, 104 в bbox города** | **STORE — biggest win: fills schools category with geodata** |
| Частные школы | `…exportjson?index=private_schools&from=1&count=100` | same (не указана) | same schema | HTTP 200, 717 rows | **64** | **STORE** |
| ВУЗы | `…exportjson?index=higher_education_org1&from=1&count=100` | same | same | HTTP 200, 132 rows | **23** | **STORE** |
| ЦОН (ps_centers) | `…exportjson?index=ps_centers&from=1&count=100` | same | `NameKaz,NameRus,ShortAddressKaz,AddressKaz,geoposition,TaxStructure,Region,Code,ModifiedDate…` | HTTP 200, 555 rows; verbatim: `{"NameRus":"…Нур-Султана…филиала…","geoposition":"51.2075,71.318056","Region":"710000000; Г.АСТАНА"}` | **11** (филиалы ЦОН в Астане) | STORE (minor — ЦОН уже в данных? перепроверить дедупликацию) |
| №730 спорт объекты | `…exportjson?index=sporttyk_keshender_turaly_dere1&from=1&count=100` (bare `api/detailed` → 0; `/v14` тоже работает) | same | `nsksk/nsksr, mr/mk, rrr/rrk (режим работы), vsk/vsr, ktk/ktr, fior/fiork, id` | HTTP 200, **7 rows**; verbatim: `{"nsksr":"ГККП «Ледовый дворец «Алау»…","mr":"г.Астана, пр.Кабанбай батыра, 47",...}` | **7 спорт-объектов с режимом работы, без координат** | **STORE (hours)** |
| Центры техосмотра | `api/detailed/diagnostic_inspection_centers` → `{"totalCount":355,...}` | same | — | bare 200 totalCount 355, **но exportjson → 0 rows** | 0 | **SCHEMA-only, no data** |
| Учреждения культуры (Акмола) | `…exportjson?index=madeniet_mekemeleri_sarailar2&from=1&count=100` | same | name kk/ru, услуги, Геопозиция, адрес, режим работы, тел, email, сайт | HTTP 200, **249 rows, 0 строк с токеном Астана** | 0 | **DEAD for Astana** (живой отрицательный результат: аналога для города нет) |
| Туристские маршруты Астаны | `…exportjson?index=nur-sultan_kalasynyn__turistik&from=1&count=100` | same | `naimenovanie_turmarshruta_rus/kaz, naimenovanie_regiona_rus, otchetnyi_period_rus` | HTTP 200, **62 rows**; verbatim: `{"naimenovanie_turmarshruta_rus":"\"Столичный колейдоскоп\"","naimenovanie_regiona_rus":"город Астана","otchetnyi_period_rus":"2025 год"}` | 62 названий маршрутов, без точек/часов | RUNTIME-текст / контекст (маршрут-имена для RAG) |
| Фонтаны | `…exportjson?index=103_informaciya_po_fontanam_g&from=1&count=100` | same | счётчики по районам | HTTP 200, 6 rows (район Алмата=6, Нура=7 за 2025) | агрегаты, не POI | DEAD для POI |
| 52 набора акимата Астаны (весь срез byGovAgencyId=AVUvu_Wu99eXTcgzf9td) | как выше, `…/api/detailed/<uri>` → 0 → `exportjson` | same | name/address/phone schemas, 3–19 полей | **50/52 с данными** (2 без: `astana_kalasynyn_perzenthana`, `opendata-api-uri364`); **0/52 с координатами — подтверждено на новом движке**; часы только №730 | см. выше | name+address-регистры; STORE точечно |

All endpoints above fetched 2026-10-17 keyless with `User-Agent` + `Accept: application/json`.

## Wins
- **Full mechanical sweep done: 3944/3944 probed, zero guessing.** 2309 live datasets, every one classified by field presence.
- **+204 Астанских POI с lat/lon** (школы 106, частные школы 64, вузы 23, ЦОН 11) — координатная категория, которой на портале раньше не видели. Все строки с валидированным admin-полем (`region_nam`/`Region`), 104/106 школ в city-bbox.
- **Ключевой механический факт:** `/vN`-скрейпинг не нужен; всё решает `exportjson` без version. Это удешевляет будущие проходы в ~5 раз (нет 5-секундной HTML-страницы на набор).
- Честный негатив: координаты в еGov существуют только у НИТ (школы), ЦОН и региональных акиматов (Акмола/ВКО/Кызылорда/Караганда). Ни один набор акимата Астаны не имеет координат; часы — только №730 спорт.
- HTTP-коды как сигнал: 456 = «схема есть, данных нет» (368 наборов), 404 = 641, 0 bare = почти всегда решается exportjson.

## Dead / rejected + why
- **diagnostic_inspection_centers** — totalCount 355 bare, но экспорт пуст: SCHEMA-only.
- **madeniet_mekemeleri_sarailar2 / konak_uileri / sport_keshenderi_turaly_derekt** (Акмола) — 0 Астанских объектов; «Астана» в адресах = трассы.
- **Все 25 наборов `*_vko`** (ВКО), ~10 `batys_*` (БҚО), `t*` (Караганда), Кызылорда, Жамбыл — координаты/часы есть, но чужие регионы; не граница Астаны.
- **641 × HTTP404 и 368 × HTTP456** — битые/пустые публикации, в оборот не брать.
- **nur-sultan_kalasy_boiynsha_isk (№124)** — `ptrurrk` не часы (тип объекта), из списка часов исключён.

## Unverified leads
- `tirkelgen_dini_birlestikteri_z`/`dini_imarattary` (культовые сооружения Акмолинской обл., 100+ страниц, обновлены 2026-10-01) — не проверено, есть ли Астана в этих 100+ (у Астаны отдельный `759_list_of_religious_buildin` на 32 строки — вероятно, дубль).
- `koliktik_bakylau_beketterinde_1` (Минтранс, посты контроля, 100+, 2026-10-14) — координаты есть, но не проверено, покрывает ли трассы вокруг Астаны.
- `zholaushylardy_tasymaldau_bas3` (Центр упр. пассажирскими перевозками, Талдыкорган) — 1 строка с гео-полем; транспортных наборов Астаны на портале нет, подтверждено.
- Точный экстент страниц «100+» для `*_vko`-семейства не пейджирован (счётчик = число выкачанных страниц × 100).