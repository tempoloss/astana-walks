# Дека «Анық»: исходники

`slides.html` — сама дека: 15 слайдов 1920 × 1080, анимации, показ из браузера (как показывать — `../README.md`,
почему так выглядит — `style.md`). Остальное её собирает и проверяет:

    uv run docs/presentation/deck/build.py --sheet app/.local/deck3_sheet.png

`build.py` готовит `img/` (скриншоты стенда в JPEG и QR) и `data/geo.js` (карта и маршрут живого ответа), проверяет,
что все числа из `slides_data.py` написаны на слайдах и что у каждой фотографии на слайде «Источники» есть автор,
лицензия и ссылка, снимает финальный кадр каждого слайда (`out/slide_NN.png`) и видео каждого слайда с анимацией
карты или счётчиков (`out/slide_NN.mp4`, 30 кадров в секунду, по шагам времени), собирает `../deck.pdf` (статичные
кадры), `../deck.pptx` (кадры, видео с автозапуском по кругу, заметки), `../speaker_notes.md` и контакт-лист. Нужны
ffmpeg и Chromium из Playwright (`uv run --with playwright playwright install chromium` один раз); `out/` в git не идёт.

## Файлы

| файл | что |
|---|---|
| `slides.html` | слайды, время появления (`data-at`), текст речи (`<aside class="notes">`) и его источники (`<aside class="src">`) |
| `deck.js` | показ: клавиши, масштаб; анимации — чистые функции времени: полёт по карте к маршруту, кольцо вайба, 120 сценариев, счётчики, районы, точки мест |
| `style.css`, `fonts.css` | оформление; шрифты из `fonts/` |
| `style.md` | что изменилось после v2 и почему |
| `figures.py` | данные карт для `data/geo.js`: места с их источником, районы, Есіл в кадре 1920 × 1080 |
| `slides_data.py` | числа слайдов из файлов-источников для проверки |
| `shots/` | `shoot.py` снимает стенд, `shots.jsonl` — запросы, точки, время и ответы целиком, `factcheck.py` и `factcheck.md` — проверка |
| `photos/` | фотографии Астаны с Wikimedia Commons: `credits.json` (файл, автор, лицензия, кадр), `fetch.py` скачивает оригинал в `photos/.cache` и кадрирует |
| `research.md` | задание, как показывают проекты на хакатонах и что из этого взято |
| `img/` | скриншоты стенда в JPEG (делает `build.py`) и QR стенда |

Анимация слайда 3 повторяет сцену демо-видео (`CityMap`, `zoomCam` из `app/.local/video/demo-2010/stage`): карта
города, полёт к Mega Silk Way, путь живого ответа `hero_walk` по улицам (`place_legs[0].shape`), места ответа; камера
садится так, что маршрут стенда на скриншоте ложится точно на наш (`build.py`, `HERO_HERE_PX` и `HERO_PIN1_PX`).

## Откуда числа

- `data/api_data_2026-10-19.json` — публичный `/api/data` стенда (страница «Данные»), сохранён 19.10.2026 в 17:15.
- `app/eval/results/canonical.md` — таблица оценки, колонки `poi.enriched`, и раздел «ИИ-режим»;
  `app/eval/results/runs_poi.enriched_offline.jsonl` — пять сценариев задания (`tz1`–`tz5`); разбираются при сборке.
- `data/poi.enriched.json`, `data/districts.geojson` — база и границы районов (корень репозитория).
- `data/rivers.geojson` — Есіл и притоки из OpenStreetMap (Overpass, 19.10.2026), © OpenStreetMap contributors, ODbL.
- Из кода при сборке: 0,3 с (`app/web/static/js/assistant.js`), ~100 м (`README.md`), 500 м (`app/walks/reqlog.py`),
  группы от 5 (`app/walks/demand.py`), афиша каждые 6 часов (`deploy/vps/anyq-events.timer`).
- Константы с источником в комментарии `slides_data.py`: число тестов (pytest на коде стенда 19.10.2026), раунды
  ИИ-персон (`docs/dialog.md`).

## Скриншоты

Все кадры приложения — свежие ответы живого стенда https://anyq.an8kk.dev, сняты 19.10.2026 вечером `shots/shoot.py`:
реальное время и погода стенда, геолокация браузера — точка старта, между запросами 45 с, профиль не создаётся. В деке
кадры `hero_walk_steps` (слайд 3: тот же ответ `hero_walk`, снятый через 0,65 с после отправки, когда ответ уже был на
экране, а карта показывала весь путь), `kids_kk`, `cafe_en`, `kids_ru`, `vibe`, `city`; каждый проверен в
`shots/factcheck.md`. Подложка карты в приложении: © OpenStreetMap contributors, OpenMapTiles, OpenFreeMap.

Кадр `sat_walk` (слайд 4) снят не со стенда: приложение из ветки со слоем «Спутник» запущено на ноутбуке в боевом
режиме (`python -m web`, без флагов `WALKS_*`, ключ Esri — файл из `ARCGIS_API_KEY_FILE`), 19.10.2026 22:50,
`shots/shoot.py --only sat_walk --base http://127.0.0.1:PORT/`; слой включён, один запрос у Байтерека, камера z17 над путём.
Ключа модели у этого запуска нет, текст ответа — шаблон из данных; места, часы и путь — тот же код и те же данные.
Проверка — `shots/factcheck.md`, раздел «Кадры не со стенда». Снимки: Imagery: Powered by Esri · Source: Esri,
Vantor, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community.

## Фотографии

Wikimedia Commons, авторы и лицензии — на слайде «Источники» и в `photos/credits.json`: Bernard Gagnon, «Nurjol
Boulevard, Astana» (CC0, обложка); Dauren Nabijan, «Khan-Shatyr shopping mall» (CC0, слайд 2); Matti Blume, «Night
at Esil District, Astana (P1190721)» (CC BY-SA 4.0, слайд 14). Все три кадрированы.

## Шрифты

Source Serif 4 (Adobe), IBM Plex Sans и IBM Plex Mono (IBM): SIL Open Font License 1.1, тексты лицензий в
`fonts/OFL-*.txt`. Все три набирают казахский (ә ғ қ ң ө ұ ү һ і).
