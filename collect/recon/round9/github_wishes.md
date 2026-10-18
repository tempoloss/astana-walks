# Round 9 — «Опенсорс форумы, где уже есть пожелания» (GitHub issue-трекеры)

Дата: 2026-10-18. Метод: GitHub Search API (keyless, `/search/issues`), UA `astana-walks-research/0.1 (an8kk.sa@gmail.com)`, ≤1 req/s.
Сырые ответы: `gh_*.json` в этом каталоге. Все нули перепроверены вторым методом (кавычки/кириллица) — directive Main.

Важно про имена репо: `organicmaps/Organic-Maps` не существует (422, см. `gh_organicmaps_Organic_Maps_geo.json`);
реальный — **`organicmaps/organicmaps`** (проверено через `/orgs/organicmaps/repos`). `valhalla-mvf/valhalla` → **`valhalla/valhalla`**.

## 1. Гео-запросы (Astana / Казахстан)

| q= (ровно так) | total_count | сырой файл |
|---|---|---|
| `repo:osmandapp/Osmand astana OR казахстан OR kazakhstan OR almaty OR астана in:title,body` | 3 | gh_osmandapp_Osmand_geo.json |
| `repo:osmandapp/Osmand "astana" in:title,body` | 0 | gh_osmand_astana_re1.json |
| `repo:osmandapp/Osmand "Астана" in:title,body` | 0 | gh_osmand_astana_re2.json |
| `repo:osmandapp/Osmand kazakhstan in:title,body` | 3 | gh_osmand_kazakhstan.json |
| `repo:organicmaps/organicmaps astana OR kazakhstan OR казахстан OR almaty OR астана in:title,body` | 3 | gh_organicmaps_geo.json |
| `repo:organicmaps/organicmaps astana in:title,body` | 1 | gh_organicmaps_astana.json |
| `repo:organicmaps/organicmaps kazakhstan in:title,body` | 2 | gh_organicmaps_kazakhstan.json |
| `repo:StreetComplete/StreetComplete "astana" in:title,body` | 0 | gh_streetcomplete_astana_re1.json |
| `repo:StreetComplete/StreetComplete "Казахстан" OR "kazakhstan" in:title,body` | 0 | gh_streetcomplete_kz_re.json |
| `repo:graphhopper/graphhopper "astana" in:title,body` | 0 | gh_graphhopper_astana_re1.json |
| `repo:graphhopper/graphhopper "Астана" OR "Казахстан" in:title,body` | 0 | gh_graphhopper_kz_re.json |
| `repo:graphhopper/graphhopper "kazakhstan" in:title,body` | 0 | gh_graphhopper_kz_re1.json |
| `repo:valhalla/valhalla "astana" OR "Астана" in:title,body` | 0 | gh_valhalla_astana_re.json |
| `repo:valhalla/valhalla "kazakhstan" OR "Казахстан" OR "almaty" OR "Алматы" in:title,body` | 1 | gh_valhalla_kz_re.json |

Все `total_count: 0` с `search_type: "lexical"` выжили повторную проверку кавычками и кириллицей → **measured dead**.

Единственный valhalla-хит #1972 — ШУМ: `kazakhstan-latest.osm.pbf` в логе списка extract-файлов, не пожелание.

### Итоговые гео-хиты (6 уникальных, 1 из них noise)
- **KZ-wishes/bugs:**
  - organicmaps #6798 «Bilingual map» (2023-12-08, open, rx1, 6 комм.) — двуязычные названия на карте, ru/en; напрямую про kk/ru имена.
  - organicmaps #6736 «House numbers in regions with few alphabets» (2023-11-30, open) — адресация для регионов с «малыми» алфавитами.
  - Osmand #15696 «Add Kazakh language to the map configuration» (2022-11-11, closed) — казахский язык интерфейса/карты.
  - organicmaps #13113 «Route Basel–Istanbul–Astana–Jarkent crashes iPhone…» (2026-07-04, open) — KZ-специфичный баг длинного маршрута через Астану.
- **Noise:** Osmand #8401 (календарные ссылки, KZ упомянут вскользь), #19074 (рендер дорог в степях, desert-слой), valhalla #1972 (лог .pbf).

## 2. Walking-relevant (одиночные термины в title, sort=reactions)

