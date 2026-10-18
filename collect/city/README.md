# collect/city — городские слои состояния из OpenStreetMap

> Источники этого раздела не добавлены в `collect/SOURCES.md` (сводную секцию добавляет мейн-агент на merge);
> полные вердикты разведки — SOURCES.md §14.2 («горит ли свет») и §14.6 (OSM Notes), вердикты обоих — STORE, ODbL.

Запуск — из корня репозитория:

```
uv run python -m collect.city        # data/city/{osm_notes,lit,construction}.json + city_stats.json
```

Повторный запуск идемпотентен: ответы лежат в `.local/http_cache.sqlite` (ключ = метод + URL + тело),
вежливые лимиты через `collect.net` (UA `astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)`, ≤1 req/s на Overpass).

## Источники

| источник | URL | лицензия | вежливость | частота обновления | что храним |
|---|---|---|---|---|---|
| OSM Notes API | `https://api.openstreetmap.org/api/0.6/notes/search.json?bbox=71.25,50.98,71.60,51.25&closed=-1&limit=300` | ODbL-1.0 (© OpenStreetMap contributors) | дефолт-политика `collect.net` (2 rps, 1 запрос за прогон) | еженедельно | id, координаты, даты, статус, классификация, URL заметки + сниппет первого комментария (≤200 зн.) — без треда, имён авторов и html |
| Overpass (зеркало) | `https://maps.mail.ru/osm/tools/overpass/api/interpreter` (overpass-api.de с этого хоста недоступен) | ODbL-1.0 | 0.2 rps (`collect.net`) | еженедельно | `lit=yes\|no` пешеходные/дорожные ways (упрощённая геометрия, порог ~5 м), `highway=construction` ways |

Атрибуция каждой записи: `license: "ODbL-1.0"`, `attribution: "© OpenStreetMap contributors, ODbL"`,
`source_url` и `fetched_at`.

## Классификация заметок (`notes.classify`)

Первый комментарий (нормализованный пробел) матчится на регулярки, первый матч выигрывает:
`closure` (авто-репорты Organic Maps/MAPS.ME «заведение исчезло», «нету», «вывеска снята», «переехал»…),
`new_place` («открылось», «прошу добавить», «началось строительство»…), `construction` («under construction»,
«снос»…), `hours` («opening hours»…), иначе `other`. Классификация — эвристика для сортировки «Города»,
не факт: сигнал продукту всегда «на OSM есть открытая заметка: место могло закрыться» (смогло/не смогло —
проверяет человек по ссылке).

## Выходные файлы

- `data/city/osm_notes.json` — список заметок (одна страница API: `closed=-1&limit=300`, сортировка по last_updated desc,
  `date_created` 2016→2026; **не** окно в 45 дней — фильтра по дате в коллекторе нет, `notes_open` внутри страницы
  = нижняя граница, пейджинг по датам — после 22.10; отсортированы по id);
- `data/city/lit.json` — ways с явным `lit=yes|no` (только пешеходные/дорожные значения highway; отсутствие тега
  в OSM НЕ хранится — «неизвестно ≠ не освещено»);
- `data/city/construction.json` — `highway=construction`;
- `data/city/city_stats.json` — счётчики, распределения, снапшот, атрибуция.

Потребитель — `app/walks/city_layers.py` (чистые функции, без сети; каталог данных переопределяется
`WALKS_CITY_DIR`, флаги CLI: `--city-notes`, `--city-lit`, `--city-construction`, `--city-summary`).
