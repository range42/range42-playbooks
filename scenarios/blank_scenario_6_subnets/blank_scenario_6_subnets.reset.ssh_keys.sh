#!/bin/bash

##
## blank_scenario_6_subnets.reset.ssh_keys.sh - clear ~/.ssh/known_hosts entries for
## every VM in manifest/scenario_vms.json (deployable + optional VMs).
##
## Use when a redeploy reuses the same IPs but cloud-init regenerated the host
## SSH keys (otherwise ssh complains about REMOTE HOST IDENTIFICATION CHANGED).
##
## Manifest-driven : iterates all VMs by IP AND by r42.<vm_name> alias to cover
## both forms of known_hosts entries (HashKnownHosts=yes hashes the IP ; alias-
## keyed entries survive an IP-only sweep otherwise).
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t INFRASTRUCTURE_IP   < <(jq -r '.vms[].ip'      "$MANIFEST")
mapfile -t INFRASTRUCTURE_NAME < <(jq -r '.vms[].vm_name' "$MANIFEST")

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR IP    : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

for name in "${INFRASTRUCTURE_NAME[@]}"; do
    echo ":: REMOVE SSH KEY FOR ALIAS : r42.$name"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "r42.$name"
done

echo ""
echo ":: done - ${#INFRASTRUCTURE_IP[@]} IPs + ${#INFRASTRUCTURE_NAME[@]} hostnames cleaned"
