#!/bin/bash

##
## delete networks - the SDN subnets and vnets of THIS scenario
##
## Scope comes from manifest/scenario_vms.json, like every other script here : the `net*` bridges
## its entries carry. Nothing outside that list is read or removed - a hypervisor hosts several
## scenarios, and taking one down must never damage another one's networks.
##
## THE SHARED ZONE IS KEPT. net142 alone is used by around 14 scenarios, so the zone also holds
## their vnets. An empty zone carries nothing, unlike a legacy bridge left with an address.
##
## NEVER `ip link del` A VNET INTERFACE. Measured on px-testing 2026-08-24 : ifupdown2 wants to
## play the post-down of the interfaces it configured at the next reload, fails without
## /sys/class/net/<if>/brif/, and then EVERY ifreload on the hypervisor fails - other scenarios
## included. Hence the sequence below : objects, then one apply, and the apply brings them down.
##
## ORDER IMPOSED BY PROXMOX : subnets, then vnets. A vnet still holding a subnet cannot be removed.
##
## ONE APPLY, at the end. Each apply replays every post-up hook on the node, adding a rule per
## NAT-enabled subnet - measured 1 -> 3 -> 5 -> 9 -> 11 over four applies. Applying per vnet would
## inflate the very rules the last step exists to clear.
##
## Companions:
##   - blank_scenario_2_sdn.setup_networks.sh          - create the SDN objects
##   - blank_scenario_2_sdn.delete_networks.sh (this)  - remove them, keeping the shared zone
##

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENARIO="$(basename "$SCRIPT_DIR")"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

[[ -f "$MANIFEST" ]] || { echo "ERROR: manifest not found: $MANIFEST" >&2 ; exit 1 ; }
## checked separately : a malformed manifest makes the query below yield nothing, which the guard
## further down would report as "no net* bridge" - blaming the wrong thing
jq -e . "$MANIFEST" >/dev/null 2>&1 || { echo "ERROR: manifest is not valid json: $MANIFEST" >&2 ; exit 1 ; }

## an absent devkit would leave the live reads empty : this would delete nothing and report success
for c in jq \
         proxmox_vm.list.to.jsons.sh \
         proxmox_network.datacenter.list_sdn_vnets.to.jsons.sh \
         proxmox_network.datacenter.list_sdn_subnets.to.jsons.sh \
         proxmox_network.sdn_vnet.delete_sdn_subnet.to.jsons.sh \
         proxmox_network.datacenter.delete_sdn_vnet.to.jsons.sh \
         proxmox_network.datacenter.apply_sdn.to.jsons.sh \
         proxmox_network.sdn_subnet_cidr.delete_extra_snat_rules.to.jsons.sh ; do
    command -v "$c" >/dev/null 2>&1 || { echo "ERROR: not on PATH: $c" >&2 ; exit 1 ; }
done

TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT

#### #### ####
#
# 1. WHICH NETWORKS. Derived from the `bridge` field and never from the IP third octet : two
#    template entries in the repo intentionally carry bridge=vmbr140 with a 192.168.142.x address
#    (plan section 4.3). Every subnet in the repo is a /24.
#
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

N_DECL=$(grep -c . "$TMP/networks.jsonl" || true)
if [[ "$N_DECL" -eq 0 ]] ; then
    echo "ERROR: $SCENARIO declares no SDN network" >&2
    echo "       its manifest carries no net* bridge - a scenario still on vmbr* has nothing" >&2
    echo "       here to remove" >&2
    exit 1
fi

echo ":: scenario : $SCENARIO"
echo ":: networks : $(jq -r '.vnet' "$TMP/networks.jsonl" | tr '\n' ' ')"
echo ""

#### #### ####
#
# 2. PRE-FLIGHT. Proxmox refuses to delete a vnet a network card still references - documented in
#    sdn_network.delete.all - and it refuses AFTER the subnet is already gone, which leaves a
#    half-removed network. So ask first, in one read.
#
#    VMs AND TEMPLATES ARE REPORTED SEPARATELY : delete_vms_only keeps the templates BY DESIGN and
#    a template's card sits on the templating vnet. Lumping them together would make this refuse
#    for ever on a normal host, pointing at a command that cannot fix it.
#
VM_IDS=$(jq -r  '[ (.vms // [])[].vm_id       ] | map(tostring) | join("|")' "$MANIFEST")
TPL_IDS=$(jq -r '[ (.templates // [])[].vm_id ] | map(tostring) | join("|")' "$MANIFEST")

