"""P4 scaffold tests — pure starter-topology generation (shared by CLI + TUI)."""

from r42playbooks.core import constants as C
from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.scaffold import scaffold_topology
from r42playbooks.core.validate import semantic_problems


def test_scaffold_produces_valid_topology(fake_catalog):
    cat = load_catalog(fake_catalog)
    t = scaffold_topology(cat, scenario="lab1", layout_id="default-3zone",
                          policy_id="air-gap-ctf")
    assert t.scenario == "lab1"
    assert semantic_problems(t, cat) == []
    assert t.network_policy.template == "air-gap-ctf"


def test_scaffold_picks_box_template_by_role(fake_catalog):
    cat = load_catalog(fake_catalog)
    t = scaffold_topology(cat, scenario="lab1", layout_id="default-3zone",
                          policy_id="air-gap-ctf")
    templates = {b.box_template for b in t.boxes}
    assert "admin-wazuh" in templates  # admin zone
    assert "vuln-box" in templates     # ctf zone


def test_scaffold_respects_octet_rule(fake_catalog):
    cat = load_catalog(fake_catalog)
    t = scaffold_topology(cat, scenario="lab1", layout_id="default-3zone",
                          policy_id="air-gap-ctf")
    for box in t.boxes:
        assert C.octet_matches_vm_id(box.vm_id, box.ip), box
