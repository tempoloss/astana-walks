# Погода: прогноз MET Norway, наблюдения станции и официальные предупреждения (runtime)

Не коллектор: ничего не пишется в `data/`. Код — `app/walks/metno.py` (прогноз), `app/walks/metar.py`,
`app/walks/kazhydromet.py`, `app/walks/apparent.py` (общая формула ощущаемой температуры), склейка в
`app/walks/weather.py::fetch_weather`, тексты в `app/walks/i18n_weather.py`, тесты `app/tests/test_weather_metno.py`,
`app/tests/test_weather_obs.py` (записанный ответ — `app/tests/fixtures/metno_locationforecast_astana.json`).
Вердикты — `collect/SOURCES.md` §14.0–14.1 и §15–17; проверка этих вердиктов — раздел «Проверка» ниже.

## Источники

| что | эндпоинт | лицензия | атрибуция в ответе | обновление |
|---|---|---|---|---|
| Текущая погода: METAR/SPECI аэропорта Астаны (UACC) — станция Казгидромета, доставка по обмену ВМО | `GET https://aviationweather.gov/api/data/metar?ids=UACC&format=raw&hours=6`; запасной `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=UACC&data=metar&hours=6&format=onlycomma&…` (IEM ASOS) | NOAA/NWS, public domain | «по наблюдению Казгидромета (METAR UACC), 17.10 17:00»; доставка через NOAA/NWS — только в «деталях источника» (`weather.source_details`) | кэш 10 мин (60 с после сбоя); метео-отчёт старше 3 ч не «сейчас» → прогноз MET Norway + пометка «наблюдение устарело» |
| Штормовые предупреждения (ОЯ) по Астане | `POST https://www.kazhydromet.kz/ajax_storm.php` (`region=20`), страница `https://www.kazhydromet.kz/ru/storm` | Приказ МЭГПР № 267 (23.07.2021): общедоступная информация предоставляется безвозмездно, **обязательна ссылка на источник** | текст предупреждения дословно + ссылка `https://www.kazhydromet.kz/ru/storm` (`weather.warning_text`) | кэш 15 мин (5 мин после сбоя) |
| Бюллетень НМУ (смог) | `GET https://www.kazhydromet.kz/ru/ecology/ezhednevnyy-byulleten-sostoyaniya-vozdushnogo-basseyna-nmu` (+ `?date=YYYY-MM-DD` — архив по дате публикации) | то же | то же, ссылка на страницу бюллетеня | то же |
| Прогноз: температура, влажность, ветер, осадки следующего часа | `GET https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=51.13&lon=71.43` (MET Norway) | **CC BY 4.0 + NLOD 2.0**, коммерческое использование разрешено, кредит «MET Norway» (раздел «Проверка») | «прогноз: MET Norway (CC BY 4.0)» (`weather.credit_lines`, CLI «Данные погоды», страница «Данные») | до `Expires` ответа (в проверке — ≈ 3 мин вперёд, пол 60 с, потолок 6 ч), затем `If-Modified-Since` = прежний `Last-Modified` (304 без тела); сбой сети — 60 с; 403/429 — 15 мин; ряд без подтверждения > 3 ч не отдаётся |
| PM2.5 / EAQI (**только демо**, `WALKS_AIR_DEMO=1`; по умолчанию выключено) | `GET https://air-quality-api.open-meteo.com/v1/air-quality?…&current=pm2_5,european_aqi` | CC BY 4.0, **бесплатный API только для некоммерческого использования** | «качество воздуха: Open-Meteo (CC BY 4.0), бесплатный API — только для демо / некоммерческого использования» | кэш 10 мин |
| Восход / закат | локальная формула NOAA (`walks/sun.py`), без запросов | — | «расчёт» | — |

Открытие: страницы Казгидромета на «meteoalert» и «touristic_city» — карта-виджет и прогноз по туристическим точкам, ленты
предупреждений в них нет; рабочая лента — `/ajax_storm.php` (тот же, что дёргает сама страница `/ru/storm`).

## Как читается

