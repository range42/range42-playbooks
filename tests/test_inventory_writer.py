"""inventory_writer parity (ported from range42-backend-api
``tests/core/test_inventory_writer.py`` @ feature/gamenet-authoring-v1,
issue #67), plus a byte-level golden comparison against the backend's
``write_inventory`` output.

The golden files in ``tests/golden/inventory/`` were generated from the
backend's ``write_inventory`` at port time over the shared topology vectors
(``01-minimal`` @ team_count=1, ``02-multi-team`` @ team_count=3). The port is
required to reproduce them byte-for-byte — that is the convergence acceptance
gate for this module.
"""
import json
from pathlib import Path

import pytest
import yaml

from r42topo.core.inventory_writer import write_inventory

VECTORS = Path(__file__).parent / "vectors" / "test-vectors" / "topology"
GOLDEN = Path(__file__).parent / "golden" / "inventory"


# --- golden byte-compare (convergence acceptance) --------------------------

@pytest.mark.parametrize(
    "name, kw",
    [
        ("01-minimal", dict(team_count=1, codename="MIN", proxmox_address="10.0.0.1")),
        ("02-multi-team", dict(team_count=3, codename="MT", proxmox_address="10.0.0.1")),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_matches_backend_golden(tmp_path, name, kw):
    topology = json.loads((VECTORS / f"{name}.json").read_text())
    dest = tmp_path / "hosts.yml"
    write_inventory(
        topology=topology,
        ssh_keys_dir=Path("/keys"),
        dest=dest,
        **kw,
    )
    produced = dest.read_text()
    expected = (GOLDEN / f"{name}.hosts.yml").read_text()
    assert produced == expected, f"{name}: inventory diverged from backend golden"


# --- mirrored backend unit tests -------------------------------------------

def test_writes_minimal_inventory(tmp_path):
    topology = json.loads((VECTORS / "01-minimal.json").read_text())
    out = tmp_path / "hosts.yml"
    write_inventory(
        topology=topology,
        team_count=1,
        codename="MIN",
        proxmox_address="10.0.0.1",
        ssh_keys_dir=tmp_path / "ssh_keys",
        dest=out,
    )

    inv = yaml.safe_load(out.read_text())
    assert "all" in inv
    children = inv["all"]["children"]
    assert "r42_admin" in children
    assert "proxmox" in children
    # The minimal fixture has one admin node with id "host-01"
    assert any("host-01" in h for h in children["r42_admin"]["hosts"])


def test_writes_multi_team_inventory(tmp_path):
    topology = json.loads((VECTORS / "02-multi-team.json").read_text())
    out = tmp_path / "hosts.yml"
    write_inventory(
        topology=topology,
        team_count=3,
        codename="MT",
        proxmox_address="10.0.0.1",
        ssh_keys_dir=tmp_path / "ssh_keys",
        dest=out,
    )

    inv = yaml.safe_load(out.read_text())
    children = inv["all"]["children"]

    # Shared admin VM appears once
    admin_hosts = list(children["r42_admin"]["hosts"].keys())
    assert len([h for h in admin_hosts if "wazuh" in h]) == 1

    # Per-team trainee VM appears 3 times
    blank_hosts = list(children["r42_blank_group"]["hosts"].keys())
    assert any("1-trainee" in h for h in blank_hosts)
    assert any("2-trainee" in h for h in blank_hosts)
    assert any("3-trainee" in h for h in blank_hosts)


def test_inventory_uses_correct_ip_for_team(tmp_path):
    topology = json.loads((VECTORS / "02-multi-team.json").read_text())
    out = tmp_path / "hosts.yml"
    write_inventory(
        topology=topology,
        team_count=2,
        codename="MT",
        proxmox_address="10.0.0.1",
        ssh_keys_dir=tmp_path / "ssh_keys",
        dest=out,
    )

    inv = yaml.safe_load(out.read_text())
    blank = inv["all"]["children"]["r42_blank_group"]["hosts"]
    # bridge_base=140; team 1 -> 192.168.141.200; team 2 -> 192.168.142.200
    team1_host = next(h for h in blank if "1-trainee" in h)
    team2_host = next(h for h in blank if "2-trainee" in h)
    assert blank[team1_host]["ansible_host"] == "192.168.141.200"
    assert blank[team2_host]["ansible_host"] == "192.168.142.200"


def test_skips_non_host_node_kinds(tmp_path):
    """network/router/firewall/skin/group nodes are NOT inventory hosts.
    Only vm/lxc/docker nodes should appear in the host inventory."""
    topology = json.loads((VECTORS / "02-multi-team.json").read_text())
    # Multi-team fixture has a 'network' node — shouldn't appear in any group.
    out = tmp_path / "hosts.yml"
    write_inventory(
        topology=topology,
        team_count=1,
        codename="MT",
        proxmox_address="10.0.0.1",
        ssh_keys_dir=tmp_path / "ssh_keys",
        dest=out,
    )
    inv = yaml.safe_load(out.read_text())
    all_hosts = []
    for grp in inv["all"]["children"].values():
        all_hosts.extend(grp.get("hosts", {}).keys())
    assert not any("team-net" in h for h in all_hosts), \
        "Network nodes must not appear as inventory hosts"


def test_wazuh_agent_attachment_adds_client_membership(tmp_path):
    """A node carrying a wazuh-agent catalog_role attachment is also listed
    (membership-only, no host vars) under r42_admin_wazuh_clients."""
    topology = {
        "schema_version": "1.0",
        "kind": "gamenet",
        "naming_prefix": "wz",
        "bridge_base": 140,
        "nodes": [
            {
                "id": "trainee", "kind": "vm", "role": "team",
                "replication": {"scope": "per_team"},
                "template_vmid": 9020,
                "attachments": [
                    {"source": {"kind": "catalog_role",
                                "ref": "software.install.wazuh-agent"},
                     "stage": "install"},
                ],
            }
        ],
    }
    out = tmp_path / "hosts.yml"
    write_inventory(
        topology=topology, team_count=2, codename="WZ",
        proxmox_address="10.0.0.1", ssh_keys_dir=tmp_path / "ssh_keys", dest=out,
    )
    inv = yaml.safe_load(out.read_text())
    clients = inv["all"]["children"]["r42_admin_wazuh_clients"]["hosts"]
    # One membership entry per team, each with no host vars.
    assert len(clients) == 2
    assert all(v == {} for v in clients.values())
    assert any("1-trainee" in h for h in clients)
    assert any("2-trainee" in h for h in clients)


def test_rejects_node_without_role(tmp_path):
    """VM/LXC nodes MUST have a role; preflight catches this but inventory_writer
    is also a defense layer."""
    topology = {
        "schema_version": "1.0",
        "kind": "gamenet",
        "naming_prefix": "x",
        "bridge_base": 140,
        "nodes": [
            {
                "id": "broken", "kind": "vm",
                "replication": {"scope": "shared"},
                "template_vmid": 9001, "config": {}, "attachments": []
                # no 'role' field
            }
        ],
    }
    out = tmp_path / "hosts.yml"
    with pytest.raises(ValueError, match="missing 'role'"):
        write_inventory(
            topology=topology, team_count=1, codename="X",
            proxmox_address="10.0.0.1", ssh_keys_dir=tmp_path, dest=out,
        )
