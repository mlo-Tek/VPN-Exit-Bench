#!/bin/bash
set -euo pipefail

APP_NAME="vpn-exit-bench"
IMAGE_NAME="vpn-exit-bench:latest"
SRC_DIR="/mnt/cache/appdata/vpn-exit-bench-src"
CONFIG_DIR="/mnt/cache/appdata/vpn-exit-bench"
VPN_DIR="$CONFIG_DIR/vpns"

mkdir -p "$VPN_DIR/Proton" "$VPN_DIR/OVPN"

cd "$SRC_DIR"

echo "==> Building $IMAGE_NAME"
docker build -t "$IMAGE_NAME" .

echo "==> Removing old container if present"
docker rm -f "$APP_NAME" >/dev/null 2>&1 || true

echo "==> Starting $APP_NAME"
docker run -d \
  --name "$APP_NAME" \
  --restart unless-stopped \
  -p 8787:8787 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$CONFIG_DIR:/config" \
  -e HOST_CONFIG_DIR="$VPN_DIR" \
  -e WORKER_IMAGE="$IMAGE_NAME" \
  -e DOWNLOAD_MB=100 \
  "$IMAGE_NAME"

echo
echo "VPN Exit Bench is running on port 8787."
echo "Open: http://UNRAID-IP:8787"
