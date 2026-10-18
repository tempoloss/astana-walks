# Разведка официальных сайтов сетей и площадок Астаны (ScoutChains, 2026-10-17)

Метод: ~200 вежливых GET (UA `astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)`, ≤1 req/s на домен, кэш `.local/http_cache.sqlite`, `collect/net.py`), для каждого домена — `robots.txt` + главная/страница контактов/локатор; в HTML искали `application/ld+json`, `openingHours`, `lat`/`lng`, `часы работы`, `режим работы`, `жұмыс уақыты`. Все сниппеты ниже — дословные фрагменты сохранённых ответов (fetched_at = 2026-10-17). Только официальные сайты; агрегаторы (2GIS/Yandex/Restoran.kz) исключены.

Вердикт: **STORE** = часы (или координаты) лежат в статическом HTML/JSON, можно хранить с evidence · **RUNTIME** = данные есть, но рендерятся JS/блокировкой · **DEAD** = домен мёртв/нет точки в Астане/нет сайта.

Парсинг часов: только через `collect/sites/hours.py` (правила 2026-10-17, после фикса запятых после дней и kk «Жк»; поведение проверялось прогоном `analyze()` на дословных сниппетах этого файла). Парсится корректно: famecity «Часы работы - ежедневно с 11:00 до 22:00» → `Mo-Su 11:00-22:00`; khanshatyr KZ «КҮНДЕЛІКТІ: 10:00 — 22:00; Жм, Сб: 10:00 — 23:00» → `Mo-Su …; Fr,Sa …`; uzbechka1 «Часы Пн—Вс 11:00 — 23:00»; ailand «10:00-22:00 ПН-ЧТ» → `Mo-Th 10:00-22:00`; white «ПН-ВС 09:00 - 00:00» → `Mo-Su 09:00-24:00` (дни названы, флага нет); gorky KZ «Сейсенбі-жексенбі: 10:00-21:00» → `Tu-Su`; bapool «ПН-ВС, с 6:00 до 23:00» → `Mo-Su 06:00-23:00` и nmrk kk-дни «Сс-Жк» → `Tu-Su` — починено в hours.py; KFC/Hardees таблицы «понедельник 00:25-23:15» → `Mo 00:25-23:15`. Для Papa John's/Starbucks/Zebra per-day поля нужно собрать в одну строку до конвертации («Понедельник: 10.00 - 00.00; …» → `Mo… 10:00-24:00`; одинокий «09:00-23:00» без дня → `(None, ["needs_days"])`). Осознанные отказы (тихий `(None, [])`, raw сохраняется): srq.kz «Магазины: 1,2,3 этажи 10:00 - 22:00» и строки с текстовым префиксом-лейблом — «Время работы кассы Пн - Пт: 10:00 — 19:00» (astanaopera) и «ҚР Ұлттық музейінің жұмыс уақыты 10:00 - 18:00 Сс-Жк» (nmrk): без лейбла обе строки парсятся, краулер обязан обрезать лейбл/часы касс до вызова (это часы кассы/музея, не площадки целиком); keruen.kz «Galmart - 09.00-23.00» — зоны ТЦ с точками вместо двоеточий, разбирать каждую зону отдельно.

Key | Значение
--- | ---
hours? | `Да(html)` в статическом HTML/инлайн-JSON; `Да(JS)` только после рендера; `част.` частичные (касса/офис, не заведение); `Нет`
coords? | `Да(html)`/`Нет`
robots | `OK` (пусто/Allow), `част.` (есть Disallow, но нужные пути открыты), `Disallow: /` (полный запрет), `404`=нет файла (можно), `403`/`SSL` (не прочитан)

## Кофейни