- **METAR**: тип/станция/время `DDHHMMZ` (месяц выводится от «сейчас»), ветер (MPS/KT/KMH, порывы), видимость, группы
  «текущей погоды» до первой группы тренда (`NOSIG`/`TEMPO`/`BECMG`/`RMK` — это прогноз, не наблюдение), температура/точка росы.
  Видимая температура — Стедмана без радиации (`walks/apparent.py`, одна формула для METAR и прогноза): `T + 0.33·e − 0.70·v − 4.0`,
  `e` — из точки росы (METAR) или из относительной влажности (MET Norway: `e = RH/100 · 6.105·exp(17.27·T/(237.7+T))`).
- **Что считается «неблагоприятным»** (индикаторы → причины на kk/ru/en):

  | код METAR | индикатор | примечание |
  |---|---|---|
  | `TS` (не `VCTS`) | гроза | |
  | `FZRA`, `FZDZ` | ледяной дождь | |
  | `RA`, `SHRA`, `+DZ`, `GR`, `PL`, `GS` | дождь | слабый `-RA`, `-DZ`/`DZ` — нет (порог 2.5 мм/ч у Open-Meteo = «умеренный») |
  | `SN`, `SG`, `SHSN` (не слабые) | снег | слабый `-SN` — нет |
  | `BLSN` | метель | всегда; `DRSN` (позёмка) — только при видимости ≤ 2000 м |
  | `FG`, `FZFG` | туман | `MIFG/BCFG/PRFG` — нет; `BR` (дымка) — при видимости ≤ 2000 м |
  | `FU`, `HZ` | **смог** (дым/мгла): воздух плохой | PM2.5 из Open-Meteo остаётся |
  | ветер/порыв ≥ 12 м/с | сильный ветер | степень 1 критериев ОЯ Казгидромета: 12–14 м/с |
  | видимая температура ≤ −15 °C | холод | порог не менялся |
  | видимая температура ≥ +35 °C | жара | Казгидромет: +35…+40 °C — степень опасности 3 |

  При свежем наблюдении (≤ 3 ч) оно заменяет температуру/ветер прогноза и решает «непогоду» (`source="metar"`); осадки
  прогноза (`next_1_hours` MET Norway) остаются в поле `precipitation_mm` как справка (станция знает *что* падает, модель — *сколько*), в оценку не идут.
- **ОЯ**: период — из заголовка («с 20 ч. 17 октября до 08 ч. 18 октября 2026 г.»); активное предупреждение по Астане
  (`region=20`) = `adverse` (приоритет помещениям), причина «штормовое предупреждение Казгидромета».
- **НМУ**: бюллетень выходит накануне на следующие сутки («18 октября неблагоприятные метеорологические условия ожидаются в
  городах …, Астана»). Страница на сегодня публикуется вчера, поэтому берётся и архив `?date=<вчера>`. Астана в списке =
  сутки; Астана после «ночью» = только ночь (**принято 00:00–08:00 и 20:00–24:00**, в бюллетене часы не названы). Активный НМУ
  = `air_bad` (смог). Предупреждение, которое начнётся в ближайшие 24 ч, отдаётся в `warnings` с `active=False`.
- **robots.txt**: читается и соблюдается (кэш 24 ч); у kazhydromet.kz его нет (отдаётся HTML-404) — это «без ограничений»;
  ≤ 1 запрос в секунду к хосту (`kazhydromet.MIN_INTERVAL_S`), User-Agent `astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)`.
  METAR-API (aviationweather.gov, IEM) — публичные программные API без robots-ограничений, запрос раз в 10 минут.

## Поля `WeatherInfo`

`source` (`metar` | `met-no` | `manual`), `forecast_used` (прогноз MET Norway прочитан: источник осадков и при `source="metar"`),
`observed_at` (ISO, +05:00), `obs_stale`, `obs_raw` (METAR дословно), `conditions`
(индикаторы), `warnings` (список `WeatherWarning`, активные первыми) и свойство `warning` (первое). `WeatherWarning`:
`kind` (`storm`|`nmu`), `title`, `text` (дословно), `source_url` (обязательная ссылка), `issued`, `valid_from/valid_to`,
`active`, `attachment_url` (PDF ОЯ).

