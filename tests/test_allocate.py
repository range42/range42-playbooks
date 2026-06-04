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
from r42playbooks.core.errors import CatalogNotFoundError, CompileError, ValidationError
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.spec import ScenarioSpec


def _alloc(catalog, **spec_overrides):
    base = {
        "name": "gen_lab",
        "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf",
        "boxes": [{"template": "admin-wazuh", "subnet": "admin"}],
    }
    base.update(spec_overrides)
    return allocate(ScenarioSpec.model_validate(base), catalog)


# --- template VM resolution (catalog-driven) --------------------------------

def test_box_image_resolved_from_template_vm(fake_catalog):
    """template_vm reference on BoxTemplate drives image resolution."""
    alloc = _alloc(load_catalog(fake_catalog))
    # admin-wazuh → template-vm-ubuntu-noble-medium-04-8g-64g → ubuntu_noble
    assert all(b.image == "ubuntu_noble" for b in alloc.boxes)
    assert {t.image for t in alloc.templates} == {"ubuntu_noble"}


def _add_box_template(fake_catalog, *, box_id: str, template_vm: str) -> None:
    layer = fake_catalog / "05_topology_layer" / "box_templates" / box_id / "v1.0.0"
    layer.mkdir(parents=True)
    (layer / "template.yml").write_text(
        f"id: {box_id}\napi_version: 1\n"
        f"template_vm: \"{template_vm}\"\n"
        f"default_inventory_group: r42_student\n",
        encoding="utf-8",
    )


def test_debian_box_selects_a_debian_trixie_template(fake_catalog):
    """A box referencing a debian_trixie template_vm clones that image."""
    from r42playbooks.core.catalog import load_catalog as _load
    _add_box_template(fake_catalog, box_id="deb-box",
                      template_vm="template-vm-debian-trixie-small")
    catalog = _load(fake_catalog)
    spec = ScenarioSpec.model_validate({
        "name": "deb_lab", "subnet_layout": "default-3zone", "boxes": [{"template": "deb-box", "subnet": "student"}],
    })
    box = allocate(spec, catalog).boxes[0]
    assert box.image == "debian_trixie"
    assert box.template_vm_id == 9321
    assert box.template_name == "template-vm-debian-trixie-small"


def test_unknown_template_vm_blocks_allocation(fake_catalog):
    """A box referencing a template_vm that doesn't exist raises CompileError."""
    from r42playbooks.core.catalog import load_catalog as _load
    _add_box_template(fake_catalog, box_id="ghost-vm-box",
                      template_vm="template-vm-does-not-exist")
    catalog = _load(fake_catalog)
    spec = ScenarioSpec.model_validate({
        "name": "ghost_lab", "subnet_layout": "default-3zone",
        "boxes": [{"template": "ghost-vm-box", "subnet": "student"}],
    })
    with pytest.raises(CompileError, match="template-vm-does-not-exist"):
        allocate(spec, catalog)


# --- octet rule + base octets ---------------------------------------------

def test_admin_box_gets_demo_lab_slot(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog))
    box = alloc.boxes[0]
    assert box.vm_name == "admin-wazuh"
    assert box.vm_id == 1100
    assert box.ip == "192.168.142.100"
    assert box.bridge == "vmbr142"


def test_student_box_uses_student_base_octet(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "student-box", "subnet": "student"}])
    box = alloc.boxes[0]
    assert box.vm_id == 1160
    assert box.ip == "192.168.143.160"


def test_octet_rule_holds_for_every_placed_box(fake_catalog):
    alloc = _alloc(
        load_catalog(fake_catalog),
        boxes=[{"template": "admin-wazuh", "subnet": "admin"}, {"template": "vuln-box", "count": 5, "subnet": "ctf"}],
    )
    for box in alloc.boxes:
        assert C.octet_matches_vm_id(box.vm_id, box.ip), box


# --- count expansion -------------------------------------------------------

def test_count_expands_to_zero_padded_names(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "vuln-box", "count": 5, "subnet": "ctf"}])
    names = [b.vm_name for b in alloc.boxes]
    assert names == ["vuln-box-00", "vuln-box-01", "vuln-box-02", "vuln-box-03", "vuln-box-04"]
    ids = [b.vm_id for b in alloc.boxes]
    assert ids == [1170, 1171, 1172, 1173, 1174]
    ips = [b.ip for b in alloc.boxes]
    assert ips == [f"192.168.144.{o}" for o in range(170, 175)]


def test_count_one_keeps_bare_template_name(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "vuln-box", "subnet": "ctf"}])
    assert alloc.boxes[0].vm_name == "vuln-box"


def test_box_resolves_clone_template_vm_id(fake_catalog):
    alloc = _alloc(load_catalog(fake_catalog), boxes=[{"template": "vuln-box", "subnet": "ctf"}])
    box = alloc.boxes[0]
    assert box.template_vm_id == 9221  # lowest 1cpu/4gb/32gb


