#!/usr/bin/env bash
set -euo pipefail

echo "=== [1/5] Updating Ubuntu 24.04 ARM64 (aarch64) packages ==="
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg ufw git jq cron

echo "=== [2/5] Installing Docker Engine & Compose Plugin ==="
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
fi

echo "=== [3/5] Installing Tailscale Mesh VPN ==="
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi

echo "=== [4/5] Hardening Firewall (Allow SSH + Tailscale Interface Only) ==="
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow in on tailscale0
sudo ufw --force enable

echo "=== [5/5] Configuring Nightly 03:00 Backup Cron ==="
mkdir -p "$(pwd)/backups"
CRON_CMD="0 3 * * * cd $(pwd) && docker exec lokachakra-postgres pg_dump -U lokachakra lokachakra_db | gzip > ./backups/pg_\$(date +\%F).sql.gz && find ./backups -type f -mtime +7 -delete"
(crontab -l 2>/dev/null | grep -v "lokachakra-postgres" || true; echo "$CRON_CMD") | crontab -

echo "=== Starting Lokachakra Oracle Cloud ARM64 Stack ==="
docker compose -f docker-compose.yml -f docker-compose.oracle.yml up -d --build
