## Licence (constant for all rows below)
Wikivoyage text: **CC BY-SA 4.0** — footer: "Text is available under the Creative Commons Attribution-ShareAlike License" (established for this pipeline in rounds 1–4, `collect/wikivoyage_places.py`; same terms on it/he/pl editions). STORE = yes, with attribution + share-alike for derived text. Fetch URL base for every row: `https://{L}.wikivoyage.org/w/api.php` (live HTTP 200 all probes below unless noted).

# 1. Authoritative edition list
`https://en.wikivoyage.org/w/api.php?action=query&titles=Astana&prop=langlinks&lllimit=500` → 16 langlinks: **de, el, eo, fa, fi, fr, he, it, nl, pl, pt, ru, tr, uk, vi, zh**. Parsed previously: en, de, ru, uk → 13 new probed live (each existence-verified by pageid, then wikitext fetched).

| edition | title (pageid) | listings (count) | hours= non-empty | price= non-empty | lat= filled | wdid= | phone | url | desc/content | GPX wpt (poi2gpx) | live proof | verdict / delta |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **it** | Astana (2233) | **~80** (`{{see/do/buy/eat/drink/sleep/listing}}`+`{{marker}}`) | **29** | **9** | ~70 | **33** | ~45 | ~30 | ~55 | **104** (1 lime, 4 go, 29 see, 8 do, 10 buy, 7 drink, 6 eat, 10 sleep, 3 other) | `action=parse&page=Astana&prop=wikitext` 200; e.g. `Torre di Bayterek … orari=Dom-Gio 10:00-21:00, Ven-Sab 9:00-21:00 \| prezzo=intero 500 T, ridotto 150 T \| wikidata=Q804210`; `Museo Nazionale … orari=Mar-Dom 10:00-18:00 \| prezzo=700 tenge per la collezione principale, 1000 tenge aggiuntivi per la galleria d'oro \| wikidata=Q18405670`; `Mappa Atameken … orari=Lun-Dom 9:00-21:00 \| prezzo=400 tenge, guida in inglese 500 tenge (giu 2019)` | **JACKPOT — STORE.** Fills hours (~25 museums/venues: Palace of Peace `Lun-Dom 10:00-18:00`, Ak Orda `Mar-Sab 7:30-20:00`, National Archives, Senate, Expo, all 10 malls 10:00–22:00, 6 restaurants, circus, Khazret mosque `09:00-21:00`), prices (Baiterek 500/150 T, National Museum 700+1000 T, Atameken 400 T, Alzhir 500 T, Ali Babas 3000 T, hostel 2000/6000 KZT), +55 long RU-language-agnostic descriptions, 33 wdid join keys, ~10 `immagine=` Commons filenames (photo-hole N/A via Commons anyway). poilo: 104 GPX wpts incl transport hub coordinates. |
| **he** | אסטנה (3339) | **~55** (`{{מוקדי}}`/`{{פעילויות}}`/`{{אוכל}}`/`{{שתייה}}`/`{{לינה}}`/`{{קניות}}`/`{{רשומה}}`) | **2** (Eurasia mall `פתוח בימים בכל ימות השבוע בין השעות 10:00 עד 21:00`; Fusion club `Ven-Sab 23:00-05:00` equivalent) | 0 | ~52 | **19** | ~25 | ~15 | 2 | **51** | wikitext 200: `שם=Palace of Peace and Reconciliation … lat=51.123056 \| long=71.463611 \| טלפון=+7 7172 74 47 44 \| ויקינתונים=Q2119741`; `שם=Bayterek Tower … טלפון=+7 701 998 2535 \| ויקינתונים=Q804210`; `שם=Eurasia shopping mall … שעות=פתוח בימים בכל ימות השבוע בין השעות 10:00 עד 21:00` | **STORE (secondary).** Main value = **19 wdid + 51 coord'd POIs** as cross-check/aliases against it; near-zero hours/price. Note he error: Nur-Astana Mosque coords 51.2175/71.6958 are wrong (out of bbox — it has correct 51.1266/71.4157). |
| **pl** | Astana (294) | **13 `{{zobacz}}`** + ~25 plaintext eat/hotel entries | 6 (in prose inside `opis=`: `Wt-Nd 10:00-20:00` ×3, `Codziennie 09:00-21:00`, `Mar-Dom 10:00-18:00`, sauna 24h) | 7 in prose (`500 tenge dla dorosłych, 150 tenge dla 5-15 lat`, `700 tenge…+1000 złota galeria`, `Wejście 500 tenge, audioprzewodnik 500 tenge`, melnica `główne 500-3000 tenge`, Ali Babas `3000 tenge`, Rafe `3000 tenge`) | 13 | 0 | ~8 | ~6 | ~30 | 0 — poi2gpx returns `No geocoded POI's in this WV acticle.` (tool doesn't parse pl templates) | wikitext 200: `Wieża Bajterek … opis=… 500 tenge dla dorosłych, 150 tenge dla 5-15 lat (z dokumentacją), poniżej 5 lat są bezpłatne`; `Muzeum Narodowe … opis=Wt-Nd 10:00-20:00 … 700 tenge do kolekcji głównej, 300 koncesji, dodatkowe 1000 tenge na złotą galerię`; `Meczet Sułtana Khazret … opis=Codziennie 09:00-21:00, ale turyści powinni unikać piątkowych popołudniowych modlitw` | **STORE (secondary).** Longest descriptions of any edition (polish, 200–600 chars each incl. Alzhir with bus schedule 10:00/11:50/13:00/14:30, 400 T). Hours must be regex-mined from `opis=` prose, not from a `godziny=` field (always empty). |
| fi | Astana (102) | 3 `{{Listing}}` | 0 | 0 | 3 | 0 | 0 | 2 | 0 | 3 | `Listing … name = Baiterekin torni … lat = 51.128265 \| long =71.430509 \| hours = \| price = \| content =` | EMPTY for attrs — coords-only dupes. Skip re-probe. |
| el | Νουρ-Σουλτάν (881) | 4 `{{see}}` | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | `see … name=Πύργος Μπαϊτέρεκ … lat=51.128239 \| long=71.430484 \| hours= \| price= \| content=` | EMPTY. Skip. |
| fr | Astana (17315) | 0; 1 `{{aller}}` (airport, Q174233) + 3 `{{Représentation diplomatique}}` | 1 structured `horaire={{Horaire\|1\|4\|8\|30\|12\|30\|14\|\|17\}}` (Belgian embassy) | 0 | 4 | 2 (Q174233, Q2841645) | 2 | 3 | 3 | n/a | Voir/Faire/Manger all empty. Embassies useless for us. Skip. |
| fa | آستانا (48) | 1 `{{دیدن}}` | 0 | 0 | 0 | 0 | 0 | 0 | 1 | n/a | 1 listing, no coords, desc only ("این برج نماد شهر … ۳۴۷ متر ارتفاع دارد" — also wrong height). Skip. |
| eo | Nursultano (5556) | 0 | — | — | — | — | — | — | — | n/a | Skeleton, no POI sections at all. Skip. |
| nl | Noersoeltan (214) | 0 | — | — | — | — | — | — | — | n/a | Bare bullet list ("de piramide van de vrede"). Skip. |
| pt | Astana (254) | 0 | — | — | — | — | — | — | — | n/a | All sections empty. Skip. |
| tr | Astana (3762) | 0 | — | — | — | — | — | — | — | n/a | Article is 2 sentences + category. Skip. |
| vi | Nursultan (83) | 0 | — | — | — | — | — | — | — | n/a | Outline; only transport prose. Skip. |
| zh | 阿斯塔納 (9611) | 0 | — | — | — | — | — | — | — | n/a | Skeleton with empty 观光/购物/用餐. NOTE: zh title is traditional 阿斯塔納 (simplified 阿斯塔纳 404s). Skip. |
| ru | Астана (6257) — re-counted | ~45 `{{listing}}` | 3 (Baiterek `09:00–21:00`, Sunday `11:00 - 00:00`, Chili Peppers `12:00 - 1:00`; Khan Shatyr has typo `hours==10:00–22:00`) | 2 (Atameken `входной билет 400 тенге…(2022)`, Alzhir vicinity) | ~20 | 11 (Q804210, Q4494668, Q1813417, Q573362, Q113675887, Q2119741, Q18405670, Q21371563, Q16632800, Q671484, Q1046294+…) | ~10 | ~8 | ~40 | n/a (already in pipeline) | Newest & richest ru data (2024 lastedit): 3 new POIs not in older en dump: Сфера Nur Alem (51.0894/71.4162), Центральная мечеть Q113675887, Айленд aquapark, + 10 ТРЦ w/o coords. Worth a re-run of the ru parser. |

# 2. Sub-articles / districts
- `list=allpages&apprefix=Astana/` on it and fr → **empty**. No edition splits Astana into districts. he has all 55 POIs in the single article; it likewise (823 lines).
- Redirects found: it `Nur-Sultan` (54574) → `#RINVIA [[Astana]]`; ru `Бурабай` → `Боровое`; ru `Акмолинская область` → `Северный Казахстан`. No hidden content.

# 3. Kazakh-tourism corpus (same licence, same parser)
| article | editions checked | listings | coords | wdid | hours | price | verdict |
|---|---|---|---|---|---|---|---|
| **Turkestan** | en (36938), it (45864), ru (13512), pl `Turkiestan (miasto)` exists, fa | en 14 (Yasawi `hours=09:00-18:00 \| price=5000 tenge for foreigners; 2000 tenge for nationals` wdid=Q46069, lastedit 2026-07-04; Hilvet price=500 tenge wdid=Q12576534; 3 Eat w/ hours+phone; 5 Drink; Platinum Hotel price=10,000 tenge 2026), it ~30 (Yasawi `orari=Lun-Dom 9:00-18:00 \| prezzo=500 tenge`, Hotel Khanaka prezzo `18.000/40.000 tenge`, Sauran Q4409147, Otrar Q956911, Arystan Bab Q4273752 w/ coords), ru 5 (4 hotels empty, Yasawi wdid=Q46069) | yes | 6 | **en+it yes** | **yes** | **STORE** — fills Turkestan for future multi-city; note en price (5000 T) vs it (500 T) conflict = freshness flag. |
| **Burabay/Borovoe** | en `Burabay National Park` (143217), ru `Боровое` (35061), ru `Щучинск` (1998), en `Kokshetau` (17938) | en: prose only (fees `198 tenge per pedestrian`, boats `1000T per half hour`, banya `5k tenge per hour`, bus №11 `250 tenge`, updated 2026). ru: 6 `{{listing type=see}}` coords-only (Болектау, Жумбактас, Окжетпес, Поляна Абылай-хана Q115268713, Кокше Q4420555, Пещера Кенесары Q16433273) + ru Щучинск 3 sleep listings no coords | 6 | 4 | 0 | prose in en | **STORE (small)** — 6 coord'd Burabay POIs as new POIs/aliases; en prose has current 2026 prices. |
| **Korgalzhyn** | en: no article (`titles=Korgalzhyn` missing); ru: no article | only markers: en `Kazakhstani North` `{{marker\|name=[[Korgalzhyn State Nature Reserve]]\|wikidata=Q1046294}}` + ru Astana `{{listing type=vicinity … wdid=Q1046294 \| unesco=yes \| lat=50.590183 \| long=70.022660 … description=посещение возможно только с экскурсией}}` | 1 | 1 | 0 | 0 | Alias + 1 POI (vicinity marker). No dedicated article exists anywhere — hole stays open. |
| Akmola region | ru redirect → `Северный Казахстан` (5719); en `Kazakhstani North` (17145) | en: 8 `{{marker type=city}}` + 3 destination markers, **all with wdid** (Q1520, Q4099294 Burabay NP, Q1046294, Q1817735 Bayanaul, Q1571825 Naurzum…) | — | 11 | 0 | 0 | Skeleton w/ good wdids. |

# 4. GPX skeleton (poi2gpx, coords+type, no attrs)
- it: **104 wpts** (fetched full GPX, live). he: **51 wpts** (counted from GPX: 25 see, 3 do, 1 buy, 9 eat, 2 drink, 11 sleep). pl: `No geocoded POI's in this WV acticle.` en/de/ru/uk already covered. GPX useful only as coord/type skeleton; the wikitext parse supersedes it for it/he.

# 5. Join-key availability (honest assessment)
- **it**: 33 listings carry `wikidata=Q…` → joinable by wdid; ~70 carry lat/long → lat/lon join (±50 m) to `data/poi.enriched.json`; the rest (small cafés, hostels) = name-only join, ~15 genuinely new POIs (Barys Arena Q16632800 has wdid but no hours, etc.).
- **he**: 19 wdid (same Q-ids as it for the overlapping sights — good cross-validation), ~51 with coords, ~30 name-only.
- **pl**: 0 wdid, 13 coords, remainder name-only (`Baiterek`→Байтерек etc.; Polish names transliterate predictably).
- Practical pipeline: wdid exact join → lat/lon radius join → normalized-name fallback; hours/prices from it > pl(prose-mined) > he.

# 6. kk.wikipedia category tree (description hole 2.4→6 %)
| category (Санат:) | members | live proof |
|---|---|---|
| Астана ғимараттары мен құрылыстары (+4 subcats) | **20 pages + 4 subcats** | `list=categorymembers&cmpageid=706294` HTTP 200 — Абу-Даби Плаза, Ақорда, Астана Арена, Хан Шатыр, Talan Towers, Қазмедиа орталығы, Назарбаев орталығы, МЕГА Астана, Астаналық цирк… |
| Астана көшелері | 667 (mostly stub street stubs — low value) | allcategories pageid 108048 categoryinfo `"pages": 667` |
| Астана ескерткіштері | 30 | pageid 483190 |
| Астана саябақтары | 7 | pageid 716030 |
| Астана театрлары | 7 | pageid 589857 |
| Астана сәулеті | 5 (+1 subcat) | pageid 483191 |
| Астана мұражайлары | **1** | pageid 749407 |
- **Extract quality** (`prop=extracts&exintro&explaintext`): Ақорда **~1400 chars**, Қазмедиа орталығы ~1000, Астана Арена ~700, Talan Towers ~560, Абу-Даби Плаза ~430, Астаналық цирк ~330, Тәуелсіздік сарайы ~330 — real KK-language descriptions. Short stubs exist too (Хан Шатыр ~130, Бейбітшілік ~110). Caveat: disambiguation traps (`Бәйтерек` is a village-list page; `МЕГА Астана` title redirects missing — use `МEGA` exact form). Estimated delta: **+25–30 Kazakh descriptions** for buildings/monuments already in our DB (join by name/coord), directly attacking the RU-only description hole. Category API quirk: `cmtitle` with Cyrillic+space fails `invalidcategory`; use `cmpageid` (pageids listed above).

# 7. kk.wikivoyage
- **Does not exist.** `kk.wikivoyage.org` resolves to Incubator `Wy/kk` — 6 pages total, main page only, zero Astana content beyond a 1-line mention. Nobody should re-probe kk/vo/hi/id/ar/cs/hu/ro/da/sv/ja/ko/th — none are in the langlinks, so they cannot have the article.

## Wins
1. **it:Astana = +29 hours, +9 prices, +33 wdid, +~55 descriptions, 104 coord'd POIs** — single biggest hours/price delta of the whole recon, CC BY-SA 4.0, zero new code beyond locale alias `nome/orari/prezzo/descrizione` in `wikivoyage_places.py`.
2. pl:Astana prose-mined hours/prices for 13 sights + ~25 venues (deepest non-EN descriptions).
3. he:Astana: 19 wdids + 51 coord'd POIs for cross-language dedupe validation.
4. ru:Astana was refreshed since our last parse (2024-2025 lastedits): 3 new POIs incl. Nur Alem sphere and Central Mosque (Q113675887) — re-run ru parser.
5. Turkestan en+it: full hours+prices (Yasawi 09:00-18:00, 5000 T foreign / 2000 T CIS, updated 2026-07) — first real Turkestan corpus for multi-city.
6. kk.wikipedia: 20 building/monument pages with kk extracts (several >300 chars) → KK descriptions for existing POIs.

## Dead / rejected
- eo, nl, pt, tr, vi, zh, el (attrs), fa, fi (attrs), fr (except 3 embassy listings): Astana article = skeleton/coords-only — do not re-probe.
- kk.wikivoyage: does not exist (Incubator Wy/kk, 6 pages).
- pl poi2gpx: broken for pl templates (`No geocoded POI's`).
- Korgalzhyn: no dedicated Wikivoyage article in any edition; only a `type=vicinity` marker in ru:Astana (Q1046294) and en region marker.
- Hotel category: he/pl/it hotel listings exist as `sleep` vCards (~25 across it/he/pl) but that's our known no-`hotel`-category issue, not fixed by this corpus.

## Unverified leads
- zh:zh-classical/other zh variants for 阿斯塔納 — langlinks say zh exists; only 阿斯塔納 (traditional) verified; simplified redirect unconfirmed.
- `vo` (Volapük) wikivoyage was in the old brief's try-list: not in langlinks, existence of any KZ article unprobed (low value, skipped).
- kk street articles (667): extracts untested — likely stubs, only worth mining for RU/KK street-name aliases.
- Wikiquote/Wikisource sitelinks for these POIs: skipped (per task item 6 allowance).