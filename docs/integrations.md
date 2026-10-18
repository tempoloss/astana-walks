# Integrations — astana-walks

Исследование провайдеров данных: что даём, доступ, лимиты/цена, лицензия, покрытие Астаны, дизайн адаптера, вердикт.
Формат проверки: ключевые keyless-запросы выполнены 2026-10-16 (запросы и ответы приведены дословно). Разметка [не проверено] — там, где нет живого прогона.

Общий контракт адаптера: `fetch(area|query) -> NormalizedRecord[]`, где `NormalizedRecord = {source, source_url, license, snapshot_date, confidence, name, lat, lon, category, hours?, rating?, description?, raw_ref}`. Batch-слои пишут в снапшот-хранилище; runtime-слои (погода, роутинг) не хранят или хранят TTL-кэш.

---

## 1. Wikidata SPARQL

- **Данные**: POI-факты с P625 (координаты), P31 (тип), названия ru/en, часы (P3090/P8631 редко), официальные ссылки, instanceof-иерархия (музей Q33506, памятник Q4989906, парк Q22698 и т.п.).
- **Доступ**: `https://query.wikidata.org/sparql` (GET/POST, без ключа). Ключ не нужен; обязателен описательный `User-Agent` (медиавики-политика).
- **Лимиты**: таймаут 60 с на запрос; 60 с серверного времени в минуту на клиента (burst 120 с); ≤30 ошибочных запросов/мин; ≤5 параллельных на IP; 429 + `Retry-After` при превышении; бан за игнор. Источник: https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual
- **Лицензия**: CC0 1.0 (структурированные данные Wikidata) — STORE да, MODIFY да, FILTER/rank да, атрибуция не обязательна, но желательна (ссылка на элемент). Аффилированный текст Википедии — CC BY-SA (см. карточку 2).
- **Покрытие Астаны** [spot-check]: WDQS в момент прогона отдавал 502/504 (5 попыток), счёт выполнен через публичное зеркало QLever. Точный запрос:
  ```sparql
  PREFIX p: <http://www.wikidata.org/prop/>
  PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  PREFIX wdt: <http://www.wikidata.org/prop/direct/>
  PREFIX wikibase: <http://wikiba.se/ontology#>
  PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
  SELECT ?typeLabel (COUNT(?item) AS ?count) WHERE {
    ?item p:P625/psv:P625 ?coord .
    ?coord wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .
    FILTER(?lat >= "50.98"^^xsd:decimal && ?lat <= "51.25"^^xsd:decimal && ?lon >= "71.25"^^xsd:decimal && ?lon <= "71.60"^^xsd:decimal)
    ?item wdt:P31 ?type .
    ?type rdfs:label ?typeLabel . FILTER(lang(?typeLabel) IN ("ru","en"))
  } GROUP BY ?typeLabel ORDER BY DESC(?count) LIMIT 25
  ```
  Результат (дубль ru/en на тип): hotel/гостиница 39, tram stop 18, building 16, village 11, mosque/мечеть 9, university 8, hostel 7, ministry 6, park/парк 5, monument/памятник 5, railway station 4, district 4 … итого top-25 = **274** строк-типов по bbox 50.98–51.25 / 71.25–71.60.
- **Интеграция**: batch-адаптер `fetch(bbox|city_qid) -> records`; кэш — снапшот раз в неделю/месяц (нет ограничения на хранение), рантайм-запросы к WDQS не нужны. Совместный пайплайн с OSM-коллектором: Wikidata — enrichment (ссылки, описания, идентификаторы).
- **Вердикт**: use now — CC0, ключ не нужен, покрытие ядра POI неполное (сотни, не тысячи объектов), идеально как enrichment + source_url.

## 2. Wikipedia REST summary

