#!/usr/bin/env bash
# Deploys apartment103 (nginx + frontend + backend + MongoDB) to a single
# remote host over SSH using Docker Compose. Rsyncs the repo, then builds
# and starts the stack on the remote host.
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
# The TLS certificate + private key are the one exception to "never written
# to disk": nginx needs them as files, not env vars. Their filenames come
# from SSL_CERT_FILE/SSL_KEY_FILE in deploy/env/<environment>.env; the files
# themselves are read from .secrets/certs/<environment>/ on THIS machine and
# scp'd (mode 600) to .secrets/certs/ under the remote deploy path, which
# docker-compose.yml mounts into the nginx container.
#
# `docker`/`docker compose` on the remote host require sudo, and that sudo
# requires a password (no NOPASSWD entry) — so it can't just be prefixed onto
# a normal non-interactive ssh command; there's no tty for sudo to prompt on.
# Instead, the password is read once (interactively, or from
# $DEPLOY_SUDO_PASSWORD for CI) and streamed to `sudo -S` as the first line of
# stdin on each remote docker invocation — the same "never touches disk"
# treatment as the other secrets. `sudo -S` consumes exactly that one line and
# leaves the rest of stdin (the exported secrets + compose command, for the
# build step) untouched for the command it runs.
#
# Usage:
#   ./deploy.sh [-i ssh_key] [-v] <preprod|prod> <user@host> [remote-path] [ssh-port]
#
# -v prints ssh/scp/rsync protocol-level debug output (connection setup,
# auth, transfer progress) — use it to see where the script is stuck when a
# step times out. All ssh/scp calls also set ConnectTimeout and keepalive
# options so a dead/unreachable host or a firewall dropping an idle
# connection mid-build fails with a clear error instead of hanging silently.
set -euo pipefail

usage() {
  echo "Usage: $0 [-i ssh_key] [-v] <preprod|prod> <user@host> [remote-path] [ssh-port]" >&2
  exit 1
}

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

SSH_KEY=""
VERBOSE=false
while getopts ":i:v" opt; do
  case "$opt" in
    i) SSH_KEY="$OPTARG" ;;
    v) VERBOSE=true ;;
    \?) echo "Unknown option: -$OPTARG" >&2; usage ;;
    :) echo "Option -$OPTARG requires an argument" >&2; usage ;;
  esac
done
shift $((OPTIND - 1))

if [[ -n "$SSH_KEY" && ! -f "$SSH_KEY" ]]; then
  echo "SSH key not found: $SSH_KEY" >&2
  exit 1
fi