| name | domain | locator URL | hours? | coords? | format | robots | snippet |
|---|---|---|---|---|---|---|---|
| Starbucks KZ | starbucks.com.kz | https://www.starbucks.com.kz/stores | Да(html) | Да(html) | инлайн-JSX в HTML: `weeklyWorkingHours` per-day + `"location":{"lon":..,"lat":..}`; города фильтруются клиентски | OK (`Allow: /`) | `"sunday":"09:00-23:00"},"location":{"lon":71.398898,"lat":51.116641}` (Starbucks NCity, Астана; 361 диапозон времени, 31 аст. координата) |
| Zebra Coffee | zebracoffee.kz → zebra-coffee.clients.site | https://zebra-coffee.clients.site/ | Да(html) | част. (адреса без lat/lng) | инлайн-JSON `readableSchedule[]` per-day на лендинге; сам .kz — редирект | OK (clients.site `Allow: /`; zebracoffee.kz robots = HTML-страница) | `\"readableSchedule\":[{\"day\":\"Понедельник\",\"isToday\":false,\"hours\":[\"07:30–23:00\"],\"closed\":false},{\"day\":\"Вторник\"...` |
| Master Coffee | mastercoffee.kz | https://mastercoffee.kz/contacts | Да(html) | Нет | инлайн-JS конфиг `config_open` | OK (opencart-паттерны) | `config_open&quot;:&quot;ПН-ПТ 09:00 - 18:00 \| СБ 10:00 - 16:00&quot;` |
| Coffee BOOM | coffeeboom.kz | https://coffeeboom.kz/about/contacts/ | Нет | Да(JS) | SPA (iiko/«foodpicasso»), точек в HTML нет | OK (`/mailer`, `/shop/my` закрыты) | — |
| Coffee Like | coffee-like.com | https://coffee-like.com/contacts | Нет | Нет | SPA; кофейная сеть RU/KZ, карта через JS | OK | — |
| Coffeedelia | coffeedelia.tilda.ws | — | Нет | Нет | тильда-визитка; **филиалов в Астане нет** (Алматы) | OK (tilda-стандарт) | — |
| Drinkit | drinkit.ru | — | Нет | Нет | WP SPA; в наших данных 2 Астаны | OK (`/wp-admin`) | — |
| Costa Coffee KZ | costacoffee.kz | https://www.costacoffee.kz/ | Нет | Нет | **DEAD для краула**: Cloudflare-IP, но `SSL: UNEXPECTED_EOF`/`WinError 10054` | SSL fail | — |
| Black Cup | (нет сайта) | — | — | — | **DEAD**: только 2GIS/Instagram | — | — |

## Фастфуд и сети общепита

