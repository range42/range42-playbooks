#!/bin/bash

##
## setup networks - create the SDN zone, vnets and subnets THIS scenario declares
##
## The declaration is 00_sdn_bootstrap/_main.yml, next to this script : it carries the zone and the
## per-network `snat`, which the manifest cannot express. Nothing is declared here, this only runs
## it - the same way setup.sh runs main.yml.
##
## Idempotent : the bundle it imports reads the live cluster and writes only what is missing.
##
## --dry-run writes NOTHING. It answers "what would an apply create ?" from the manifest and two
## read-only devkit calls. It does NOT show `snat` drift - that lives in the playbook, and
## `range42-context networks-internet-list` already reports declared against live.
##
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE to be exported -
## set by `range42-context use <codename> blank_scenario_2_sdn`.
##
## Any other argument is propagated to ansible-playbook.
##
## Companions:
##   - blank_scenario_2_sdn.setup_networks.sh (this)   - create the SDN objects
##   - blank_scenario_2_sdn.delete_networks.sh         - remove them, keeping the shared zone
##

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENARIO="$(basename "$SCRIPT_DIR")"
DECLARATION="$SCRIPT_DIR/00_sdn_bootstrap/_main.yml"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

[[ -f "$DECLARATION" ]] || { echo "ERROR: SDN declaration not found: $DECLARATION" >&2 ; exit 1 ; }

DRY_RUN=false
ARGS=()
for a in "$@" ; do
    case "$a" in
        --dry-run) DRY_RUN=true ;;
        *)         ARGS+=("$a") ;;
    esac
done

if ! $DRY_RUN ; then
    ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
        -l "all" \
        "$DECLARATION" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
        ${ARGS[@]+"${ARGS[@]}"}
    exit $?
fi

#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
# --dry-run : what an apply would create. READ ONLY.
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

[[ -f "$MANIFEST" ]] || { echo "ERROR: manifest not found: $MANIFEST" >&2 ; exit 1 ; }
## checked separately : a malformed manifest makes the query below yield nothing, which the guard
## further down would report as "no net* bridge" - blaming the wrong thing
jq -e . "$MANIFEST" >/dev/null 2>&1 || { echo "ERROR: manifest is not valid json: $MANIFEST" >&2 ; exit 1 ; }

## an absent devkit would leave the live reads empty and every network would read "create"
for c in jq \
         proxmox_network.datacenter.list_sdn_vnets.to.jsons.sh \
         proxmox_network.datacenter.list_sdn_subnets.to.jsons.sh ; do
    command -v "$c" >/dev/null 2>&1 || { echo "ERROR: not on PATH: $c" >&2 ; exit 1 ; }
done

TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT

## Derived from the `bridge` field and never from the IP third octet : two template entries in the
## repo intentionally carry bridge=vmbr140 with a 192.168.142.x address (plan section 4.3). Every
## subnet in the repo is a /24. Same query as delete_networks.sh.
jq -c '
    # every bridge the manifest names, VMs and templates alike
      [ (.vms // [])[], (.templates // [])[] ]
    | map(.bridge // "") | unique

    # SDN only : a vmbr* entry is a scenario not migrated yet
    | map(select(startswith("net")))

    # the number carries the subnet : net143 -> 192.168.143.0/24
    | map({ vnet: ., octet: ltrimstr("net") })
    | map(select(.octet | test("^[0-9]{1,3}$")))
    | map({ vnet, subnet: ("192.168." + .octet + ".0/24") })
    | .[]
' "$MANIFEST" > "$TMP/networks.jsonl"

if [[ "$(grep -c . "$TMP/networks.jsonl" || true)" -eq 0 ]] ; then
    echo "ERROR: $SCENARIO carries no net* bridge in its manifest" >&2
    echo "       a scenario still on vmbr* has nothing to compare" >&2
    exit 1
fi


# A FAILED READ MUST NOT READ AS "nothing is there" : on a delete that is a silent no-op looking
# like success, and on a dry-run it reports every network as missing. An empty result is legitimate
# (a fresh cluster has no subnet), so the exit status is what decides, never the emptiness.
read_live() {   # $1 = devkit on PATH, $2 = destination file
    local out
    out=$("$1" 2>/dev/null) || { echo "ERROR: $1 failed - the live state is unknown, refusing" >&2 ; exit 1 ; }
    printf '%s\n' "$out" | jq -c . > "$2" 2>/dev/null || : > "$2"
}

echo ":: reading the live cluster ..."
read_live proxmox_network.datacenter.list_sdn_vnets.to.jsons.sh   "$TMP/live_vnets.jsonl"
read_live proxmox_network.datacenter.list_sdn_subnets.to.jsons.sh "$TMP/live_subnets.jsonl"
echo ""

## The CIDR is matched through the subnet ID, `<zone>-<cidr with / as ->`, which is what Proxmox
## builds : that compares the CIDR without needing the zone name, and `subnet_cidr` is protected by
## `else omit` in the role so it can be absent. Matching on `subnet_vnet` alone would report a vnet
## holding a DIFFERENT subnet as "in place", when an apply would in fact create one.
jq -c -n \
   --slurpfile networks "$TMP/networks.jsonl" \
   --slurpfile lv       "$TMP/live_vnets.jsonl" \
   --slurpfile ls       "$TMP/live_subnets.jsonl" '
    [ $lv[].vnet ] as $live_vnets
    | $networks[] as $n
    | ([ $ls[]
         | select(.subnet_vnet == $n.vnet)
         | select(.subnet | endswith("-" + ($n.subnet | gsub("/"; "-")))) ] | length) as $declared_live
    | { vnet: $n.vnet, subnet: $n.subnet,
        verdict: (if   $declared_live > 0             then "in place"
                  elif ($n.vnet | IN($live_vnets[]))  then "create subnet"
                  else                                     "create vnet + subnet" end) }' > "$TMP/diff.jsonl"

printf "   %-10s %-20s %s\n" "VNET" "SUBNET" "WHAT AN APPLY WOULD DO"
jq -r '"\(.vnet)\t\(.subnet)\t\(.verdict)"' "$TMP/diff.jsonl" \
  | while IFS=$'\t' read -r vnet subnet verdict ; do
      printf "   %-10s %-20s %s\n" "$vnet" "$subnet" "$verdict"
    done

PENDING=$(jq -s '[ .[] | select(.verdict != "in place") ] | length' "$TMP/diff.jsonl")
echo ""
if [[ "$PENDING" -eq 0 ]] ; then
    echo ":: every network is already there - an apply would only reconcile the live rules"
else
    echo ":: ${PENDING} network(s) to create - run without --dry-run"
fi
echo ""
