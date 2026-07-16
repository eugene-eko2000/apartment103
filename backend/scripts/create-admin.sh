#!/usr/bin/env bash
# Interactively prompts for the fields needed to seed an Admin account and
# runs `mongo-migrate create-admin`. Needed to bootstrap the very first
# admin, since POST /admins itself requires an existing admin to call it.
set -euo pipefail

pushd "$(dirname "$0")/.."

read -rp "First name: " first_name
read -rp "Family name: " family_name
read -rp "Email: " email
read -rp "Phone number: " phone_number

uv run mongo-migrate create-admin \
  --first-name "$first_name" \
  --family-name "$family_name" \
  --email "$email" \
  --phone-number "$phone_number"

popd