| name | domain | locator URL | hours? | coords? | format | robots | snippet |
|---|---|---|---|---|---|---|---|
| KFC KZ | kfc.kz | https://www.kfc.kz/stores | Да(html) | Да(html) | карточки `<div data-id data-lat data-lng data-address>` + per-day таблицы `<td>понедельник</td><td>HH:MM-HH:MM</td>` (прецедент §11 SOURCES) | OK (`/manuals/`) | `<option value="2410">Астана</option>`; `data-lat="51.116390158138" data-lng="71.399327210976" data-address="Turan Ave, 020000 Astana, Kazakhstan"`; `<td >понедельник</td> <td class="text-right "> 00:25-23:15` |
| Hardee's KZ | hardees.kz | https://www.hardees.kz/stores | Да(html) | Да(html) | та же платформа что KFC (оба бренда — satu): `data-lat/data-lng` + недельные таблицы, город в `<option value="2410">Астана` | OK (только Sitemap) | `<div class="row align-items-center mt-3" data-lat="51.1280172" data-lng="71.4253271">`; `<td >понедельник</td> <td class="text-right "> 10:00 ` (357 врем.диапазонов, 100 аст.координат) |
| Papa John's KZ | papajohns.kz | https://order.papajohns.kz/api/outlet/list/?all=true | Да(html=JSON) | Да(html=JSON) | **чистый JSON-эндпоинт** без auth: 19 заведений, 5 аст. — поля `hours_text` {ru,kk} per-day + `points` [lat,lng] + `address` | OK (robots = HTML, файла нет) | `"hours_text":{"ru":"Понедельник: 10.00 - 00.00; Вторник: 10.00 - 00.00...` + `"points":[51.128054, 71.411582]` (ТЦ Азия Парк, Астана) |
| Burger King KZ | burgerking.kz | https://www.burgerking.kz/restoranlar | RUNTIME | RUNTIME | **SSL: сертификат просрочен** (`certificate has expired`) — краул невозможен без обхода (запрещён); список ресторанов лежит PDF-ом на сайте | SSL fail | — |
| Salam Bro | salambro.kz | — | — | — | **DEAD**: NXDOMAIN; жив лишь `salambroanel.tilda.ws` (требует JS-форм, часов нет); по поиску сеть закрыла стационарные точки Астаны | NXDOMAIN | — |
| Del Papa / ABR | abr.kz | https://abr.kz/restaurant/del-papa | Нет(JS) | Да(JS) | SPA (холдинг IFFD); `/contacts` есть, часы только в JS-бандле | 404 (нет файла) | — |
| Dodo Pizza | dodopizza.kz | https://dodopizza.kz/astana/contacts | RUNTIME | RUNTIME | **403 bot-block** и на страницу, и на robots (Cloudflare); JSON-API закрыт (`/api/locations` 403) | 403 | — |
| Domino's KZ | dominos.kz | — | — | — | **DEAD**: в РК сеть не представлена; домен = self-signed cert | SSL | — |
| Tanuki | tanukifamily.kz | https://tanukifamily.kz/tanuki_kz/astana/restaurants/ | RUNTIME | RUNTIME | **HTTP 401** на раздел Астаны (auth-gated iiko-платформа) | OK (WP, query-паттерны) | — |
| Yakitoriya KZ | yakitoriya.kz | https://yakitoriya.kz/ | Нет(JS) | част. | SPA iiko (`aiChat` строки «режим работы»), одна точка Астана (ADP) | OK | — |
| Gippo | gippo.kz | https://gippo.kz/contacts/ | Нет | Нет | WP; на контактах только офис «Пн - Пт: 09:00 - 18:00 ... 8 (727) 255 80 86» (Алматы); **доставки в Астане нет** (города: Алматы/Шымкент/Петропавловск) | OK | — |
| Shashlychok | shashlychok.kz | https://shashlychok.kz/ | Нет(JS) | Да(JS) | SPA iiko; 21 POI в наших данных | OK | — |
| Pinta | pinta.kz | https://pinta.kz/ | Нет(JS) | Нет | Nuxt SPA | 404 | — |
| Ocean Basket KZ | oceanbasket.kz | https://oceanbasket.kz/ | Нет(JS) | Нет | SPA (Restoran Holdings); /restorany,/contacts 404 | OK | — |
| CrepeCafe | crepecafe.kz | https://crepecafe.kz/rus/contacts | Да(JS)+част.(html) | Да(html) | Next.js: на /rusflight есть `initialWorkingHours:null`, но страница контактов содержит 9 аст. широт (51.13...) в инлайн-пропсах | OK | `\"initialWorkingHours\":null,\"initialOrderData\":\"$undefined\",\"lang\":\"rus\"` + `cs=51.13188863327351` на /rus/contacts |
| Узбечка №1 | uzbechka1.kz | https://uzbechka1.kz/ | Да(html) | Нет | лендинг: футер с адресами 4 точек Астаны + общие часы; JSON-LD `openingHours` | OK (`Allow: *`) | `ул. Жумекен Нажимеденов, 26</button>...<h4>Часы</h4><p>Пн—Вс</p><p>11:00 — 23:00</p><p>Доставка по всей Астане</p>` |
| Roni Pizza | ronipizza.kz | https://ronipizza.kz/contacts | Нет | част.(JS) | SPA; «аст.» совпадений много, но это SVG-пути, точных lat/lng в тексте нет | 404 | — |
| Farsh | farsh-burger.kz | https://farsh-burger.kz/ | Да(html=JSON-LD) | Да(JS) | JSON-LD `FoodEstablishment` + шаблон `График работы` в пропсах | OK (закрыт checkout/profile) | `"shopAlerts.scheduleLink\":\"График работы\",\"shopAlerts.shopListingClosed\":\"Технический день\"` |
| BAO Noodles&Sushi | baofood.kz | https://baofood.kz/contacts | Да(html=JSON-LD) | Да(html) | **JSON-LD `Restaurant` + `openingHoursSpecification`** per-day | OK | `"openingHoursSpecification": [ { "@type": "OpeningHoursSpecification", "dayOfWeek": [ "Monday", "Tuesday", "Wednesday",` |
| Trattoria.kz | trattoria.kz | https://trattoria.kz/ | Нет(JS) | Да(JS) | SPA с якорем #location | OK | — |
| Paul KZ | paul.kz | https://paul.kz/ | Нет | Нет | SPA; /contacts /cafes 404 (франшиза, мало точек) | OK | — |
| Dегирмен | degirmen.kz | https://degirmen.kz/filialy/ | Нет | Да(html) | WP: страница филиалов, 5 аст. координат в HTML, часы в JS-виджете | OK | — |
| WHITE / Gasteria | white.kz | https://white.kz/contacts/ | Да(html) | Нет | Bitrix: блок времени у каждого заведения холдинга (Gasteria, Leto Cafe…) | 404 (нет файла) | `<time datetime="T12:00/T02:00">ПН-ВС 09:00 - 00:00</time>` (gasteria.astana) |
| Golpas | golpas.cafe | https://golpas.cafe/contacts | Нет | Нет | SPA | OK | — |
| I'm (IFFD) | im.kz | https://im.kz/restaurants | Нет(JS) | Да(JS) | Nuxt SPA (13 аст. совпадений из конфигов) | OK | — |
| Goodproject (Lilou/Eva/Malena) | goodproject.kz | https://goodproject.kz/contacts/ | Нет | Нет | WP; список ресторанов только ссылкой | OK | — |
| Plov.kz (Dala) | plov.kz | https://plov.kz/ | Нет(JS) | Нет | SPA iiko-платформы | OK | — |
| Sandyq Group | sandyqgroup.com | https://sandyqgroup.com/contacts/ | Нет(маркетинг) | Нет | WP-корпорация; «часы работы» встречается только в промо-тексте франшизы | OK | — |
| Korean House | korean-house.kz | — | — | — | **DEAD**: NXDOMAIN | — | — |
| La Creme | lacreme.kz | https://www.lacreme.kz/delivery | Нет(JS) | Нет | Tilda-shop, выбор точки через JS | OK | — |
| Lepim i varim | lepimivarim.ru | https://lepimivarim.ru/ | Нет | Нет | RU-сеть, /contacts 404; в Астане точки под др. именем | OK | — |
| Ambrella | ambrella.kz | — | Нет | Нет | коннект-таймаут (6 попыток) | fail | — |
| Ferrum Cafe | ferrum.kz | — | Нет | Нет | SSL verify fail | SSL | — |
| FairPlay (спорт-бары) | fairplay.kz | — | Нет | Нет | SSL hostname-mismatch; 24 POI в данных | SSL | — |

