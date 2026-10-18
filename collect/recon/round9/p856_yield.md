# Round 9 recon — P856 hours yield for cultural venues

RECON ONLY. Base `data/poi.enriched.json` (2294 records) was read, not changed. Raw data: `p856_raw.json` (the Wikidata response, reachability log, crawled pages, snippets). Run date 2026-10-18.

## Funnel (records, not domains)

"Cultural" = the 4 categories named in the brief (`museum_gallery`, `culture_theatre_cinema`, `entertainment`, `coworking_library`) = "core-4". A wider 8-category cut (adds `attraction_landmark`, `viewpoint`, `park_garden`, `kids_playground`, the set used by `collect/sites/culture_inventory.py`) is shown for comparison.

**Single citable definition ("authoritative"):** venue Q-id = top-level `wikidata_id` (76 records in the base) ∪ `data/wiki_enrichment.json` matches. (Measured: 42 records also carry an OSM tag `wikidata=Q…`; every one of them is already in `wikidata_id`, so the tag adds nothing. 42 re-verified by the parent with a list-string matcher: `tags` is a LIST of 'key=value' strings, NOT a dict — dict `.get()` and dict-shaped grep both give a silent 0, and the earlier disputed line "tags.wikidata = 0" was exactly that artifact.) Core-4 = 125 records, 100 without `opening_hours`.

| step | core-4 authoritative | wide-8 authoritative |
|---|---:|---:|
| cultural records | 125 | 760 |
| …without `opening_hours` | **100** | 726 |
| …with a venue-level Q-id | **14** | 36 |
| …whose Wikidata entity has a non-deprecated P856 | **7** | 10 |
| …whose P856 domain answered 2xx | **5** | 7 |
| …with venue-level hours text on the site | **1** (`way/230358855`) | 1 |
| …with hours convertible to a valid OSM `opening_hours` | **0** | 0 |

Superseded first cut (kept only so the run is reproducible; do NOT cite): Q-id from OSM tag ∪ `wiki_enrichment.json` gave core-4 = 9 Q-id records (7 P856, 5 reachable) and wide-8 = 24 / 9 / 6. It missed 5 core-4 Q-ids (Q96035145, Q16433519, Q4230441, Q12561825, Q12530274) because it did not read `wikidata_id`.

Notes on the numbers:
- The earlier statement in this file that "no shipped record has a top-level `wikidata_id`" was wrong; corrected above.
- Wikidata: two `wbgetentities` calls (`ids` joined by `|`, `props=claims`, UA `astana-walks-research/0.1 (an8kk.sa@gmail.com)`): 24 Q-ids first, then the 12 Q-ids the first cut had missed (36 distinct in the wide cut, all exist). The 5 missing core-4 Q-ids carry **no P856**, so the core-4 funnel stays at 7 P856 / 5 reachable. The wide cut gains one P856: `http://sobor.kz/hramy/konstantino-eleninskiy-sobor` (Q97168093, `attraction_landmark`; 200; the page prints church service times «ежедневно в 9.00 … и в 17.00», not visiting hours, so no hours).
- Reachability (GET, 1 req/s, timeout 15 s, from this Windows host):

| P856 URL | status |
|---|---|
| https://astanaballet.com/ | 200 (→ /ru) |
| https://astanaopera.kz/ | 200 |
| http://www.zhastar-theatre.kz | 200 |
| http://nabrk.kz/en/ | 200 (→ https) |
| http://www.muslim.kz | 200 (wide scope only: mosque) |
| https://www.qazaqconcert.kz/ | 200 |
| http://museumgold.kz/ | **503** (parked-domain stub; `data/sites/facts/museumgold.kz.json` documents the same) |
| http://indepalace.kz/ | **no DNS** (`getaddrinfo failed`; facts file records the same on repeated probes) |
| https://botsad-nursultan.kz | **no DNS** (wide scope only) |
| http://sobor.kz/hramy/konstantino-eleninskiy-sobor | 200 (wide scope only; service times, no visiting hours) |

  Core-4: 5 reachable domains (astanaballet.com, astanaopera.kz, zhastar-theatre.kz, nabrk.kz, qazaqconcert.kz); wide-8: 7 (adds muslim.kz, sobor.kz). Fewer than 10 exist, so "top-10 reachable domains" = all of them.
- Extraction: `robots.txt` checked, then landing page + up to 7 keyword-matched internal links + `/contacts`, `/ru/contacts` (≤9 pages/domain, 1 req/s). A window is kept only if a time range `HH:MM–HH:MM` sits within ~120/80 chars of an hours keyword; the window text is stored verbatim. `collect.sites.hours.to_osm` was applied to every window: it returned `None` for all.

