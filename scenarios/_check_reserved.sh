#!/bin/bash
#
# Validate scenarios/_reserved.json :
#   1. It exists and is non-empty
#   2. It is in sync with the per-scenario manifests (would-regenerate produces identical content)
#   3. No vm_id collision across VMs (NON-template entries)
#   4. No (bridge, IP) collision across VMs (NON-template entries)
#   5. Templates listed in multiple scenarios are consistent (same vm_id → same vm_name / spec / ip / bridge)
#   6. No vm_id collision between a template and a VM (cross-role)
#   7. No (bridge, IP) collision between a template and a VM (cross-role)
#   8. No (bridge, IP) collision between distinct templates (different vm_ids sharing same bridge/IP)
#
# Returns non-zero on any failure. Safe to use as a pre-commit hook or CI gate.
#
# Output uses ANSI colors when stdout is a TTY and NO_COLOR is unset.
#
# Usage:
#   ./scenarios/_check_reserved.sh
#

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

OUT="$SCRIPT_DIR/_reserved.json"

# Colors (only when stdout is a TTY and NO_COLOR is not set)
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    YELLOW=$'\033[0;33m'
    BOLD=$'\033[1m'
    RESET=$'\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BOLD=''
    RESET=''
fi

fail=0

# 1. file exists + non-empty
if [ ! -s "$OUT" ]; then
    printf '%sFAIL:%s %s missing or empty\n' "$RED" "$RESET" "$OUT"
    exit 1
fi

# 2. sync check (regenerate to a temp + diff)
TMP="$(mktemp)"
for manifest in */manifest/scenario_vms.json; do
    [ -f "$manifest" ] || continue
    scenario="$(basename "$(dirname "$(dirname "$manifest")")")"
    jq -c --arg s "$scenario" '.vms[]      | . + {scenario: $s}'                          "$manifest" >> "$TMP"
    jq -c --arg s "$scenario" '.templates[] | . + {scenario: $s, role: "template"}'       "$manifest" >> "$TMP"
done

if ! diff -q "$OUT" "$TMP" >/dev/null; then
    printf '\n%sFAIL:%s _reserved.json is %sOUT OF SYNC%s with per-scenario manifests\n' "$RED" "$RESET" "$YELLOW" "$RESET"
    printf '      run %s./scenarios/_regenerate_reserved.sh%s to fix\n\n' "$BOLD" "$RESET"
    fail=1
fi
rm -f "$TMP"

# 3. vm_id collisions on NON-template entries (VMs)
dup_vmid=$(jq -r 'select(.role != "template") | .vm_id' "$OUT" | sort -n | uniq -d)
if [ -n "$dup_vmid" ]; then
    printf '\n%sFAIL:%s vm_id collision(s) between VMs:\n\n' "$RED" "$RESET"
    while read -r vmid; do
        printf '  vm_id %s%s%s:\n' "$RED" "$vmid" "$RESET"
        jq -c --argjson v "$vmid" 'select(.role != "template" and .vm_id == $v)' "$OUT" | sed 's/^/    /'
    done <<< "$dup_vmid"
    printf '\n'
    fail=1
fi

# 4. (bridge, IP) collisions on NON-template entries (VMs)
dup_brip=$(jq -r 'select(.role != "template") | "\(.bridge) \(.ip)"' "$OUT" | sort | uniq -d)
if [ -n "$dup_brip" ]; then
    printf '%sFAIL:%s (bridge, IP) collision(s) between VMs:\n\n' "$RED" "$RESET"
    while read -r brip; do
        bridge="${brip%% *}"
        ip="${brip##* }"
        printf '  %s %s%s%s:\n' "$bridge" "$RED" "$ip" "$RESET"
        jq -c --arg b "$bridge" --arg i "$ip" 'select(.role != "template" and .bridge == $b and .ip == $i)' "$OUT" | sed 's/^/    /'
    done <<< "$dup_brip"
    printf '\n'
    fail=1
fi

