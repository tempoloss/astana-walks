# collect/mobility — «как добраться» и парковка (SOURCES.md §14.2)

Три слоя; запуск из корня репозитория:

```
uv run python -m collect.mobility                                # остановки + автобусы аэропорта (всегда)
WALKS_MOBILITY_PARKING=1 uv run python -m collect.mobility       # + снимок парковок ЦОДД (без лицензии!)
WALKS_MOBILITY_PARKING=1 uv run python -m collect.mobility.parking   # только парковки
uv run python -m collect.mobility.stops                          # только остановки
```

Выходы: `data/mobility/{stops,stops_stats,airport_bus,parking_zones,parking_zones_stats}.json`.
Всё HTTP — через `collect.net` (UA `astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)`, токен-бакет,
ретраи, кэш `.local/http_cache.sqlite`).

## 1. Автобусные остановки — `stops.py`

| источник | что берём | лицензия | вежливость |
|---|---|---|---|
| Zenodo record 15769359 (`gtfs_data.zip` → `stops.txt`, 173 строки; файл cp1251) | остановки с координатами; **расписания GTFS — реконструкция из GPS (READ-ME записи), НЕ храним** | CC BY 4.0 | 1 скачивание, кэш-файл `.local/mobility/gtfs_data.zip` |
| OSM `highway=bus_stop`, `public_transport=platform[bus=yes]` через Overpass | площадки/остановки с именами и `shelter` | ODbL 1.0 | через общий `overpass()` с зеркалами; в этом окружении доступно только `maps.mail.ru` (≤1 req/5 с) |

Атрибуция (хранится в `stops_stats.json` дословно): *«GTFS stops: Mansurova, Aigerim; Mussina, Aigerim;
Aubakirov, Sanzhar; Nugumanova, Aliya; Yedilkhan, Didar (2025): „From Raw GPS to GTFS: A Real-World Open
Dataset for Bus Travel Time Prediction“, Zenodo, https://zenodo.org/records/15769359, CC BY 4.0
(doi:10.5281/zenodo.15769359; журнальная версия doi:10.3390/data10080119). OSM platforms: © OpenStreetMap
contributors, ODbL 1.0, https://www.openstreetmap.org/copyright»*.

Склейка: точка GTFS в радиусе 40 м от OSM-платформы — одна остановка (запись OSM выигрывает, id GTFS
сохраняется в `gtfs_ids`); GTFS-дубликаты схлопываются в ту же 40 м. Обновление: по желанию, пересборка
идемпотентна (кэш HTTP).

## 2. Автобусы аэропорта — `airport_bus.py`

`https://nn-airport.kz/pages/bus` (после GET `/lang/ru` — русская версия страницы). Хранятся **только
датированные факты** с дословными сниппетами ≤300 знаков (ГК РК ст. 974 п. 4; полный текст страницы не
копируется): маршруты №10/№12 — «Выезд из города в аэропорт маршрута №10 — 5.50 — 21.23…» и т.д., тариф
«90 тенге картой / 180 наличными», часы работы автобусов 6:00–23:00. Лицензия на сайте не указана →
`licence: "none stated (facts from the airport's own website; source dated, quotes ≤ 300 chars)"`.
Политесн��сть: 1 запрос за сбор, robots.txt портала не запрещает страницы для пассажиров (меню/страницы
серверные), кэш — навсегда до явной пересборки.

## 3. Парковки ЦОДД — `parking.py` ⚠️ БЕЗ ЛИЦЕНЗИИ

`pkg-mobile-gateway-service.jquo.kz/api/v1/parkings?zoom=18` (+ `/parkings/{uuid}`; `/tariffs`,
`/residential-zones`, `/abonements` — 401 без ключа). Эндпоинт извлечён из chunk-*.js портала
`pkg-payment.jquo.kz` — **reverse-engineered приватный JSON, лицензии нет** (оферта — SPA-заглушка).

Правила изоляции (решение Main, обзор e963cfd):
- снимок — в отдельный файл `data/mobility/parking_zones.json`, каждая запись несёт
  `licence: "none (operator gateway, reverse-engineered)"` и `attribution: «ЦОДД Астаны / UIMS»`;
- сбор **выключен по умолчанию**: без `WALKS_MOBILITY_PARKING=1` модуль ничего не скачивает и печатает
  отказ; слой в `app/walks/mobility.py` тоже выключен по умолчанию (`parking_at` → None без флага);
- удаление фичи = удалить `collect/mobility/parking.py` и `data/mobility/parking_zones*.json`
  (ничто другое на них не ссылается);
- не публиковать этот файл в открытых наборах без договора с оператором.

Единица цены шлюза не документирована; публичная страница тарифов портала называет «Простой» 500 ₸/час,
«Дифференцированный» 500 ₸ день / 300 ₸ ночной час. В данных хранятся сырые числа; времён периодов
(`tariff_rule_groups`) шлюз без авторизации не отдаёт — только упорядоченный список.

## Тесты

`uv run --with pytest python -m pytest collect/tests/test_mobility.py -q` (коллекторы, без сети) и
`cd app && uv run pytest tests/test_mobility.py -q` (чистый слой `walks/mobility.py`): точка в полигоне,
границы тарифного окна, дедуп остановок, «после последнего рейса — данных нет».

## Чистый слой приложения

`app/walks/mobility.py`: `parking_at(lat, lon, when)`, `nearest_stops(lat, lon, n=2)` (пешком = прямая
×1.3 при 75 м/мин — как `walking.straight_leg`), `airport_bus(now)`. Флаги CLI:
`--parking`, `--stops`, `--airport-bus` (`uv run python -m walks.cli --parking --lat … --lon …`).
