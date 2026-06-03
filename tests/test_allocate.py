"""Step 4 — allocation + manifest/scenario_vms.json (RED before GREEN).

Invariants under test (plan §4, §7.1):
  - octet rule (vm_id last 3 digits == IP last octet) holds for every placed box;
  - templates are NOT placed / never octet-checked; templates[] is the full table;
  - count>1 expands to <template>-00..0(N-1);
  - lowest-matching template vm_id is selected for a box spec (H2);
  - global uniqueness vs _reserved.json (other scenarios block; band bumps);
  - manifest matches the demo_lab schema.
All tests use the fake_catalog fixture (real range42-catalog never in checkout).
"""

import pytest

from r42playbooks.core import constants as C
from r42playbooks.core.allocate import Allocation, allocate, manifest_dict
from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.spec import ScenarioSpec
from r42playbooks.core.templates_table import TEMPLATE_TABLE, select_template


def _alloc(catalog, **spec_overrides):
    base = {
        "name": "gen_lab",
        "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf",
        "boxes": [{"template": "admin-wazuh"}],
    }
    base.update(spec_overrides)
    return allocate(ScenarioSpec.model_validate(base), catalog)


# --- template table / selection (H2) --------------------------------------

def test_select_template_picks_lowest_matching_vm_id():
    # 9234 and 9244 both match 4cpu/8gb/64gb -> lowest wins
    t = select_template("4cpu/8gb/64gb")
    assert t.vm_id == 9234


def test_select_template_override_by_vm_id():
    t = select_template("4cpu/8gb/64gb", override_vm_id=9244)
    assert t.vm_id == 9244


def test_select_template_unknown_spec_raises():
    with pytest.raises(Exception):
        select_template("999cpu/1tb/1pb")


# --- octet rule + base octets ---------------------------------------------

def test_admin_box_gets_demo_lab_slot(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog))
    box = alloc.boxes[0]
    assert box.vm_name == "admin-wazuh"
    assert box.vm_id == 1100
    assert box.ip == "192.168.142.100"
    assert box.bridge == "vmbr142"


def test_student_box_uses_student_base_octet(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "student-box"}])
    box = alloc.boxes[0]
    assert box.vm_id == 1160
    assert box.ip == "192.168.143.160"


def test_octet_rule_holds_for_every_placed_box(fake_catalog):
    alloc = _alloc(
        load_catalog(fake_catalog),
        boxes=[{"template": "admin-wazuh"}, {"template": "vuln-box", "count": 5}],
    )
    for box in alloc.boxes:
        assert C.octet_matches_vm_id(box.vm_id, box.ip), box


# --- count expansion -------------------------------------------------------

def test_count_expands_to_zero_padded_names(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "vuln-box", "count": 5}])
    names = [b.vm_name for b in alloc.boxes]
    assert names == ["vuln-box-00", "vuln-box-01", "vuln-box-02", "vuln-box-03", "vuln-box-04"]
    ids = [b.vm_id for b in alloc.boxes]
    assert ids == [1170, 1171, 1172, 1173, 1174]
    ips = [b.ip for b in alloc.boxes]
    assert ips == [f"192.168.144.{o}" for o in range(170, 175)]


def test_count_one_keeps_bare_template_name(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "vuln-box"}])
    assert alloc.boxes[0].vm_name == "vuln-box"


def test_box_resolves_clone_template_vm_id(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "vuln-box"}])
    box = alloc.boxes[0]
    assert box.template_vm_id == 9221  # lowest 1cpu/4gb/32gb


def test_attachments_merge_template_defaults_and_spec_additions(fake_catalog):
    alloc = _alloc(
        load_catalog(fake_catalog),
        boxes=[{
            "template": "vuln-box",
            "attachments_add": [
                {"kind": "role", "catalog_ref": "software.install.extra", "params": {}},
            ],
        }],
    )
    refs = [a.catalog_ref for a in alloc.boxes[0].attachments]
    assert "software.install.wazuh-agent" in refs   # from template default
    assert "software.install.extra" in refs         # from spec addition


