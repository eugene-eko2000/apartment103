#!/usr/bin/env bash
# Seeds the first Admin account by running `mongo-migrate create-admin`.
# Needed to bootstrap the very first admin, since POST /admins itself
# requires an existing admin to call it. Requires `uv` and a reachable
# MongoDB, so run it either in local dev or inside the backend container
# (see deploy/create-admin.sh, which execs into the container on a deployed
# host and calls this with all four flags set).
#
# Any field not passed as a flag is prompted for interactively.
#
# Usage:
#   ./create-admin.sh [--first-name NAME] [--family-name NAME] [--email EMAIL] [--phone-number NUMBER]
set -euo pipefail

pushd "$(dirname "$0")/.." > /dev/null

first_name=""
family_name=""
email=""
phone_number=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --first-name) first_name="$2"; shift 2 ;;
    --family-name) family_name="$2"; shift 2 ;;
    --email) email="$2"; shift 2 ;;
    --phone-number) phone_number="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$first_name" ]] && read -rp "First name: " first_name
[[ -z "$family_name" ]] && read -rp "Family name: " family_name
[[ -z "$email" ]] && read -rp "Email: " email
[[ -z "$phone_number" ]] && read -rp "Phone number: " phone_number

uv run mongo-migrate create-admin \
  --first-name "$first_name" \
  --family-name "$family_name" \
  --email "$email" \
  --phone-number "$phone_number"

popd > /dev/null
