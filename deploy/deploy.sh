#!/usr/bin/env bash
# Deploys apartment103 (frontend + backend + MongoDB) to a single remote
# host over SSH using Docker Compose. Rsyncs the repo, then builds and starts
# the stack on the remote host.
#
# Non-secret config comes from deploy/env/<environment>.env (rsynced to the
# host like the rest of the repo). Real secrets come from
# .secrets/<environment>.env on THIS machine and are never written to the
# deployment host's disk by this script: they're sent over the SSH
# transport as `export KEY=value` lines executed by the remote shell, so
# `docker compose` picks them up from its own process environment. (Note:
# `docker compose --env-file /dev/stdin` looks like it should do this more
# simply, but silently fails to read anything on Compose v2 — verified
# against v2.31 — hence the export-based approach.) Dedicated secrets
# management (Vault/Swarm secrets/etc.) is a further follow-up, not part of
# this script.
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
SECRETS_DIR="$REPO_ROOT/.secrets"
SECRETS_FILE="$SECRETS_DIR/$ENVIRONMENT.env"
PROJECT_NAME="apartment103-$ENVIRONMENT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE." >&2
  echo "Copy deploy/env/$ENVIRONMENT.env.example to deploy/env/$ENVIRONMENT.env and fill in real values first." >&2
  exit 1
fi

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Missing $SECRETS_FILE." >&2
  echo "Copy .secrets/$ENVIRONMENT.env.example to .secrets/$ENVIRONMENT.env (chmod 600) and fill in real values first." >&2
  exit 1
fi

secrets_dir_mode="$(stat -f '%OLp' "$SECRETS_DIR" 2>/dev/null || stat -c '%a' "$SECRETS_DIR" 2>/dev/null || true)"
if [[ -n "$secrets_dir_mode" && "$secrets_dir_mode" != "700" ]]; then
  echo "Warning: $SECRETS_DIR is mode $secrets_dir_mode, expected 700 (chmod 700 '$SECRETS_DIR')." >&2
fi

# The compose file deliberately doesn't hard-require these (so read-only
# commands like `ps`/`logs` don't need secrets piped in) — so check here
# instead, before anything gets sent over the network.
if ! grep -Eq '^JWT_SECRET_KEY=\S' "$SECRETS_FILE"; then
  echo "JWT_SECRET_KEY is empty in $SECRETS_FILE — refusing to deploy." >&2
  exit 1
fi

echo "==> Syncing repo to $SSH_TARGET:$REMOTE_PATH"
ssh -p "$SSH_PORT" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH'"
rsync -az --delete \
  -e "ssh -p $SSH_PORT" \
  --exclude '.git' \
  --exclude '.secrets' \
  --exclude 'node_modules' \
  --exclude '.next' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  --exclude '*.egg-info' \
  --exclude 'deploy/env/*.env' \
  "$REPO_ROOT/" "$SSH_TARGET:$REMOTE_PATH/"

echo "==> Copying $ENVIRONMENT env file (non-secret config only)"
ssh -p "$SSH_PORT" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH/deploy/env'"
scp -P "$SSH_PORT" "$ENV_FILE" "$SSH_TARGET:$REMOTE_PATH/deploy/env/$ENVIRONMENT.env"

echo "==> Building and starting containers on remote host (secrets exported into the remote shell only, never written to disk)"
{
  echo "set -euo pipefail"
  echo "cd '$REMOTE_PATH/deploy'"
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    printf 'export %s=%q\n' "$key" "$value"
  done < "$SECRETS_FILE"
  echo "docker compose -p '$PROJECT_NAME' -f docker-compose.yml -f docker-compose.$ENVIRONMENT.yml --env-file 'env/$ENVIRONMENT.env' up -d --build"
} | ssh -p "$SSH_PORT" "$SSH_TARGET" bash -s

echo "==> Deployed. Container status:"
ssh -p "$SSH_PORT" "$SSH_TARGET" \
  "docker compose -p '$PROJECT_NAME' -f '$REMOTE_PATH/deploy/docker-compose.yml' -f '$REMOTE_PATH/deploy/docker-compose.$ENVIRONMENT.yml' --env-file '$REMOTE_PATH/deploy/env/$ENVIRONMENT.env' ps"

echo
echo "Note: DB migrations are not run automatically (they don't need secrets — mongo-migrate only uses MONGO_URI/MONGO_DB). To apply them:"
echo "  ssh -p $SSH_PORT $SSH_TARGET \"cd $REMOTE_PATH/deploy && docker compose -p $PROJECT_NAME -f docker-compose.yml -f docker-compose.$ENVIRONMENT.yml --env-file env/$ENVIRONMENT.env exec backend uv run --no-sync mongo-migrate migrate --forward --no-use-transaction\""
