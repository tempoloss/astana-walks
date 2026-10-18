"""KartaView photo grid over Astana, keyless (scout method 21.11: /2.0/photo/?lat&lng&radius<=500).

Saves the raw records BEFORE any join is computed: kv_photos_raw.json. Prints the photo count.
Run: python collect/recon/round10/kv_grid_fetch.py  (from repo root)
"""
import json, math, time, urllib.request, urllib.error
from pathlib import Path

UA = {"User-Agent": "astana-walks-recon/1.0"}
CENTER = (51.13, 71.43)
HALF = 0.030  # ~3.3 km N-S, ~2 km E-W box around EXPO/Baiterek/Old town spine
STEP = 0.0045  # ~500 m
OUT = Path(__file__).with_name("kv_photos_raw.json")


FAILED: dict[str, int] = {}  # point -> last error code; reported at the end, never silent


def fetch(lat: float, lng: float) -> list[dict]:
    base = f"https://api.kartaview.org/2.0/photo/?lat={lat:.4f}&lng={lng:.4f}&radius=500"
    out: list[dict] = []
    page, more = 1, True
    while more and page <= 5:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(f"{base}&page={page}", headers=UA), timeout=25
                ) as x:
                    j = json.loads(x.read(4_000_000).decode("utf-8", "replace"))
                # envelope: {"result": {"data": [...], "hasMoreData": bool}, "status": {...}}
                res = j.get("result") or {}
                if isinstance(res, dict):
                    out.extend(res.get("data") or [])
                    more = bool(res.get("hasMoreData"))
                else:
                    out.extend(res if isinstance(res, list) else [])
                    more = False
                break
            except urllib.error.HTTPError as e:
                FAILED[f"{lat:.4f},{lng:.4f}"] = e.code
                if e.code == 429:
                    time.sleep(4 + 4 * attempt)  # rate limit: back off, do not swallow into a low count
                    continue
                time.sleep(2 + 3 * attempt)
            except Exception:
                FAILED[f"{lat:.4f},{lng:.4f}"] = -1
                time.sleep(2 + 3 * attempt)
        else:
            more = False
        page += 1
    return out


def main() -> None:
    seen: dict[str, dict] = {}
    pts = 0
    lats = [CENTER[0] - HALF + STEP * k for k in range(int(2 * HALF / STEP) + 1)]
    lons = [CENTER[1] - HALF + STEP * k for k in range(int(2 * HALF / STEP) + 1)]
    for a in lats:
        for b in lons:
            pts += 1
            for p in fetch(a, b):
                pid = str(p.get("id"))
                if pid not in seen and p.get("lat") is not None and p.get("lng") is not None:
                    seen[pid] = {
                        "id": pid,
                        "lat": p["lat"],
                        "lng": p["lng"],
                        "sequenceId": p.get("sequenceId"),
                        "shotDate": p.get("shotDate") or p.get("dateAdded"),
                    }
            if pts % 30 == 0:
                print(f"{pts} points, {len(seen)} unique photos", flush=True)
            time.sleep(0.15)
    OUT.write_text(json.dumps(sorted(seen.values(), key=lambda r: r["id"]), ensure_ascii=False), "utf-8")
    print("done:", pts, "grid points ->", len(seen), "unique photos saved to", OUT.name)
    if FAILED:
        import collections
        print("FAILED points:", len(FAILED), dict(collections.Counter(FAILED.values()).most_common(4)))
        Path(__file__).with_name("kv_grid_errors.json").write_text(json.dumps(FAILED, ensure_ascii=False), "utf-8")


if __name__ == "__main__":
    main()
