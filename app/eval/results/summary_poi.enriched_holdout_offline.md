# Оценка: `poi.enriched`, режим `offline`

Набор кейсов: holdout. Кейсов: 20, рекомендаций: 56.
Прогон: метка `offline`, режим `offline`, 20 записей, данные `data/poi.enriched.json`, git `a007589+uncommitted`, 2026-10-19T21:12:46+05:00.

| метрика | значение |
|---|---|
| кейсов | 20 |
| hallucinated_poi (должно быть 0) | 0 |
| constraint_ok_rate (рекомендации без нарушений) | 73.2% |
| кейсов без единого нарушения | 50.0% |
| honest_unknown_rate (кейсы) | 100.0% |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% |
| coverage (≥1 рекомендация проходит все ограничения) | 75.0% |
| diversity (нет дублей сети среди рекомендаций) | 100.0% |
| top-1 без нарушений ограничений | 80.0% |
| top-1 с подтверждённым «открыто» | 65.0% |
| доля рекомендаций с неизвестными часами | 66.1% |
| доля рекомендаций не из OSM-записей | 60.7% |
| средняя дорога до рекомендации, мин | 8.5 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 16.1% |
| … за счёт расширения радиуса (radius_factor > 1) | 1.8% |
| … за счёт другой категории (back-fill) | 14.3% |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 0.0% |
| padding: кейсы хотя бы с одной такой рекомендацией | 30.0% |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 15 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 48 мс |
| latency ответа ИИ, медиана | н/п |
| latency ответа ИИ, p90 | н/п |
| honest_unknown_rate по рекомендациям | 100.0% |
| Wi-Fi/розетка есть в данных у рекомендаций кейсов «розетка» | 0.0% |
| кейсов, где остановка маршрута закрыта к моменту прихода по порядку маршрута | 1 |

## Распределение моделей (`model_link`)

| звено | кейсов |
|---|---|
| template | 20 |

## Нарушения (кейсов с кодом)

| код | кейсов |
|---|---|
| category_not_allowed | 6 |
| category_forbidden | 4 |
| walk_too_long | 4 |
| over_budget | 2 |
| outdoor_in_cold_or_smog | 1 |

## Кейсы с нарушениями

- `h02-nurly-fri-train`: category_forbidden, category_not_allowed, walk_too_long
- `h05-arena-tue-rain`: category_forbidden, category_not_allowed
- `h06-kenesary-sat-first-time`: walk_too_long
- `h09-botsad-thu-typos`: category_forbidden, category_not_allowed
- `h11-akorda-holiday-cold-tea`: walk_too_long
- `h12-keruen-sun-smog-air`: category_forbidden, category_not_allowed, outdoor_in_cold_or_smog
- `h13-nurly-tue-late-hungry`: category_not_allowed
- `h14-kenesary-wed-dog`: over_budget
- `h16-lovers-tue-sunset`: over_budget, walk_too_long
- `h20-keruen-newyear-cold`: category_not_allowed
