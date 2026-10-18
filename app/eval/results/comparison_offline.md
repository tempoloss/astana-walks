# `poi.json` vs `poi.enriched.json`, режим `offline`

Кейсов: 44 / 44.

| метрика | poi | poi.enriched | Δ |
|---|---|---|---|
| кейсов | 44 | 44 | +0 |
| hallucinated_poi (должно быть 0) | 0 | 0 | +0 |
| constraint_ok_rate (рекомендации без нарушений) | 97.4% | 99.2% | +1.8 п.п. |
| кейсов без единого нарушения | 93.2% | 97.7% | +4.5 п.п. |
| honest_unknown_rate (кейсы) | 100.0% | 100.0% | +0.0 п.п. |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% | 100.0% | +0.0 п.п. |
| coverage (≥1 рекомендация проходит все ограничения) | 97.7% | 97.7% | +0.0 п.п. |
| diversity (нет дублей сети среди рекомендаций) | 100.0% | 100.0% | +0.0 п.п. |
| top-1 без нарушений ограничений | 97.7% | 97.7% | +0.0 п.п. |
| top-1 с подтверждённым «открыто» | 59.1% | 56.8% | -2.3 п.п. |
| доля рекомендаций с неизвестными часами | 47.0% | 45.6% | -1.4 п.п. |
| доля рекомендаций не из OSM-записей | 0.0% | 59.2% | +59.2 п.п. |
| средняя дорога до рекомендации, мин | 6.1 | 5.0 | -1.1 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 15.7% | 8.8% | -6.9 п.п. |
| … за счёт расширения радиуса (radius_factor > 1) | 0.9% | 0.8% | -0.1 п.п. |
| … за счёт другой категории (back-fill) | 6.1% | 2.4% | -3.7 п.п. |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 8.7% | 5.6% | -3.1 п.п. |
| padding: кейсы хотя бы с одной такой рекомендацией | 20.5% | 13.6% | -6.9 п.п. |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — | — | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п | н/п | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 6 мс | 10 мс | +4 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 11 мс | 20 мс | +9 мс |
| latency ответа ИИ, медиана | н/п | н/п | н/п |
| latency ответа ИИ, p90 | н/п | н/п | н/п |
| honest_unknown_rate по рекомендациям | 100.0% | 100.0% | +0.0 п.п. |
| Wi-Fi/розетка в данных у рекомендаций кейсов «розетка» | 28.6% | 28.6% | +0.0 п.п. |

## model_link

- poi: {'template': 44}
- poi.enriched: {'template': 44}

## Кейсы, где изменился top-1 (16 из 44)

| кейс | poi | poi.enriched |
|---|---|---|
| `tz3` | Детская площадка · kids_playground · osm · unknown · 1 мин | Fame City Entertainment Centre · entertainment · overture+official_site · open · 1 мин |
| `tz5` | Лигалайф · bar_nightlife · osm · open · 6 мин | Ozen · bar_nightlife · osm+overture+official_site · open · 7 мин |
| `expo-wk14-normal-tourist` | Gasteria · cafe · osm · open · 9 мин | Coffee BOOM, Мәңгілік Ел даңғылы, 55, B2.4 · cafe · official_site · open · 2 мин |
| `expo-wk14-cold-kids` | Gasteria · cafe · osm · open · 9 мин | Nur Alem Museum of Future Energy · museum_gallery · overture+wikivoyage · unknown · 1 мин |
| `expo-hol-smog-quiet` | Gasteria · cafe · osm · unknown · 9 мин | Coffee BOOM, Мәңгілік Ел даңғылы, 55, B2.4 · cafe · official_site · unknown · 2 мин |
| `expo-wk14-normal-mobility` | Gasteria · cafe · osm · open · 9 мин | Coffee BOOM, Мәңгілік Ел даңғылы, 55, B2.4 · cafe · official_site · open · 2 мин |
| `msw-night-cold-night` | Пинта · bar_nightlife · osm · open · 1 мин | Coffee BOOM, Қабанбай батыр даңғылы, 62 үй · cafe · official_site · open · 3 мин |
| `baiterek-eve-smog-kids` | CrepeCafe · cafe · osm · open · 4 мин | Picture Day · museum_gallery · overture · unknown · 6 мин |
| `khan-hol-cold-tourist` | Bambino · cafe · osm · unknown · 2 мин | Cafe Latte · cafe · overture · unknown · 1 мин |
| `khan-eve-cold-kids` | Fame City · entertainment · osm · unknown · 1 мин | Fame City Entertainment Centre · entertainment · overture+official_site · open · 1 мин |
| `khan-eve-smog-mobility` | Лепим и варим · cafe · osm · open · 2 мин | Le Pain Quotidien · cafe · overture+official_site · open · 1 мин |
| `lrt-wk14-cold-walk` | Welcome to Astana · attraction_landmark · osm · unknown · 79 мин ⚠ walk_too_long | Альжан ана · attraction_landmark · wikidata · unknown · 34 мин ⚠ walk_too_long |
| `left-eve-normal-kids` | Национальный музей Республики Казахстан · museum_gallery · osm · unknown · 12 мин | Kulanshi Art Centre · museum_gallery · overture · unknown · 8 мин |
| `left-wk14-normal-quiet` | Блэкбери · cafe · osm · open · 5 мин | Happy Cake · cafe · official_site · open · 2 мин |
| `left-eve-cold-tourist` | Блэкбери · cafe · osm · open · 5 мин | Happy Cake · cafe · official_site · open · 2 мин |
| `left-wk14-smog-kids` | Блэкбери · cafe · osm · open · 5 мин | Kulanshi Art Centre · museum_gallery · overture · unknown · 8 мин |