if [[ -n "$VM_IDS" || -n "$TPL_IDS" ]] ; then
    echo ":: checking what is still attached ..."
    VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>/dev/null | grep '"vm_id":[0-9]' || true)

    LIVE_VMS="" ; LIVE_TPL=""
    if [[ -z "$VM_LIST_JSON" ]] ; then
        ## a node carrying no VM at all is a valid state, not a failure. And this check is a
        ## courtesy anyway : Proxmox itself is what refuses a vnet a card still references, so a
        ## listing we could not read degrades to its refusal, never to a silent wrong delete.
        echo ":: no VM on the node"
    else
        ## an empty id list would turn the regex into a match-everything
        [[ -n "$VM_IDS"  ]] && LIVE_VMS=$(printf '%s\n' "$VM_LIST_JSON" | grep -E "\"vm_id\":($VM_IDS)([^0-9]|\$)"  | jq -r '.vm_id' | sort -n | tr '\n' ' ')
        [[ -n "$TPL_IDS" ]] && LIVE_TPL=$(printf '%s\n' "$VM_LIST_JSON" | grep -E "\"vm_id\":($TPL_IDS)([^0-9]|\$)" | jq -r '.vm_id' | sort -n | tr '\n' ' ')
    fi

    if [[ -n "${LIVE_VMS// /}" ]] ; then
        echo "" >&2
        echo "REFUSING: this scenario still has VMs on the cluster" >&2
        echo "  vm ids : ${LIVE_VMS}" >&2
        echo "  A vnet cannot be removed while a card references it, and the refusal would come" >&2
        echo "  after the subnet is already gone - a half-removed network." >&2
        echo "  Remove them first :  range42-context delete-vms" >&2
        exit 1
    fi
    if [[ -n "${LIVE_TPL// /}" ]] ; then
        echo "" >&2
        echo "REFUSING: this scenario's templates are still on the cluster" >&2
        echo "  template ids : ${LIVE_TPL}" >&2
        echo "  Their card sits on the templating network, so its vnet cannot be removed." >&2
        echo "  delete-vms keeps templates by design - use :  range42-context delete" >&2
        echo "  Rebuilding them afterwards takes a while, which is why this is not implied." >&2
        exit 1
    fi
    echo ":: nothing attached - safe to proceed"
    echo ""
fi

#### #### ####
#
# 3. WHAT IS ACTUALLY THERE. The subnet id below is the one the API returned, never a value this
#    script built. The join key is `subnet_vnet` : `subnet_cidr` is protected by `else omit` in the
#    role, and omit DROPS the key, so it can be absent.
#

# A FAILED READ MUST NOT READ AS "nothing is there" : on a delete that is a silent no-op looking
# like success, and on a dry-run it reports every network as missing. An empty result is legitimate
# (a fresh cluster has no subnet), so the exit status is what decides, never the emptiness.
read_live() {   # $1 = devkit on PATH, $2 = destination file
    local out
    out=$("$1" 2>/dev/null) || { echo "ERROR: $1 failed - the live state is unknown, refusing" >&2 ; exit 1 ; }
    printf '%s\n' "$out" | jq -c . > "$2" 2>/dev/null || : > "$2"
}

echo ":: reading the live cluster ..."
read_live proxmox_network.datacenter.list_sdn_subnets.to.jsons.sh "$TMP/live_subnets.jsonl"
read_live proxmox_network.datacenter.list_sdn_vnets.to.jsons.sh   "$TMP/live_vnets.jsonl"

## EVERY subnet of our vnets, not the first : a vnet may hold more than one, and Proxmox refuses to
## delete a vnet that still holds any. Taking only the first left the vnet delete to fail.
jq -c -n --slurpfile networks "$TMP/networks.jsonl" --slurpfile live "$TMP/live_subnets.jsonl" '
    [ $networks[].vnet ] as $ours
    | $live[]
    | select(.subnet_vnet | IN($ours[]))
    | { sdn_vnet: .subnet_vnet, sdn_subnet_id: .subnet }' > "$TMP/subnets_to_delete.jsonl"