ENVIRONMENT="${1:-}"
SSH_TARGET="${2:-}"
[[ -z "$ENVIRONMENT" || -z "$SSH_TARGET" ]] && usage
if [[ "$ENVIRONMENT" != "preprod" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be 'preprod' or 'prod', got: $ENVIRONMENT" >&2
  exit 1
fi
REMOTE_PATH="${3:-/opt/apartment103-$ENVIRONMENT}"
SSH_PORT="${4:-22}"

SSH_KEEPALIVE_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=10)
SSH_OPTS=(-p "$SSH_PORT" "${SSH_KEEPALIVE_OPTS[@]}")
SCP_OPTS=(-P "$SSH_PORT" "${SSH_KEEPALIVE_OPTS[@]}")
RSYNC_SSH="ssh -p $SSH_PORT ${SSH_KEEPALIVE_OPTS[*]}"
if [[ -n "$SSH_KEY" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY")
  SCP_OPTS+=(-i "$SSH_KEY")
  RSYNC_SSH+=" -i $SSH_KEY"
fi
RSYNC_VERBOSE_OPTS=()
if [[ "$VERBOSE" == true ]]; then
  SSH_OPTS+=(-v)
  SCP_OPTS+=(-v)
  RSYNC_SSH+=" -v"
  RSYNC_VERBOSE_OPTS=(-v --progress --stats)
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/env/$ENVIRONMENT.env"
SECRETS_DIR="$REPO_ROOT/.secrets"
SECRETS_FILE="$SECRETS_DIR/$ENVIRONMENT.env"
CERTS_DIR="$SECRETS_DIR/certs/$ENVIRONMENT"
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

SSL_CERT_FILE="$(grep -E '^SSL_CERT_FILE=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
SSL_KEY_FILE="$(grep -E '^SSL_KEY_FILE=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
if [[ -z "$SSL_CERT_FILE" || -z "$SSL_KEY_FILE" ]]; then
  echo "SSL_CERT_FILE and SSL_KEY_FILE must be set in $ENV_FILE." >&2
  exit 1
fi

if [[ ! -f "$CERTS_DIR/$SSL_CERT_FILE" || ! -f "$CERTS_DIR/$SSL_KEY_FILE" ]]; then
  echo "Missing $CERTS_DIR/$SSL_CERT_FILE or $CERTS_DIR/$SSL_KEY_FILE." >&2
  echo "Place the TLS certificate chain and private key for $ENVIRONMENT there first (a single cert covering both FRONTEND_DOMAIN and API_DOMAIN as SAN entries)." >&2
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

if [[ -n "${DEPLOY_SUDO_PASSWORD:-}" ]]; then
  SUDO_PASSWORD="$DEPLOY_SUDO_PASSWORD"
else
  read -rs -p "Password for sudo on $SSH_TARGET: " SUDO_PASSWORD
  echo
fi
if [[ -z "$SUDO_PASSWORD" ]]; then
  echo "A sudo password is required (set DEPLOY_SUDO_PASSWORD or enter one when prompted)." >&2
  exit 1
fi

log "==> Syncing repo to $SSH_TARGET:$REMOTE_PATH"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH'"
rsync -az --delete \
  ${RSYNC_VERBOSE_OPTS[@]+"${RSYNC_VERBOSE_OPTS[@]}"} \
  -e "$RSYNC_SSH" \
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
log "==> Repo synced"

log "==> Copying $ENVIRONMENT env file (non-secret config only)"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH/deploy/env'"
scp "${SCP_OPTS[@]}" "$ENV_FILE" "$SSH_TARGET:$REMOTE_PATH/deploy/env/$ENVIRONMENT.env"

log "==> Copying $ENVIRONMENT TLS certificate + key"
REMOTE_CERTS_DIR="$REMOTE_PATH/.secrets/certs"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_CERTS_DIR' && chmod 700 '$REMOTE_PATH/.secrets' '$REMOTE_CERTS_DIR'"
scp "${SCP_OPTS[@]}" "$CERTS_DIR/$SSL_CERT_FILE" "$CERTS_DIR/$SSL_KEY_FILE" "$SSH_TARGET:$REMOTE_CERTS_DIR/"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "chmod 600 '$REMOTE_CERTS_DIR/$SSL_CERT_FILE' '$REMOTE_CERTS_DIR/$SSL_KEY_FILE'"

log "==> Building images and starting containers on remote host (secrets exported into the remote shell only, never written to disk)"
log "    this builds images, runs pending DB migrations, then starts the stack — a cold build (image pulls, npm/uv installs) can take several minutes; output streams below as it happens"
{
  printf '%s\n' "$SUDO_PASSWORD"
  echo "set -euo pipefail"
  echo "cd '$REMOTE_PATH/deploy'"
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    printf 'export %s=%q\n' "$key" "$value"
  done < "$SECRETS_FILE"
  # Deliberately no `set -x` here even in verbose mode: this remote session's
  # environment holds the sudo password + secrets fed in above, and a trace
  # would echo them to the log.
  COMPOSE="docker compose -p '$PROJECT_NAME' -f docker-compose.yml -f docker-compose.$ENVIRONMENT.yml --env-file 'env/$ENVIRONMENT.env'"
  echo "$COMPOSE build"
  # Run migrations before anything else comes up: `run` starts mongo first
  # (backend's depends_on: condition: service_healthy in docker-compose.yml
  # applies to `run` too) and waits for its healthcheck, then applies pending
  # migrations in a throwaway container. Mongo here is a standalone instance
  # (no replica set), hence --no-use-transaction. If this fails, `set -e`
  # aborts before backend/frontend/nginx start, so the app never boots
  # against a half-migrated or incompatible schema.
  echo "$COMPOSE run --rm backend uv run --no-sync mongo-migrate migrate --forward --no-use-transaction"
  echo "$COMPOSE up -d"
  # nginx's config templates are bind-mounted (docker-compose.yml), not baked
  # into an image, and are only re-rendered by the container entrypoint on
  # start — so a template-only edit doesn't change the service's resolved
  # config and `up -d` above won't recreate it, leaving the old rendered
  # config running. Force it every deploy so template changes always land.
  echo "$COMPOSE up -d --force-recreate nginx"
} | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "sudo -S -p '' bash -s"
log "==> Remote build/migrate/start finished"

log "==> Deployed. Container status:"
printf '%s\n' "$SUDO_PASSWORD" | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
  "sudo -S -p '' docker compose -p '$PROJECT_NAME' -f '$REMOTE_PATH/deploy/docker-compose.yml' -f '$REMOTE_PATH/deploy/docker-compose.$ENVIRONMENT.yml' --env-file '$REMOTE_PATH/deploy/env/$ENVIRONMENT.env' ps"

echo
SSH_HINT="ssh -t -p $SSH_PORT"
[[ -n "$SSH_KEY" ]] && SSH_HINT="ssh -t -p $SSH_PORT -i $SSH_KEY"
echo "Note: DB migrations were applied automatically above, before the app started. To check migration history or re-run manually if needed:"
echo "  $SSH_HINT $SSH_TARGET \"cd $REMOTE_PATH/deploy && sudo docker compose -p $PROJECT_NAME -f docker-compose.yml -f docker-compose.$ENVIRONMENT.yml --env-file env/$ENVIRONMENT.env run --rm backend uv run --no-sync mongo-migrate migrate --forward --no-use-transaction\""
echo
echo "Note: to bootstrap the first Admin account, SSH in and run deploy/create-admin.sh directly on the host:"
echo "  $SSH_HINT $SSH_TARGET \"cd $REMOTE_PATH/deploy && ./create-admin.sh $ENVIRONMENT\""
