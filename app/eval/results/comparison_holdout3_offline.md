# `poi.json` vs `poi.enriched.json`, режим `offline`

Кейсов: 24 / 24.

| метрика | poi | poi.enriched | Δ |
|---|---|---|---|
| кейсов | 24 | 24 | +0 |
| hallucinated_poi (должно быть 0) | 0 | 0 | +0 |
| constraint_ok_rate (рекомендации без нарушений) | 75.0% | 74.2% | -0.8 п.п. |
| кейсов без единого нарушения | 50.0% | 54.2% | +4.2 п.п. |
| honest_unknown_rate (кейсы) | 100.0% | 100.0% | +0.0 п.п. |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% | 100.0% | +0.0 п.п. |
| coverage (≥1 рекомендация проходит все ограничения) | 87.5% | 87.5% | +0.0 п.п. |
| diversity (нет дублей сети среди рекомендаций) | 100.0% | 100.0% | +0.0 п.п. |
| top-1 без нарушений ограничений | 70.8% | 66.7% | -4.1 п.п. |
| top-1 с подтверждённым «открыто» | 58.3% | 50.0% | -8.3 п.п. |
| доля рекомендаций с неизвестными часами | 53.1% | 56.1% | +3.0 п.п. |
| доля рекомендаций не из OSM-записей | 0.0% | 45.5% | +45.5 п.п. |
| средняя дорога до рекомендации, мин | 12.2 | 11.6 | -0.6 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 14.1% | 12.1% | -2.0 п.п. |
| … за счёт расширения радиуса (radius_factor > 1) | 1.6% | 3.0% | +1.4 п.п. |
| … за счёт другой категории (back-fill) | 10.9% | 7.6% | -3.3 п.п. |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 1.6% | 1.5% | -0.1 п.п. |
| padding: кейсы хотя бы с одной такой рекомендацией | 25.0% | 20.8% | -4.2 п.п. |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — | — | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п | н/п | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 12 мс | 15 мс | +3 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 37 мс | 51 мс | +14 мс |
| latency ответа ИИ, медиана | н/п | н/п | н/п |
| latency ответа ИИ, p90 | н/п | н/п | н/п |
| honest_unknown_rate по рекомендациям | 100.0% | 100.0% | +0.0 п.п. |
| Wi-Fi/розетка в данных у рекомендаций кейсов «розетка» | 100.0% | 100.0% | +0.0 п.п. |

## model_link

- poi: {'template': 24}
- poi.enriched: {'template': 24}

## Кейсы, где изменился top-1 (9 из 24)

| кейс | poi | poi.enriched |
|---|---|---|
| `h3-06` | Эфир · cafe · osm · open · 10 мин | Happy Cake · cafe · official_site · open · 6 мин |
| `h3-07` | Сквер · park_garden · osm · unknown · 8 мин | Singing Fountain Astana · attraction_landmark · overture · unknown · 6 мин |
| `h3-10` | Якитория · restaurant · osm · open · 2 мин | Grand Opera · attraction_landmark · overture · unknown · 7 мин ⚠ category_not_allowed |
| `h3-11` | Парк Астана · park_garden · osm · unknown · 5 мин | Central Park Astana · park_garden · overture · unknown · 4 мин |
| `h3-14` | Bambino · cafe · osm · unknown · 5 мин | Vista Restaurant and Bar · restaurant · overture · unknown · 5 мин |
| `h3-15` | TLP Flowers & Coffee · cafe · osm · open · 12 мин | Grand Hall · restaurant · overture · unknown · 13 мин |
| `h3-20` | У Аркадия · cafe · osm · open · 10 мин | Happy Cake · cafe · official_site · open · 7 мин |
| `h3-22` | vanilla · cafe · osm · unknown · 5 мин | Coffee BOOM, Тұран даңғылы, 18 · cafe · official_site · unknown · 2 мин |
| `h3-23` | Парк Астана · park_garden · osm · unknown · 5 мин | Central Park Astana · park_garden · overture · unknown · 4 мин |