Для эффектов карты (необязательные, пусто = «неизвестно», а не «ясно»): `wind_from_deg` (откуда дует, градусы; с `wind_kmh`
из того же источника: METAR, иначе MET Norway `wind_from_direction`; штиль и `VRB` — `None`), `wind_gust_kmh` (порывы METAR),
`cloud_pct` (METAR: `FEW`≈19, `SCT`≈44, `BKN`≈75, `OVC`/`VV`=100, `SKC`/`CLR`/`NSC`/`CAVOK`=0; иначе MET Norway
`cloud_area_fraction`; METAR без группы облаков — `None`, прогноз не подмешивается), `precip_now` (`""`|`rain`|`snow`) и
`precip_level` (1 `-`, 2 без знака, 3 `+`) — что падает на станции сейчас по группам текущей погоды (`DZ RA PL GR` — дождь,
`SN SG GS IC` — снег, смесь = снег; `BL`/`DR` — не падение; тренды и `VC` не считаются). Осадки «сейчас» берутся только из
наблюдения, прогнозный слой их не рисует.

## Эффекты карты и карточка погоды: `GET /api/conditions`

Читает последнее значение фонового обновления (`walks.weather.refreshed_weather`) и ряд MET Norway в памяти
(`metno.upcoming`), в сеть не ходит; пока первое обновление не закончилось, `known: false` (страница спрашивает снова через
30 с). Ответ (`walks/conditions.py`): `sun` (высота солнца в градусах по `walks.sun.sun_altitude`, `morning`, `phase`:
`night`/`dawn`/`golden`/`dusk`/`day`, `rise`/`set` — восход и закат сегодня по расчёту) и блоки, каждый с `source`
(`metar`|`met-no`|`kazhydromet`|`open-meteo`) и временем наблюдения `at` (HH:MM, +05:00) или `null`, когда данных нет:
`temp` (температура и «ощущается»), `wind` (откуда, скорость, порывы), `sky` (облачность, %), `precip` (что падает сейчас),
`vis` (видимость METAR, м; 9999 = 10 км и больше), `air` (действующее НМУ с `title` и `url` — ссылкой на бюллетень — или дым /
дымка по METAR), `pm25` (только при `WALKS_AIR_DEMO=1`), `hours` (ближайшие часы MET Norway: `at`, `temp_c`, `precip_mm`,
`sym` — `clear|partly|cloud|fog|rain|sleet|snow|thunder`). Наблюдение старше 3 ч не показывается; «падает сейчас» — не старше
90 мин; видимость и осадки — только из METAR, не из прогноза.

Рисует и показывает всё это `web/static/js/map-weather.js` (небо, ветер, осадки) и `web/static/js/weather-panel.js`
(карточка). Ветер — немного тонких линий тока вдоль одного измеренного вектора с медленным изгибом у каждой линии (без
поля: станция одна); линия одной толщины, гаснет с обоих концов (без головы и точки: яркая голова с хвостом читается как
«головастик»); скорость пропорциональна измеренной, сильнее ветер — больше и длиннее линий, не толще и не ярче; штиль
(< 0,5 м/с), `VRB` и отсутствие данных — ничего.
На карте ничего постоянного нет: кнопка «Эффекты» (иконка и короткий факт, например «СЗ 9 м/с») открывает карточку: сейчас,
ветер со стрелкой и порывами, видимость, воздух (НМУ со ссылкой на Казгидромет, PM2.5), ближайшие часы, восход / закат, внизу
переключатель эффектов (выбор хранится в `localStorage` `anyq.fx`, при `prefers-reduced-motion` по умолчанию выключено).
Блок без данных в карточке отсутствует, при пустом ответе — одна фраза «Данных о погоде пока нет».

## Офлайн и демо

`WALKS_OFFLINE=1` (и `--offline`): ни одного запроса, поведение прежнее (погода неизвестна, восход/закат — по формуле).
Пресеты демо (`WALKS_DEMO_PIN=1`) идут через `manual_weather` — фиксированные входы, `source="manual"`, наблюдений,
предупреждений и кредитов нет (`warm_cache.py --verify-only` не трогает сеть).
При сбое сети последнее удачное наблюдение и последние ОЯ/НМУ остаются в памяти процесса: наблюдение отдаётся со своим
временем, пока ему ≤ 3 ч, дальше — прогноз и пометка «устарело»; ОЯ/НМУ — пока не закончился их период. Тот же принцип у
прогноза: последний ряд MET Norway обслуживает «сейчас» не дольше 3 ч после последнего подтверждения (200 или 304).

## Оговорки