# --- _reserved.json uniqueness --------------------------------------------

def test_other_scenario_vm_id_collision_bumps_band(fake_catalog, reserved_factory):
    # another scenario owns vm_id 1170, but on a different IP -> octet .170 still
    # free for our ctf subnet, so the band bumps (2170) keeping the octet rule.
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": 1170, "ip": "10.9.9.9", "scenario": "other_lab"},
    ]))
    spec = ScenarioSpec.model_validate({
        "name": "gen_lab", "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf", "boxes": [{"template": "vuln-box"}],
    })
    box = allocate(spec, load_catalog(fake_catalog), reserved).boxes[0]
    assert box.ip == "192.168.144.170"
    assert box.vm_id == 2170
    assert C.octet_matches_vm_id(box.vm_id, box.ip)


def test_other_scenario_ip_collision_bumps_octet(fake_catalog, reserved_factory):
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": 1170, "ip": "192.168.144.170", "scenario": "other_lab"},
    ]))
    spec = ScenarioSpec.model_validate({
        "name": "gen_lab", "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf", "boxes": [{"template": "vuln-box"}],
    })
    box = allocate(spec, load_catalog(fake_catalog), reserved).boxes[0]
    assert box.ip == "192.168.144.171"
    assert box.vm_id == 1171


def test_template_rows_never_reallocated(fake_catalog, reserved_factory):
    # _reserved.json carries 9xxx template rows; no placed box may land in 9xxx.
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": t.vm_id, "vm_name": t.vm_name, "ip": t.ip, "bridge": t.bridge,
         "role": "template", "scenario": "other_lab"} for t in TEMPLATE_TABLE
    ]))
    spec = ScenarioSpec.model_validate({
        "name": "gen_lab", "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf", "boxes": [{"template": "vuln-box", "count": 3}],
    })
    alloc = allocate(spec, load_catalog(fake_catalog), reserved)
    for box in alloc.boxes:
        assert box.vm_id < 9000


# --- manifest --------------------------------------------------------------

def test_manifest_matches_demo_lab_schema(fake_catalog):
    alloc = _alloc(
        load_catalog(fake_catalog),
        name="demo_clone",
        boxes=[{"template": "admin-wazuh"}, {"template": "vuln-box", "count": 5}],
    )
    m = manifest_dict(alloc)
    assert m["scenario"] == "demo_clone"
    assert m["version"] == 2
    assert {"scenario", "version", "description", "vms", "templates"} == set(m)
    # vms sorted by vm_id, demo_lab row shape
    assert m["vms"] == sorted(m["vms"], key=lambda v: v["vm_id"])
    assert set(m["vms"][0]) == {"vm_id", "vm_name", "ip", "role", "bridge"}


def test_manifest_templates_populated_not_empty(fake_catalog):
    # H1 guard: the old compiler hard-coded templates:[]; here it must be full.
    alloc = _alloc(load_catalog(fake_catalog))
    m = manifest_dict(alloc)
    assert len(m["templates"]) == len(TEMPLATE_TABLE) == 12
    assert set(m["templates"][0]) == {"vm_id", "vm_name", "spec", "ip", "bridge"}


def test_unknown_box_template_raises(fake_catalog):
    catalog = load_catalog(fake_catalog)
    spec = ScenarioSpec.model_validate({
        "name": "gen_lab", "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf", "boxes": [{"template": "ghost-box"}],
    })
    with pytest.raises(Exception):
        allocate(spec, catalog)


def test_allocation_is_deterministic(fake_catalog):
    catalog = load_catalog(fake_catalog)
    a1 = _alloc(catalog, boxes=[{"template": "vuln-box", "count": 3}])
    a2 = _alloc(catalog, boxes=[{"template": "vuln-box", "count": 3}])
    assert isinstance(a1, Allocation)
    assert manifest_dict(a1) == manifest_dict(a2)