- **Данные**: `GET https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}` → `title, extract, coordinates (lat/lon), thumbnail, content_urls, type, license`. Для POI-карточек: описание + миниатюра + ссылка.
- **Доступ**: без ключа; требуется `User-Agent` (политика https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines).
- **Лимиты**: явной квоты нет; общий лимит API Wikimedia 100 req/s (руководство по использованию API ФВМ), блокировка за дефолтные UA.
- **Лицензия**: текст — CC BY-SA 4.0 (поле `license` в ответе); STORE да, но с атрибуцией (TASL: автор «Wikipedia contributors», ссылка на статью, указание CC BY-SA, пометка об изменениях при редактировании); ShareAlike распространяется на производный текст; FILTER/rank по своим критериям — да.
- **Покрытие Астаны** [spot-check]: `GET ru.wikipedia.org/api/rest_v1/page/summary/Байтерек_(монумент)` → `coordinates: {lat: 51.12825, lon: 71.430472}`, `type: standard`, extract «„Байтере́к“ — монумент и смотровая башня…». Успешный ключless-ответ.
- **Интеграция**: batch-enrichment: по названию/QID из Wikidata берём summary; храним extract + ссылку + лицензию в снапшоте (CC BY-SA позволяет хранить).
- **Вердикт**: use now — бесплатно, легально храним текст с атрибуцией и share-alike-пометкой.

## 3. Wikimedia Pageviews

- **Данные**: `GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/{access}/{agent}/{article}/monthly/{start}/{end}` — помесячные/подневные просмотры статьи; прокси «народной популярности» для ранжирования POI.
- **Доступ**: без ключа, `User-Agent` обязателен.
- **Лимиты**: 100 req/s (AQS) ; для массовых выгрузок — дампы `dumps.wikimedia.org/other/pageviews/`. Источник: https://wikitech.wikimedia.org/wiki/Data_Platform/Systems/AQS
- **Лицензия**: CC0 1.0 — STORE/MODIFY/FILTER свободно, атрибуция не требуется.
- **Покрытие Астаны** [spot-check]: `per-article/ru.wikipedia/all-access/user/Байтерек_(монумент)/monthly/20250901/20250930` → **6510 просмотров** за сентябрь 2025.
- **Интеграция**: batch: для каждого POI с sitelink'ом раз в месяц тянем monthly-просмотры → признак `popularity` для ранжирования.
- **Вердикт**: use now — CC0, дёшево, усиливает ranking.

## 4. data.egov.kz (API v4)

- **Данные**: открытые данные госорганов РК (Elasticsearch backend). По Астане реально есть: перечень госучреждений культуры (`perechen_gosudarstvennyh_uchrezhdenii_kultury` — адреса, телефоны), наборы музея-заповедника «Бозок», «Казреставрация» (памятники истории и культуры), реестры министерства туризма. Наборы полей часто включают `latitude/longitude` (см. образец API: датасет преступлений Астаны содержит `latitude: "51.126707959999997", longitude: "71.434872580000004"`).
- **Чего нет** (по поиску портала, 2026-10-16): отдельного датасета «парки/скверы Астаны», «детские площадки Астаны», отдельного «памятники Астаны с координатами» — полного списка памятников в ИС «Әділет» (постановление акимата), машинночитаемого на портале нет. Источники: https://data.egov.kz/datasets/view?index=perechen_gosudarstvennyh_uchrezhdenii_kultury , https://data.egov.kz/datasets/view?index=madeni_eskertkishter
- **Доступ**: `GET https://data.egov.kz/api/v4/{dataset}/v{N}?apiKey=…&size=&from=` + `source={JSON Query DSL}`; mapping — `/api/v4/mapping/{dataset}`; ключ — в кабинете разработчика после входа на портал (ЭЦП/eGov ID). Док: https://data.egov.kz/pages/samples
- **Лимиты**: публично не документированы; Elasticsearch-пагинация `from/size`, большие `size` вызывают таймауты шлюза [не проверено — из FAQ/сообщества].
- **Лицензия**: нацрежим открытых данных РК — данные госорганов для использования/переиспользования (закон «О доступе к информации», ст. 12-13 открытые данные); STORE да, MODIFY да, FILTER да. Точных номеров пунктов Terms на портале нет — отметить в коде `license: "opendata-gov-kz"`. [не проверено дословно]
- **Покрытие Астаны** [spot-check]: ключless `GET https://data.egov.kz/api/v4/datasets?size=5` → `{"error":"API key is required","status":"403"}` — API жив, но без ключа не читается; реальные счётчики датасетов снять после регистрации ключа.
- **Интеграция**: batch-адаптер по списку имён датасетов; нормализация полей (тексты координат → float); confidence=0.6 (данные ведомственные, даты обновления плавают).
- **Вердикт**: use under contract (бесплатно, но нужен API-ключ через eGov-аккаунт) — скудное покрытие по POI-профилю, полезно для культуры/туризма как официальный источник.

