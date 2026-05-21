#!/bin/bash
#
# Regenerate scenarios/_reserved.json — the aggregated source of truth across all scenarios.
#
# Reads every scenarios/<scenario>/manifest/scenario_vms.json and concatenates all VMs and
# templates into a single NDJSON file (one entry per line), with a "scenario" field added.
#
# Templates from each scenario are tagged role="template". VMs already have a role field
# in the per-scenario manifest.
#
# Run this after modifying any per-scenario manifest. The output is checked into git so
# everyone has a consistent view without running jq on N files.
#
# Usage:
#   ./scenarios/_regenerate_reserved.sh
#
# Companion: scenarios/_check_reserved.sh — validates that _reserved.json is in sync
# with the per-scenario manifests, and that vm_ids / (bridge, IP) are collision-free for
# non-template entries.
#

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

OUT="$SCRIPT_DIR/_reserved.json"
TMP="$(mktemp)"

count_scenarios=0
for manifest in */manifest/scenario_vms.json; do
  [ -f "$manifest" ] || continue
  scenario="$(basename "$(dirname "$(dirname "$manifest")")")"
  jq -c --arg s "$scenario" '.vms[]      | . + {scenario: $s}'                          "$manifest" >> "$TMP"
  jq -c --arg s "$scenario" '.templates[] | . + {scenario: $s, role: "template"}'       "$manifest" >> "$TMP"
  count_scenarios=$((count_scenarios + 1))
done

mv "$TMP" "$OUT"

count_lines=$(wc -l < "$OUT")
echo "regenerated $OUT"
echo "  scenarios processed : $count_scenarios"
echo "  entries (NDJSON)    : $count_lines"
