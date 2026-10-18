# Оценка: `poi`, режим `offline`

Набор кейсов: holdout. Кейсов: 20, рекомендаций: 51.
Прогон: метка `offline`, режим `offline`, 20 записей, данные `data/poi.json`, git `9fbe2fc`, 2026-10-18T21:56:19+05:00.

| метрика | значение |
|---|---|
| кейсов | 20 |
| hallucinated_poi (должно быть 0) | 0 |
| constraint_ok_rate (рекомендации без нарушений) | 76.5% |
| кейсов без единого нарушения | 50.0% |
| honest_unknown_rate (кейсы) | 100.0% |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% |
| coverage (≥1 рекомендация проходит все ограничения) | 80.0% |
| diversity (нет дублей сети среди рекомендаций) | 100.0% |
| top-1 без нарушений ограничений | 75.0% |
| top-1 с подтверждённым «открыто» | 50.0% |
| доля рекомендаций с неизвестными часами | 64.7% |
| доля рекомендаций не из OSM-записей | 0.0% |
| средняя дорога до рекомендации, мин | 7.8 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 33.3% |
| … за счёт расширения радиуса (radius_factor > 1) | 2.0% |
| … за счёт другой категории (back-fill) | 25.5% |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 5.9% |
| padding: кейсы хотя бы с одной такой рекомендацией | 55.0% |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 8 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 27 мс |
| latency ответа ИИ, медиана | н/п |
| latency ответа ИИ, p90 | н/п |
| honest_unknown_rate по рекомендациям | 100.0% |
| Wi-Fi/розетка есть в данных у рекомендаций кейсов «розетка» | 0.0% |
| кейсов, где остановка маршрута закрыта к моменту прихода по порядку маршрута | 0 |

## Распределение моделей (`model_link`)

| звено | кейсов |
|---|---|
| template | 20 |

## Нарушения (кейсов с кодом)

| код | кейсов |
|---|---|
| category_not_allowed | 5 |
| walk_too_long | 4 |
| category_forbidden | 2 |
| over_budget | 1 |

## Кейсы с нарушениями

- `h02-nurly-fri-train`: walk_too_long
- `h05-arena-tue-rain`: walk_too_long
- `h06-kenesary-sat-first-time`: walk_too_long
- `h09-botsad-thu-typos`: category_forbidden, category_not_allowed
- `h11-akorda-holiday-cold-tea`: walk_too_long
- `h14-kenesary-wed-dog`: over_budget
- `h16-lovers-tue-sunset`: category_not_allowed
- `h18-nu-tue-en-read`: category_forbidden, category_not_allowed
- `h19-hazret-sun-kk-museum`: category_not_allowed
- `h20-keruen-newyear-cold`: category_not_allowed
