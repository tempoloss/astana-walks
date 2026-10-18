# Round 9 — afisha probe (2026-10-18), 4 venues (nabrk.kz skipped: library)

Window: 2026-10-18 .. 2026-10-25 (next 7 days). HTTP: UA `astana-walks-research/0.1 (an8kk.sa@gmail.com)`, ≤1 req/s, timeout 20 s. Raw pages in `afisha_probe_raw/`.
All afisha URLs below were taken from `<a href>` on the landing page (or from a link printed on the page / URL string shipped in the site's own JS bundle). Zero guessed slugs; zero 404s.

## Semantic frame (owner's red line)
Everything here is an EVENT (date/time/title), a runtime hint "сегодня показ в HH:MM" layered on top of honest-unknown `opening_hours`. It does NOT close the opening_hours hole. No weekly pattern is inferred from any of it.

## Summary

| domain | events in 7d (Astana) | doors field | render | afisha URL (found via) |
|---|---|---|---|---|
| astanaballet.com | 1 | no (only start, `На сцене 18.00`) | server HTML (Laravel-ish, paginated `?page=N`, 6 pages) | `/ru/posters` (landing nav «Афиша») |
| astanaopera.kz | 1 | no (`event_time`, `event_time_to` always null) | **JS** (Nuxt SSR shell, list empty in HTML) → JSON API `/api/posters` | `/afisha` (landing «Барлық афишалар»); API path from `/_nuxt/98329a2.js` |
| zhastar-theatre.kz | 0 | no | server HTML, but data junk | landing «Айлық күнтізбе» + `/performances/for-adults` |
| qazaqconcert.kz | 2 (+1 Almaty, excluded) | no (`Уақыты:` only) | server HTML | `/posters` (landing «Барлық оқиғалар»), detail `/poster/<slug>` |
| **total** | **4** | | | |

## 1–5 per venue

### astanaballet.com — events_7d = 1
- Landing `https://astanaballet.com/ru` → nav «Афиша» `/ru/posters` (also «Репертуар» `/ru/stagings/repertoire`, undated).
- Server HTML, plain. List sorted ascending, 4 events/page, pagination link `?page=2` printed on page ("1 /6"). Page 1 first item is 24 Oct → nothing before it; 25 Oct has none. Only 24 Oct falls in the window. Month is text («октября»), **no year in markup** (assumed current).
- Examples (https://astanaballet.com/ru/posters):
  - `Наследие Великой степи` / `24 октября` / `На сцене` / `18.00` / `пр. Улы Дала, 43` (in window)
  - `Музыка сквозь поколения` / `28 октября` / `На сцене` / `19.00` (just outside window)
  - `Ромео и Джульетта` / `30 октября` / `На сцене` / `19.00` (outside)
- Page 2 (`https://astanaballet.com/ru/posters?page=2`): `«Кармен-сюита» и «Арканы судьбы»` 6 ноября 19.00 / 7 ноября 18.00 etc.
- Doors: no. Detail page `/ru/stagings/nasledie-velikoy-stepi` has no doors/«сбор гостей»/duration text (grepped: 0).
- Rights: footer `© 2019 AstanaBallet. All Rights Reserved.` (generic). robots.txt: `Disallow: /balletcp` only. No clause on factual reuse.

### astanaopera.kz — events_7d = 1
- Landing `https://astanaopera.kz/` → «Барлық афишалар» `/afisha`.
- **JS-rendered**: `/afisha` HTML is a Nuxt SSR shell (filter chips only; `window.__NUXT__` has `data:[{}]`, no events). The list is fetched client-side from `GET /api/posters?page=1&lang=ru&limit=50` — endpoint string and params (`page,lang,type,limit`) read verbatim from the site's own `/_nuxt/98329a2.js` (`f.a.get(h.a+"/api/posters",…)`, base `h.a=""` in `795149f.js`, i.e. same origin). Not a guessed path. Public JSON, 200, 315 KB, no auth/token. Total 17 posters (`meta.total:17`), one `event` object each = next showing.
- Fields: `title`, `scene_name`/`hall_name`, `event.event_date`, `event.event_time`, `event.event_time_to` (null everywhere), `event.price_from` (null), `event.ticket_link` (null), `minutes`, `age_limit`.
- Examples (https://astanaopera.kz/api/posters?page=1&lang=ru&limit=50):
  - `"title":"Дружная семейка струнных инструментов"` … `"event_date":"2026-10-18","event_date_to":null,"event_time":"15:00:00","event_time_to":null,…"hall_name":"Камерный зал"` (in window; note: today, 15:00 may already be past depending on local time)
  - `"title":"Самұрық келген таң"` … `"event_date":"2026-10-26","event_time":"15:00:00","hall_name":"Камерный зал"` (just outside)
  - `"title":"Jazz Lounge в Опере"` … `"event_date":"2026-10-28","event_time":"19:00:00","hall_name":"Камерный зал"` (outside)
- Doors: no field (`event_time_to` exists but is end-time slot, always null). Grep `двер|doors` = 0.
- Caveat: only ONE upcoming showing per production is exposed here (so recurrence counts under-report); that is a limitation of the list endpoint, not evidence of absence of other dates.
- Rights: no © / «все права» string anywhere on the pages; robots.txt `Disallow:` empty (allow all).

### zhastar-theatre.kz (ТЮЗ) — events_7d = 0
- Landing `https://zhastar-theatre.kz/` has «Айлық күнтізбе» (monthly calendar) — 72 `calendar__box data-date="DD.MM.YYYY"` blocks in server HTML + nav «Репертуар» → `/performances/for-adults`, `/performances/for-children` (undated lists of titles, no dates/times at all; "1 ден 7" pagination).
- Server HTML (datepicker filtering is client JS, but all 72 boxes are already in HTML).
- The calendar data is **not trustworthy**: 72 boxes, 61 distinct dates, majority stale 2024–2025 (e.g. `05.11.2024`, `29.11.2024`), plus obviously junk future dates (11× `14.06.2034`, `16.07.2039`, `13.08.2040`, `05.12.2030`, `03.10.2019`, `28.06.2018`) and times like `12:06`/`15:09`. Only one date ≥ today and ≤ 2026: `26.11.2026`. Nothing in 18–25 Oct 2026.
- Examples (https://zhastar-theatre.kz/ — verbatim):
  - `Асауға тұсау … күні мен уақыты: 29.11.2024  19:00` (stale)
  - `Ж. Сомжурек «ТІЛЕП-САРЫҚЫЗ» … күні мен уақыты: 26.11.2026 15:09` (only post-today 2026 entry; 15:09 looks like CMS creation time, not a show time)
  - `Е.Уахитов «ҚҰДАЛАР» … күні мен уақыты: 18.06.2027 15:16` (junk-looking)
- Ticket link goes to `https://ticketon.kz/place/teatr-zhastar` (different party): it bounces through a Queue-it virtual-queue 302 chain and my plain curl (no cookie jar) ended in a redirect loop (curl exit 47); not pursued (out of the 5 domains, bot-gated).
- Doors: no.
- Rights: footer `©2024 - Жастар театры` only. robots.txt `Disallow:` empty.

### qazaqconcert.kz (Астана Концерт Залы) — events_7d = 2 (Astana) (+1 Almaty)
- Landing `https://qazaqconcert.kz/` → «Барлық оқиғалар» `/posters` (nav «Афиша»). Server HTML, plain; each `.afisha_item` has date, hall, title, link to `/poster/<slug>` (slug taken from the link). **Start time is only on the detail page** (`Күні / Уақыты / Зал` fields), so listing needs +1 request per event (1 req/event, ~10 events). Listing shows 10 events total (21.10 … 14.11).
- In window (listing `https://qazaqconcert.kz/posters`): 21.10.2026 «БІЗДІҢ ЖӘРМЕҢКЕ» Үлкен зал; 22.10.2026 ӘУЕЛЕТІП ӘН САЛСА Камералық зал; 23.10.2026 ҚОСАМЫН ӘНГЕ АТЫҢДЫ — hall `Құрманғазы оркестрінің залы (Алматы қаласы, Абылайхан к-сі, 83)` = **Almaty, excluded from Astana count** (touring show).
- Examples (verbatim from detail pages):
  - https://qazaqconcert.kz/poster/bizdi-zrmeke_20260930160757 :: `Күні: 21.10.2026` / `Уақыты: 19:00` / `Зал: Үлкен зал` — «БІЗДІҢ ЖӘРМЕҢКЕ»
  - https://qazaqconcert.kz/poster/ueletip-n-salsa :: `Күні: 22.10.2026` / `Уақыты: 19:00` / `Зал: Камералық зал` — ӘУЕЛЕТІП ӘН САЛСА
  - https://qazaqconcert.kz/poster/kosamyn-nge-atydy :: `Күні: 23.10.2026` / `Уақыты: 19:00` / `Зал: Құрманғазы оркестрінің залы (Алматы қаласы, Абылайхан к-сі, 83)` (Almaty — excluded)
- Doors: no, only `Уақыты`. Grep `двер|doors` = 0.
- Rights: footer `©2019-2026. Барлық құқықтар сақталған.` («All rights reserved» — generic, covers site content/design; says nothing about factual reuse). robots.txt `Allow: /`, `Disallow: /admin/`.

### nabrk.kz — skipped (library; event case not applicable). Landing 200 was fetched during the reachability pass only; not retained.

## Cross-venue observations
- No venue publishes doors-open separately; only a single start time (ballet shows «На сцене 18.00», QC `Уақыты`, opera `event_time`). So the runtime hint can only be "показ в HH:MM", never "двери в HH:MM".
- Only Opera needs a JS-bundle lookup to find a JSON endpoint; the other three are curl-parseable. QC needs one extra GET per event for time. Ballet needs year inference and pagination.
- ТЮЗ's own calendar is unusable as-is (stale/junk). Don't treat it as evidence of "no show".
- Everything is a point-in-time event list. No recurring weekly pattern was inferred or extracted from any of it; where a venue does show repeats (Romeo & Juliet 30 and 31 Oct at ballet) those are two dated listings from the site's own list, not a derived rule.
- Rights: no site shows a clause forbidding reuse of factual date/time/title; closest are generic © lines quoted above (Ballet, QC, ТЮЗ), none at all on Opera.
