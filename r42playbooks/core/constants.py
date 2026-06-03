"""Regexes, limits, and naming rules shared across the core.

Single source of truth for the patterns that several modules validate against,
so the scenario-name rule (must match the backend resolver) and the security
deny-list never drift between models, the compiler, and the catalog loader.
"""

import re

# Scenario name — mirrors range42-backend-api resolve_scenarios_playbook():
#   <playbooks>/scenarios/<name>/main.yml, name segments are [A-Za-z0-9_-],
#   slash-joined, NO dots, no leading/trailing slash.
SCENARIO_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$")

# vm_name / inventory host leaf — lowercase kebab, bounded length.
VM_NAME_RE = re.compile(r"^[a-z0-9-]{1,40}$")

# Ansible inventory group — lowercase snake. Hyphenated groups (e.g. proxmox-cli)
# are intentional and hard-coded by the compiler, never sourced from a topology,
# because ansible.cfg sets force_valid_group_names=never (see workspace CLAUDE.md).
INVENTORY_GROUP_RE = re.compile(r"^[a-z0-9_]+$")

# Catalog reference — role/stack ids MAY contain dots (e.g. software.install.wazuh),
# unlike scenario names. Kept deliberately separate from SCENARIO_NAME_RE.
CATALOG_REF_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")

# Proxmox bridge interface.
BRIDGE_RE = re.compile(r"^vmbr[0-9]+$")

# IPv4 address and CIDR (syntactic; semantic checks live in the compiler).
IPV4_RE = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
IPV4_CIDR_RE = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$")

# Proxmox node name — requires a leading alphanumeric (no empty, no leading dash
# which a subprocess could read as a flag), bounded length per RFC-952/Proxmox.
PROXMOX_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")

# Network-policy matrix endpoints (catalog-authored): src is a zone name or "*";
# dst is a zone name, "svc:<name>", or "*".
MATRIX_SRC_RE = re.compile(r"^(\*|[a-z0-9-]{1,40})$")
MATRIX_DST_RE = re.compile(r"^(\*|svc:[a-z0-9-]{1,40}|[a-z0-9-]{1,40})$")

# Interface name for compiled iptables rules (bridges, uplink NICs).
IFACE_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
# iptables destination port or inclusive range, e.g. "1514" or "1514:1515".
PORT_SPEC_RE = re.compile(r"^[0-9]{1,5}(:[0-9]{1,5})?$")

# vm_id bounds: 4-digit ids in the project's allocated band.
VM_ID_MIN = 1000
VM_ID_MAX = 9999

# Upper bound on how many VMs a single composed box may expand to (count>1).
# Bounds runaway allocation from a hostile/typo'd scenario.r42.yml.
BOX_COUNT_MAX = 99

# Catalog template id — dotless kebab (distinct from dotted role refs and from
# the scenario-name rule). Used for directory names under 05_topology_layer/.
TEMPLATE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Version directory under a template id, e.g. "v1.0.0".
VERSION_DIR_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

# Catalog layout: the new topology layer and its categories.
TOPOLOGY_LAYER_DIR = "05_topology_layer"
CATEGORY_BOX_TEMPLATES = "box_templates"
CATEGORY_NETWORK_POLICIES = "network_policies"
CATEGORY_SUBNET_LAYOUTS = "subnet_layouts"

# Security deny-list: substrings that must never appear in a free-text topology
# field. Blocks Jinja/SSTI (`{{ }}`, `{% %}`, `${`), shell metacharacters,
# path traversal, and argv-flag injection. Fields are rejected, never sanitized.
DENYLIST_SUBSTRINGS: tuple[str, ...] = (
    "{{", "}}", "{%", "%}", "${", "`", ";", "|", "&", "\n", "\r", "\x00", "..",
)


def violates_denylist(value: str) -> bool:
    """Return True if *value* contains any denied substring or a leading dash."""
    if value.startswith("-"):
        return True
    return any(token in value for token in DENYLIST_SUBSTRINGS)


def reject_injection(value: str) -> str:
    """Field-validator helper: raise ValueError if *value* is deny-listed."""
    if violates_denylist(value):
        raise ValueError("value contains a forbidden character or pattern")
    return value


def reject_injection_nested(obj):
    """Recursively deny-list-check every string key/value in a dict/list/scalar.

    Used for free-form ``params`` / ``overrides`` dicts whose values can flow
    into Ansible variables (Jinja2 render surface) or compiled rule fields.
    """
    if isinstance(obj, str):
        reject_injection(obj)
    elif isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(key, str):
                reject_injection(key)
            reject_injection_nested(val)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            reject_injection_nested(item)
    return obj


def octet_matches_vm_id(vm_id: int, ip: str) -> bool:
    """Project rule: a single-subnet VM's vm_id last 3 digits == IP last octet.

    Enforced as an error for newly authored boxes; legacy ``_reserved.json``
    rows that predate the rule are only warned about (handled in idalloc).
    """
    return vm_id % 1000 == int(ip.rsplit(".", 1)[-1])
