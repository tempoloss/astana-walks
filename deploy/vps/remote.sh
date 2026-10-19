#!/bin/bash
# Runs on the VPS as root, from the freshly unpacked release: bash /opt/anyq/<sha>/deploy/vps/remote.sh <sha>
# Idempotent. Touches only the `anyq` user, /opt/anyq, /var/lib/anyq and the units anyq.service /
# cloudflared-anyq.service; nothing else on the host.
set -euo pipefail

sha="$1"
root=/opt/anyq
rel="$root/$sha"
state=/var/lib/anyq

id anyq >/dev/null 2>&1 || useradd --system --home-dir "$state" --no-create-home --shell /usr/sbin/nologin anyq
install -d -o anyq -g anyq -m 0750 "$state" "$state/uv-cache"
chown -R anyq:anyq "$rel"
runuser -u anyq -- env HOME="$state" UV_CACHE_DIR="$state/uv-cache" UV_PYTHON_DOWNLOADS=never \
  bash -c "cd '$rel/app' && uv sync --frozen --no-dev --python 3.12"
# the afisha collector (collect/) has its own, small environment at the release root
runuser -u anyq -- env HOME="$state" UV_CACHE_DIR="$state/uv-cache" UV_PYTHON_DOWNLOADS=never \
  bash -c "cd '$rel' && uv sync --frozen --no-dev --python 3.12"
# the satellite layer's tile cache (app/web/tiles.py): filled once here, as the service user, so a down upstream never
# leaves the layer empty; a repeated run asks only for missing tiles
install -d -o anyq -g anyq -m 0750 "$state/tiles"
runuser -u anyq -- env HOME="$state" WALKS_TILE_CACHE="$state/tiles" \
  bash -c "cd '$rel/app' && .venv/bin/python scripts/seed_tiles.py" || echo "tile seed incomplete: the layer fills on demand"

install -m 0644 "$rel/deploy/vps/anyq.service" /etc/systemd/system/anyq.service
install -m 0644 "$rel/deploy/vps/cloudflared-anyq.service" /etc/systemd/system/cloudflared-anyq.service
install -m 0644 "$rel/deploy/vps/anyq-events.service" /etc/systemd/system/anyq-events.service
install -m 0644 "$rel/deploy/vps/anyq-events.timer" /etc/systemd/system/anyq-events.timer
systemctl daemon-reload
systemctl enable anyq >/dev/null 2>&1
systemctl enable --now anyq-events.timer >/dev/null 2>&1

ln -sfn "$rel" "$root/current"
systemctl restart anyq

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8520/healthz >/dev/null 2>&1; then
    echo "anyq healthy: $sha"
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8520/healthz >/dev/null || { journalctl -u anyq -n 40 --no-pager; exit 1; }

# keep the three newest releases
ls -1dt "$root"/*/ | grep -v "/current/" | tail -n +4 | xargs -r rm -rf
systemctl is-active anyq
