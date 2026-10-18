# `poi.json` vs `poi.enriched.json`, режим `offline`

Кейсов: 41 / 41.

| метрика | poi | poi.enriched | Δ |
|---|---|---|---|
| кейсов | 41 | 41 | +0 |
| hallucinated_poi (должно быть 0) | 0 | 0 | +0 |
| constraint_ok_rate (рекомендации без нарушений) | 98.3% | 100.0% | +1.7 п.п. |
| кейсов без единого нарушения | 95.1% | 100.0% | +4.9 п.п. |
| honest_unknown_rate (кейсы) | 100.0% | 100.0% | +0.0 п.п. |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% | 100.0% | +0.0 п.п. |
| coverage (≥1 рекомендация проходит все ограничения) | 100.0% | 100.0% | +0.0 п.п. |
| diversity (нет дублей сети среди рекомендаций) | 100.0% | 100.0% | +0.0 п.п. |
| top-1 без нарушений ограничений | 100.0% | 100.0% | +0.0 п.п. |
| top-1 с подтверждённым «открыто» | 68.3% | 65.9% | -2.4 п.п. |
| доля рекомендаций с неизвестными часами | 40.0% | 37.7% | -2.3 п.п. |
| доля рекомендаций не из OSM-записей | 0.0% | 63.1% | +63.1 п.п. |
| средняя дорога до рекомендации, мин | 5.4 | 4.6 | -0.8 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 22.6% | 15.6% | -7.0 п.п. |
| … за счёт расширения радиуса (radius_factor > 1) | 0.0% | 0.0% | +0.0 п.п. |
| … за счёт другой категории (back-fill) | 7.8% | 4.1% | -3.7 п.п. |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 14.8% | 11.5% | -3.3 п.п. |
| padding: кейсы хотя бы с одной такой рекомендацией | 31.7% | 24.4% | -7.3 п.п. |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — | — | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п | н/п | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 7 мс | 11 мс | +4 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 10 мс | 20 мс | +10 мс |
| latency ответа ИИ, медиана | н/п | н/п | н/п |
| latency ответа ИИ, p90 | н/п | н/п | н/п |
| honest_unknown_rate по рекомендациям | 100.0% | 100.0% | +0.0 п.п. |
| Wi-Fi/розетка в данных у рекомендаций кейсов «розетка» | 28.6% | 28.6% | +0.0 п.п. |

## model_link

- poi: {'template': 41}
- poi.enriched: {'template': 41}

## Кейсы, где изменился top-1 (15 из 41)

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
| `left-eve-normal-kids` | Национальный музей Республики Казахстан · museum_gallery · osm · unknown · 12 мин | Kulanshi Art Centre · museum_gallery · overture · unknown · 8 мин |
| `left-wk14-normal-quiet` | Блэкбери · cafe · osm · open · 5 мин | Happy Cake · cafe · official_site · open · 2 мин |
| `left-eve-cold-tourist` | Блэкбери · cafe · osm · open · 5 мин | Happy Cake · cafe · official_site · open · 2 мин |
| `left-wk14-smog-kids` | Блэкбери · cafe · osm · open · 5 мин | Kulanshi Art Centre · museum_gallery · overture · unknown · 8 мин |
