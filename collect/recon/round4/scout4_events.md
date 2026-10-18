| source | endpoint | licence / ToS quote | fields | live proof | Astana yield | verdict |
|---|---|---|---|---|---|---|
| kino.kz | GET https://kino.kz/en/cinema/62 (Next SPA) | robots: `Allow: /`; licence unknown | JSON-LD MovieTheater: name/address + cdn photos; showtimes JS-only (Lorem ipsum placeholders) | 200; `meta-script:ld+json: [{"@type":"MovieTheater","name":"Kinopark 6 Keruencity Astana"...}]` | 8+ cinema venues w/ address+photos server-side | RUNTIME for showtimes; venue facts STORE-facts (also fills photos hole) |
| chaplin.kz | GET / and /timetable | robots empty | nothing server-side | 200 empty shell | 0 | DEAD (needs headless) |
| armancinema.kz | GET / | — | — | DNS ENOTFOUND | 0 | DEAD |
| kinopark.kz | GET /ru/movies/today?city=...010000 | licence unknown | date rail server-side; sessions JS | 200; `Сегодня\nЗавтра\nпн, 19 октября` | 3 Astana cinemas | RUNTIME |
| inastana.kz | GET /afisha, /afisha/{id}/{slug} | `meta-Googlebot-News: noindex`; no explicit scraping ban found | title, cinema, street address, dates, per-session times | 200: `Арман 3D ... улица Кабанбай батыра, 21 ... 10:30 12:05 14:40 17:05 21:00 23:50`; index `16 событий. 14 сегодня` | ~16 concurrent; Арман 3D, Chaplin Mega Silk Way | STORE-facts (evidence link) — best legal cinema-showtimes source |
| kassir.kz | GET /ru/all/show/{slug}, /venue/{slug}; robots 404 | offer §8.2 ticket-copy ban only; no site-content clause verbatim in offer | title, date, age, price, description, venue+address, poster URL | 200; `BIART MUSIC HALL, г. Астана, улица Сыганак, 17/41`; sitemap lastmod 2026-10-17 | 2 events on homepage; hourly category pages | RUNTIME-leaning; fact-parsing defensible — REVIEW before storing |
| ticketon.kz | GET /sitemap.xml → sitemap-kz-ru-events.xml (4713 lines) | robots verbatim: `Content-Signal: search=yes,ai-train=no`, GPTBot/ClaudeBot/CCBot/Google-Extended/Amazonbot etc `Disallow: /`; oferta (api-gw.ticketon.kz/f3/v1/images/oferta_ru.pdf): ban on copying text/images/databases and `Автоматизированный сбор (парсинг / скрейпинг)` | event URLs by category incl. -astana slugs | 200 sitemap updated 2026-10-17T11:40:49Z; event pages redirect-loop | ~1100 KZ events | CONTRACT (b2b) — do NOT scrape |
| sxodim.com | GET /astana/events/today, /week, /search-events?date_from=&date_to= | robots verbatim: `User-agent: *\nDisallow:` | title, category, price, date+time, venue+street, image, organizer | 200; `от 13 000 тенге, 7 ноября в 19:00, The Bus, шоссе Коргалжын, 3`; meta `15 мест и событий` | 15 events today, calendar thru Dec, seasonal articles | STORE-facts (best legal aggregator) |
| afisha.yandex.kz | GET /astana | robots allows pages, `Disallow: /api`; Yandex ToS → no storage | featured cards, selections, venue/date/price | 200; `Kreator — Wyndham Garden Astana•17 ноября, 19:00 — от 30 000 тнг` | featured + nearest-events | RUNTIME |
| afisha.kz / afisha.nur.kz / kuda.kz / gorod.kz | GET | — | — | DNS dead ×2; kuda refused; gorod.kz parked (bomberwin.homes 404) | 0 | DEAD |
| qazaqconcert.kz | GET / and /posters | venue-own page | title, date `Күні: 21.10.2026`, time, hall, ticketon link | 200; 10 upcoming events | 10 upcoming @ QAZAQSTAN | STORE-facts |
| astanaopera.kz | GET /ru/afisha; /api/afisha, /api/shows | licence unknown | React JS only; api → HTML shell | 200 shell | 0 machine-readable | RUNTIME (headless) or CONTRACT |
| kazconcerthall.kz / astanaballet.kz / barysarena.kz / astanacircus.kz / nationalmuseum.kz / museumoffuture.kz | GET | — | — | DNS dead; astanaballet TLS invalid; museum via ticketon | 0 | DEAD (content moved: youticket, Yandex Afisha, qazaqconcert) |
| astana-dpkm.kz | GET / + /index.php/novosti/* | venue-own (ГККП акимата) | city projects + dates | 200; `фестиваль «Шабыт» ... с 18 по 22 ноября` | ~6 projects/yr + news | STORE-facts |
| gov.kz astana-madeniet | GET /org/astana-madeniet?lang=ru | official gov | festival/event news w/ dates | 200; `IV Международный театральный фестиваль «TEATR ALL»` | seasonal news | STORE-facts |
| visitastana.kz | GET /events and /en/events | — | — | HTTP 500 both | 0 | DEAD (retry later) |
| astana.kz | GET /ru/events | official | JS shell `Загрузка...` | 200 shell | ? | RUNTIME pending XHR discovery |
| alem.ai | GET /en/ | venue-own | hours 10:00-18:30 Tue–Sun, price ₸2500, tour ₸10000 | 200 verbatim | 1 POI (prices+hours) | STORE-facts |
| youticket.kz | GET /en/events/{slug} + sitemap (categories museum/circus/concert/exhibition/kids/excursion) | own page | hours, prices, address, lat/lng 51.0895,71.4157 | 200 verbatim alem-ai | Astana Hub ticketing — growing | STORE-facts |
| Eventbrite | GET /d/kazakhstan--astana/events/ | API v3 token required, no bulk storage | 4 events: Founders Running Club, United beauty show @EXPO IEC | 200; 4 unique events | ~4, business/edu | CONTRACT / low value |
| Ticketmaster Discovery | GET /discovery/v2/events.json?countryCode=KZ | developer terms | — | 401 no key; docs: KZ not covered (totalElements 0) | 0 | DEAD for KZ |
| International Showtimes API | GET api.internationalshowtimes.com/v4/cinemas/?countries=KZ | key required | showtimes JSON 120+ countries | 401; KZ coverage [не проверено] | ? | CONTRACT — try demo key |
| Wikidata | SPARQL P31/P279*→Q165650, P276=Q1520 | CC0 | — | result 0 | 0 | DEAD |
| tengrinews/afisha, informburo RSS | GET /afisha/, /rss | news © | /afisha = stale 2020–2022 Weekend articles; /rss/ timeout; informburo /rss 403 | 200 stale | ~0 | DEAD as events feed |
| Alau Ice Palace | GET mtexm.com/object/alau/price (operator); alau.info; IG @alauicepalace | venue-own | season opens 24 Oct; weekend 5 sessions 11:30–23:00; weekday 2 sessions; 1500–2000₸; Кабанбай батыра 47 | via web_search citations (mtexm, newtimes) | 1 venue + weekly recurring | STORE-facts |
| City fairs | GET gov.kz/org/astana/press/news/details/1035865 | official | Қазанат hippodrome (Кркаралы 1) Sat–Sun 09–18; Keryen Joly (Алаш 35/35Б) Sat–Sun 10–19; Era Bazary (Коргалжын 96); permanent Бейбарыс Султана 23; regional rotation (17–18 Oct СКО/Павлодар/Улытау) | via web_search (kursiv, informburo, ratel, gov.kz) | 4 recurring weekly locations | STORE-facts — no API needed |
| Winter seasonal | gov.kz press details/901398, /666411; sxodim articles | press/city-guide | Astana Winter Park 6000 m² + 1.4-km refrigerated track; Triathlon Ice Park 1200 m²; EXPO rink 14:00–21:45; City Square; Presidensky park; Atatürk park; Mega Arena indoor | via web_search citations | 8+ seasonal POIs | STORE-facts (annual Nov refresh) |

## Wins
1. sxodim.com/astana — fully server-side, robots allows all, 15+ concurrent events with prices/venues/addresses, plus evergreen seasonal articles (rinks, sled hills). STORE.
2. inastana.kz/afisha — only source with verbatim per-session cinema showtimes server-side + cinema street addresses. Fact-parsing legal path for hole #6 cinema.
3. Venue-own cluster (collect/sites rule): qazaqconcert.kz/posters, astana-dpkm.kz, gov.kz astana-madeniet, alem.ai, youticket.kz, mtexm.com/object/alau — ~8 authoritative feeds, zero ToS risk.
4. Recurring layers w/o API: weekly city fairs (official gov.kz press, 4 locations, regional rotation), winter rinks/ice towns (annual gov.kz announcement). Covers markets + seasonal rinks holes entirely.
5. Ticketon sitemap (sitemap-kz-ru-events.xml, ~1100 KZ events, hourly lastmod) proves the corpus; pursue CONTRACT (Freedom Ticketon b2b), do not scrape (oferta bans parsing, robots blocks all AI UAs).

## Dead / rejected + why
- chaplin.kz — empty JS shell.
- armancinema.kz — DNS dead.
- afisha.kz, afisha.nur.kz — DNS dead.
- kuda.kz — connection refused; gorod.kz/astana/afisha — domain parked (bomberwin.homes 404).
- kazconcerthall.kz, barysarena.kz, astanacircus.kz, museumoffuture.kz, astanafuture.museum — DNS dead.
- astanaballet.kz — TLS cert invalid.
- nationalmuseum.kz — connection refused (museum sells via ticketon).
- visitastana.kz/events — HTTP 500 both locales.
- tengrinews/afisha — stale 2020–2022 articles; RSS unavailable.
- Ticketmaster Discovery — no KZ coverage.
- Wikidata events — 0 rows.
- 2GIS event cards — RUNTIME only: API rules §4.7 «Пользователь не вправе кэшировать любые Продукты» (verified verbatim).
- Yandex Afisha as source — RUNTIME only (ToS).

## Unverified leads
- astana.kz/ru/events XHR — reverse the JS bundle for the JSON endpoint (would be the cleanest official STORE source).
- astanaopera.kz internal API — capture real XHR via headless browser (/api/afisha, /api/shows return shells).
- International Showtimes API — request demo key, check `?countries=KZ` for Astana cinemas.
- Eventbrite API v3 with token — confirm monthly culture events in Astana.
- kazticket.kz (Alau tickets) — unreachable from this host; retry from other network.
- National Library (nbtlibry), TsDI, Qyran, Museum of the First President — not yet probed individually; same venue-own rule applies.
- PredictHQ / Amadeus events — commercial, price not public [не проверено].
- liter.kz / kursiv.media / baq.kz weekly city digests — RSS feeds worth probing for media-announcement facts.
