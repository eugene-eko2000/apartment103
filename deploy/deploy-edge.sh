#!/usr/bin/env bash
# Deploys the shared edge proxy (deploy/edge/) to a single remote host over
# SSH using Docker Compose, as its own Compose project: apartment103-edge.
#
# The edge is the only thing on the host that binds :80 and :443. It
# terminates TLS for all four hostnames and decides one thing — which
# ENVIRONMENT a request belongs to — then forwards it, Host header intact, to
# that environment's own nginx over the apartment103-<env>-edge networks. The
# environments themselves are deployed separately with deploy.sh; because this
# proxy re-resolves its upstreams per request, redeploying either environment
# needs no reload here. See docs/single-host-deployment-proposal.md.
#
# Much smaller than deploy.sh: no application secrets to stream in and no DB
# migrations to run. Non-secret config comes from deploy/edge/env/edge.env
# (scp'd, like the per-environment env files). The one sensitive thing the
# edge needs is the TLS private key, which is a file rather than an env var:
# the cert + key named in edge.env are read from .secrets/certs/edge/ on THIS
# machine and scp'd (mode 600) to .secrets/certs/ under the remote deploy
# path, which deploy/edge/docker-compose.yml mounts read-only.
#
# `docker`/`docker compose` on the remote host require sudo with a password,
# which is streamed to `sudo -S` on stdin exactly as deploy.sh does it — see
# the comments there.
#
# Usage:
#   ./deploy-edge.sh [-i ssh_key] [-v] <user@host> [remote-path] [ssh-port]
#
# -v prints ssh/scp/rsync protocol-level debug output.
set -euo pipefail

