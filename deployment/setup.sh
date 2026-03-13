#!/usr/bin/env bash
# setup.sh — runs on the EC2 instance (Amazon Linux 2023)
# Installs Docker + Compose, clones the repo, and starts the stack.
# Called automatically by deploy.sh via SSH.

set -euo pipefail

REPO_URL="${REPO_URL:-}"          # injected by deploy.sh
BRANCH="${BRANCH:-main}"
APP_DIR="/opt/pulse"
ENV_FILE="${APP_DIR}/.env"

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[setup] Installing system packages..."
sudo dnf update -y -q
sudo dnf install -y -q git

# ── 2. Docker ─────────────────────────────────────────────────────────────────
echo "[setup] Installing Docker..."
sudo dnf install -y -q docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# ── 3. Docker Compose plugin ──────────────────────────────────────────────────
echo "[setup] Installing Docker Compose plugin..."
COMPOSE_VERSION="v2.27.1"
COMPOSE_DIR="/usr/local/lib/docker/cli-plugins"
sudo mkdir -p "${COMPOSE_DIR}"
sudo curl -fsSL \
  "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o "${COMPOSE_DIR}/docker-compose"
sudo chmod +x "${COMPOSE_DIR}/docker-compose"

# ── 4. Clone repository ───────────────────────────────────────────────────────
if [[ -z "${REPO_URL}" ]]; then
  echo "[setup] ERROR: REPO_URL is not set. Pass it via the environment before calling setup.sh."
  exit 1
fi

echo "[setup] Cloning ${REPO_URL} (branch: ${BRANCH})..."
sudo git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
sudo chown -R ec2-user:ec2-user "${APP_DIR}"

# ── 5. .env file ──────────────────────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[setup] Creating .env from env.example — EDIT IT before starting the stack."
  cp "${APP_DIR}/deployment/env.example" "${ENV_FILE}"
  # Inject the instance's own public IP
  PUBLIC_IP=$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4 || echo "")
  if [[ -n "${PUBLIC_IP}" ]]; then
    sed -i "s|<your-ec2-public-ip>|${PUBLIC_IP}|g" "${ENV_FILE}"
    echo "[setup] EC2_PUBLIC_IP set to ${PUBLIC_IP}"
  fi
fi

# ── 6. Start the stack ────────────────────────────────────────────────────────
echo "[setup] Starting Pulse stack..."
cd "${APP_DIR}"

# docker commands need the group to take effect — use 'sg docker'
sg docker -c "
  docker compose \
    -f docker-compose.yml \
    -f deployment/docker-compose.prod.yml \
    up -d --build
"

echo ""
echo "[setup] Done. Services:"
sg docker -c "docker compose ps"
echo ""
echo "Next steps:"
echo "  1. Edit ${ENV_FILE} to set a strong POSTGRES_PASSWORD."
echo "  2. Run: sudo -u ec2-user bash -c 'cd ${APP_DIR} && docker compose -f docker-compose.yml -f deployment/docker-compose.prod.yml restart postgres spark-job'"
