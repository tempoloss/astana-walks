# Анық — помощник для прогулок по Астане (RAG)

Пешеходный помощник для Астаны: по точке пользователя и свободному запросу («Я у EXPO, хочу что-то необычное на 1–2 часа, пешком») подбирает 1–3 места с объяснением, расстоянием, временем в пути и мини-маршрутом на карте.

Проект сделан для кейса AITU НИЦ Smart City. Тезис: «в Астане не хватает не мест, а сведений о них». Поэтому данные собираются из открытых источников с атрибуцией, а в отдельном слое «город» есть анонимные отметки людей о реальном состоянии мест.

## Структура

- `app/` — приложение: конвейер `walks/` (разбор запроса → поиск → генерация → маршрут), веб-интерфейс (`web/`: Starlette + MapLibre, `python -m web`), оценка качества (`eval/`), тесты.
- `collect/` — сборка базы POI из OpenStreetMap, Overture Maps, Wikipedia/Wikidata, официальных сайтов заведений (`collect/sites`), госреестров и Wikivoyage, затем слияние записей об одном месте (`collect/dedupe.py`); афиша событий «что происходит сегодня» (`collect/events` → `data/events.json`, читает `app/walks/events.py`).
- `data/` — собранная база (`poi.enriched.json`), базовая выборка только из OSM (`poi.json`), статистика, [атрибуция](data/ATTRIBUTION.md).
- `docs/` — интеграции, сценарии, презентационные материалы; [`docs/figures.md`](docs/figures.md) — числа для слайдов.
- `scripts/` — вспомогательные скрипты (`make_figures.py`).

## Запуск приложения

```
cd app
uv sync
uv run python -m web                          # http://localhost:8600
```

Без сети: `WALKS_OFFLINE=1`. Ключи и цепочки ИИ настраиваются в `app/.env.example`; без ключа приложение работает на шаблонном тексте.

## Пересборка данных

Из корня репозитория:

```
uv run python -m collect.build            # districts → osm → overture → geocheck → wiki → wiki_places → merge → sites → gov → dedupe → wikivoyage, всё через кэш
uv run python -m collect.build --refresh  # перекачать (вежливо)
```

## Оценка качества

```
cd app
uv run poe eval
```

Оценка идёт на базовом и обогащённом наборе, на основной выборке и на отложенной. Результаты — `app/eval/results/`, сценарии — `docs/scenarios.md`.

## Цифры и рисунки

```
uv run python scripts/make_figures.py
```

Скрипт читает статистику из `data/` и пишет `docs/figures.md`. Числа в нём не редактируются вручную.

## Источники и лицензии

**Данные.** Файлы `data/` с данными OpenStreetMap (список — в [`data/NOTICE.md`](data/NOTICE.md)) — производная база OSM, лицензия **ODbL 1.0** (© OpenStreetMap contributors); в ней лежат вклады с другими лицензиями: Overture Maps (по вкладчику: Meta, Microsoft, PinMeTo — CDLA-Permissive-2.0, Foursquare — Apache-2.0, AllThePlaces — CC0), Wikidata и Wikimedia Pageviews (CC0), Wikipedia (CC BY-SA 4.0), остановки из Zenodo (CC BY 4.0), факты официальных сайтов заведений и открытых данных госорганов (со ссылкой на страницу). Лицензия базы и как получить машиночитаемую копию — [`data/NOTICE.md`](data/NOTICE.md); тексты лицензий — [`LICENSES/`](LICENSES/); Notice Foursquare — [`data/NOTICE_overture.txt`](data/NOTICE_overture.txt).

**Сервисы во время работы.** Прогноз погоды — MET Norway (CC BY 4.0 + NLOD 2.0); наблюдения метеостанции аэропорта и штормовые предупреждения — Казгидромет (со ссылкой на источник); качество воздуха (PM2.5) — Open-Meteo (CC BY 4.0) только в демо-режиме `WALKS_AIR_DEMO=1`: его бесплатный API некоммерческий. Пешие маршруты — Valhalla: на стенде свой сервер на данных OSM (`WALKS_VALHALLA_URL`), локально по умолчанию сервер FOSSGIS (для демо; для платного продукта нужен свой сервер). Карта — OpenFreeMap (OpenMapTiles, OpenStreetMap); переключатель «Спутник» кладёт под неё снимки Sentinel-2 cloudless 2016 (EOX, CC BY 4.0) из дискового кэша нашего сервера; ИИ — Gemini API.

**Таблица «источник — лицензия — обязательство — где выполнено — что нужно для продакшена» с цитатами первоисточников — [`docs/licensing.md`](docs/licensing.md).** Краткие строки атрибуции — [`data/ATTRIBUTION.md`](data/ATTRIBUTION.md).

**Лицензия кода.** Не выбрана: файла LICENSE в репозитории нет. Это решение владельца, варианты и их цена — в [`docs/licensing.md`](docs/licensing.md), раздел 5.

## Приватность

Координаты округляются до ~100 м сразу на входе. Текст запроса и точные координаты не сохраняются. На диск пишутся только анонимный агрегат запросов и добровольные отметки без идентификаторов; личный профиль создаётся только по включению пользователем. Подробности — в [`app/README.md`](app/README.md), раздел «Приватность».