def test_attachments_merge_template_defaults_and_spec_additions(fake_catalog):
    alloc = _alloc(
        load_catalog(fake_catalog),
        boxes=[{
            "template": "vuln-box",
            "subnet": "ctf",
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
        "network_policy": "air-gap-ctf", "boxes": [{"template": "vuln-box", "subnet": "ctf"}],
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
        "network_policy": "air-gap-ctf", "boxes": [{"template": "vuln-box", "subnet": "ctf"}],
    })
    box = allocate(spec, load_catalog(fake_catalog), reserved).boxes[0]
    assert box.ip == "192.168.144.171"
    assert box.vm_id == 1171


def test_template_rows_never_reallocated(fake_catalog, reserved_factory):
    # _reserved.json carries 9xxx template rows; no placed box may land in 9xxx.
    catalog = load_catalog(fake_catalog)
    # Use the actual template VMs from the catalog as the reserved set.
    template_entries = [
        {"vm_id": t.vm_id, "vm_name": t.vm_name, "ip": t.ip, "bridge": t.bridge,
         "role": "template", "scenario": "other_lab"}
        for img in catalog.images.values()
        for t_spec in img.proxmox_templates
        for t in [type("T", (), {"vm_id": t_spec.vm_id, "vm_name": t_spec.vm_name,
                                  "ip": f"192.168.140.{t_spec.ip_octet}", "bridge": "vmbr140"})()]
    ]
    reserved = ReservedIndex.from_file(reserved_factory(template_entries))
    spec = ScenarioSpec.model_validate({
        "name": "gen_lab", "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf", "boxes": [{"template": "vuln-box", "count": 3, "subnet": "ctf"}],
    })
    alloc = allocate(spec, catalog, reserved)
    for box in alloc.boxes:
        assert box.vm_id < 9000


# --- manifest --------------------------------------------------------------

def test_manifest_matches_demo_lab_schema(fake_catalog):
    alloc = _alloc(
        load_catalog(fake_catalog),
        name="demo_clone",
        boxes=[{"template": "admin-wazuh", "subnet": "admin"}, {"template": "vuln-box", "count": 5, "subnet": "ctf"}],
    )
    m = manifest_dict(alloc)
    assert m["scenario"] == "demo_clone"
    assert m["version"] == 2
    assert {"scenario", "version", "description", "vms", "templates"} == set(m)
    # vms sorted by vm_id, demo_lab row shape
    assert m["vms"] == sorted(m["vms"], key=lambda v: v["vm_id"])
    assert set(m["vms"][0]) == {"vm_id", "vm_name", "ip", "subnet", "bridge", "image"}
    assert all(v["image"] == "ubuntu_noble" for v in m["vms"])  # fake_catalog boxes default


def test_manifest_templates_selective_not_full_table(fake_catalog):
    """templates[] contains only the VMs the scenario actually needs (not the full table)."""
    alloc = _alloc(load_catalog(fake_catalog))
    m = manifest_dict(alloc)
    # admin-wazuh needs template-vm-ubuntu-noble-medium-04-8g-64g only
    assert len(m["templates"]) == 1
    assert m["templates"][0]["vm_id"] == 9234
    assert m["templates"][0]["image"] == "ubuntu_noble"
    assert set(m["templates"][0]) == {"vm_id", "vm_name", "spec", "ip", "bridge", "image"}


def test_manifest_templates_multi_image(fake_catalog):
    """A scenario with both ubuntu and debian boxes has both images in templates[]."""
    _add_box_template(fake_catalog, box_id="deb-box2",
                      template_vm="template-vm-debian-trixie-small")
    alloc = _alloc(
        load_catalog(fake_catalog),
        boxes=[{"template": "admin-wazuh", "subnet": "admin"}, {"template": "deb-box2", "subnet": "student"}],
    )
    m = manifest_dict(alloc)
    assert {t["image"] for t in m["templates"]} == {"ubuntu_noble", "debian_trixie"}
    assert len(m["templates"]) == 2


def test_unknown_box_template_raises(fake_catalog):
    catalog = load_catalog(fake_catalog)
    spec = ScenarioSpec.model_validate({
        "name": "gen_lab", "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf", "boxes": [{"template": "ghost-box", "subnet": "admin"}],
    })
    with pytest.raises(CatalogNotFoundError):
        allocate(spec, catalog)


def test_allocation_is_deterministic(fake_catalog):
    catalog = load_catalog(fake_catalog)
    a1 = _alloc(catalog, boxes=[{"template": "vuln-box", "count": 3, "subnet": "ctf"}])
    a2 = _alloc(catalog, boxes=[{"template": "vuln-box", "count": 3, "subnet": "ctf"}])
    assert isinstance(a1, Allocation)
    assert manifest_dict(a1) == manifest_dict(a2)


def test_missing_template_subnet_raises(fake_catalog):
    """A subnet layout without template_subnet raises CompileError at allocation."""
    layer = fake_catalog / "05_topology_layer" / "subnet_layouts" / "no-tpl-subnet" / "v1.0.0"
    layer.mkdir(parents=True)
    (layer / "template.yml").write_text(
        "id: no-tpl-subnet\napi_version: 1\n"
        "subnets:\n  - {name: admin, cidr: 192.168.99.0/24, bridge: vmbr99}\n",
        encoding="utf-8",
    )
    catalog = load_catalog(fake_catalog)
    spec = ScenarioSpec.model_validate({
        "name": "bad_lab", "subnet_layout": "no-tpl-subnet",
        "boxes": [{"template": "admin-wazuh", "subnet": "admin"}],
    })
    with pytest.raises(CompileError, match="no template_subnet"):
        allocate(spec, catalog)
