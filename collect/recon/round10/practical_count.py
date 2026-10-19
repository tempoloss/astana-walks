"""Count OSM coverage of practical/walkable layers the shipped base LACKS.

Appends each result to practical_layers_count.jsonl as it arrives, so a cut run
still holds partial numbers. Run from repo root:
    python collect/recon/round10/practical_count.py
"""
import json, time, urllib.request
from pathlib import Path

UA = {"User-Agent": "astana-walks-recon/1.0", "Accept": "*/*"}
BB = "(51.00,71.10,51.30,71.80)"
MIRROR = "https://overpass-api.de/api/interpreter"
OUT = Path(__file__).with_name("practical_layers_count.jsonl")

GROUPS = {
    "supermarket": 'nwr["shop"="supermarket"]',
    "convenience": 'nwr["shop"="convenience"]',
    "greengrocer": 'nwr["shop"="greengrocer"]',
    "butchery": 'nwr["shop"="butchery"]',
    "bakery": 'nwr["shop"="bakery"]',
    "pharmacy": 'nwr["amenity"="pharmacy"]',
    "atm": 'nwr["amenity"="atm"]',
    "bank": 'nwr["amenity"="bank"]',
    "fuel": 'nwr["amenity"="fuel"]',
    "hotel": 'nwr["tourism"="hotel"]',
    "hostel": 'nwr["tourism"="hostel"]',
    "guest_house": 'nwr["tourism"="guest_house"]',
    "post_office": 'nwr["amenity"="post_office"]',
    "parking": 'nwr["amenity"="parking"]',
    "marketplace": 'nwr["amenity"="marketplace"]',
    "veterinary": 'nwr["amenity"="veterinary"]',
    "laundry": 'nwr["amenity"="laundry"]',
    "hairdresser": 'nwr["shop"="hairdresser"]',
    "car_wash": 'nwr["amenity"="car_wash"]',
    "bench": 'nwr["amenity"="bench"]',
    "drinking_water": 'nwr["amenity"="drinking_water"]',
    "toilets": 'nwr["amenity"="toilets"]',
    "recycle": 'nwr["amenity"="recycling"]',
}

def count(q: str) -> dict | str:
    body = f"[out:json][timeout:50];({q}{BB};);out count;"
    for attempt in range(2):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(MIRROR, data=("data=" + body).encode(), headers=UA), timeout=90
            ) as x:
                e = json.loads(x.read())["elements"][0]["tags"]
                return {"nodes": int(e.get("nodes", 0)), "ways": int(e.get("ways", 0))}
        except Exception as ex:
            err = str(ex)[:60]
            time.sleep(20)
    return "ERR:" + err

def main() -> None:
    done = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                done[r["layer"]] = r
            except Exception:
                pass
    for name, q in GROUPS.items():
        if name in done:
            continue
        res = count(q)
        OUT.open("a", encoding="utf-8").write(
            json.dumps({"layer": name, "count": res}, ensure_ascii=False) + "\n"
        )
        print(name, res, flush=True)
        time.sleep(3)

if __name__ == "__main__":
    main()