## ТРЦ

| name | domain | locator URL | hours? | coords? | format | robots | snippet |
|---|---|---|---|---|---|---|---|
| Khan Shatyr | khanshatyr.com | https://khanshatyr.com/contacts | Да(html) | Нет(html) | статический HTML RU/KZ | OK (`Disallow:` пусто) | `Астана қ-сы, Тұран д-лы 37 КҮНДЕЛІКТІ: 10:00 — 22:00; Жм, Сб: 10:00 — 23:00` / `ЕЖЕДНЕВНО: 10:00 — 22:00; Пт, Сб: 10:00 — 23:00` |
| Keruen | keruen.kz | https://keruen.kz/rezhim_raboty + /contacts | Да(html) | Да(html) | статический HTML: график по зонам ТЦ + `data-latitude/data-longitude` на /contacts | 404 (нет файла) | `График работы ТРЦ: ... Супермаркет: Galmart - 09.00-23.00 ... Рестораны: 10.00-24.00` ; `data-latitude="51.128343" data-longitude="71.425408"` |
| Saryarka mall | srq.kz | https://srq.kz/ru | Да(html) | Нет | статический HTML (модалка `#modalWorkingHours` в markup) | OK (только /storage/app/) | `Время работы: Магазины: 1,2,3 этажи 10:00 - 22:00 ... Кафе, бары, рестораны: 3 этаж 10:00 - 24:00 Кинотеатр: 3 этаж 10:00 - 03:00` |
| Abu Dhabi Plaza | abudhabiplaza.info | https://abudhabiplaza.info/contacts | Нет(общий) | Да(html) | Next.js; координаты внутри URL 2GIS-виджета (lat/lng в query), часы каждого якоря | OK (`/menu`) | `options=%7B%22pos%22%3A%7B%22lat%22%3A51.12212523774275%2C%22lon%22%3A71.42799854278566%2C%22zoom%22%3A16%7D` |
| Mega Silk Way | mega.kz | https://mega.kz/ru/Tenant/MEGA-Silk-Way | RUNTIME | RUNTIME | Nuxt-VUE-шелл (6.5 КБ, всё в `/​_nuxt/*.js`); часы «10:00–22:00» только после рендера | OK (пустой) | — |
| Keruen City (Коргалжынское) | keruencity.kz | — | Нет | Нет | домен резолвится, коннект не поднимается (timeout/SSL) | fail | — |
| Asia Park | asiapark.kz | https://www.asiapark.kz/ | Нет | Нет | лендинг без графика | 404 | — |
| Astana Mall | astanamall.com | — | Нет | Нет | домен припаркован (robots прокси-сервера `cpx.php`/`popunder`); astanamall.kz → 403 Cloudflare | OK(мусор) | — |
| Аружан | arujan.kz | — | Нет | Нет | SSL verify fail | SSL | — |

