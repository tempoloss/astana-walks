# `poi.json` vs `poi.enriched.json`, режим `offline`

Кейсов: 44 / 44.

| метрика | poi | poi.enriched | Δ |
|---|---|---|---|
| кейсов | 44 | 44 | +0 |
| hallucinated_poi (должно быть 0) | 0 | 0 | +0 |
| constraint_ok_rate (рекомендации без нарушений) | 98.3% | 99.2% | +0.9 п.п. |
| кейсов без единого нарушения | 95.5% | 97.7% | +2.2 п.п. |
| honest_unknown_rate (кейсы) | 100.0% | 100.0% | +0.0 п.п. |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% | 100.0% | +0.0 п.п. |
| coverage (≥1 рекомендация проходит все ограничения) | 97.7% | 97.7% | +0.0 п.п. |
| diversity (нет дублей сети среди рекомендаций) | 100.0% | 100.0% | +0.0 п.п. |
| top-1 без нарушений ограничений | 97.7% | 97.7% | +0.0 п.п. |
| top-1 с подтверждённым «открыто» | 61.4% | 59.1% | -2.3 п.п. |
| доля рекомендаций с неизвестными часами | 50.4% | 45.6% | -4.8 п.п. |
| доля рекомендаций не из OSM-записей | 0.0% | 61.6% | +61.6 п.п. |
| средняя дорога до рекомендации, мин | 6.3 | 5.3 | -1.0 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 12.6% | 8.8% | -3.8 п.п. |
| … за счёт расширения радиуса (radius_factor > 1) | 0.8% | 0.8% | +0.0 п.п. |
| … за счёт другой категории (back-fill) | 3.4% | 2.4% | -1.0 п.п. |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 8.4% | 5.6% | -2.8 п.п. |
| padding: кейсы хотя бы с одной такой рекомендацией | 15.9% | 13.6% | -2.3 п.п. |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — | — | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п | н/п | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 7 мс | 12 мс | +6 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 12 мс | 23 мс | +11 мс |
| latency ответа ИИ, медиана | н/п | н/п | н/п |
| latency ответа ИИ, p90 | н/п | н/п | н/п |
| honest_unknown_rate по рекомендациям | 100.0% | 100.0% | +0.0 п.п. |
| Wi-Fi/розетка в данных у рекомендаций кейсов «розетка» | 33.3% | 33.3% | +0.0 п.п. |

## model_link

- poi: {'template': 44}
- poi.enriched: {'template': 44}

## Кейсы, где изменился top-1 (20 из 44)

| кейс | poi | poi.enriched |
|---|---|---|
| `tz3` | Детская площадка · kids_playground · osm · unknown · 1 мин | Fame City Entertainment Centre · entertainment · overture+official_site · open · 1 мин |
| `tz5` | Лигалайф · bar_nightlife · osm · open · 6 мин | Ozen · bar_nightlife · osm+overture+official_site · open · 7 мин |
| `expo-wk14-normal-tourist` | Gasteria · cafe · osm · open · 9 мин | Coffee BOOM, Мәңгілік Ел даңғылы, 55, B2.4 · cafe · official_site · open · 2 мин |
| `expo-wk14-cold-kids` | Gasteria · cafe · osm · open · 9 мин | Nur Alem Museum of Future Energy · museum_gallery · overture+wikivoyage · unknown · 1 мин |
| `expo-hol-smog-quiet` | Gasteria · cafe · osm · unknown · 9 мин | Coffee BOOM, Мәңгілік Ел даңғылы, 55, B2.4 · cafe · official_site · unknown · 2 мин |
| `expo-wk14-normal-mobility` | Gasteria · cafe · osm · open · 9 мин | Coffee BOOM, Мәңгілік Ел даңғылы, 55, B2.4 · cafe · official_site · open · 2 мин |
| `msw-night-cold-night` | Пинта · bar_nightlife · osm · open · 1 мин | Coffee BOOM, Қабанбай батыр даңғылы, 62 үй · cafe · official_site · open · 3 мин |
| `msw-hol-normal-kids` | Детская площадка · kids_playground · osm · unknown · 4 мин | Nur Alem Museum of Future Energy · museum_gallery · overture+wikivoyage · unknown · 11 мин |
| `baiterek-eve-smog-kids` | CrepeCafe · cafe · osm · open · 4 мин | Picture Day · museum_gallery · overture · unknown · 6 мин |
| `khan-hol-cold-tourist` | Bambino · cafe · osm · unknown · 2 мин | Cafe Latte · cafe · overture · unknown · 1 мин |
| `khan-eve-cold-kids` | Fame City · entertainment · osm · unknown · 1 мин | Fame City Entertainment Centre · entertainment · overture+official_site · open · 1 мин |
| `khan-eve-smog-mobility` | Лепим и варим · cafe · osm · open · 2 мин | Le Pain Quotidien · cafe · overture+official_site · open · 1 мин |
| `lrt-wk14-cold-walk` | Welcome to Astana · attraction_landmark · osm · unknown · 79 мин ⚠ walk_too_long | Альжан ана · attraction_landmark · wikidata · unknown · 34 мин ⚠ walk_too_long |
| `left-eve-normal-kids` | Национальный музей Республики Казахстан · museum_gallery · osm · unknown · 12 мин | Kulanshi Art Centre · museum_gallery · overture · unknown · 8 мин |
| `left-wk14-normal-quiet` | Блэкбери · cafe · osm · open · 5 мин | Happy Cake · cafe · official_site · open · 2 мин |
| `left-night-normal-night` | Golpas · bar_nightlife · osm · open · 8 мин | Kömir Highvill Ishim · bar_nightlife · overture · unknown · 3 мин |
| `left-eve-cold-tourist` | Блэкбери · cafe · osm · open · 5 мин | Happy Cake · cafe · official_site · open · 2 мин |
| `left-wk14-smog-kids` | Блэкбери · cafe · osm · open · 5 мин | Kulanshi Art Centre · museum_gallery · overture · unknown · 8 мин |
| `wish1` | Байтерек · attraction_landmark · osm · unknown · 1 мин | Водно-Зеленый Бульвар · park_garden · overture · unknown · 7 мин |
| `wish2` | Байтерек · attraction_landmark · osm · unknown · 1 мин | Водно-Зеленый Бульвар · park_garden · overture · unknown · 7 мин |