- Одна станция (аэропорт ≈ 12 км от центра): городской микроклимат (смог по дворовым печам) METAR видит косвенно (`FU/HZ`).
- Период ночного НМУ — допущение выше; текст бюллетеня дословный, детали по районам не публикуются.
- Первый запрос Казгидромета в процессе занимает ~3 с (robots + лента ОЯ + 2 страницы НМУ по 1 запросу в секунду); дальше кэш 15 мин.

## Прогноз MET Norway: что читаем

`compact` содержит всё, что нам нужно, — `complete` не нужен: `air_temperature`, `relative_humidity`, `wind_speed` (instant) и
`next_1_hours.details.precipitation_amount`. Берётся запись ряда, ближайшая к «сейчас» (не дальше 2 ч); ощущаемая температура
считается общей формулой (выше); ветер м/с → км/ч; осадки = `next_1_hours` этой записи, а если записи нет (дальний горизонт,
последний шаг ряда — шаг 6 ч) — 0.0, как раньше при отсутствии поля у Open-Meteo. Координаты — 2 знака (в условиях максимум 4).
Запрос несёт User-Agent `astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)` и `Accept-Encoding: gzip`. Код 203 (устаревшая
версия продукта) пишется в лог, как требуют условия.

## Проверка заявлений прошлых раундов (2026-10-17)

Первичные источники прочитаны заново; «живой» запрос — с этого же дня.

| заявление | итог | чем проверено |
|---|---|---|
| Бесплатный API Open-Meteo — только некоммерческий | **подтверждено** | https://open-meteo.com/en/terms: «You may only use the free API services for non-commercial purposes.»; коммерческое: «Operating websites or apps that have subscriptions or display advertisements. … Integrating our service into commercial products»; таблица: «Commercial use ❌» для Free / ✅ для API Standard+. Лимиты free: 600/мин, 5 000/час, 10 000/день, 300 000/мес |
| MET Norway: CC BY 4.0 + NLOD 2.0, коммерческое использование | **подтверждено** | https://api.met.no/doc/License: «all data and products are licensed under the Norwegian Licence for Open Government Data (NLOD) 2.0 and Creative Commons 4.0 BY International licences. Credit should be given to … MET Norway … «Data from MET Norway», «Based on data from MET Norway»»; https://www.met.no/en/free-meteorological-data/Licensing-and-crediting: «Data produced by us is free to use» |
| Нужен идентифицирующий User-Agent | **подтверждено, но жёстче не в виде 403** | https://api.met.no/doc/TermsOfService: «All requests must (if possible) include an identifying User Agent-string … company email address or a link to the company website … If we cannot contact you in case of problems, you risk being blocked without warning»; «fake or random strings as identification … will result in a permanent ban». Живая проверка: запросы с `Python-urllib/3.12`, `python-requests/2.31` и **без** User-Agent получили **200** (Expires 15:31:34 GMT) — 403 за «общий» UA мы **не воспроизвели**; блокировка по условиям — по усмотрению сервера, поэтому UA проекта с контактом идёт всегда |
| 5+ знаков координат → 403 | **частично**: в условиях — «For new products, requests with 5+ decimals will return a 403 Forbidden»; `locationforecast/2.0` с `lat=51.13123&lon=71.43123` вернул **200** (живая проверка) | мы используем 2 знака в любом случае |
| Кэш: `Expires`, `If-Modified-Since` | **подтверждено** | условия: «don't repeat requests until the time indicated in the `Expires` response header. Cache data locally and use the `If-Modified-Since` request header … should be identical to the previous Last-Modified». Живая проверка: ответ 200 `Expires: Sat, 17 Oct 2026 15:31:34 GMT` при `Date: 15:28:21` (**Expires всего ≈ 3 мин вперёд**, не 30), `Last-Modified: Sat, 17 Oct 2026 15:00:05 GMT`; повтор с `If-Modified-Since` = этому значению → **304** без тела и с теми же `Expires`/`Last-Modified`; `Accept-Encoding: gzip` → 2.9 КБ вместо 40 КБ |
| Лимит запросов | **подтверждено** | «Anything over 20 requests/second per application (total, not per client) requires special agreement»; троттлинг — 429 («Always check response `Status` headers and limit traffic immediately»). Наш кэш: один запрос на `Expires` на процесс |
| Личные данные | к сведению | «If you call the API directly from an app or browser, the user's IP address will be stored in our logs, along with any possible geocoordinates» — запросы идут с сервера, только с фиксированной точкой центра Астаны (не с координатами пользователя) |
| US Embassy Astana PM2.5 даёт живой поток через AirNow | **опровергнуто для живого потока; архив подтверждён** | станция есть в `https://files.airnowtech.org/airnow/today/Monitoring_Site_Locations_V2.dat` (`KAZ010001`, «U.S. Department of State Kazakhstan - Astana», статус `Active`), но в `…/airnow/today/HourlyData_*.dat` за 17.10.2026 её **нет** (счёт строк `KAZ010001`: 0), а в `…/airnow/2025/20250301/HourlyData_2025030112.dat` — есть (1), в `20250305` — уже 0. Архивные CSV `…/airnow/EmbassyHistorical/Astana/{2018,2019,2022,2023,2024,2025}/Astana_PM2.5_*.csv` лежат (бакет S3 `files.airnowtech.org`), последняя строка `Astana_PM2.5_2025_03_MTD.csv` — `2025-03-04 06:00 PM`, каталога `2026/` нет. Прекращение публикации: Eos, «404: Air Quality Data from U.S. Embassies Removed» — «On 4 March, AirNow … shut down its webpage that reported data from air quality monitors at U.S. embassies» (по выдаче поиска; сам текст страницы не открывался). Для живого PM2.5 непригодно; как архив норм/сезонности — возможно, лицензия на CSV [не проверена] |
| OpenAQ v3 — бесплатный ключ | **подтверждено** | `GET https://api.openaq.org/v3/locations?coordinates=51.13,71.43&radius=25000` → **401** «A valid API key must be provided in the X-API-Key header»; v2 → **410** «Gone»; без ключа проверить покрытие Астаны нельзя; единственный источник OpenAQ по Астане — то же посольство (остановлено), по §15.4 SOURCES.md [не перепроверено: нужен ключ] |
| Казгидромет: бюллетень НМУ как источник PM2.5 | **не даёт чисел** | страница бюллетеня — список городов («… ожидаются в городах …, Астана»), концентраций нет; других страниц Казгидромета с PM2.5 по Астане без ключа не нашлось (`/ru/ecology`, `/ru/airquality` → 404) |
| Исправления передачи: ЦОДД без лицензии, OpenAddresses только для алиасов, №730 — часы администрации, ЕРСОП 0/217 | не затрагиваются этой задачей, не перепроверялись | — |

