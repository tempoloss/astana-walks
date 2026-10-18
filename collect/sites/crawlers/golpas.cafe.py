"""golpas.cafe: stores nothing, on purpose.

The site is a Flutter SPA with no server-rendered content. The restaurant list its app shows comes from
https://ailillu.kz/api/v0/restaurants (the URL is hard-coded in main.dart.js) — but that is the API of an
ordering-platform vendor serving 155 restaurants of dozens of brands (Coffee, Saya, SQ, Doner, Italita, ...,
17 of them «Гол+Пас»), not Golpas' own backend and not a page of the business. Facts from it are third-party
platform data, so no branch is stored; the POIs keep their OSM/Overture values. (Until 2026-10-17 17 branches were
stored from it with `confidence` 0.7; the 8 POIs they matched got an address and an `opening_hours_official`.)
"""
from __future__ import annotations

from collect.sites.fetch import SiteFetcher

API = "https://ailillu.kz/api/v0/restaurants"


def crawl(fetcher: SiteFetcher):  # noqa: ARG001 - nothing is fetched: see the module docstring
    notes = ("no first-party data: golpas.cafe is a Flutter SPA whose restaurant list comes from "
             "https://ailillu.kz/api/v0/restaurants, the multi-tenant ordering platform of a vendor (155 restaurants, "
             "dozens of brands, per-restaurant `organization_id`/`brand_id`), not Golpas' own backend; the list is "
             "third-party platform data and is not stored. Earlier the 17 'Гол+Пас' entries were stored from it "
             "(confidence 0.7) and dropped on 2026-10-17: the POI-level rule is that official hours must come from a "
             "domain that speaks for the POI and from the business's own page.")
    return [], [], notes