| q= | total | верх |
|---|---|---|
| `repo:valhalla/valhalla "pedestrian" in:title` | 100 | #4419 rx4/23комм, #6094 rx4, #3736 rx2 |
| `repo:valhalla/valhalla "pedestrian routing" in:title,body` | 39 | #4419, #4657, #5085 |
| `repo:graphhopper/graphhopper "walking" OR "pedestrian" in:title` | 33 | #82 rx6 (2013, open), #2932/#3058 crossing |
| `repo:organicmaps/organicmaps pedestrian OR walking OR sidewalks in:title` | 77 | #4147 rx4, #2056 rx4, #8328 rx3 |
| `repo:osmandapp/Osmand "opening hours" in:title` | 101 | #22415 rx9, #2610 rx7, #15464 rx4 |
| `repo:osmandapp/Osmand sidewalk in:title` | 10 | #2567 rx2 foot routing via sidewalks |
| `repo:StreetComplete/StreetComplete sidewalk in:title` | 83 | #5022 rx9 sidewalk overlay |
| `repo:StreetComplete/StreetComplete "street lighting" in:title` | 6 | #5539 rx2, #430 rx2 |

### (a) Желания, релевантные peшему ассистенту в Астане (открытые, с upvotes)
1. valhalla #4419 (2023-11-28, open, rx4, 23 комм.) «Pedestrians appear unable to leave sidewalks, rendering pedestrian routing in cities poorly supported» — **движок прямо в нашем стеке** (app/walks/walking.py).
2. valhalla #6094 (2026-05-20, open, rx4) «Handling different types of pedestrian crossings» — переходы.
3. valhalla #3736 (2022-09-09, open, rx2) «No routing around highway=pedestrian areas» — Хан Шатыр/Баспана.
4. Osmand #22415 (2025-04-23, open, rx9) «Last checked opening hours» — свежесть часов работы POI.
5. Osmand #2610 (2016-05-27, open, rx7) «Support for public holiday in opening hours parser» — праздники KZ (Наурыз и т.д.).
6. Osmand #15464 (2022-10-12, open, rx4) «Smarter handling of opening hours of POIs».
7. organicmaps #4147 (2022-12-24, open, rx4) «Route freely over pedestrian areas»; #2056 (2022-02-08, open, rx4) «Pedestrian navigation improvements»; #8328 (2024-05-29, open, rx3) «Crossing-aware voice directions».
8. StreetComplete #5022 (2023-05-14, open, rx9) «pedestrian point features … sidewalk overlay» — это про сбор sidewalk/lighting-данных (квесты), т.е. источник данных для тротуаров/освещения, а не роутинг.

### (b) KZ-специфичные баги — см. §1 (4 шт.)
### (c) Шум — многотысячные OR-запросы по телу (1905/536/503) без вхождения темы в title.

## 3. Upstream relevance (наш стек)
- **Valhalla — да, смотреть обязательно:** #4419, #6094, #3736, #4657 (open) влияют на ноги наших пеших маршрутов; #6195 (GSoC pedestrian area routing, closed 2026) — работа уже ведётся вверх по течению.
- **GraphHopper — не в стеке** (в app/walks только valhalla; grep подтверждает). #82 area routing rx6 — наблюдать.
- Астана-специфичных открытых issues в valhalla/graphhopper: **0** (перепроверено).

## 4. Лицензирование (проверено по первоисточнику)
https://docs.github.com/en/site-policy/github-terms/github-terms-of-service, раздел **D. User-Generated Content**:
- **D.3 Ownership and License Grants:** «You own Your Content.»
- **D.5 License Grant to Other Users:** «By making a repository public, you grant other Users a nonexclusive, worldwide license to use, display, perform and reproduce (by forking) Your Content through the Service as permitted by GitHub's functionality.»
Вывод: CC BY-SA НЕТ (в отличие от Stack Exchange). Текст issue — © автора, общественная лицензия не даётся. Значит: **в дек только цитата+ссылка, в нашу БД не кладём** — согласуется с уже принятым правилом «quotes-with-link only».
Сырой снимок ToS: gh_tos_raw.html / gh_tos_text.txt.

## Verdict
GitHub-трекеры — **ограниченно пригодный** wishes-канал для дека: Astana-специфичных пожеланий почти нет (6 гео-хитов на 5 репо, из них ~2 wishes), зато есть измеримые upvoted-пожелания по пеому роутингу/часам работы POI/двуязычным картам в трекерах тех же OSS-движков, что мы используем (valhalla #4419, OsmAnd opening-hours rx7–9, Organic Maps bilingual rx1+6 комм., StreetComplete sidewalk rx9). Формулировка для слайда: «те же пожелания уже открыты апстрим-сообществами наших движков» — цитатами+ссылками. Не тянет на отдельный канал мониторинга: реакций мало (<10), цикл медленный.
