#!/usr/bin/env bash
# deployment/manage.sh
# Day-2 management helper for the Pulse stack on EC2.
# Usage: bash deployment/manage.sh <command>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/deployment/.env"
COMPOSE_FILES="-f $REPO_ROOT/docker-compose.yml -f $REPO_ROOT/deployment/docker-compose.prod.yml"
COMPOSE="docker compose $COMPOSE_FILES --env-file $ENV_FILE"

cd "$REPO_ROOT"

case "${1:-help}" in

  start)
    echo "Starting all services..."
    $COMPOSE up -d
    ;;

  stop)
    echo "Stopping all services (volumes preserved)..."
    $COMPOSE down
    ;;

  restart)
    echo "Restarting all services..."
    $COMPOSE restart
    ;;

  status)
    $COMPOSE ps
    ;;

  logs)
    SERVICE="${2:-spark-job}"
    echo "Streaming logs for: $SERVICE  (Ctrl+C to exit)"
    $COMPOSE logs -f "$SERVICE"
    ;;

  destroy)
    echo "WARNING: This will STOP all containers and DELETE all volumes (Kafka data, Postgres data, Spark checkpoints)."
    read -r -p "Type 'yes' to confirm: " confirm
    if [[ "$confirm" == "yes" ]]; then
      $COMPOSE down -v
      echo "All containers and volumes removed."
    else
      echo "Aborted."
    fi
    ;;

  help|*)
    echo "Usage: bash deployment/manage.sh <command> [service]"
    echo ""
    echo "Commands:"
    echo "  start             Start all services"
    echo "  stop              Stop all services (volumes preserved)"
    echo "  restart           Restart all services"
    echo "  status            Show running containers"
    echo "  logs [service]    Tail logs (default: spark-job)"
    echo "  destroy           Stop + wipe all volumes (destructive)"
    echo ""
    echo "Available services: zookeeper, kafka, postgres, spark-job, producer"
    ;;

esac