## Кинотеатры

| name | domain | locator URL | hours? | coords? | format | robots | snippet |
|---|---|---|---|---|---|---|---|
| Kinopark (Kinoplexx) | kinopark.kz / kinoplexx.kz | https://www.kinopark.kz/ru | RUNTIME | RUNTIME | Next.js; афиша/кинотеатры через `booking.api.kinopark.kz` (публичные пути `/v2/cinemas` — 404, нужна реверс-инженерия бандла); JSON-LD Organization; в HTML только справочные часы | OK | `"section2item8":"Прайм-тайм – временные интервалы наибольшей активности: с 18:00 до 22:30 в будние дни и с 12:00 до 23:00 в праздники` |
| Chaplin Cinemas | chaplin.kz | https://chaplin.kz/astana/cinemas/5 | RUNTIME | RUNTIME | SPA-афиша по залам (MEGA Silk Way и др.), статических часов/координат нет | OK | — |
| Arman 3D | arman3d.kz | https://arman3d.kz/61 | RUNTIME | Нет | киноцентр, расписание через JS | OK | — |
| Евразия Cinema 7 | eurasia-cinema7.kz | https://eurasia-cinema7.kz/index.php?view=contacts | Нет | Да(html) | PHP-сайт; на контактах 2 аст. координаты, часов нет | OK | — |

## Развлечения

