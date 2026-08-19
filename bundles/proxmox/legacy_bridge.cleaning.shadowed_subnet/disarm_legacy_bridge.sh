#!/bin/bash
#
# disarm_legacy_bridge.sh - remove one subnet's `address` and NAT lines from a legacy bridge stanza
#                           in /etc/network/interfaces. DURABLE : this writes to disk.
#
# usage : disarm_legacy_bridge.sh <bridge> <address_cidr> [--dry-run] [--yes]
#   e.g.  disarm_legacy_bridge.sh vmbr143 192.168.143.1/24 --dry-run
#
# WHY A SCRIPT AND NOT AN INLINE AWK. Called from Ansible, an inline awk crosses four levels of
# escaping - Jinja, YAML, shell, awk - and a single quoting mistake edits the wrong line of the
# hypervisor's network config. This file is read as-is, testable on its own, reviewable.
#
# WHY BOTH LINES. Two different symptoms, two different lines, one intent :
#   `address <cidr>`  -> the host resolves the subnet's route to THIS bridge, where no VM is
#                        attached, so a VM on the vnet is unreachable and its return traffic is lost
#   `... MASQUERADE`  -> replayed by every `ifreload -a`, so it silently undoes an internet-off
# `inject_nat_rules.sh REMOVE` only ever removed the second one.
#
# WHAT IT NEVER DOES : delete the bridge, delete the stanza, touch another stanza, or write in
# place. We disarm, we do not demolish.
#
# ON A CLEAN HOST it is a silent no-op : an absent bridge, or a stanza that does not carry that
# address, exits 0 having reported and changed nothing. Nothing is asked of the operator either -
# the confirmation only happens when there is something to remove.
#

set -u

INTERFACES="${INTERFACES:-/etc/network/interfaces}"

BRIDGE="${1:-}"
ADDR="${2:-}"
DRY_RUN=false
ASSUME_YES=false
shift 2 2>/dev/null || true
for a in "$@" ; do
    case "$a" in
        --dry-run) DRY_RUN=true ;;
        --yes|-y)  ASSUME_YES=true ;;
        *) echo "unknown option : $a" >&2 ; exit 2 ;;
    esac
done

if [ -z "$BRIDGE" ] || [ -z "$ADDR" ]; then
    echo "usage: $0 <bridge> <address_cidr> [--dry-run] [--yes]" >&2
    exit 2
fi

## the address is used in a fixed-string grep below, never as a pattern, but a malformed value here
## would silently match nothing and report a clean host. So it is checked.
case "$ADDR" in
    *[0-9].[0-9]*/[0-9]*) : ;;
    *) echo "ERROR: <address_cidr> must look like 192.168.143.1/24, got '$ADDR'" >&2 ; exit 2 ;;
esac

[ -r "$INTERFACES" ] || { echo "ERROR: cannot read $INTERFACES" >&2 ; exit 1 ; }

#### #### ####
#
# 1. DETECT. Read the stanza and decide whether there is anything to do at all. An absent bridge is
#    the normal answer on a clean host.
#
if ! grep -qE "^[[:space:]]*iface[[:space:]]+${BRIDGE}([[:space:]]|$)" "$INTERFACES" ; then
    echo "nothing-to-do: no '${BRIDGE}' stanza in ${INTERFACES}"
    exit 0
fi

## the stanza's own lines : from its `iface` up to the next `auto`/`iface`/`source` at column 0
stanza_of() {
    awk -v b="$BRIDGE" '
        /^[[:space:]]*(auto|iface|source|allow-)/ {
            if (inb) exit
            inb = ($1 == "iface" && $2 == b)
        }
        inb { print }
    ' "$INTERFACES"
}

STANZA="$(stanza_of)"
HAS_ADDR=$(printf '%s\n' "$STANZA" | grep -cF -- " ${ADDR}" || true)
HAS_NAT=$(printf '%s\n' "$STANZA"  | grep -cE 'MASQUERADE|-j[[:space:]]+SNAT' || true)

if [ "$HAS_ADDR" -eq 0 ] && [ "$HAS_NAT" -eq 0 ]; then
    echo "nothing-to-do: ${BRIDGE} carries neither ${ADDR} nor a NAT rule - already disarmed"
    exit 0
fi

