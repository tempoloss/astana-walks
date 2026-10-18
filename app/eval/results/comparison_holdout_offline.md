# `poi.json` vs `poi.enriched.json`, режим `offline`

Кейсов: 20 / 20.

| метрика | poi | poi.enriched | Δ |
|---|---|---|---|
| кейсов | 20 | 20 | +0 |
| hallucinated_poi (должно быть 0) | 0 | 0 | +0 |
| constraint_ok_rate (рекомендации без нарушений) | 70.8% | 73.2% | +2.4 п.п. |
| кейсов без единого нарушения | 45.0% | 50.0% | +5.0 п.п. |
| honest_unknown_rate (кейсы) | 100.0% | 100.0% | +0.0 п.п. |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% | 100.0% | +0.0 п.п. |
| coverage (≥1 рекомендация проходит все ограничения) | 70.0% | 75.0% | +5.0 п.п. |
| diversity (нет дублей сети среди рекомендаций) | 100.0% | 100.0% | +0.0 п.п. |
| top-1 без нарушений ограничений | 70.0% | 80.0% | +10.0 п.п. |
| top-1 с подтверждённым «открыто» | 40.0% | 60.0% | +20.0 п.п. |
| доля рекомендаций с неизвестными часами | 68.8% | 67.9% | -0.9 п.п. |
| доля рекомендаций не из OSM-записей | 0.0% | 48.2% | +48.2 п.п. |
| средняя дорога до рекомендации, мин | 9.1 | 8.1 | -1.0 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 25.0% | 16.1% | -8.9 п.п. |
| … за счёт расширения радиуса (radius_factor > 1) | 4.2% | 1.8% | -2.4 п.п. |
| … за счёт другой категории (back-fill) | 20.8% | 14.3% | -6.5 п.п. |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 0.0% | 0.0% | +0.0 п.п. |
| padding: кейсы хотя бы с одной такой рекомендацией | 50.0% | 30.0% | -20.0 п.п. |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — | — | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п | н/п | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 8 мс | 12 мс | +4 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 28 мс | 33 мс | +5 мс |
| latency ответа ИИ, медиана | н/п | н/п | н/п |
| latency ответа ИИ, p90 | н/п | н/п | н/п |
| honest_unknown_rate по рекомендациям | 100.0% | 100.0% | +0.0 п.п. |
| Wi-Fi/розетка в данных у рекомендаций кейсов «розетка» | 0.0% | 0.0% | +0.0 п.п. |

## model_link

- poi: {'template': 20}
- poi.enriched: {'template': 20}

## Кейсы, где изменился top-1 (8 из 20)

| кейс | poi | poi.enriched |
|---|---|---|
| `h02-nurly-fri-train` | Jibek Joly · mall · osm · unknown · 9 мин ⚠ walk_too_long | Coffee BOOM, Ахмет Байтұрсынов көшесі, 32 · cafe · official_site · open · 10 мин ⚠ walk_too_long |
| `h03-keruen-sat-date` | CrepeCafe · cafe · osm · open · 5 мин | Selfie · restaurant · osm+overture+official_site · open · 6 мин |
| `h05-arena-tue-rain` | TLP Flowers & Coffee · cafe · osm · open · 18 мин ⚠ walk_too_long | Coffee BOOM, Орынбор көшесі, 12 · cafe · official_site · open · 9 мин |
| `h13-nurly-tue-late-hungry` | Jibek Joly · mall · osm · unknown · 9 мин | Coffee BOOM, Ахмет Байтұрсынов көшесі, 32 · cafe · official_site · open · 10 мин |
| `h15-arena-sat-football` | Ледовый дворец Алау · sport · osm · unknown · 7 мин | Астана Арена · sport · wikidata+state_registry · unknown · 1 мин |
| `h17-saparzhai-tue-coffee` | У Аркадия · cafe · osm · open · 10 мин | Happy Cake · cafe · official_site · open · 7 мин |
| `h18-nu-tue-en-read` | Drinkit · cafe · osm · open · 12 мин | Starbucks Мега Силк Вэй Университет · cafe · official_site · open · 9 мин |
| `h20-keruen-newyear-cold` | Национальная академическая библиотека Республики Казахстан · coworking_library · osm · unknown · 3 мин ⚠ category_not_allowed | Qaganat · cafe · osm+official_site · open · 8 мин |