jq -c -n --slurpfile networks "$TMP/networks.jsonl" --slurpfile live "$TMP/live_vnets.jsonl" '
    [ $live[].vnet ] as $live_vnets
    | $networks[]
    | select(.vnet | IN($live_vnets[]))
    | { sdn_vnet: .vnet }' > "$TMP/vnets_to_delete.jsonl"

N_SUB=$(grep -c . "$TMP/subnets_to_delete.jsonl" || true)
N_VNET=$(grep -c . "$TMP/vnets_to_delete.jsonl"  || true)
echo ":: live     : ${N_SUB} subnet(s), ${N_VNET} vnet(s)"
echo ""

#### #### ####
#
# 4. DELETE. Subnets first, vnets next, neither applying.
#
if [[ "$N_SUB" -gt 0 ]] ; then
    echo ":: deleting ${N_SUB} subnet(s) ..."
    proxmox_network.sdn_vnet.delete_sdn_subnet.to.jsons.sh --json < "$TMP/subnets_to_delete.jsonl" >/dev/null || {
        echo "ERROR: a subnet delete failed - no apply was run, nothing is half applied" >&2 ; exit 1 ; }
else
    echo ":: no subnet of this scenario is live"
fi

if [[ "$N_VNET" -gt 0 ]] ; then
    echo ":: deleting ${N_VNET} vnet(s) ..."
    proxmox_network.datacenter.delete_sdn_vnet.to.jsons.sh --json < "$TMP/vnets_to_delete.jsonl" >/dev/null || {
        echo "ERROR: a vnet delete failed - run range42-context networks-apply to put the subnets back" >&2 ; exit 1 ; }
else
    echo ":: no vnet of this scenario is live"
fi

## ONLY IF SOMETHING WAS WRITTEN. An apply runs `ifreload -a`, which replays every post-up hook and
## ADDS a rule per NAT-enabled subnet. Applying with nothing pending would inflate the very rules
## the next step clears - on an already-empty host this script would make things worse.
if [[ "$N_SUB" -gt 0 || "$N_VNET" -gt 0 ]] ; then
    echo ":: applying, once ..."
    proxmox_network.datacenter.apply_sdn.to.jsons.sh --json >/dev/null || {
        echo "ERROR: the apply failed - the objects are gone but the interfaces may still be up" >&2 ; exit 1 ; }
else
    echo ":: nothing was removed - no apply"
fi

#### #### ####
#
# 5. RECONCILE TO ZERO. Deleting a subnet removes its post-down hook BEFORE that hook ever runs, so
#    the live MASQUERADE rule outlives the object that declared it and no API read shows it. This
#    runs AFTER the apply, so the post-down had its chance first. Safe with no apply too : the
#    primitive only ever deletes.
#
#    The CIDRs are the declared ones PLUS those of the subnets actually removed - a vnet of ours
#    holding a subnet nobody declared would otherwise leave its live rules behind for good.
{
    jq -r '.subnet' "$TMP/networks.jsonl"
    jq -r '.sdn_subnet_id | capture("(?<net>[0-9.]+)-(?<mask>[0-9]+)$") | .net + "/" + .mask' \
       "$TMP/subnets_to_delete.jsonl"
} | sort -u | jq -R -c 'select(length > 0) | { sdn_subnet_cidr: ., sdn_snat_want: "0" }' > "$TMP/reconcile.jsonl"

echo ":: reconciling the live rules to zero on $(grep -c . "$TMP/reconcile.jsonl" || true) network(s) ..."
proxmox_network.sdn_subnet_cidr.delete_extra_snat_rules.to.jsons.sh --json < "$TMP/reconcile.jsonl" >/dev/null || {
    echo "ERROR: the reconciliation failed - check with range42-context networks-internet-list" >&2 ; exit 1 ; }

echo ""
echo ":: done - the shared zone is untouched"
echo ":: recreate everything with: range42-context networks-apply"
echo ""