## Hours actually extractable (3 verbatim evidence snippets)

1. `https://nabrk.kz/en/page/work-schedule-library` → `way/230358855` (the only venue-level hit):
   > `Work schedule of library The National Academic Library of the Republic of Kazakhstan is open from 09.00 a.m. to 19.00 p.m. Saturday-Sunday from 09.00 a.m. to 18.00 p.m. The last Friday of each mont`
   Not OSM-convertible (weekday range unnamed — `needs_days`). The Russian page already stored in `data/sites/facts/nabrk.kz.json` says `до 20.00`, so the EN and RU pages disagree on the weekday closing time (19:00 vs 20:00); neither may be merged without a decision.
2. `https://astanaopera.kz/ru/contacts` → `way/917478479` — **box-office** hours, not venue hours:
   > `Время работы кассы Пн - Пт: 10:00 — 19:00 Сб - Вс: 10:00 — 18:00 Телефоны кассы +7 7172 709 600 Кассы закрываются за час`
3. `https://astanaopera.kz/contacts` (Kazakh) — the same box-office schedule:
   > `Кассаның жұмыс уақыты Жұмыс күндері: 10:00 — 19:00 Демалыс күндері: 10:00 — 18:00 Касса телефондары +7 7172 709 600 Касса жұмыстың`

No hours text at all (0 snippets) on astanaballet.com, zhastar-theatre.kz, qazaqconcert.kz, muslim.kz (consistent with the existing facts notes: no hours / JS widget / per-event schedule).

## Overlap with what is already harvested

Every one of the reachable (5 core-4 + 2 wide-8 extras) P856 domains (and museumgold.kz, indepalace.kz) already has a `data/sites/facts/<domain>.json` from the earlier first-party crawl (`collect/sites`), with the same conclusions (opera = box office only, nabrk = raw hours with `needs_days`, others = no hours). So the P856 route reproduced known evidence and found **0 new** hours.

## NEW records that would get non-null `opening_hours`: **0**

(Counted, authoritative definition: 100 cultural records without hours → 14 with Q-id → 7 with P856 → 5 reachable → 1 with venue-level hours text → 0 convertible without guessing days; the 1 candidate is already in `hours_unqualified` as raw text.)

## Verdict

P856 does not close the cultural hours hole: the Q-id bottleneck (14 of 100 records; authoritative definition, supersedes the earlier 9) and the website bottleneck (7 P856, 2 of them dead) leave 5 reachable domains, and none of them publishes venue-level hours in a form that converts to a valid `opening_hours` — measured 0 new records, against the 100 missing. Two caveats for the numbers: (1) only the 4-category scope was the target; the wide 8-category scope gives the same 0; (2) the extractor is a keyword+time-range window, so a schedule rendered by JS or in a PDF/image would be missed (the existing facts note this for qazaqconcert.kz).

- **(a) Safe today (no shipped data touched):** nothing from P856 is worth harvesting as new evidence — all reachable domains (5 core-4 + 2 wide-8 extras) are already in `data/sites/facts/`. The only open thing is the nabrk.kz EN/RU 19:00-vs-20:00 weekday discrepancy, which can sit as evidence in `data/sites/facts/` (or a note under `collect/recon/round9/`). Deck line must NOT say "hours gathered for N venues"; the honest line is "P856 route measured: 0 new venues, 5 official sites reachable, no new hours". Do not touch `data/poi.enriched.json`, `poi_enriched_stats.json` or the 40.5/36.9/66.7 unknown-hours rate.
- **(b) After 22.10:** no merge of P856 hours is justified (0 records). If the team wants to attack the hole after 22.10, the lever is not Wikidata but the 41 core records that already have an OSM `website` (only 3 domains in `facts/` have any hours: gorkytheatre.kz `Tu-Su 10:00-21:00`, nmrk.kz `Tu-Su 10:00-18:00`, nabrk.kz raw). Note [INFERENCE, not verified]: the `gorkytheatre.kz` and nmrk.kz facts belong to Overture-duplicate POIs (`overture/074ed08c-…`, `overture/f666893a-…`) that still show `opening_hours = null` in the base, so a join/dedupe fix could surface 2 records; any such merge changes `honest_unknown_rate` and the holdout pass rates, so it would go in one commit with `merge.py` and a regenerated `docs/scenarios.md` table.