## PM2.5: решение

Легального PM2.5-источника по Астане без ключа **нет** (AirNow/Госдеп — остановлен, OpenAQ — ключ и тот же источник, Казгидромет —
только НМУ без концентраций). Поэтому:

1. Нога Open-Meteo Air Quality по умолчанию **выключена** (`WALKS_AIR_DEMO` не задан): в коммерческом продукте PM2.5 неизвестен
   («воздух неизвестен», подбор по воздуху не меняется), а сигнал смога дают METAR `FU`/`HZ` и НМУ Казгидромета.
2. `WALKS_AIR_DEMO=1` включает её для демо; ответ при этом подписан «качество воздуха: Open-Meteo (CC BY 4.0), бесплатный API —
   только для демо / некоммерческого использования» (CLI, страница «Данные»).
3. Собственный индекс смога по спутниковому AOD **не строится**: непроверенные числа выдавались бы за факт.
4. Если появится бесплатный ключ (OpenAQ v3) — это CONTRACT-источник (ключ в окружении, не в репозитории), проверить покрытие Астаны
   и лицензию каждого провайдера; пока ключа нет — не подключено.

## Что менять в атрибуции (`data/ATTRIBUTION.md` не правился)

Строка про Open-Meteo сейчас: «weather and air quality, CC BY 4.0, «Weather data by Open-Meteo.com»». Нужно:
- «**MET Norway** — weather forecast (locationforecast 2.0), CC BY 4.0 / NLOD 2.0, «Based on data from MET Norway», https://api.met.no/doc/License»;
- «**Open-Meteo** — air quality (PM2.5), CC BY 4.0, only in demo mode (`WALKS_AIR_DEMO=1`); its free API is for non-commercial use, https://open-meteo.com/en/terms».
