## Атрибуция: что изменили определения, код и данные

Между замером `a90279c` и текущим деревом изменилось сразу три вещи: определения метрик (`eval/metrics.py`: оракул часов `poi_hours`, правило 24/7 в праздник, см. «Определения метрик» ниже), код системы (раунды fuzz, `split` и `conflict` в часах) и набор `poi.enriched` (2183 → 2314 мест, часы с официальных сайтов). Четыре колонки их разделяют: **1** — замер как есть; **2** — те же ответы (прогоны `a90279c`), оценённые определениями сейчас на наборе до обогащения; **3** — текущий код на наборе до обогащения (`git show 6a8cbc9:data/poi.enriched.json`, офлайн, метка `preswap`); **4** — текущий код и набор. Вклад определений = 2 − 1, кода = 3 − 2, данных = 4 − 3. Набор `poi.json` обогащением не менялся (файл тот же), для него различается только код; в таблицу он не входит. Таблица строится из прогонов и git, вручную не правится.

Источник: git `54815fd+uncommitted`, 18.10.2026 17:32. Раздел считается отдельной командой `cd app && uv run poe eval-attribution` (ей нужна git-история с коммитами `a90279c` и `6a8cbc9`); обычный `poe eval` его не пересчитывает, а вставляет этот файл как есть. Отпечаток текущих прогонов (колонка 4) `176403514827ce8e`: если прогоны изменятся, `canonical.md` пометит раздел устаревшим.

| набор | метрика | 1 до, как измерено | 2 до, определения сейчас | 3 код сейчас, данные до (2183) | 4 код и данные сейчас (2314) | вклад определений | вклад кода | вклад данных |
|---|---|---|---|---|---|---|---|---|
| main (41) | кейсов без нарушений | 100.0% | 100.0% | 97.6% | 100.0% | +0.0 п.п. | -2.4 п.п. | +2.4 п.п. |
| main (41) | constraint_ok_rate | 100.0% | 100.0% | 99.2% | 100.0% | +0.0 п.п. | -0.8 п.п. | +0.8 п.п. |
| main (41) | coverage | 100.0% | 100.0% | 100.0% | 100.0% | +0.0 п.п. | +0.0 п.п. | +0.0 п.п. |
| holdout (20) | кейсов без нарушений | 55.0% | 55.0% | 60.0% | 60.0% | +0.0 п.п. | +5.0 п.п. | +0.0 п.п. |
| holdout (20) | constraint_ok_rate | 79.7% | 79.7% | 83.3% | 77.6% | +0.0 п.п. | +3.6 п.п. | -5.7 п.п. |
| holdout (20) | coverage | 85.0% | 85.0% | 85.0% | 80.0% | +0.0 п.п. | +0.0 п.п. | -5.0 п.п. |
| holdout2 (24) | кейсов без нарушений | 33.3% | 33.3% | 33.3% | 33.3% | +0.0 п.п. | +0.0 п.п. | +0.0 п.п. |
| holdout2 (24) | constraint_ok_rate | 84.3% | 84.3% | 87.1% | 84.3% | +0.0 п.п. | +2.8 п.п. | -2.8 п.п. |
| holdout2 (24) | coverage | 37.5% | 37.5% | 37.5% | 37.5% | +0.0 п.п. | +0.0 п.п. | +0.0 п.п. |
| holdout3 (24) | кейсов без нарушений | 58.3% | 58.3% | 58.3% | 58.3% | +0.0 п.п. | +0.0 п.п. | +0.0 п.п. |
| holdout3 (24) | constraint_ok_rate | 78.8% | 78.8% | 78.8% | 78.8% | +0.0 п.п. | +0.0 п.п. | +0.0 п.п. |
| holdout3 (24) | coverage | 87.5% | 87.5% | 91.7% | 91.7% | +0.0 п.п. | +4.2 п.п. | +0.0 п.п. |
| abstain (8) | honest_abstain_rate | 100.0% | 100.0% | 100.0% | 100.0% | +0.0 п.п. | +0.0 п.п. | +0.0 п.п. |
| abstain (8) | constraint_ok_rate | 100.0% | 100.0% | 100.0% | 100.0% | +0.0 п.п. | +0.0 п.п. | +0.0 п.п. |

Кейсы, у которых результат отличается между четырьмя колонками (8). «Определения» — отличие колонок 1 и 2 (те же ответы, та же база), «код» — 2 и 3 (одна база и одни определения), «данные» — 3 и 4 (один код и одни определения).

| набор | кейс | 1 | 2 | 3 | 4 | причина |
|---|---|---|---|---|---|---|
| main | `khan-eve-cold-kids` | ✅ | ✅ | ❌ category_not_allowed | ✅ | код (набор мест изменился, top-1 тот же); данные (у «Fame City Entertainment Centre» изменились часы; у «Le Pain Quotidien» изменились часы) |
| holdout | `h02-nurly-fri-train` | ❌ category_forbidden, category_not_allowed, walk_too_long | ❌ category_forbidden, category_not_allowed, walk_too_long | ❌ walk_too_long | ❌ category_forbidden, category_not_allowed, walk_too_long | код (top-1: Музей истории железных дорог Казахстана → Jibek Joly); данные (новое место «Coffee BOOM, Ахмет Байтұрсынов көшесі, 32»; «Музей истории железных дорог Казахстана» вошло в ответ (в данных то же место)) |
| holdout | `h06-kenesary-sat-first-time` | ❌ walk_too_long | ❌ walk_too_long | ❌ walk_too_long | ✅ | данные (у «Музей первого президента РК Н. А. Назарбаева» изменились часы) |
| holdout | `h13-nurly-tue-late-hungry` | ❌ category_not_allowed | ❌ category_not_allowed | ✅ | ❌ category_not_allowed | код (top-1: Nurlyzhol_vokzaly → Jibek Joly); данные (новое место «Coffee BOOM, Ахмет Байтұрсынов көшесі, 32»; «Nurlyzhol_vokzaly» вошло в ответ (в данных то же место)) |
| holdout2 | `h2-05-piramida-tourist-hour` | ❌ category_forbidden, category_not_allowed, over_budget, walk_too_long | ❌ category_forbidden, category_not_allowed, over_budget, walk_too_long | ❌ over_budget | ❌ over_budget, walk_too_long | код (top-1: Italio → Barista); данные (у «Национальный музей Республики Казахстан» изменились часы; новое место «Happy Cake») |
| holdout3 | `h3-09` | ❌ no_recs | ❌ no_recs | ❌ over_budget, walk_too_long | ❌ over_budget, walk_too_long | код (top-1: — → Механик) |
| holdout3 | `h3-21` | ❌ no_recs | ❌ no_recs | ❌ over_budget, walk_too_long | ❌ over_budget, walk_too_long | код (top-1: — → Детская площадка (улица Колсай)) |
| holdout3 | `h3-24` | ❌ category_forbidden, category_not_allowed, walk_too_long | ❌ category_forbidden, category_not_allowed, walk_too_long | ❌ category_not_allowed | ❌ category_not_allowed | код (top-1: Президентский парк (Нур-Султан) → Golpas) |
