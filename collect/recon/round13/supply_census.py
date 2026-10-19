"""OSM supply census for every layer the silent battery says we lack: one Overpass
request, per (tagset) a total count and a named count. A layer is a POI candidate only
with real named supply; a huge nameless mass is park-furniture class (owner policy).

    uv run python collect/recon/round13/supply_census.py
Writes supply_census.json next to this file. Legal: ODbL, read-only counting, UA polite.
"""
from __future__ import annotations
import json, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ENDPOINT = "https://overpass-api.de/api/interpreter"
MIRRORS = [
    ENDPOINT,
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
AREA = 'area["name"="Астана"]["admin_level"~"4|6|7|8"]->.a;'
# label -> list of Overpass filters (each a complete nwr selector minus the area)
LAYERS = {
    "marketplace": ['nwr["amenity"="marketplace"]'],
    "tobacco": ['nwr["shop"="tobacco"]'],
    "dentist": ['nwr["amenity"="dentist"]', 'nwr["healthcare"="dentist"]'],
    "clinic_urgent": ['nwr["amenity"="clinic"]', 'nwr["healthcare"~"^(clinic|centre|laboratory)$"]'],
    "bus_stop": ['nwr["highway"="bus_stop"]'],
    "rail_station": ['nwr["railway"~"^(station|halt|tram_stop)$"]', 'nwr["public_transport"="station"]["railway"]'],
    "metro": ['nwr["station"="subway"]'],
    "taxi_stand": ['nwr["amenity"="taxi"]'],
    "parking": ['nwr["amenity"="parking"]'],
    "fuel": ['nwr["amenity"="fuel"]'],
    "post_office": ['nwr["amenity"="post_office"]'],
    "post_box": ['nwr["amenity"="post_box"]'],
    "parcel_locker": ['nwr["amenity"="parcel_locker"]', 'nwr["vending"="parcel_locker"]'],
    "notary": ['nwr["office"="notary"]'],
    "lawyer": ['nwr["office"="lawyer"]'],
    "police": ['nwr["amenity"="police"]'],
    "fire_rescue": ['nwr["amenity"~"^(fire_station|rescue_station)$"]'],
    "veterinary": ['nwr["amenity"="veterinary"]'],
    "pet_boarding": ['nwr["amenity"="animal_boarding"]', 'nwr["shop"="pet"]'],
    "laundry_dryclean": ['nwr["amenity"~"^(laundry|dry_cleaning)$"]', 'nwr["shop"~"^(laundry|dry_cleaning)$"]'],
    "shower": ['nwr["amenity"="shower"]'],
    "sauna": ['nwr["leisure"="sauna"]', 'nwr["amenity"="sauna"]'],
    "hairdresser_beauty": ['nwr["shop"~"^(hairdresser|beauty|massage)$"]'],
    "phone_repair": ['nwr["shop"="mobile_phone"]', 'nwr["craft"~"^(electronics_repair|phone_repair)$"]'],
    "pawn_money": ['nwr["amenity"~"^(pawn|money_lender)$"]', 'nwr["financial"="pawnbroker"]',
                   'nwr["shop"="pawnbroker"]'],  # the KZ tag is shop=pawnbroker (32 named, round 25); without it
    # this layer measured ~0 and would have falsely closed the class
    "food_court": ['nwr["amenity"="food_court"]'],
    "cemetery": ['nwr["landuse"="cemetery"]', 'nwr["amenity"="grave_yard"]'],
    "worship": ['nwr["amenity"="place_of_worship"]'],
    "bakery_confectionery": ['nwr["shop"~"^(bakery|confectionery|pastry)$"]'],
    "bicycle_rental_parking": ['nwr["amenity"~"^(bicycle_rental|bicycle_parking)$"]'],
    "ice_rink": ['nwr["leisure"="ice_rink"]'],
    "swim_ski": ['nwr["sport"~"^(swimming|skiing)$"]', 'nwr["leisure"~"^(water_park|swimming_pool)$"]'],
    "bench": ['nwr["amenity"="bench"]'],
    "waste_recycling": ['nwr["amenity"~"^(waste_basket|recycling|toilets)$"]'],
    "zoo_aquarium": ['nwr["tourism"~"^(zoo|aquarium|theme_park)$"]'],
    "farmers_market": ['nwr["amenity"="marketplace"]["marketplace"="produce"]', 'nwr["shop"~"^(greengrocer|butcher|cheese|delicatessen)$"]'],
    "nature_playground": ['nwr["leisure"="playground"]'],
    "viewpoint_picnic": ['nwr["tourism"~"^(viewpoint|picnic_site)$"]'],
    "cycle_infra": ['nwr["highway"="cycleway"]'],
}

# hungry-layer mirror: the category table flagged ГОЛОД exactly where LAYERS above was blind
# (advisory 22) - museum/theatre/sport-core/library/coworking + paid parking, recycling, lockers
LAYERS.update(
    {
        "museum_core": ['nwr["tourism"~"^(museum|gallery)$"]'],
        "theatre_cinema_core": ['nwr["amenity"~"^(theatre|cinema)$"]'],
        "sport_core": ['nwr["leisure"~"^(stadium|pitch|sports_centre|sports_hall)$"]'],
        "library_core": ['nwr["amenity"="library"]'],
        "coworking_core": ['nwr["amenity"="coworking_space"]'],
        "bowling_billiard_climbing": ['nwr["sport"~"^(bowls|billiards|climbing|karting|skateboard)$"]'],
        "parking_paid": ['nwr["amenity"="parking"]["fee"~"^(yes|amount)$"]'],
        "recycling_bins": ['nwr["amenity"="recycling"]'],
        "parcel_lockers": ['nwr["amenity"="parcel_locker"]', 'nwr["vending"="parcel_locker"]'],
        "bench": ['nwr["amenity"="bench"]'],
    }
)

def q(label: str, sels: list[str]) -> str:
    out = ["[out:json][timeout:60];", AREA]
    for s in sels:  # union total
        out.append(f"({s}(area.a););")
    out.append(f'out count;')
    named = "+".join(f'({s}["name"](area.a);)' for s in sels)
    out.append(f"[out:json][timeout:60];{AREA}({named});out count;")
    return "\n".join(out)

def main():
    import io
    res = {}
    done = set()  # resume: finished layers are not re-asked (Overpass 429 pressure); error rows do NOT count
    jf = HERE / "supply_census.jsonl"
    if jf.exists():
        for line in jf.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if "error" not in d and d.get("layer"):
                done.add(d["layer"])
                res[d["layer"]] = {k: v for k, v in d.items() if k != "layer"}
    for label, sels in LAYERS.items():
        if label in done:
            continue
        body_all = "[out:json][timeout:60];" + AREA + "".join(f"({sel}(area.a););" for sel in sels) + "out count;"
        body_named = "[out:json][timeout:60];" + AREA + "".join(f'({sel}["name"](area.a););' for sel in sels) + "out count;"
        try:
            def cnt(body, suspect_zero: bool = False):
                last: Exception | None = None
                # rotation also moves with the minute: a RESCAN of one suspect layer must not re-enter the
                # same mirror that produced the zero (advisory) - deterministic index alone did exactly that
                start = (int(time.time()) // 60 + list(LAYERS).index(label)) % len(MIRRORS)
                zero_seen, last_val = 0, None
                for attempt in range(7 if suspect_zero else 4):
                    url = MIRRORS[(attempt + start) % len(MIRRORS)]
                    req = urllib.request.Request(
                        url, data=("data=" + body).encode(), method="POST",
                        headers={"User-Agent": "astana-walks-supply-census (research)",
                                 "Content-Type": "application/x-www-form-urlencoded"})
                    try:
                        with urllib.request.urlopen(req, timeout=75) as r:
                            payload = json.loads(r.read().decode("utf-8", "replace"))
                    except Exception as ex:  # overpass-api.de answers 429 as HTML; retry the next mirror/backoff
                        last = ex
                        time.sleep(20 * (attempt + 1))
                        continue
                    # `out count` returns ONE element tags={nodes,ways,relations,total} - there is no "count"
                    # key; reading it made EVERY layer a false 0 (sanity check: pharmacy=188 read as 0).
                    # A valid JSON WITHOUT any count element is NOT a zero - loaded mirrors answer
                    # {"elements":[]} - that must retry/raise, else metro/taxi 0/0 could be that lie too.
                    last_val = None
                    for e in payload.get("elements", []):
                        t = e.get("tags", {})
                        if "total" in t:
                            last_val = int(t["total"]); break
                        if {"nodes", "ways", "relations"} & t.keys():
                            last_val = sum(int(t.get(k, 0)) for k in ("nodes", "ways", "relations")); break
                        if "count" in t:
                            last_val = int(t["count"]); break
                    if last_val is None:
                        last = RuntimeError(f"{url}: valid JSON without a count element")
                        time.sleep(6)
                        continue
                    if last_val == 0 and suspect_zero and zero_seen < len(MIRRORS):
                        # §25 mirror trap: combined `["k=v"]["name"]` answers a VALID JSON 0 on some mirrors;
                        # only a zero that every mirror repeats is the truth (bus_stop: census 0, probe 544)
                        zero_seen += 1
                        time.sleep(3)
                        continue
                    return last_val
                raise last if last else RuntimeError(f"{label}: no answer after retries")
            a = cnt(body_all)
            n = cnt(body_named, suspect_zero=(a >= 10))  # a named-zero on a non-trivial total is re-asked
            res[label] = {"total": a, "named": n}
            print(label, a, n, "re-asked" if n == 0 and a >= 10 else "", flush=True)
        except Exception as ex:
            res[label] = {"error": str(ex)[:140]}
            print(label, "ERR", str(ex)[:100], flush=True)
        (HERE / "supply_census.jsonl").open("a", encoding="utf-8").write(
            json.dumps({"layer": label, **res[label]}, ensure_ascii=False) + "\n")  # flushed per layer:
        time.sleep(2.5)   # a 429 mid-run costs only the layer it hit, never the whole census
    (HERE / "supply_census.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote supply_census.json")

if __name__ == "__main__":
    sys.exit(main())
