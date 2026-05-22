#!/bin/bash
#
# Search scenarios/_reserved.json for entries matching a term read from stdin.
#
# Input  : stdin — one term per line. Empty lines are ignored.
# Output : matching NDJSON entries (one per line), with a colored summary header.
#
# Match rules :
#   - vm_id    : exact (as string, so "1000" matches vm_id 1000 but not 10000)
#   - bridge   : exact (e.g. "vmbr142")
#   - vm_name  : substring (e.g. "admin-wazuh" finds bs2-admin-wazuh + demo_lab admin-wazuh)
#   - ip       : substring (e.g. "192.168.142" finds all VMs on the admin subnet)
#   - scenario : substring (e.g. "blank" finds all bs<N> scenarios)
#
# Long result sets are truncated to MAX_LINES (default 15). Override with env :
#   MAX_LINES=50 echo "vmbr140" | ./_check_reserved_search.sh
#   MAX_LINES=0  echo "vmbr140" | ./_check_reserved_search.sh   # 0 = unlimited
#
# Colors are emitted only when stdout is a TTY and NO_COLOR is unset.
#

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

OUT="$SCRIPT_DIR/_reserved.json"
MAX_LINES="${MAX_LINES:-15}"

# Colors (only when stdout is a TTY and NO_COLOR is not set)
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    YELLOW=$'\033[0;33m'
    BLUE=$'\033[0;34m'
    BOLD=$'\033[1m'
    DIM=$'\033[2m'
    RESET=$'\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; DIM=''; RESET=''
fi

show_usage() {
    cat <<EOF
${BOLD}Usage:${RESET}
  echo "<term>"                       | ${BLUE}./_check_reserved_search.sh${RESET}
  printf '<term1>\\n<term2>\\n'         | ${BLUE}./_check_reserved_search.sh${RESET}

${BOLD}Search rules:${RESET}
  vm_id     exact match (as string)
  bridge    exact match (e.g. "vmbr142")
  vm_name   substring (e.g. "admin-wazuh" → finds bs2-admin-wazuh + demo_lab admin-wazuh)
  ip        substring (e.g. "192.168.142" → all VMs on the admin subnet)
  scenario  substring (e.g. "blank" → all bs<N> scenarios)

${BOLD}Examples:${RESET}
  ${DIM}# find by exact vm_id${RESET}
  ${GREEN}echo "1000"                | ./_check_reserved_search.sh${RESET}

  ${DIM}# find by exact IP${RESET}
  ${GREEN}echo "192.168.142.100"     | ./_check_reserved_search.sh${RESET}

  ${DIM}# find by partial IP (subnet)${RESET}
  ${GREEN}echo "192.168.143"         | ./_check_reserved_search.sh${RESET}

  ${DIM}# find all VMs on a bridge${RESET}
  ${GREEN}echo "vmbr147"             | ./_check_reserved_search.sh${RESET}

  ${DIM}# find by vm_name substring${RESET}
  ${GREEN}echo "admin-wazuh"         | ./_check_reserved_search.sh${RESET}

  ${DIM}# find all entries of a scenario${RESET}
  ${GREEN}echo "_init_lab"           | ./_check_reserved_search.sh${RESET}

  ${DIM}# multiple terms in one call${RESET}
  ${GREEN}printf '1000\\n5100\\n9221\\n' | ./_check_reserved_search.sh${RESET}

${BOLD}Options (via env):${RESET}
  MAX_LINES=N    truncate result lists to N entries (default ${BOLD}${MAX_LINES}${RESET}; 0 = unlimited)
  NO_COLOR=1     disable ANSI colors
EOF
}

if [ ! -s "$OUT" ]; then
    printf '%sERROR:%s %s missing or empty — run ./_regenerate_reserved.sh first\n' "$RED" "$RESET" "$OUT" >&2
    exit 1
fi

# No stdin (interactive TTY) → show usage
if [ -t 0 ]; then
    show_usage
    exit 0
fi

while IFS= read -r term; do
    # skip empty / whitespace-only lines
    [ -z "${term// }" ] && continue

    matches=$(jq -c --arg t "$term" '
        select(
            (.vm_id | tostring) == $t                or
            .bridge == $t                            or
            ((.vm_name  // "") | contains($t))       or
            ((.ip       // "") | contains($t))       or
            ((.scenario // "") | contains($t))
        )
    ' "$OUT")

    if [ -z "$matches" ]; then
        printf '%sno match%s for %s"%s"%s\n' "$YELLOW" "$RESET" "$BOLD" "$term" "$RESET"
        continue
    fi

    n=$(printf '%s\n' "$matches" | wc -l)

    if [ "$MAX_LINES" -gt 0 ] && [ "$n" -gt "$MAX_LINES" ]; then
        printf '%s%d match%s for %s"%s"%s %s(showing first %d, set MAX_LINES=0 for all)%s:\n' \
            "$GREEN" "$n" "$RESET" "$BOLD" "$term" "$RESET" "$DIM" "$MAX_LINES" "$RESET"
        printf '%s\n' "$matches" | head -n "$MAX_LINES" | sed 's/^/  /'
        printf '  %s... %d more truncated%s\n' "$DIM" "$((n - MAX_LINES))" "$RESET"
    else
        printf '%s%d match%s for %s"%s"%s:\n' "$GREEN" "$n" "$RESET" "$BOLD" "$term" "$RESET"
        printf '%s\n' "$matches" | sed 's/^/  /'
    fi
    printf '\n'
done
