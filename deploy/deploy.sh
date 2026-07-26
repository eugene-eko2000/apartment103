#!/usr/bin/env bash
# Deploys apartment103 (frontend + backend + MongoDB) to a single remote
# host over SSH using Docker Compose. Rsyncs the repo, then builds and starts
# the stack on the remote host.
#
# Config today comes from a plain env file (deploy/env/<environment>.env) —
# secrets management is a follow-up step, not part of this script.
#
# Usage:
#   ./deploy.sh <preprod|prod> <user@host> [remote-path] [ssh-port]
set -euo pipefail

usage() {
  echo "Usage: $0 <preprod|prod> <user@host> [remote-path] [ssh-port]" >&2
  exit 1
}

ENVIRONMENT="${1:-}"
SSH_TARGET="${2:-}"
[[ -z "$ENVIRONMENT" || -z "$SSH_TARGET" ]] && usage
if [[ "$ENVIRONMENT" != "preprod" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be 'preprod' or 'prod', got: $ENVIRONMENT" >&2
  exit 1
fi
REMOTE_PATH="${3:-/opt/apartment103-$ENVIRONMENT}"
SSH_PORT="${4:-22}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/env/$ENVIRONMENT.env"
PROJECT_NAME="apartment103-$ENVIRONMENT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE." >&2
  echo "Copy deploy/env/$ENVIRONMENT.env.example to deploy/env/$ENVIRONMENT.env and fill in real values first." >&2
  exit 1
fi

echo "==> Syncing repo to $SSH_TARGET:$REMOTE_PATH"
ssh -p "$SSH_PORT" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH'"
rsync -az --delete \
  -e "ssh -p $SSH_PORT" \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.next' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  --exclude '*.egg-info' \
  --exclude 'deploy/env/*.env' \
  "$REPO_ROOT/" "$SSH_TARGET:$REMOTE_PATH/"

echo "==> Copying $ENVIRONMENT env file"
ssh -p "$SSH_PORT" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH/deploy/env'"
scp -P "$SSH_PORT" "$ENV_FILE" "$SSH_TARGET:$REMOTE_PATH/deploy/env/$ENVIRONMENT.env"

echo "==> Building and starting containers on remote host"
# shellcheck disable=SC2087
ssh -p "$SSH_PORT" "$SSH_TARGET" bash -s <<EOF
set -euo pipefail
cd '$REMOTE_PATH/deploy'
docker compose \
  -p '$PROJECT_NAME' \
  -f docker-compose.yml \
  -f docker-compose.$ENVIRONMENT.yml \
  --env-file 'env/$ENVIRONMENT.env' \
  up -d --build
EOF

echo "==> Deployed. Container status:"
ssh -p "$SSH_PORT" "$SSH_TARGET" \
  "docker compose -p '$PROJECT_NAME' -f '$REMOTE_PATH/deploy/docker-compose.yml' -f '$REMOTE_PATH/deploy/docker-compose.$ENVIRONMENT.yml' --env-file '$REMOTE_PATH/deploy/env/$ENVIRONMENT.env' ps"

echo
echo "Note: DB migrations are not run automatically. To apply them:"
echo "  ssh -p $SSH_PORT $SSH_TARGET \"cd $REMOTE_PATH/deploy && docker compose -p $PROJECT_NAME -f docker-compose.yml -f docker-compose.$ENVIRONMENT.yml --env-file env/$ENVIRONMENT.env exec backend uv run mongo-migrate migrate --forward --no-use-transaction\""
