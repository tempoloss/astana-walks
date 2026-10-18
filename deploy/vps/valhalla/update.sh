#!/bin/bash
# Runs on the VPS as root: first install AND every refresh of the Astana routing graph. Idempotent.
#   bash update.sh                 download Geofabrik Kazakhstan, cut Astana, build tiles, swap, restart
#   bash update.sh --keep-source   reuse the Kazakhstan file already in /var/lib/anyq-valhalla/source
# Touches only: /var/lib/anyq-valhalla, the container anyq-valhalla (compose project anyq-valhalla) and the
# throw-away image anyq-osmium:local. The graph is built in a side directory and swapped in only when it is
# complete, so a failed build leaves the running routing untouched.
set -euo pipefail
trap 'echo "update.sh failed at line $LINENO (the running routing is untouched until step 4)" >&2' ERR

here=$(cd "$(dirname "$0")" && pwd)
compose="$here/docker-compose.yml"
base=/var/lib/anyq-valhalla
src="$base/source"
data="$base/data"
next="$base/next"
old="$base/data.old"
pbf_url=https://download.geofabrik.de/asia/kazakhstan-latest.osm.pbf
bbox=71.20,50.95,71.65,51.30 # minlon,minlat,maxlon,maxlat: Astana and its surroundings
image=$(docker compose -f "$compose" config --images)
keep_source=0
[ "${1:-}" = "--keep-source" ] && keep_source=1

install -d -m 0755 "$base" "$src"
rm -rf "$next" && install -d -m 0755 "$next"

echo "== 1/5 source"
if [ "$keep_source" = 0 ] || [ ! -s "$src/kazakhstan-latest.osm.pbf" ]; then
  curl -fL --retry 3 --retry-delay 10 -o "$src/kazakhstan-latest.osm.pbf.part" "$pbf_url"
  want=$(curl -fsSL "$pbf_url.md5" | cut -d' ' -f1)
  have=$(md5sum "$src/kazakhstan-latest.osm.pbf.part" | cut -d' ' -f1)
  [ "$want" = "$have" ] || { echo "md5 mismatch: $have != $want" >&2; exit 1; }
  mv "$src/kazakhstan-latest.osm.pbf.part" "$src/kazakhstan-latest.osm.pbf"
fi

echo "== 2/5 Astana extract ($bbox)"
docker build -q -t anyq-osmium:local -f "$here/osmium.Dockerfile" "$here" >/dev/null
# strategy simple: one pass, ~30 MB of memory (complete_ways over the whole country needs more than 2 GB and is
# killed by the limit); a way that crosses the box edge is cut there, which does not matter 20 km outside the city
docker run --rm --memory 2g --memory-swap 2g --cpus 2 --cpu-shares 256 \
  -v "$src:/src:ro" -v "$next:/out" anyq-osmium:local \
  extract -b "$bbox" --strategy simple --overwrite -o /out/astana.osm.pbf /src/kazakhstan-latest.osm.pbf
ls -l "$next/astana.osm.pbf"

echo "== 3/5 tiles"
# elevation is built into the tiles (SRTM, downloaded once for the 11 tiles): without it a walk is 1-7 % faster than
# on the public server, with it the legs agree with it; admin / timezone / default-speeds data changed nothing
docker run --rm --memory 2g --memory-swap 2g --cpus 2 --cpu-shares 256 \
  -v "$next:/custom_files" \
  -e use_tiles_ignore_pbf=False -e serve_tiles=False -e force_rebuild=True -e build_tar=True \
  -e build_admins=False -e build_time_zones=False -e build_elevation=True -e build_transit=False \
  -e use_default_speeds_config=False -e traffic_name= -e server_threads=2 \
  "$image" build_tiles
test -s "$next/valhalla_tiles.tar" || { echo "no tile tar built" >&2; exit 1; }

echo "== 4/5 swap and start"
docker compose -f "$compose" stop >/dev/null 2>&1 || true
rm -rf "$old"
[ -d "$data" ] && mv "$data" "$old"
mv "$next" "$data"
docker compose -f "$compose" up -d --force-recreate

healthy() {
  for _ in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' anyq-valhalla 2>/dev/null)" = healthy ] && return 0
    sleep 2
  done
  return 1
}
if ! healthy; then
  echo "new graph did not become healthy; rolling back" >&2
  docker logs --tail 40 anyq-valhalla >&2 || true
  docker compose -f "$compose" stop >/dev/null 2>&1 || true
  if [ -d "$old" ]; then
    rm -rf "$data" && mv "$old" "$data" && docker compose -f "$compose" up -d
  fi
  exit 1
fi

echo "== 5/5 smoke test"
curl -fsS -H 'Content-Type: application/json' http://127.0.0.1:8002/route \
  -d '{"locations":[{"lat":51.1283,"lon":71.4305},{"lat":51.1325,"lon":71.4033}],"costing":"pedestrian"}' \
  | python3 -c 'import sys,json; s=json.load(sys.stdin)["trip"]["summary"]; print("Baiterek -> Khan Shatyr: %.2f km, %d s" % (s["length"], s["time"]))'
rm -rf "$old"
[ "$keep_source" = 1 ] || rm -f "$src/kazakhstan-latest.osm.pbf"
echo "valhalla updated"
