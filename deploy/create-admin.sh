#!/usr/bin/env bash
# Bootstraps the first Admin account on a deployed host. Run this directly
# from an SSH session on the deployment host (after deploy.sh has synced
# this directory there) — it has no MongoDB access itself, so it prompts for
# the admin's fields here and execs into the running backend container
# (which has `uv`/mongo-migrate and a direct connection to MongoDB) to
# actually create the record, via backend/scripts/create-admin.sh.
#
# Usage:
#   ./create-admin.sh <preprod|prod>
set -euo pipefail

usage() {
  echo "Usage: $0 <preprod|prod>" >&2
  exit 1
}

ENVIRONMENT="${1:-}"
[[ -z "$ENVIRONMENT" ]] && usage
if [[ "$ENVIRONMENT" != "preprod" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be 'preprod' or 'prod', got: $ENVIRONMENT" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="env/$ENVIRONMENT.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — this host doesn't look deployed for $ENVIRONMENT yet." >&2
  exit 1
fi

PROJECT_NAME="apartment103-$ENVIRONMENT"

read -rp "First name: " first_name
read -rp "Family name: " family_name
read -rp "Email: " email
read -rp "Phone number: " phone_number

# Run in your own SSH session (not piped from elsewhere), so sudo can prompt
# you for its password on this terminal directly — unlike deploy.sh, which
# runs from a separate, non-interactive ssh session and has to stream the
# password in over stdin instead.
sudo docker compose -p "$PROJECT_NAME" \
  -f docker-compose.yml -f "docker-compose.$ENVIRONMENT.yml" \
  --env-file "$ENV_FILE" \
  exec -T backend /app/scripts/create-admin.sh \
  --first-name "$first_name" \
  --family-name "$family_name" \
  --email "$email" \
  --phone-number "$phone_number"
