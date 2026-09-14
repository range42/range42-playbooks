#!/bin/bash
# Remove only this scenario's manifest net* VNets and their authoritative live
# subnets through the guarded cluster pipeline. The shared zone is retained.
# Requires the same active inventory/vault environment as setup_networks.sh.
# --dry-run/--check/-C perform privileged read-only scope inspection; remaining
# Ansible arguments are forwarded. Never infer source CIDRs from names or IDs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DECLARATION="$SCRIPT_DIR/00_sdn_bootstrap/delete.yml"
[[ -f "$DECLARATION" ]] || { echo "ERROR: SDN deletion declaration not found: $DECLARATION" >&2; exit 1; }
: "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR:?Run range42-context use <codename> <scenario> first}"
: "${RANGE42_VAULT_PASSWORD_FILE:?Run range42-context use <codename> <scenario> first}"
ARGS=()
READ_ONLY=()
for argument in "$@"; do
    case "$argument" in
        --dry-run|--check|-C) READ_ONLY=(-e '{"BUNDLE_SDN_DELETE_READ_ONLY":true}') ;;
        *) ARGS+=("$argument") ;;
    esac
done
# Ansible --check would skip the commands that prove read-only scope. The
# explicit boolean preview executes those GETs while excluding all write tasks.
exec ansible-playbook \
    -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l all "$DECLARATION" \
    --vault-password-file "$RANGE42_VAULT_PASSWORD_FILE" \
    "${ARGS[@]}" "${READ_ONLY[@]}"
