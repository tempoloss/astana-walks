# Round 9 — Satellite night lights vs OSM `lit` (Astana, тёплый/безопасный путь)

RECON ONLY. Date: 2026-10-18. No edits outside `collect/recon/round9/`.

## 1. Measured OSM lit layer (local, no network)

`data/city/lit.json` (collect/city/roads.py, © OpenStreetMap contributors, ODbL-1.0):

- ways with explicit lit tag: **956** → **lit=yes 858 / lit=no 98**
- pedestrian-like subset (footway/path/pedestrian) inside that file: 586 (yes 541 / no 45)

But this file is *only* the tagged universe — the real question is the denominator.

## 2. The gap: pedestrian network lit-tag coverage (Overpass probe)

bbox 51.10,71.39–51.16,71.47 (~6×8 км центр), `way[highway~footway|path|pedestrian]`:

| metric | value |
|---|---|
| footway/path/pedestrian ways total | **6 539** |
| with any `lit=*` | **233** |
| `lit=yes` | 198 |
| `lit=no` | 35 |
| **coverage** | **3.6 %** → **gap 96.4 %** |

Raw: `overpass_footway_counts_raw.json`, aggregated in `lit_coverage.json`.
Mirror note: `maps.mail.ru` Overpass returned 504 to every probe on 2026-10-18 (even a trivial bench count); counts were taken from `overpass-api.de` with the same UA/rate-limit (<1 req/s).

The tagged universe (lit.json, 956 roads+footways) is tiny next to the pedestrian network denominator — the gap is enormous → option (b) territory.

## 3. Resolution math — can VIIRS resolve a street?

VIIRS DNB native pixel = **750 m** (Black Marble VNP46A1/A2/A3/A4; 500 m is the pan-sharpened VNP46A2 surface type, still not street-level).

- Astana bbox 71.28–71.55 E, 51.03–51.25 N ≈ 18.9 × 24.3 km → **~25 × 32 ≈ 810 pixels for the entire city**.
- Main avenue ~20 km → **20 000 / 750 ≈ 27 pixels end-to-end**.
- One pixel = 0.5625 km² ≈ 7–8 typical city blocks; a 20 m-wide street occupies ≈ 2.7 % of a pixel area.
- Bonus killer: DNB radiance **saturates** in bright urban cores (Collection 2 ships saturation/quality flags), so within-Astana pixel contrast is compressed exactly where walking routes live.

→ VIIRS cannot answer "is this sidewalk lit". It can only answer "how bright is this district".

## 4. Licenses (raw text saved, one quoted line each)

### 4.1 NASA Black Marble (VNP46/VJ146) — `nl_blackmarble_datause.txt`
Earthdata (EOSDIS) Data Use Guidance, fetched 2026-10-18:
> "Unless the content is marked with a use restriction or license, data provided from a NASA-led mission are licensed as Creative Commons Zero (CC0). While there are no restrictions on the use of these data, data users are very strongly urged to cite the data used in their work products."

**CC0 / public domain → storable under our rule** (attribution requested, not required; no-endorsement clause applies to NASA logo use). `blackmarble.gitlab.io` is not an official NASA endpoint (official: blackmarble.gsfc.nasa.gov + LAADS DAAC).

### 4.2 EOG / Colorado School of Mines VNL annual composites — `nl_eog_vnl_license.txt`
> "Many of the VIIRS Nighttime Lights data are available under Creative Commons Attribution 4.0 International license."

**CC BY 4.0 → storable with attribution** ("This product was made utilizing VIIRS Nighttime Light (VNL) data produced by the Earth Observation Group, Payne Institute, Colorado School of Mines"). Note: specialized feeds (Nightfire, VBD) and bulk API need a paid commercial license — not needed here.

### 4.3 Light Pollution Map (lightpollutionmap.info) — `nl_lightpollutionmap_tos.txt`
No ToS page at all (`/About/TermsOfUse/`, `/About/`, `/About/Terms/` … all 404; site is a JS app). Help page Q14:
> "The use of data from www.lightpollutionmap.info should be credited to 'Jurij Stare, www.lightpollutionmap.info'. If VIIRS/Sky Brightness data is used or displayed it should also include 'NASA's Black Marble nighttime lights product'."

It is an **aggregator without an explicit grant** (credit-only convention, scraping not sanctioned). Its World Atlas 2015 overlay layer is **CC BY-NC 4.0** (GFZ/Falchi et al.) → NC, not storable. The site itself points to NASA VNP46A4 raw GeoTIFFs "under CC0 license" — the correct path is to download those, not to scrape LPM.

### 4.4 ecight / "Lucent Globe" — `nl_lucentglobe_license.txt`
lucentglobe.com `/license`, `/licensing` = 404; homepage is:
> "© 2025, Lucent Globe. | Terms of Service | Privacy Policy"

…a Shopify store selling **laundry/dishwasher detergent sheets** (Queensland, AU). Not a night-lights data vendor; the "ecight/lucentglobe" lead is a dead end / name confusion. No commercial data license exists to evaluate.

## 5. Verdict — option (b)

Street-level value of satellite night lights is **zero** (27 px per 20 km avenue, saturation in core). But the OSM `lit` gap on the pedestrian network is **96.4 %** (233/6 539). Therefore: do not use VIIRS for routing decisions; a **district-level "известная яркость" context layer** (e.g. mean annual radiance per city district polygon from VNP46A4/VJ146A4) is a defensible post-22.10 enrichment — it labels "this part of the city is dark" without pretending to know about a specific sidewalk.

License path, exactly: pull **NASA Black Marble VNP46A4/VJ146A4 yearly "AllAngle_Composite_Snow_Free" GeoTIFFs from LAADS/Earthdata (CC0)** — storable in our DB with a citation line; alternative **EOG VNL CC BY 4.0**. Store **nothing** from lightpollutionmap.info (no grant + NC-contaminated overlay); ignore Lucent Globe.