usage() {
  echo "Usage: $0 [-i ssh_key] [-v] <user@host> [remote-path] [ssh-port]" >&2
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

SSH_TARGET="${1:-}"
[[ -z "$SSH_TARGET" ]] && usage
REMOTE_PATH="${2:-/opt/apartment103-edge}"
SSH_PORT="${3:-22}"

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
EDGE_DIR="$SCRIPT_DIR/edge"
ENV_FILE="$EDGE_DIR/env/edge.env"
SECRETS_DIR="$REPO_ROOT/.secrets"
CERTS_DIR="$SECRETS_DIR/certs/edge"
PROJECT_NAME="apartment103-edge"
# Both environments' networks. Created here as well as in deploy.sh, always
# idempotently, so that whichever of the three projects is deployed first
# brings up what it needs and the rest are no-ops.
EDGE_NETWORKS=(apartment103-preprod-edge apartment103-prod-edge)

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE." >&2
  echo "Copy deploy/edge/env/edge.env.example to deploy/edge/env/edge.env and fill in real values first." >&2
  exit 1
fi

# The cert/key filenames live in edge.env; the files themselves must be in
# .secrets/certs/edge/. prod and preprod may name the same pair (they do by
# default) — dedupe so scp isn't handed the same file twice.
CERT_FILES=()
for var in PROD_SSL_CERT_FILE PROD_SSL_KEY_FILE PREPROD_SSL_CERT_FILE PREPROD_SSL_KEY_FILE; do
  value="$(grep -E "^$var=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
  if [[ -z "$value" ]]; then
    echo "$var must be set in $ENV_FILE." >&2
    exit 1
  fi
  if [[ ! -f "$CERTS_DIR/$value" ]]; then
    echo "Missing $CERTS_DIR/$value (named by $var in $ENV_FILE)." >&2
    echo "Place the TLS certificate chain and private key there first. One certificate covering all four hostnames as SAN entries is enough — *.bergseehome.ch plus bergseehome.ch covers them, since every name is single-level." >&2
    exit 1
  fi
  [[ " ${CERT_FILES[*]-} " == *" $value "* ]] || CERT_FILES+=("$value")
done

secrets_dir_mode="$(stat -f '%OLp' "$SECRETS_DIR" 2>/dev/null || stat -c '%a' "$SECRETS_DIR" 2>/dev/null || true)"
if [[ -n "$secrets_dir_mode" && "$secrets_dir_mode" != "700" ]]; then
  echo "Warning: $SECRETS_DIR is mode $secrets_dir_mode, expected 700 (chmod 700 '$SECRETS_DIR')." >&2
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

# Only deploy/edge/ is synced — the edge has no application code to build, and
# nothing in it should ever reach for either environment's files. The layout
# under $REMOTE_PATH mirrors the repo (deploy/edge/ + .secrets/certs/) so the
# compose file's ../../.secrets/certs mount resolves the same way it does here.
log "==> Syncing deploy/edge/ to $SSH_TARGET:$REMOTE_PATH/deploy/edge"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH/deploy/edge'"
rsync -az --delete \
  ${RSYNC_VERBOSE_OPTS[@]+"${RSYNC_VERBOSE_OPTS[@]}"} \
  -e "$RSYNC_SSH" \
  --exclude 'env/*.env' \
  "$EDGE_DIR/" "$SSH_TARGET:$REMOTE_PATH/deploy/edge/"
log "==> deploy/edge synced"

log "==> Copying edge env file (non-secret config only)"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_PATH/deploy/edge/env'"
scp "${SCP_OPTS[@]}" "$ENV_FILE" "$SSH_TARGET:$REMOTE_PATH/deploy/edge/env/edge.env"

log "==> Copying TLS certificate(s) + key(s): ${CERT_FILES[*]}"
REMOTE_CERTS_DIR="$REMOTE_PATH/.secrets/certs"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_CERTS_DIR' && chmod 700 '$REMOTE_PATH/.secrets' '$REMOTE_CERTS_DIR'"
for f in "${CERT_FILES[@]}"; do
  scp "${SCP_OPTS[@]}" "$CERTS_DIR/$f" "$SSH_TARGET:$REMOTE_CERTS_DIR/"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "chmod 600 '$REMOTE_CERTS_DIR/$f'"
done

log "==> Starting the edge proxy on the remote host"
{
  printf '%s\n' "$SUDO_PASSWORD"
  echo "set -euo pipefail"
  echo "cd '$REMOTE_PATH/deploy/edge'"
  # Both environments' networks, created here rather than by any of the three
  # Compose projects: the edge attaches to networks it does not own, so
  # `docker compose down` on an environment can never pull one out from under
  # it, and the three projects can be deployed in any order. An environment
  # that is not up yet is simply a 502 on its own hostnames.
  for net in "${EDGE_NETWORKS[@]}"; do
    echo "docker network inspect '$net' >/dev/null 2>&1 || docker network create '$net'"
  done
  COMPOSE="docker compose -p '$PROJECT_NAME' --env-file 'env/edge.env'"
  echo "$COMPOSE up -d"
  # The nginx config template is bind-mounted, not baked into the image, and
  # is only re-rendered by the container entrypoint at start — so a
  # template-only edit doesn't change the service definition and `up -d`
  # above won't recreate the container, leaving the old rendered config
  # running. rm deletes the container object outright so the following `up`
  # must create a new one, which always re-runs the entrypoint's envsubst.
  # Same reasoning as deploy.sh; see the longer note there.
  echo "$COMPOSE stop nginx"
  echo "$COMPOSE rm -f nginx"
  echo "$COMPOSE up -d nginx"
  # Proof of what is actually live, in this log: the rendered server_name
  # lines are what decides which environment each hostname reaches.
  echo "sleep 2"
  echo "echo '--> edge config as rendered inside the freshly (re)started container:'"
  echo "$COMPOSE exec -T nginx nginx -T < /dev/null 2>&1 | grep -E 'server_name|set \\\$upstream'"
} | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "sudo -S -p '' bash -s"
log "==> Edge proxy started"

log "==> Deployed. Container status:"
printf '%s\n' "$SUDO_PASSWORD" | ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
  "sudo -S -p '' docker compose -p '$PROJECT_NAME' -f '$REMOTE_PATH/deploy/edge/docker-compose.yml' --env-file '$REMOTE_PATH/deploy/edge/env/edge.env' ps"

echo
echo "Note: the edge routes by hostname only. If a hostname 502s, that environment's own stack is down or was never deployed — deploy it with deploy.sh and the edge will pick it up on the next request, with no reload here."
