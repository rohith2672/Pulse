#!/usr/bin/env bash
# deployment/setup.sh
# One-time bootstrap for a fresh Ubuntu 22.04 EC2 instance.
# Run as root (or with sudo): sudo bash setup.sh
set -euo pipefail

echo "=== Pulse EC2 Bootstrap ==="

# ── System update ─────────────────────────────────────────────────────────────
apt-get update -y
apt-get upgrade -y

# ── Install dependencies ──────────────────────────────────────────────────────
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    git \
    lsb-release \
    unzip

# ── Install Docker (official repo) ───────────────────────────────────────────
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# ── Enable Docker service ─────────────────────────────────────────────────────
systemctl enable docker
systemctl start docker

# ── Add ubuntu user to docker group (no sudo needed for docker commands) ─────
usermod -aG docker ubuntu

echo ""
echo "=== Setup complete ==="
echo "Docker version : $(docker --version)"
echo "Compose version: $(docker compose version)"
echo ""
echo "Next steps:"
echo "  1. Log out and back in (or run: newgrp docker) to apply group changes"
echo "  2. Clone the repo: git clone <repo-url> ~/Pulse && cd ~/Pulse"
echo "  3. Copy and fill in env: cp deployment/.env.example deployment/.env"
echo "  4. Deploy: bash deployment/deploy.sh"