## 5. Open-Meteo Forecast

- **Данные**: прогноз погоды hourly/current/daily: температура, осадки, ветер, UV и пр. (`api.open-meteo.com/v1/forecast`), есть также sun/moon времена.
- **Доступ**: без ключа: `https://api.open-meteo.com/v1/forecast?latitude=…&longitude=…`.
- **Лимиты**: free tier — <10 000 вызовов/день, <5 000/час, <600/мин на IP; 429 при превышении. Источник: https://open-meteo.com/en/terms
- **Лицензия**: данные CC BY 4.0 (обязательна атрибуция «Weather data by Open-Meteo.com»); сам сервер AGPL-3.0 (не затрагивает нас при использовании API). STORE да (с атрибуцией), MODIFY да, FILTER да. Платный план только для коммерческого использования.
- **Покрытие Астаны** [spot-check]: `forecast?latitude=51.16&longitude=71.47&current=temperature_2m,wind_speed_10m` → `{"temperature_2m": 3.8, "wind_speed_10m": 9.4}` (2026-10-16T20:15).
- **Интеграция**: runtime-адаптер без хранения, TTL-кэш 10–30 мин на сетку точек маршрута; attribution в UI.
- **Вердикт**: ~~use now~~ **заменён в коде прогнозом MET Norway** (2026-10-17): бесплатный API Open-Meteo — только для некоммерческого использования (https://open-meteo.com/en/terms, «You may only use the free API services for non-commercial purposes»; коммерческие примеры: «apps that have subscriptions or display advertisements»). Замена — `collect/weather/README.md`.

## 6. Open-Meteo Air Quality

- **Данные**: PM2.5/PM10, NO2, O3, SO2, CO, EAQI/US AQI, UV, пыльца (только cams_europe). Для Астаны актуальна модель `cams_global` (~40 км сетка).
- **Доступ**: без ключа: `https://air-quality-api.open-meteo.com/v1/air-quality`.
- **Лимиты/лицензия**: те же, что карточка 5 (CC BY 4.0, non-commercial free, 10k/day). Источник: https://open-meteo.com/en/docs/air-quality-api
- **Покрытие Астаны** [spot-check]: `air-quality?latitude=51.16&longitude=71.47&current=pm2_5,pm10&domains=cams_global` → `{"pm2_5": 17.7, "pm10": 19.2}` (2026-10-16T15:00) — данные возвращаются корректно.
- **Интеграция**: runtime, TTL-кэш 30–60 мин, показывает «AQI сейчас» в UI и фильтрует советы маршрута.
- **Вердикт**: остаётся только как демо-переключатель `WALKS_AIR_DEMO=1` (бесплатный API — некоммерческий, ответ так и подписан): легального PM2.5-источника Астаны без ключа нет, разбор — `collect/weather/README.md`.

## 7. Valhalla (FOSSGIS public)

- **Данные**: пешеходные и авто/мультимодальные маршруты; costing `pedestrian` (`walking_speed`, `use_lit`, `step_penalty`, wheelchair-preset), `auto`, `bicycle`, transit-частично. Эндпоинты: `https://valhalla1.openstreetmap.de/route`, `/isochrone`, `/sources_to_targets`, `/status`.
- **Доступ**: без ключа; для приложения просят уведомить в GitHub Discussions и слать `X-Client-Id` + описательный `User-Agent`. Политика: https://wiki.openstreetmap.org/wiki/FOSSGIS/Server/Policy
- **Лимиты**: ~1 req/s на IP, запрет bulk/matrix-скрейпинга, лимит дистанции (~150 км) — все наши маршруты пешком в пределах города, ок.
- **Лицензия**: сервис — демо FOSSGIS e.V.; данные OSM ODbL → обязательна атрибуция «© OpenStreetMap contributors». Хранение результатов маршрута: политика не запрещает краткосрочный кэш, но для production — самохостинг (движок OSS, Apache-2.0).
- **Покрытие Астаны** [spot-check]: POST `/route` `{locations: [Байтерек 51.1282,71.4304 → 51.1700,71.4100], costing: pedestrian}` → `trip.summary.length = 5.919 km`, `time = 1256 s` — маршрут построен (короткий вариант ранее: 1.772 km, 1256 s, тоже OK).
- **Интеграция**: runtime, кэш маршрутов по (from,to,costing) TTL 1 час; при росте нагрузки — self-host через Docker (OSM-выписка Geofabrik Kazakhstan).
- **Вердикт**: use now — лучший FOSS pedestrian costing, уже в проекте; не для production SLA, план self-host.

## 8. OSRM demo

- **Данные**: маршруты по профилям car/bike/foot (`router.project-osrm.org/route/v1/{profile}/…`), table service (ограничен `max-table-size`).
- **Доступ**: без ключа; `User-Agent` обязателен.
- **Лимиты**: демо-сервер — 1 req/s на клиента; глобальный лимит ~5000 req/мин на всех; 429 при перегрузе; SLA нет (ветки dev, рестарты). Политика: https://routing.openstreetmap.de/about.html
- **Лицензия**: OSM ODbL → атрибуция «© OpenStreetMap contributors».
- **Покрытие Астаны** [spot-check]: `route/v1/foot/71.4304,51.1282;71.4100,51.1320?overview=false` → `code: Ok`, `distance: 2258.3 m` — foot-профиль работает.
- **Интеграция**: как fallback к Valhalla (тот же контракт `route(from, to, profile)`); runtime, кэш TTL 1 час.
- **Вердикт**: use now (fallback) — демо-инфраструктура без гарантий; self-host при необходимости.

## 9. 2GIS Places / Catalog API

- **Данные**: самый полный справочник Астаны: координаты, названия, адреса, рубрики, часы работы, телефоны, сайты, соцсети, способы оплаты, отзывы/рейтинг, входы в здания. Источник: https://dev.2gis.ru/api/places-api
- **Доступ**: ключ через кабинет https://platform.2gis.ru/ ; демо-ключ — 30 дней, 1 000 запросов на Places API (по 1 000 на Geocoder/Suggest/Categories/Regions), до 600 req/min. Тариф: пакет 10 000 запросов/мес — 6 700 ₽ … 5 000 000 — 250 000 ₽ (оплата за успешный запрос 200/204).
- **Лицензия/термины** (http://law.2gis.kz/api-rules/ru и оферты на law.2gis.ru): п. 3.1 оферты Справочное WebAPI — «Пользователю запрещается извлекать, сохранять полученные… Продукты и информацию из них… Кэширование Продуктов не предусмотрено»; п. 4.2 Соглашения API Карты — запрет сохранять/обрабатывать/изменять данные (кроме временного кэша геокодирования в рамках Сервиса). Т.е. STORE — нет (постоянное хранение запрещено), MODIFY/аннотирование — нет, FILTER/rank на своей стороне — нет (нельзя «фильтровать запросы» и переиспользовать выдачу, п. 4.3/4.8 по правилам api-rules); атрибуция — обязательна (бренд 2ГИС, логотип при отображении).
- **Покрытие Астаны**: полное (профильная страна, kz-домен), живой запрос не делаем — у нас нет ключа [не проверено]. [INFERENCE из документации:Places API покрывает Казахстан в полном объёме.]
- **Интеграция**: только runtime-only по требованию пользователя, никакой записи в БД — конфликтует с нашей архитектурой RAG-снапшотов.
- **Вердикт**: reject — запрет хранения/кэширования (п. 3.1, 4.2) несовместим с задачей «собрать POI-базу»; вернуться при заключении data-договора (data.2gis / On-Premise).

## 10. Google Places API (New)

- **Данные**: displayName, formattedAddress, location, types (Essentials); businessStatus, accessibility (Pro); **regularOpeningHours/currentOpeningHours, rating, userRatingCount, websiteUri** (Enterprise); photos, reviews, editorialSummary (Enterprise+Atmosphere). Прайс по полю-маске `X-Goog-FieldMask`: highest-priced-SKU-per-call.
- **Доступ**: ключ Google Cloud; SKUs: Essentials — 10 000 бесплатных вызовов/мес, Pro — 5 000, Enterprise — 1 000; далее Essentials $5 / 1000, Pro ~$17 /1000, Enterprise ~$20-25 /1000; Place Photo ~$7 /1000. Источники: https://developers.google.com/maps/billing-and-pricing/pricing , https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
- **Лицензия** (Google Maps Platform Terms + Service Specific Terms): хранение: `place_id` — можно бессрочно; `lat/lng` — кэш ≤30 календарных дней; все прочие поля Places (названия, часы, рейтинги, адреса) — постоянное хранение/кэш запрещено; prefetch/bulk-download запрещены (§3.2.3 Terms); отображение Places-контента — только на Google-карте либо с логотипом Google при списке; атрибуция автора фото обязательна. STORE — нет (кроме place_id и 30-дневных координат), MODIFY — нет, FILTER/rank — можно по метаданным, которые получены в runtime.
- **Покрытие Астаны**: покрытие Google Maps в Астане хорошее, но живой запрос не делали — нет ключа [не проверено].
- **Интеграция**: только runtime-подстановка деталей к уже сохранённым (из OSM/Wikidata) POI; никакой заливки в снапшот.
- **Вердикт**: use under contract — бесплатный лимит (10k/мес Essentials) хватает для демо, но запрет хранения делает его runtime-only enrichment; платно при Enterprise-полях (часы/рейтинг).

## 11. Yandex Maps / Geosearch API

- **Данные**: поиск организаций/геокодинг (справочник Яндекса: названия, адреса, категории, часы, рейтинги — в зависимости от тарифа).
- **Доступ**: ключ https://developer.tech.yandex.ru/ ; коммерческие тарифы https://yandex.ru/dev/commercial/doc/ru/ .
- **Лицензия** (https://yandex.ru/legal/maps_api/ru/): п. 5.1.5 условий — запрещено сохранять/извлекать/перерабатывать данные для формирования собственных баз; разрешено **временное кэширование ≤30 календарных дней** только для функциональности приложения; при прекращении использования — удалить кэш; ранжирование выдачи нельзя менять; данные обязаны отображаться на подложке Яндекс Карт. STORE — нет (кроме TTL-30-дневного кэша), MODIFY — нет, FILTER/rank — нет, атрибуция — обязательна.
- **Покрытие Астаны**: yandex.kz работает по Казахстану, покрытие организаций Астаны хорошее [не проверено — нужен ключ].
- **Интеграция**: несовместимо с batch-накоплением в собственной БД; возможно только runtime с отображением на Яндекс-карте — у нас Leaflet/OSM подложка, это запрещено.
- **Вердикт**: reject — запрет формирования собственных баз и обязательная Яндекс-подложка несовместимы с проектом.

## 12. Ticketon (партнёрский API)

- **Данные**: каталог событий/площадок Астаны: названия, категории, площадки, расписание, постеры, возрастные ограничения; позже — схемы залов, цены, покупка (Partners API). Условия публикует оферта (https://api-gw.ticketon.kz/f3/v1/images/oferta_ru.pdf). API-документация [не проверено публично]: https://ticketon.docs.apiary.io/ (черновик сообщества).
- **Доступ**: публичной самостоятельной регистрации ключей нет: заявка в b2b@ticketon.kz → субагентский/партнёрский договор с ТОО «Ticketon Events» → sandbox + токен + Swagger. Партнёрская комиссия оговаривается в договоре.
- **Лицензия**: определяется договором/офертой; афишный контент (названия, постеры) — обычно разрешено показывать с атрибуцией Ticketon, хранение и повторная публикация — по договору. [не проверено — полный текст оферты не разбирал по пунктам]
- **Покрытие Астаны**: основной рынок Ticketon — Казахстан (в т.ч. Астана), событий достаточно.
- **Интеграция**: batch-poll каталога событий (если даёт договор) → события в снапшот с `source_url` на страницу Ticketon + deeplink партнёра.
- **Вердикт**: use under contract — реального публичного ключа нет; для хакатона — deeplinks вручную, для продакшена — заявление в b2b@ticketon.kz.

## 13. sxodim.com (и афиши-агрегаторы)

- **Данные**: городская афиша Астаны (sxodim.com/astana): события, даты, площадки, возраст, билеты (ссылки на Ticketon/др.). Публичного API нет.
- **Доступ**: парсинг страниц; `robots.txt` (проверено 2026-10-16): `GET https://sxodim.com/robots.txt` → **200**, содержимое:
  ```
  User-agent: *
  Disallow:
  ```
  — запретов на обход нет.
- **Лицензия/ToS**: текст ToS на сайте о запрещённом автоматизированном сборе [не проверено дословно — страница ToS не найдена при прогоне]; отсутствие robots.txt ≠ разрешение на копирование контента: описания событий — копирайт редакции. Отображение агрегированных названий/дат/ссылок — добросовестное использование серого зоны; копирование полных текстов — нет.
- **Покрытие Астаны**: основная афиша города, ежедневные обновления.
- **Интеграция**: только лёгкий batch-агрегатор: name, date, venue, deeplink — без полных текстов; `confidence=0.6`, `snapshot_date` фиксируем.
- **Вердикт**: use under contract (серая зона) — robots.txt не запрещает, но явного разрешения/лицензии нет; для хакатона приемлемо с осторожным rate-limit и указанием источника.

## 14. Visit Astana / Kazakh Tourism

- **Visit Astana (visitastana.kz)**: официальный туристический портал столицы (ТОО «Центр развития Астаны»). Открытого API/RSS нет; сайт на 1С-Битрикс, события с JSON-LD микроразметкой Schema.org (можно вытягивать структурированные данные прямо из HTML), события дублируются в Ticketon. Источник: https://visitastana.kz/en/about-city/where-to-go/
- **Kazakh Tourism (qaztourism.kz / kazakhstan.travel / event.qaztourism.kz)**: публичного API/RSS нет; событийный календарь на SPA — данные только reverse-engineering внутренних эндпоинтов (нестабильно). Контакт для договора: info@qaztourism.kz. Источник: https://kazakhstan.travel/ru/events
- **Лицензия**: официальный контент © госструктур — свободное переиспользование не разрешено явно; только агрегация ссылок/фактов с атрибуцией.
- **Покрытие Астаны**: туристические POI + событийный календарь города — профильный источник.
- **Интеграция**: batch-парсер JSON-LD (Schema.org `TouristAttraction`/`Event`) с сайта visitastana.kz, кэш — данные публичного сайта с атрибуцией (авторские права соблюдаем: заголовок+ссылка, без копии полных текстов).
- **Вердикт**: use under contract — как вторичный источник для энричмента; полноценный feed/API отсутствует.

## 15. CTS / Avtobys / LRT Tarlan Astana (транспорт)

- **Данные**: оператор транспорта Астаны — ТОО «City Transportation Systems» (экс-«Астана LRT», бренд LRT — «Tarlan Astana»); маршруты, остановки, расписание, real-time трекинг (приложение Avtobys), тарифы Transcard. Публичного GTFS-фида **нет** (нет в Transitland/MobilityData, не выложен на cts.gov.kz).
- **Доступ**: B2B API по договору (info@avtobys.kz, https://avtobys.kz/for-partners ); GTFS-Realtime отдаётся партнёрам (2GIS, Яндекс) по соглашениям. Исторические open-data потоки движения автобусов публиковались на data.egov.kz (`avtobustardyn_osy_uakyttagy_ko`), сейчас частично в архиве.
- **Исследовательский GTFS**: открытый датасет «From Raw GPS to GTFS» (MDPI Data 2025, https://www.mdpi.com/2306-5729/10/8/119 ) — треки/расписания части маршрутов Астаны в GTFS.
- **Лицензия**: данные оператора закрыты; open-data-выгрузки gov.kz — режим открытых данных (см. карточку 4).
- **Покрытие Астаны**: полное по автобусам; LRT (Tarlan Astana, 22,4 км, 18 станций) — расписание на cts.gov.kz, машиночитаемого фида нет.
- **Интеграция**: batch: если удастся получить GTFS-выписку (или research-датасет) — cargar stops/routes в снапшот для пешеходных маршрутов «+транспорт»; real-time — вне скоупа.
- **Вердикт**: use under contract — без GTFS-фидa полноценная транзит-интеграция невозможна; запускать только через официальный запрос к CTS.

## 16. Kaspi.kz (прочее)

- **Данные**: Kaspi не публикует POI/афиша-API; только Kaspi Гид (рекламный контент, без публичного API) и платежный API для продавцов. Для нашей задачи (POI/события/транспорт) неприменимо.
- **Вердикт**: reject — нет релевантного открытого API.

---

## Сводная таблица

| Provider | Verdict | Key constraint |
|---|---|---|
| Wikidata SPARQL | use now | WDQS 60s timeout / 60s server-time per min / 5 parallel per IP; CC0 |
| Wikipedia REST summary | use now | CC BY-SA 4.0: атрибуция + share-alike, ссылка на статью |
| Wikimedia Pageviews | use now | CC0; 100 req/s; для bulk — дампы |
| data.egov.kz API v4 | use under contract (нужен бесплатный apiKey eGov) | покроет лишь культуру/туризм, парки/площадки не опубликованы |
| Open-Meteo Forecast | replaced by MET Norway | free API non-commercial only; прогноз теперь MET Norway locationforecast 2.0 (CC BY 4.0 + NLOD 2.0) |
| Open-Meteo Air Quality | demo only (`WALKS_AIR_DEMO=1`) | free API non-commercial only; других открытых PM2.5 по Астане без ключа нет |
| Valhalla (FOSSGIS) | use now | демо-политика ~1 req/s, X-Client-Id; self-host для production |
| OSRM demo | use now (fallback) | демо-сервер без SLA, 1 req/s, OSM-атрибуция |
| 2GIS Places/Catalog | reject | п. 3.1/4.2 — запрет хранения/кэширования продуктов |
| Google Places API (New) | use under contract | хранение запрещено (кроме place_id и lat/lng ≤30 дней); Enterprise-поля платные |
| Yandex Geosearch | reject | п. 5.1.5 — запрет собственных баз + обязательная подложка Яндекса |
| Ticketon | use under contract | партнёрский API только по договору (b2b@ticketon.kz) |
| sxodim.com | use under contract (серая зона) | robots.txt не запрещает (Disallow: пуст), но ToS/авторские права текстов |
| Visit Astana / Kazakh Tourism | use under contract | публичного API нет; JSON-LD парсинг с атрибуцией |
| CTS / Avtobys / LRT Tarlan | use under contract | GTFS публично не выложен; доступ по запросу к оператору |
| Kaspi | reject | нет релевантного API |
