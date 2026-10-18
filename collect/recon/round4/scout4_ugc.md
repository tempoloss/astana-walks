# UGC / social / messaging sources for the 'city layer' — legal status

Assumption for all rows: product is **commercial**, we want to store **facts** (event title, date, place, closure status) with attribution + deep-link, not full texts or media.

## 1. Telegram public channels — **the only high-yield feed**

Server-side HTML polling **works without any login**: `https://t.me/s/<username>` returns the channel's recent posts as plain HTML (verified below). MTProto `messages.getHistory` with our existing session also works on public channels.

| channel | access route + auth | ToS / licence clause verbatim | what it gives | live proof (HTTP + subscriber count) | fact type | verdict |
|---|---|---|---|---|---|---|
| **@astana_newss** "Astana news" (akimat) | `GET https://t.me/s/astana_newss` (no auth) | Telegram ToS (content licensing, https://telegram.org/tos/content-licensing): *"Access to user-generated content for any purpose other than ordinary, legitimate, and intended use of the Telegram platform as its user is prohibited."* + API ToS §1.5 (https://core.telegram.org/api/terms): *"you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial intelligence, machine learning models and similar technologies."* **Channel post text is also the channel owner's copyright** (KZ law follows Berne; copying full post = infringement even with a link). Content copyright stays with the owner. | Official city-akimat announcements (KZ+RU bilingual): city fairs, market days, Republic Day events, new openings, road closures | HTTP 200, `og:title: Astana news`, **1.78K subscribers**, recent post ids 40326–40343 (verified server-side HTML with full text + timestamps) | events, fairs, closures, new openings | **RUNTIME for full text**; **STORE derived facts only** (structured event {title, date, place, deep-link `t.me/astana_newss/<id>`}) with attribution. Never store full post text or media. |
| **@qr_tjm** "112 KZ" (МЧС РК / emergency ministry) | `GET https://t.me/s/qr_tjm` | same Telegram ToS as above + post copyright | Storm warnings, floods, fires, road closures, DARMEN alerts — covers Astana when relevant | HTTP 200, `og:title: 112 KZ`, **33.2K subscribers**, post ids 43985–44007 | weather warnings, emergencies, road closures | **RUNTIME for text; STORE derived facts + deep-link.** This is the de-facto Kazhydromet Astana alert channel (Kazhydromet itself has **no own TG channel** — confirmed by search). |
| **@tengriastana** "Tengri Astana" | `GET https://t.me/tengriastana` | same Telegram ToS + copyright | City news, closures, construction, events | HTTP 200, `og:title: Tengri Astana`, **12 571 subscribers** | city events, closures, construction | **RUNTIME / STORE derived facts + deep-link.** |
| **@sxodim_astana** "Давай Сходим! Астана" | `GET https://t.me/s/sxodim_astana` | same Telegram ToS + copyright | Biggest events feed (afisha): concerts, runs, festivals, exhibitions, street art | HTTP 200, `og:title: Давай Сходим! Астана`, **17.4K subscribers**, post ids 8956–8973 live | events (concerts, sports, festivals) | **RUNTIME / STORE derived facts + deep-link.** High value for the 'events' hole. |
| **@tengrinews** (republic) | `GET https://t.me/s/tengrinews` | same Telegram ToS + copyright | National + some city news; seasonal forecasts | HTTP 200, **252K subscribers** | weather, city news | **RUNTIME / STORE derived facts + deep-link.** (Secondary — republic-wide, low Astana yield per post.) |
| **@zakonkz** (republic) | `GET https://t.me/s/zakonkz` | same Telegram ToS + copyright | National + city news | HTTP 200, **203K subscribers** | news | **RUNTIME / STORE derived facts + deep-link.** Secondary. |
| **@astanaopera** (venue) | `GET https://t.me/s/astanaopera` | same Telegram ToS + copyright | Theatre premieres, repertoire | HTTP 200, **59 subscribers**, ids 1069–1096 | venue events | **RUNTIME / STORE derived facts + deep-link.** Low volume, niche. |
| **Kazhydromet (own)** | — | — | — | **No official Telegram channel exists** (verified by web search: Kazhydromet publishes warnings only on kazhydromet.kz, Instagram @kazhydromet, and DARMEN app). | weather warnings | **DEAD as Telegram source**; use @qr_tjm or kazhydromet.kz directly. |
| **Astana Tazalyq (cleaning)** | — | — | — | **No own Telegram channel** (verified). Official channels: astanatazalyk.kz (HTML news feed, live), Instagram @astana_tazalyq_resmi. | cleaning works, snow | **DEAD as Telegram source**; `astanatazalyk.kz/ru/news` is a live HTML feed (no API). |
| **Avtobys / LRT** | — | — | — | B2B GTFS-Realtime to partners only, no public Telegram channel (previously established). | transport | **CONTRACT** (existing lead, unchanged). |

**Safe-storage pattern for ALL Telegram rows:** store only the **derived fact** (event/closure/warning, date, place, category) + **deep-link** `t.me/<channel>/<msg_id>` + attribution "Источник: @<channel>". Full post text and media are the channel owner's copyright and Telegram's ToS forbids bulk harvesting — do **not** store full text, images, or video. Structured facts themselves (dates, places, what is closed) are not copyrightable.

## 2. Instagram / Facebook (Meta)

| route | ToS / licence clause | what it gives | live proof | fact type | verdict |
|---|---|---|---|---|---|
| Meta Graph API / Instagram oEmbed (`graph.facebook.com/{v}/instagram_oembed?url=...`, App Access Token, requires App Review for `Meta oEmbed Read`) | Meta Platform Terms (https://developers.facebook.com/terms/dfc_platform_terms/) §3.a.iv: *"Selling, licensing, or purchasing Platform Data"* is prohibited; §3.a.viii: *"Processing Platform Data for purposes other than the applicable permitted purposes set forth in Meta's Developer Docs"*; Meta ToS §3.2: *"You may not access or collect data from our Products using automated means (without our prior permission)"*. oEmbed Read permitted scope (Meta docs): *"To provide front-end views of public Facebook and Instagram pages, posts, and videos"* — display only, no bulk harvesting, no persistent caching. | Public posts of city venues/authorities (Instagram is where Astana venues actually post) | Meta ToS live (fetched). Legacy unauthenticated `api.instagram.com/oembed` deprecated 2020-10-24; `oEmbed Read` replaced by `Meta oEmbed Read` 2025-11-03 with thumbnail/author fields removed. | venue posts (photos, event announcements) | **RUNTIME-or-nothing.** Storing any scraped/cached post or image = breach. Store at most a deep-link `instagram.com/p/<id>` + our own extracted fact; never cache media or embed HTML beyond short-term display. Bulk harvesting is legally off-limits. **Not a viable commercial feed.** |
| Meta Content Library API | restricted to qualified academic / non-profit researchers (*"For-profit corporations, commercial analytics firms, marketing agencies, and for-profit news media organizations are ineligible"*). | public FB/IG posts | policy verified | — | **DEAD for commercial use.** |

## 3. Google Maps reviews / Q&A

One line: **no legal storage.** Google Maps Additional Terms (https://www.google.com/help/terms_maps/, last modified 2026-01-27) §2: *"you may not… copy the content… mass download or create bulk feeds of the content (or let anyone else do so); or use Google Maps to create or augment any other mapping-related dataset (including a mapping or navigation dataset, business listings database…)"* — reviews are content; bulk storage or a derived database is expressly prohibited. Place Details returns at most 5 reviews per request with no historical access. Verdict **RUNTIME display only, never STORE.**

## 4. OSM-adjacent live UGC (permissive licence — the legally clean wins)

| source | access route + auth | ToS / licence | what it gives | live proof | fact type | verdict |
|---|---|---|---|---|---|---|
| **OSM Notes** | `GET https://api.openstreetmap.org/api/0.6/notes/search?bbox=71.28,51.03,71.55,51.25&limit=50&closed=0` (no auth) | ODbL — from the XML response header itself: `license="http://opendatacommons.org/licenses/odbl/1-0/"`; from osm.org/copyright: *"You are free to copy, distribute, transmit and adapt our data, as long as you credit OpenStreetMap and its contributors."* | Citizens + Organic Maps users report things at coordinates: road works, closed/missing shops, new roads | HTTP 200, **9 open notes** in Astana bbox right now, examples: note 5567918 (2026-10-12) `"Перешивка на 1 линию"` (lat 51.131, lon 71.506); note 5363583 (2026-06-27) Organic Maps auto-report *"The place has gone or never existed… POI name: LDS, POI types: shop-clothes"* — i.e. an automated **closure** signal. | road works, POI closures, new roads | **STORE** (with ODbL attribution "© OpenStreetMap contributors"). Legally clean; moderate volume, mixed signal/noise. |
| **StreetComplete quests** | Not a separate API — the app writes answers directly into the OSM DB: *"The user's answer is automatically processed and uploaded directly into the OSM database. Edits are done in meaningful changesets using the user's OSM account."* (StreetComplete README). | ODbL (same as OSM) | opening_hours, wheelchair, bench, surface, toilets, etc. | — | POI attribute ground-truth | **Already covered by our existing OSM ingest** (diffs / Overpass). No new source to add; just filter changesets by editor=`StreetComplete` to catch 'fresh survey' signals. **STORE** via ODbL. |
| **OSMCha** | `GET https://osmcha.org/api/v1/changesets/?bbox=71.28,51.03,71.55,51.25&page_size=…&date__gte=…` — **auth required**: `Authorization: Token <osmcha_token>` (obtain via OSM OAuth at osmcha.org → Account Settings). Unauthenticated returns **HTTP 401** (verified). Returns GeoJSON of changesets with `create/modify/delete` counts, editor, comment, bbox. | OSMCha itself is an open-source tool (github.com/OSMCha/osmcha-frontend, GPL); the changeset metadata it serves is OSM metadata. The **map data** it points to is ODbL; changeset metadata itself (user, id, timestamps, counts) is not creative content — but attribution to OSM is good practice. | Detect **new construction** (large `create` counts), **closures/demolitions** (large `delete` counts) in a bbox, filtered by editor and suspicion flags. | HTTP 401 without token (endpoint live, confirmed via osmcha.org + docs); `api.osmcha.org` DNS currently unresolvable — use `osmcha.org/api/v1/…` host. | construction, demolition, closure signals | **CONTRACT-free, token-gated** — practically **RUNTIME/STORE derived signals**. Useful as a detector, not a content source. |
| **MapRoulette** | `GET https://maproulette.org/api/v2/tasks/box/<left>/<bottom>/<right>/<top>` (no auth) | Tasks are QA challenges, not city state. | e.g. `2_Kazakhstan_2026-06-15_RoadNameGapCheck #Kaart`, `Global - Unconnected Crosswalks` | HTTP 200, **many live Astana tasks** (task ids 357465563, 359870811, 361013953, … at coordinates inside our bbox). | OSM data-quality issues | **DEAD for our purpose** — nothing to do with 'what is happening at this place right now'; it's mapper QA workload. |

## 5. Reddit

| route | ToS / licence | what it gives | live proof | verdict |
|---|---|---|---|---|
| `https://www.reddit.com/r/astana/new.json?limit=5` (no auth) | Reddit Data API Terms (https://redditinc.com/policies/data-api-terms, last revised 2026-07-20): §2.4 *"You may not modify the User Content except to format it for such display… no other rights or licenses are granted or implied"*; §3.1 *"If you are interested in using the Data APIs for commercial purposes… you will need to enter into a separate agreement with Reddit"*; §3.2 *"use or retain any User Content, Materials, or data accessed through the Data APIs beyond your approved use case, and you must immediately delete any data not required for it"*; §6 requires deletion of all cached User Content on termination. | User reports about city places | Probe returned **HTTP 403** (unauthenticated JSON blocked; old.reddit JSON redirects to login). Live `.rss` returned **HTTP 429** (rate limited). | **DEAD for commercial feed.** Even if accessible, storing derived facts is a ToS violation without a paid Reddit agreement. Also: **r/astana is essentially dormant** (restricted posting, a few hundred subscribers, 15–20 weekly visitors); real KZ discussion happens on r/Kazakhstan (~76.5k members, [Astana] flair) — still not commercially usable without a Reddit contract. |

## 6. Forums / comment platforms

| source | ToS clause | verdict |
|---|---|---|
| **2GIS reviews** | 2GIS API Rules (law.2gis.kz/api-rules/ru) §4.2/§5.2: *"Запрещается сохранять, в том числе с целью временного хранения (кэширования), полученные с использованием Сервиса Продукты и информацию из них"*; §5.1.8 of the licence agreement: *"…делать любые автоматические и автоматизированные запросы… боты и другие средства для сбора, выгрузки и (или) передачи каких-либо данных"*. | **RUNTIME-or-nothing.** Confirms prior finding — no storage, no scraping. |
| **Otzovik / kolesa.kz forum** | — | **Irrelevant** (no KZ POI coverage / off-topic). **DEAD.** |

## 7. Waze for Cities / TomTom

| source | access route | ToS / licence | verdict |
|---|---|---|---|
| **Waze for Cities** | Partner Hub (`waze.com/partnerhub`) — only for public agencies / road authorities, bilateral agreement. | Not CC BY-NC-SA (that's an old reference). Proprietary "Waze for Cities Data Sharing Terms": partners get a *"royalty-free, non-exclusive license to use Waze real-time traffic and incident data solely within their defined jurisdiction"*, *"expressly prohibited from using Waze data for any commercial purpose"*, and *"may not distribute, publish, or sublicense raw feeds, historical data, or aggregate bulk datasets"*. | **DEAD for us** — we are not a government agency, and even if Astana akimat joined, they could not pass the feed to a commercial third party. |
| **TomTom POIs / Traffic events** | TomTom Developer Terms + enterprise MSA | Storage prohibited by default; only short-TTL client-side caching per HTTP `Cache-Control`; historical analytics requires a separate paid product (Traffic Stats) or custom enterprise license. | **CONTRACT** — paid key unlocks runtime; storage requires separate enterprise agreement. |

## 8. Our own future UGC (KZ personal-data law) + e-Otinish / iKOMEK

### KZ personal data law (Law No. 94-V of 21 May 2013 «О персональных данных и их защите»)
- **Art. 7** — collection/processing requires the data subject's **explicit consent** (with narrow Art. 9 exceptions).
- **Art. 8** — consent must be in written / e-document form with verifiable proof; must state purpose, scope, term, third-party transfer permission, cross-border transfer status.
- **Art. 12** — personal data must be **stored in databases located on the territory of Kazakhstan** (localization requirement).

**Consequence for our 'city' layer:** users' marks and any attached photos are personal data (nicknames, photos of people). We need explicit, revocable consent (Art. 7–8) at submit time, KZ-localized storage (Art. 12), and a takedown flow. Photos of **identifiable third parties** (bystanders in street shots) need their consent too — safest is to allow only photos of the place/objects, not people, or blur faces. Anonymised 'place + fact' marks without identifiers fall outside the strict personal-data regime, but the moment a nickname or photo is attached, the law applies.

### e-Otinish (eotinish.kz / e-otinish.kz) — citizen appeals register
| probe | result |
|---|---|
| `https://e-otinish.kz/api/appeals` | **HTTP 503** — no public API exposed. |
| Web research | Integration is only via **Smart Bridge** (sb.egov.kz) for **legal entities / government bodies** with security accreditation. Services: `appealsRegnumber (NITEC-S-9569)`, `e-otinish (ORGB7-S-4767)`, `appeal-status (ORGB7-S-5159)`, `appeal (KPSISU-S-3824)`. Not a public REST API. |
| `data.egov.kz/datasets/search?text=обращения` | Only **aggregate** statistics (counts per organisation per quarter), e.g. dataset `205` — «Статистические данные по обращениям физических и юридических лиц, поступающих в АО «НИТ»». |
| `data.egov.kz/datasets/getmeta?index=205` (keyless) | **HTTP 200** with full schema (fields: id, name, name_kz, year, quarter, quantity). |
| `data.egov.kz/datasets/exportjson?index=205&version=&from=0&count=10` (keyless) | **HTTP 200** but returns `[]` for dataset 205 and for kazmedia_ortalygy_baskarushy6 — row export currently yields nothing (either wrong `version` param or genuinely empty dataset). **Unverified row-level yield.** |

**Verdict e-Otinish / iKOMEK: DEAD for location-level 'problem at X' live feed.** Only **aggregate quarterly counts** are open (data.egov.kz), not per-appeal geo data. iKOMEK 109 heat-maps are internal-only (no public API; site is a bare SPA).

---

## Wins (top 5 actionable)
1. **Telegram `t.me/s/<username>` server-side HTML polling** is confirmed working without auth for @astana_newss (1.78K), @qr_tjm (33.2K), @sxodim_astana (17.4K), @tengriastana (12.5K) — gives us **events, closures, fairs, weather warnings** for the 'city layer' tomorrow. Store only derived facts + `t.me/<channel>/<id>` deep-link + "Источник: @<channel>".
2. **OSM Notes API** (`api.openstreetmap.org/api/0.6/notes/search?bbox=…&closed=0`) — **9 live open notes in Astana bbox right now**, ODbL, includes automated Organic Maps "place has gone" **closure** signals. Legally clean to store.
3. **OSMCha API** (`osmcha.org/api/v1/changesets/?bbox=…`) with an OSM OAuth token — a **construction/closure detector** (create/modify/delete counts per changeset, bbox-filtered). Free, token-gated.
4. **KZ personal-data law compliance template** (Law 94-V art. 7/8/12) is now mapped: explicit revocable consent at submit + KZ-localized storage + takedown; avoid identifiable-people photos or require blurring.
5. **data.egov.kz keyless API** (`/datasets/getmeta?index=…`) confirmed live for appeals statistics — gives **aggregate** quarterly citizen-request volumes per organisation (not per-location). Useful context, not a location feed.

## Dead / rejected + why
- **Instagram/Facebook bulk harvesting** — Meta ToS prohibits automated access; Content Library API excludes for-profit orgs. RUNTIME embeds only.
- **VK bulk harvesting** — dev.vk.com/rules §2.1/2.4 forbid storing API-retrieved wall/newsfeed data or using it for analytics; Sept-2026 policy caps unverified accounts at 10k calls/month. Plus negligible Astana user base.
- **Google Maps reviews/Q&A** — §2 of Maps Additional Terms prohibits copying/mass-download/derived datasets.
- **2GIS reviews** — §4.2/5.2 of API rules forbid caching/storage.
- **Reddit** — 403 unauth, Data API §3.1 requires separate agreement for commercial use, r/astana is dormant anyway.
- **Waze for Cities** — agency-only bilateral terms, commercial use prohibited, data non-redistributable.
- **MapRoulette** — mapper QA tasks, not city-state signals.
- **Otzovik / kolesa forum** — no KZ POI relevance.
- **e-Otinish direct API** — 503; Smart Bridge integration is legal-entity+security-accreditation gated, not public.
- **Kazhydromet / Astana Tazalyq Telegram** — do not exist as channels; use @qr_tjm (for weather) and astanatazalyk.kz HTML (for cleaning).

## Unverified leads
- **@tengri_live** and **@tengri_feed** (Telegram) — listed in @tengrinews' bio as live/aggregate feeds; not yet probed for Astana yield. Worth polling.
- **kazhydromet.kz/ru/meteoalert** — direct storm-warning page for Astana; probe for a machine-readable JSON endpoint behind the UI.
- **Astana Opera / Astana Ballet / National Museum** — confirmed to have **no** real Telegram presence (Opera has 59-subscriber ghost channel); their Instagram is the actual feed — evaluate an **oEmbed runtime** path (deep-link only, no storage) per venue.
- **data.egov.kz `exportjson` returns `[]`** for datasets 205 and kazmedia_ortalygy_baskarushy6 — needs correct `version` parameter or the datasets are genuinely empty; re-test before writing off the aggregate appeals-stats source.
- **@ikomek109_astanabot** — a Telegram *bot* for filing appeals, not a channel; check if it has any broadcast/newsletter mode we could observe.
- **Astana LRT / Avtobys public Telegram** — search found none; confirm before writing off, in case a channel was launched recently.
- **DARMEN app** (gov emergency alert app) — likely has push notifications for Astana; no public API documented, but worth checking if it exposes a feed.

---

### Explicit safe-storage summary
- **Safe to store only derived facts + deep-link (with attribution):** all Telegram channels listed (because platform ToS + channel-content copyright).
- **Safe to store the data itself (ODbL / open licence):** OSM Notes, OSM change/StreetComplete-derived data, OSMCha signals (derived from ODbL data).
- **Never store:** Google Maps reviews, 2GIS reviews, Instagram/Facebook post content, Reddit content, Waze feed, TomTom incidents (without an enterprise contract).