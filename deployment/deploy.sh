#!/usr/bin/env bash
# deployment/deploy.sh
# One-command deploy of the full Pulse stack on EC2.
# Run from the repo root: bash deployment/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/deployment/.env"
COMPOSE_FILES="-f $REPO_ROOT/docker-compose.yml -f $REPO_ROOT/deployment/docker-compose.prod.yml"

echo "=== Pulse EC2 Deploy ==="

# ── Validate env file ─────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found."
  echo "  Copy the template: cp deployment/.env.example deployment/.env"
  echo "  Then fill in EC2_PUBLIC_IP and POSTGRES_PASSWORD."
  exit 1
fi

# shellcheck source=/dev/null
source "$ENV_FILE"

if [[ -z "${EC2_PUBLIC_IP:-}" || "$EC2_PUBLIC_IP" == "<your-ec2-public-ip>" ]]; then
  echo "ERROR: EC2_PUBLIC_IP is not set in deployment/.env"
  exit 1
fi

if [[ -z "${POSTGRES_PASSWORD:-}" || "$POSTGRES_PASSWORD" == "<strong-password-here>" ]]; then
  echo "ERROR: POSTGRES_PASSWORD is not set in deployment/.env"
  exit 1
fi

echo "EC2_PUBLIC_IP : $EC2_PUBLIC_IP"
echo "POSTGRES_DB   : ${POSTGRES_DB:-pulse}"
echo ""

cd "$REPO_ROOT"

# ── Pull latest images ────────────────────────────────────────────────────────
echo "--- Pulling latest base images..."
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" pull --ignore-buildable

# ── Build custom images (spark-job) ──────────────────────────────────────────
echo "--- Building spark-job image..."
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" build spark-job

# ── Start all services ────────────────────────────────────────────────────────
echo "--- Starting all services..."
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" up -d

# ── Wait for Postgres to be healthy ──────────────────────────────────────────
echo "--- Waiting for Postgres to be healthy..."
for i in $(seq 1 30); do
  if docker inspect --format='{{.State.Health.Status}}' pulse-postgres 2>/dev/null | grep -q "healthy"; then
    echo "    Postgres is healthy."
    break
  fi
  echo "    Attempt $i/30 — not ready yet, waiting 5s..."
  sleep 5
done

# ── Print status ──────────────────────────────────────────────────────────────
echo ""
echo "=== Service Status ==="
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" ps

echo ""
echo "=== Spark Job (last 20 lines) ==="
docker logs --tail 20 pulse-spark-job 2>/dev/null || echo "(spark-job not yet started)"

echo ""
echo "=== Deploy complete ==="
echo "Data will appear in Postgres after ~11 minutes (watermark delay)."
echo "To monitor: bash deployment/manage.sh logs"
