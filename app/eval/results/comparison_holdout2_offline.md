# `poi.json` vs `poi.enriched.json`, режим `offline`

Кейсов: 24 / 24.

| метрика | poi | poi.enriched | Δ |
|---|---|---|---|
| кейсов | 24 | 24 | +0 |
| hallucinated_poi (должно быть 0) | 0 | 0 | +0 |
| constraint_ok_rate (рекомендации без нарушений) | 85.7% | 82.9% | -2.8 п.п. |
| кейсов без единого нарушения | 33.3% | 33.3% | +0.0 п.п. |
| honest_unknown_rate (кейсы) | 100.0% | 100.0% | +0.0 п.п. |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% | 100.0% | +0.0 п.п. |
| coverage (≥1 рекомендация проходит все ограничения) | 37.5% | 37.5% | +0.0 п.п. |
| diversity (нет дублей сети среди рекомендаций) | 100.0% | 100.0% | +0.0 п.п. |
| top-1 без нарушений ограничений | 95.8% | 91.7% | -4.1 п.п. |
| top-1 с подтверждённым «открыто» | 58.3% | 54.2% | -4.1 п.п. |
| доля рекомендаций с неизвестными часами | 64.3% | 57.1% | -7.2 п.п. |
| доля рекомендаций не из OSM-записей | 0.0% | 42.9% | +42.9 п.п. |
| средняя дорога до рекомендации, мин | 6.7 | 7.3 | +0.6 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 11.4% | 10.0% | -1.4 п.п. |
| … за счёт расширения радиуса (radius_factor > 1) | 0.0% | 0.0% | +0.0 п.п. |
| … за счёт другой категории (back-fill) | 11.4% | 10.0% | -1.4 п.п. |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 0.0% | 0.0% | +0.0 п.п. |
| padding: кейсы хотя бы с одной такой рекомендацией | 16.7% | 16.7% | +0.0 п.п. |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — | — | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п | н/п | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 11 мс | 14 мс | +2 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 19 мс | 23 мс | +4 мс |
| latency ответа ИИ, медиана | н/п | н/п | н/п |
| latency ответа ИИ, p90 | н/п | н/п | н/п |
| honest_unknown_rate по рекомендациям | 100.0% | 100.0% | +0.0 п.п. |
| Wi-Fi/розетка в данных у рекомендаций кейсов «розетка» | 33.3% | 33.3% | +0.0 п.п. |

## model_link

- poi: {'template': 24}
- poi.enriched: {'template': 24}

## Кейсы, где изменился top-1 (8 из 24)

| кейс | poi | poi.enriched |
|---|---|---|
| `h2-02-hazret-halal-dinner` | Lапша Tokyo · restaurant · osm · open · 10 мин | Rabiya · restaurant · overture+official_site · open · 11 мин |
| `h2-04-asiapark-cold-indoor` | Кишлак · restaurant · osm · open · 5 мин | Cafeteria · restaurant · official_site · open · 2 мин |
| `h2-05-piramida-tourist-hour` | Barista · cafe · osm · open · 10 мин | Национальный музей Республики Казахстан · museum_gallery · osm+overture+official_site+museum_register+wikivoyage · open · 13 мин ⚠ walk_too_long |
| `h2-09-nurzhol-wind-shelter` | Asai Restaurant Astana · restaurant · osm · open · 3 мин | Саксаул · restaurant · osm+overture+wikivoyage · open · 2 мин |
| `h2-15-momyshuly-park-weekend-walk` | Марипоса · cafe · osm · open · 7 мин | Happy Cake · cafe · official_site · open · 5 мин |
| `h2-16-momyshuly-park-laptop-work` | Парк / сквер · park_garden · osm · unknown · 32 мин ⚠ category_not_allowed, walk_too_long, outdoor_in_cold_or_smog | Астана, Ул. Ташенова · park_garden · overture · unknown · 41 мин ⚠ category_not_allowed, walk_too_long, outdoor_in_cold_or_smog |
| `h2-19-koktal-private-sector-weekend` | Kazakh food · cafe · osm · open · 13 мин | Батутный парк KANGO Астана · entertainment · overture · unknown · 14 мин |
| `h2-24-asiapark-mixed-typo-night` | KFC · fast_food · osm · open · 1 мин | Papa Johns Pizza · fast_food · overture+official_site · open · 1 мин |