echo ":: ${BRIDGE} in ${INTERFACES}"
echo "   address lines to remove : ${HAS_ADDR}"
echo "   NAT lines to remove     : ${HAS_NAT}"
echo ""
echo "   the exact lines :"
printf '%s\n' "$STANZA" | grep -nE "(^|[[:space:]])address[[:space:]]+${ADDR//./\\.}([[:space:]]|$)|MASQUERADE|-j[[:space:]]+SNAT" | sed 's/^/     - /'
echo ""

#### #### ####
#
# 2. BUILD THE NEW FILE ON A COPY. Never in place : a failure halfway through would leave the
#    hypervisor with a truncated network config.
#
TMP="$(mktemp "${INTERFACES}.disarm.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

awk -v b="$BRIDGE" -v addr="$ADDR" '
    ## track the stanza we are inside. A line starting a new block ends the previous one.
    /^[[:space:]]*(auto|iface|source|allow-)/ { inb = ($1 == "iface" && $2 == b) }
    ## inside OUR stanza only : drop the address line for this exact cidr, and any NAT line
    inb && $1 == "address" && $2 == addr { next }
    inb && /MASQUERADE/                  { next }
    inb && /-j[[:space:]]+SNAT/          { next }
    { print }
' "$INTERFACES" > "$TMP"

#### #### ####
#
# 3. VALIDATE THE RESULT BEFORE IT REPLACES ANYTHING. Three checks, each of which has a failure mode
#    worth catching : an empty output, a file that lost more than the lines we targeted, and a
#    config ifupdown2 refuses to parse.
#
[ -s "$TMP" ] || { echo "ERROR: the rewrite produced an empty file - original untouched" >&2 ; exit 1 ; }

BEFORE=$(wc -l < "$INTERFACES")
AFTER=$(wc -l < "$TMP")
EXPECTED=$((BEFORE - HAS_ADDR - HAS_NAT))
if [ "$AFTER" -ne "$EXPECTED" ]; then
    echo "ERROR: expected ${EXPECTED} lines after removing $((HAS_ADDR + HAS_NAT)), got ${AFTER}" >&2
    echo "       the original is untouched. Diff of what was about to be written :" >&2
    diff "$INTERFACES" "$TMP" >&2 || true
    exit 1
fi

if command -v ifquery >/dev/null 2>&1 ; then
    if ! ifquery --check --interfaces "$TMP" "$BRIDGE" >/dev/null 2>&1 ; then
        ## ifquery --check compares against the RUNNING state, so a mismatch here is expected once
        ## the address is gone. Only a PARSE failure matters, and that is what -l catches.
        if ! ifquery --interfaces "$TMP" -l >/dev/null 2>&1 ; then
            echo "ERROR: ifupdown2 cannot parse the rewritten file - original untouched" >&2
            exit 1
        fi
    fi
fi

echo "   the change that would be applied :"
diff "$INTERFACES" "$TMP" | sed 's/^/     /' || true
echo ""

if $DRY_RUN ; then
    echo "dry-run: nothing written"
    exit 0
fi

#### #### ####
#
# 4. ASK, unless told not to. Reached only when there IS something to remove - a clean host never
#    gets here. Under Ansible there is no terminal : refuse rather than assume a yes.
#
if ! $ASSUME_YES ; then
    if [ ! -t 0 ]; then
        echo "ERROR: no terminal to ask on, and --yes was not given : refused" >&2
        exit 1
    fi
    ans=""
    printf '   this edits %s. Type y to proceed, anything else to abort : ' "$INTERFACES"
    read -r ans
    case "$ans" in
        y|Y|yes|YES) : ;;
        *) echo "   aborted on your answer - nothing written" ; exit 1 ;;
    esac
fi

#### #### ####
#
# 5. BACK UP, THEN MOVE. The backup path is printed so a rollback is a `cp`, not a reconstruction.
#
BACKUP="${INTERFACES}.range42-$(date -u +%Y%m%dT%H%M%SZ).bak"
cp -p "$INTERFACES" "$BACKUP" || { echo "ERROR: backup failed, nothing written" >&2 ; exit 1 ; }
chmod --reference="$INTERFACES" "$TMP" 2>/dev/null || true
mv "$TMP" "$INTERFACES" || { echo "ERROR: move failed - restore with: cp $BACKUP $INTERFACES" >&2 ; exit 1 ; }
trap - EXIT

echo "disarmed: ${BRIDGE} lost ${HAS_ADDR} address line(s) and ${HAS_NAT} NAT line(s)"
echo "backup:   ${BACKUP}"
echo "note:     the live address and rules are NOT removed by this script - reconcile them separately"
