#!/bin/bash

##
## kunai_lab_bundles.reset.ssh_keys.sh - clear ~/.ssh/known_hosts entries for
## every IP declared in manifest/scenario_vms.json (deployable + optional VMs).
##
## Use when a redeploy reuses the same IPs but cloud-init regenerated the host
## SSH keys (otherwise ssh complains about REMOTE HOST IDENTIFICATION CHANGED).
##
## Manifest-driven : iterates all VMs (including admin-wazuh) so that even
## when INSTALL_WAZUH=NO today, the known_hosts is cleaned for the slot.
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip' "$MANIFEST")

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ""
echo ":: done - $(echo "${INFRASTRUCTURE_IP[@]}" | wc -w) known_hosts entries removed"