| name | domain | locator URL | hours? | coords? | format | robots | snippet |
|---|---|---|---|---|---|---|---|
| Fame City | famecity.kz | https://famecity.kz/ru | Да(html) | Нет | статический HTML | OK (`Allow: /`) | `Fame City обещает незабываемое и веселое времяпрепровождение с вашей семьей и друзьями. Часы работы - ежедневно с 11:00 до 22:00.` |
| Ailand (быв. Duman) | ailand.kz | https://ailand.kz/ru/schedule-ru/ | Да(html) | Да(html) | WP, страница «График работы»: сеансы океанариума/аттракционов текстом | OK (`/wp-admin`) | `10:00-22:00 ПН-ЧТ` + `Билеты на кассе можно приобрести до 21:45` (ast. координата 51.1874 на стр.) |
| Kidburg | kidburg.kz | https://kidburg.kz/ | RUNTIME | RUNTIME | **SSL self-signed** — краул запрещён политикой (без обхода); сеть сидит на taplink (блок-лист) | SSL | — |
| Happylon | happylon.kz / .com | — | RUNTIME | RUNTIME | .kz — соединение сброшено (WinError 10061/aborted), .com — self-signed cert | SSL/fail | — |
| KANGO | kangojumpastana.kz | — | — | — | **DEAD**: NXDOMAIN (и kangoastana.kz) | — | — |
| Zhuldyz (планетарий?) | zhuldyz.kz | https://zhuldyz.kz/?type=contacts&id_1=8 | Нет | Нет | uCoz-лендинг | OK | — |

## Культура

| name | domain | locator URL | hours? | coords? | format | robots | snippet |
|---|---|---|---|---|---|---|---|
| Нац. музей РК | nmrk.kz | https://www.nmrk.kz/about-museum/contacts/ | Да(html) | Нет | статический HTML KZ/RU | OK (пустой) | `ҚР Ұлттық музейінің жұмыс уақыты 10:00 - 18:00 Сс-Жк` + `Касса: 10:00 - 17:00` |
| Астана Балет / Astana Opera | astanaopera.kz | https://astanaopera.kz/ru/contacts | Да(html) | Нет | Vue SPA, но блок контактов SSR | OK (`Disallow:` пусто) | `Время работы кассы</p>...<p>Пн - Пт: 10:00 — 19:00</p> <p>Сб - Вс: 10:00 — 18:00</p>` |
| Nur Alem | expo2017astana.com | https://expo2017astana.com/ | RUNTIME | Нет | статич. сайт есть (JSON-LD WebSite), часы музея в HTML не найдены | OK | — |
| ҚР Орталық концерт залы | ckzkazakhstan.kz | http://www.ckzkazakhstan.kz/ | Нет | Нет | старый PHP, /page.php 404, часы не в HTML | OK (404→нет) | — |
| Т-р Горького | gorkytheatre.kz | https://gorkytheatre.kz/contacts | Да(html) | Нет | Bitrix, касса/репертуар текстом | OK (admin-пути) | `Сейсенбі-жексенбі: 10:00-21:00 Үзіліс: Үзіліс: 14:00-15:00` (касса; + расписание показов на KZ) |
| Т-р им. Куанышбаева | kaztheatre.kz | https://kaztheatre.kz/ru/page/kontakty | Нет | Нет | JSON-LD Organization; часов в HTML нет | OK | — |
| Президентский центр | po.qr-pib.kz | https://po.qr-pib.kz/ru/contacts | Нет | Нет | часы не в статике | OK | — |
| Б-ка Первого Президента | presidentlib.kz | — | Нет | Нет | **redirect loop** (Drupal), краул не проходит | OK | — |
| Б-ка ЕНУ | lib.enu.kz | https://lib.enu.kz/kz | Да(html)-част. | Нет | Nuxt: славик `working-hours` + заголовок «Режим работы / Жұмыс кестесі» в контентном JSON | OK | `"Жұмыс кестесі","Режим работы","Working hours","working-hours"` |
| Байтерек | baiterek.kz | https://baiterek.kz/ | RUNTIME | Нет | /visit = шелл 1.8 КБ, всё через JS | 404 (нет файла) | — |
| Пирамида | astana-piramida.kz | https://astana-piramida.kz/contacts | Нет | Нет | WP, часовой блок не найден | OK (`/wp-admin`) | — |
| Соборы (Конст.-Елен.) | sobor.kz | https://sobor.kz/kontakty | Нет | Нет | Drupal, часов нет | OK | — |
| Тал-Арт галерея | talangallery.com | — | Нет | Нет | HTTP 503 постоянно | fail | — |

## Спорт