# 5. template consistency : same vm_id across scenarios must have same vm_name/spec/ip/bridge
inconsistent_templates=$(jq -s '
    [.[] | select(.role == "template")]
    | group_by(.vm_id)
    | map(select(([.[] | "\(.vm_name)|\(.spec // "")|\(.ip)|\(.bridge)"] | unique | length) > 1))
    | .[]
    | .[0].vm_id
' "$OUT")
if [ -n "$inconsistent_templates" ]; then
    printf '%sFAIL:%s template inconsistency — same vm_id has different vm_name/spec/ip/bridge across scenarios:\n\n' "$RED" "$RESET"
    while read -r vmid; do
        printf '  template vm_id %s%s%s:\n' "$RED" "$vmid" "$RESET"
        jq -c --argjson v "$vmid" 'select(.role == "template" and .vm_id == $v)' "$OUT" | sed 's/^/    /'
    done <<< "$inconsistent_templates"
    printf '\n'
    fail=1
fi

# 6. CROSS : vm_id collision between a template and a VM
template_vmids=$(jq -r 'select(.role == "template") | .vm_id' "$OUT" | sort -un)
vm_vmids=$(jq -r 'select(.role != "template") | .vm_id' "$OUT" | sort -un)
cross_vmid=$(comm -12 <(echo "$template_vmids") <(echo "$vm_vmids"))
if [ -n "$cross_vmid" ]; then
    printf '%sFAIL:%s vm_id collision(s) between a template and a VM (cross-role):\n\n' "$RED" "$RESET"
    while read -r vmid; do
        [ -z "$vmid" ] && continue
        printf '  vm_id %s%s%s:\n' "$RED" "$vmid" "$RESET"
        jq -c --argjson v "$vmid" 'select(.vm_id == $v)' "$OUT" | sort -u | sed 's/^/    /'
    done <<< "$cross_vmid"
    printf '\n'
    fail=1
fi

# 7. CROSS : (bridge, IP) collision between a template and a VM
template_brips=$(jq -r 'select(.role == "template") | "\(.bridge) \(.ip)"' "$OUT" | sort -u)
vm_brips=$(jq -r 'select(.role != "template") | "\(.bridge) \(.ip)"' "$OUT" | sort -u)
cross_brip=$(comm -12 <(echo "$template_brips") <(echo "$vm_brips"))
if [ -n "$cross_brip" ]; then
    printf '%sFAIL:%s (bridge, IP) collision(s) between a template and a VM (cross-role):\n\n' "$RED" "$RESET"
    while read -r brip; do
        [ -z "$brip" ] && continue
        bridge="${brip%% *}"
        ip="${brip##* }"
        printf '  %s %s%s%s:\n' "$bridge" "$RED" "$ip" "$RESET"
        jq -c --arg b "$bridge" --arg i "$ip" 'select(.bridge == $b and .ip == $i)' "$OUT" | sort -u | sed 's/^/    /'
    done <<< "$cross_brip"
    printf '\n'
    fail=1
fi

# 8. (bridge, IP) collision between DISTINCT templates (after dedup by vm_id)
# Check 5 ensures consistency within same vm_id; this check ensures
# two different vm_ids don't share the same (bridge, IP).
deduped_tpl=$(jq -r 'select(.role == "template") | "\(.vm_id)|\(.bridge)|\(.ip)"' "$OUT" | sort -u)
dup_tpl_brip=$(echo "$deduped_tpl" | awk -F'|' '{print $2 "|" $3}' | sort | uniq -d)
if [ -n "$dup_tpl_brip" ]; then
    printf '%sFAIL:%s (bridge, IP) collision(s) between distinct templates:\n\n' "$RED" "$RESET"
    while read -r brip; do
        [ -z "$brip" ] && continue
        bridge="${brip%%|*}"
        ip="${brip##*|}"
        printf '  %s %s%s%s:\n' "$bridge" "$RED" "$ip" "$RESET"
        jq -c --arg b "$bridge" --arg i "$ip" 'select(.role == "template" and .bridge == $b and .ip == $i)' "$OUT" \
          | jq -s 'unique_by(.vm_id) | .[]' -c | sed 's/^/    /'
    done <<< "$dup_tpl_brip"
    printf '\n'
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    vms=$(jq -r 'select(.role != "template") | .vm_id' "$OUT" | wc -l)
    tpls=$(jq -r 'select(.role == "template") | .vm_id' "$OUT" | sort -u | wc -l)
    printf '%sOK:%s _reserved.json is in sync + collision-free\n' "$GREEN" "$RESET"
    printf '    VM entries           : %s%s%s unique vm_ids\n' "$BOLD" "$vms" "$RESET"
    printf '    unique templates     : %s%s%s\n' "$BOLD" "$tpls" "$RESET"
fi

exit "$fail"
