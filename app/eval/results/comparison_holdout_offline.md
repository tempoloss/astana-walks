# `poi.json` vs `poi.enriched.json`, режим `offline`

Кейсов: 20 / 20.

| метрика | poi | poi.enriched | Δ |
|---|---|---|---|
| кейсов | 20 | 20 | +0 |
| hallucinated_poi (должно быть 0) | 0 | 0 | +0 |
| constraint_ok_rate (рекомендации без нарушений) | 76.5% | 77.6% | +1.1 п.п. |
| кейсов без единого нарушения | 50.0% | 60.0% | +10.0 п.п. |
| honest_unknown_rate (кейсы) | 100.0% | 100.0% | +0.0 п.п. |
| honest_unknown_rate, кейсы «ночь/праздник» | 100.0% | 100.0% | +0.0 п.п. |
| coverage (≥1 рекомендация проходит все ограничения) | 80.0% | 80.0% | +0.0 п.п. |
| diversity (нет дублей сети среди рекомендаций) | 100.0% | 100.0% | +0.0 п.п. |
| top-1 без нарушений ограничений | 75.0% | 85.0% | +10.0 п.п. |
| top-1 с подтверждённым «открыто» | 50.0% | 70.0% | +20.0 п.п. |
| доля рекомендаций с неизвестными часами | 64.7% | 58.6% | -6.1 п.п. |
| доля рекомендаций не из OSM-записей | 0.0% | 51.7% | +51.7 п.п. |
| средняя дорога до рекомендации, мин | 7.8 | 6.9 | -0.9 |
| padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды | 33.3% | 24.1% | -9.2 п.п. |
| … за счёт расширения радиуса (radius_factor > 1) | 2.0% | 0.0% | -2.0 п.п. |
| … за счёт другой категории (back-fill) | 25.5% | 19.0% | -6.5 п.п. |
| … за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted) | 5.9% | 5.2% | -0.7 п.п. |
| padding: кейсы хотя бы с одной такой рекомендацией | 55.0% | 35.0% | -20.0 п.п. |
| honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено) | — | — | — |
| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |
| кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон) | н/п | н/п | н/п |
| latency пайплайна, медиана (шаблон, без ИИ) | 8 мс | 14 мс | +7 мс |
| latency пайплайна, p90 (шаблон, без ИИ) | 27 мс | 35 мс | +8 мс |
| latency ответа ИИ, медиана | н/п | н/п | н/п |
| latency ответа ИИ, p90 | н/п | н/п | н/п |
| honest_unknown_rate по рекомендациям | 100.0% | 100.0% | +0.0 п.п. |
| Wi-Fi/розетка в данных у рекомендаций кейсов «розетка» | 0.0% | 0.0% | +0.0 п.п. |

## model_link

- poi: {'template': 20}
- poi.enriched: {'template': 20}

## Кейсы, где изменился top-1 (10 из 20)

| кейс | poi | poi.enriched |
|---|---|---|
| `h02-nurly-fri-train` | Jibek Joly · mall · osm · unknown · 9 мин ⚠ walk_too_long | Coffee BOOM, Ахмет Байтұрсынов көшесі, 32 · cafe · official_site · open · 10 мин ⚠ walk_too_long |
| `h03-keruen-sat-date` | CrepeCafe · cafe · osm · open · 5 мин | Selfie · restaurant · osm+overture+official_site · open · 6 мин |
| `h05-arena-tue-rain` | TLP Flowers & Coffee · cafe · osm · open · 18 мин ⚠ walk_too_long | Coffee BOOM, Орынбор көшесі, 12 · cafe · official_site · open · 9 мин |
| `h06-kenesary-sat-first-time` | ÖM · cafe · osm · open · 4 мин | Музей первого президента РК Н. А. Назарбаева · museum_gallery · osm+wikivoyage · open · 5 мин |
| `h13-nurly-tue-late-hungry` | Jibek Joly · mall · osm · unknown · 9 мин | Coffee BOOM, Ахмет Байтұрсынов көшесі, 32 · cafe · official_site · open · 10 мин |
| `h15-arena-sat-football` | Ледовый дворец Алау · sport · osm · unknown · 7 мин | Астана Арена · sport · wikidata+state_registry · unknown · 1 мин |
| `h16-lovers-tue-sunset` | Лепим и варим · cafe · osm · open · 7 мин ⚠ category_not_allowed | Le Pain Quotidien · cafe · overture+official_site · open · 7 мин ⚠ category_not_allowed |
| `h17-saparzhai-tue-coffee` | У Аркадия · cafe · osm · open · 10 мин | Happy Cake · cafe · official_site · open · 7 мин |
| `h18-nu-tue-en-read` | Drinkit · cafe · osm · open · 12 мин | Starbucks Мега Силк Вэй Университет · cafe · official_site · open · 9 мин |
| `h20-keruen-newyear-cold` | Национальная академическая библиотека Республики Казахстан · coworking_library · osm · unknown · 3 мин ⚠ category_not_allowed | Qaganat · cafe · osm+official_site · open · 8 мин |
