# Оценка: `poi.enriched`, режим `offline`

Набор кейсов: holdout2. Кейсов: 24, рекомендаций: 70.
Прогон: метка `offline`, режим `offline`, 24 записей, данные `data/poi.enriched.json`, git `4a1b05c+uncommitted`, 2026-10-19T10:36:41+05:00.

| метрика | значение |
|---|---|
| кейсов | 24 |
| hallucinated_poi (должно быть 0) | 0 |
| constraint_ok_rate (рекомендации без нарушений) | 81.4% |
| кейсов без единого нарушения | 33.3% |
| honest_unknown_rate (кейсы) | 100.0% |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% |
| coverage (≥1 рекомендация проходит все ограничения) | 37.5% |
| diversity (нет дублей сети среди рекомендаций) | 100.0% |
| top-1 без нарушений ограничений | 91.7% |
| top-1 с подтверждённым «открыто» | 45.8% |
| доля рекомендаций с неизвестными часами | 64.3% |
| доля рекомендаций не из OSM-записей | 47.1% |
| средняя дорога до рекомендации, мин | 6.8 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 8.6% |
| … за счёт расширения радиуса (radius_factor > 1) | 0.0% |
| … за счёт другой категории (back-fill) | 8.6% |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 0.0% |
| padding: кейсы хотя бы с одной такой рекомендацией | 12.5% |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 15 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 25 мс |
| latency ответа ИИ, медиана | н/п |
| latency ответа ИИ, p90 | н/п |
| honest_unknown_rate по рекомендациям | 100.0% |
| Wi-Fi/розетка есть в данных у рекомендаций кейсов «розетка» | 33.3% |
| кейсов, где остановка маршрута закрыта к моменту прихода по порядку маршрута | 0 |

## Распределение моделей (`model_link`)

| звено | кейсов |
|---|---|
| template | 24 |

## Нарушения (кейсов с кодом)

| код | кейсов |
|---|---|
| over_budget | 15 |
| category_not_allowed | 6 |
| walk_too_long | 2 |
| outdoor_in_cold_or_smog | 1 |

## Кейсы с нарушениями

- `h2-01-hazret-morning-walk`: over_budget
- `h2-03-asiapark-family-day`: over_budget
- `h2-05-piramida-tourist-hour`: over_budget, walk_too_long
- `h2-06-piramida-stroller-accessible`: category_not_allowed
- `h2-10-nurzhol-smog-laptop`: over_budget
- `h2-11-astanamall-budget-lunch`: over_budget
- `h2-12-astanamall-late-night`: category_not_allowed, over_budget
- `h2-13-station-transit-lunch`: over_budget
- `h2-14-station-cold-wait`: over_budget
- `h2-15-momyshuly-park-weekend-walk`: category_not_allowed, over_budget
- `h2-16-momyshuly-park-laptop-work`: category_not_allowed, outdoor_in_cold_or_smog, over_budget, walk_too_long
- `h2-17-medu-between-classes`: over_budget
- `h2-19-koktal-private-sector-weekend`: over_budget
- `h2-22-kokzhiek-street-cold-kids`: category_not_allowed, over_budget
- `h2-23-botanical-garden-en-walk`: category_not_allowed, over_budget
- `h2-24-asiapark-mixed-typo-night`: over_budget