| name | domain | locator URL | hours? | coords? | format | robots | snippet |
|---|---|---|---|---|---|---|---|
| БА Pool (Барыс Арена) | bapool.kz | https://bapool.kz/ | Да(html) | Да(html) | bootstrap-лендинг с секцией ГРАФИК РАБОТЫ | **`Disallow: /`** — полный запрет → нельзя хранить, только runtime-справка | `ГРАФИК РАБОТЫ:</h6><p>ПН-ВС, с 6:00 до 23:00` |
| Велотрек Сарыарка | velotrek.kz | https://velotrek.kz/contacts/visiting-hours/ | Нет(приёмная) | Да(html) | Bitrix; «visiting-hours» = часы приёма граждан, не арены | OK (bitrix-тех.) | `title="Азаматтарды қабылдау кестесі" href="/contacts/visiting-hours/"` |
| Алау | alau.kz | https://alau.kz/kontakty/ | Нет | Нет | WP; JSON-LD `Place` на контактах; расписание массовых катаний в Instagram | OK (`/wp-admin`, `/wp-json`) | — |
| MTEX (Барыс Арена/Алау objects) | mtexm.com | https://mtexm.com/object/barys-arena | Нет | Нет | лендинги арен без часов | OK (`Disallow:` пусто) | — |
| ХК Барыс | hcbarys.kz | https://ru.hcbarys.kz/club/arena/contacts/ | Нет | Нет | Bitrix, контакты арены, часов нет | OK (bitrix-тех.) | — |
| Sokol (горнолыжка) | sokol.kz | https://sokol.kz/ | Нет | Нет | лендинг, часы не в статике | OK (пустой) | — |

## Итоги

**Можно хранить уже сейчас (STORE, часы+доказательство в статике):**
1. `order.papajohns.kz/api/outlet/list/?all=true` — 5 заведений Астаны: per-day `hours_text` + `points[lat,lng]` (5 Астана-hit в JSON) — лучший новый источник, чище KFC по формату.
2. `hardees.kz/stores` — та же схема, что уже одобренный KFC §11: `data-lat/data-lng` + недельные таблицы (100 аст. координат).
3. `starbucks.com.kz/stores` — инлайн-JSX per-day `weeklyWorkingHours` + `location.lat/lon` на 31 аст. кофейне.
4. `keruen.kz/rezhim_raboty` + `keruen.kz/contacts` (часы зон ТЦ + `data-latitude/longitude`).
5. `khanshatyr.com/contacts`, `srq.kz/ru` (ТРЦ), `famecity.kz/ru`, `ailand.kz/ru/schedule-ru/` (развлечения).
6. `nmrk.kz/about-museum/contacts/`, `astanaopera.kz/ru/contacts`, `gorkytheatre.kz/contacts` (касса) (культура).
7. `white.kz/contacts/` (Gasteria и др. `ПН-ВС 09:00 - 00:00`), `uzbechka1.kz`, `baofood.kz` (JSON-LD), `zebra-coffee.clients.site` (per-day JSON), `mastercoffee.kz`.
8. `crepecafe.kz/rus/contacts` — аст. координаты в пропсах; часы требует JS.

**Заблокированные для вежливого краула (не обходим deliberately):** `dodopizza.kz` 403 (bot-wall), `tanukifamily.kz` 401, `burgerking.kz` просроченный сертификат, `kidburg.kz`/`happylon.com`/`dominos.kz` self-signed, `bapool.kz` robots `Disallow: /` (факт часовKnown, но хранить нельзя), `fairplay.kz`/`ferrum.kz`/`arujan.kz` SSL hostname fail, `salambro.kz`/`korean-house.kz`/`kangojumpastana.kz` NXDOMAIN.

**Пустые ниши:** Coffeedelia и Black Cup в Астане фактически отсутствуют/без сайта; Domino's в РК нет; Gippo без аст. точек.

Ошибочнее всего вероятна строка: «CrepeCafe даёт аст. координаты в статике» — 9 совпадений 51.13/71.4x могут быть и не координатами заведений, а ассетами карты.
