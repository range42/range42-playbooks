"""S5b renderer — class-(B) verbatim-with-param boilerplate.

Golden-shape assertions against the §4.3 demo_lab baseline: the renderer maps
that shape onto the *composed* scenario name + its actual boxes (it never copies
demo_lab's own VMs). Verifies: the vendored ``01_init_proxmox/`` subtree (H3),
per-box ``stage_00``/``stage_01`` + devkits, top-level scripts, class-B
templates, that ``stage_01`` lists role NAMES (not copied role code), that
``secrets/`` is NOT created, and that demo_lab's group-level richness is NOT
generated (plan §7.2 richness decision).
"""

from pathlib import Path

import pytest

from r42playbooks.core import render_assets
from r42playbooks.core.allocate import allocate
from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.render import render_scenario
from r42playbooks.core.spec import ScenarioSpec, load_spec


def test_fill_raises_on_unfilled_sentinel():
    """A misspelled/forgotten key must not silently ship a leftover @@X@@."""
    import pytest
    with pytest.raises(RuntimeError):
        render_assets.fill("hello @@MISSING@@", PRESENT="x")


@pytest.fixture
def rendered(fake_catalog, valid_spec_dict, tmp_path):
    """Render the default 2-box composition (admin-wazuh + vuln-box×5) once."""
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    catalog = load_catalog(fake_catalog)
    alloc = allocate(spec, catalog)
    dest = tmp_path / "scenarios"
    root = render_scenario(alloc, spec, dest=dest)
    return spec, alloc, root


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


# --- top-level shape -------------------------------------------------------

def test_render_returns_scenario_root_dir(rendered):
    spec, _alloc, root = rendered
    assert root.is_dir()
    assert root.name == spec.name  # dest/<name>


def test_init_proxmox_subtree_copied_verbatim(rendered):
    """H3: the vendored 01_init_proxmox/ template-creation subtree is present."""
    _spec, _alloc, root = rendered
    assert (root / "01_init_proxmox" / "templates"
            / "ubuntu_noble" / "_main_ubuntu_noble.yml").is_file()
    assert (root / "01_init_proxmox" / "templates"
            / "_main_download_cloudinit_files.yml").is_file()


def test_main_yml_imports_only_emitted_sections(rendered):
    """main.yml wires 01_init_proxmox + the sections that actually have boxes."""
    _spec, _alloc, root = rendered
    main = _read(root, "main.yml")
    assert "./01_init_proxmox/templates/_main_download_cloudinit_files.yml" in main
    assert "./02_admin_infrastructure/_main.yml" in main
    assert "./04_ctf_infrastructure/_main.yml" in main
    # no student box was composed -> never import a section that wasn't emitted
    assert "03_student_infrastructure" not in main


def test_main_yml_imports_image_family_per_os(rendered):
    """main.yml creates the image set(s) the composition uses (ubuntu by default)."""
    _spec, _alloc, root = rendered
    main = _read(root, "main.yml")
    assert "./01_init_proxmox/templates/_main_download_cloudinit_files.yml" in main
    assert "./01_init_proxmox/templates/ubuntu_noble/_main_ubuntu_noble.yml" in main
    assert "debian/_main_debian.yml" not in main   # no debian box in this composition


def test_init_proxmox_is_os_selective_ubuntu_only(rendered):
    """A Ubuntu-only lab carries ONLY ubuntu_noble + downloads only ubuntu images."""
    _spec, _alloc, root = rendered
    templates = root / "01_init_proxmox" / "templates"
    assert (templates / "ubuntu_noble").is_dir()
    assert not (templates / "debian").exists()        # no inert debian template files
    download = _read(root, "01_init_proxmox/templates/_main_download_cloudinit_files.yml")
    assert "noble" in download
    assert "debian" not in download                   # no unused debian image downloaded


def test_top_level_scripts_present_and_named_for_scenario(rendered):
    spec, _alloc, root = rendered
    n = spec.name
    for rel in (
        "_activate.sh",
        f"{n}.setup.sh",
        f"{n}.setup_vms_only.sh",
        f"{n}.delete_all.sh",
        f"{n}.delete_vms_only.sh",
        f"{n}.reset.setup.sh",
        f"{n}.reset.ssh_keys.sh",
        "devkit_ansible.show_ansible_inventory.to.text.sh",
        "README.md",
        "scenario.r42.yml",
    ):
        assert (root / rel).is_file(), f"missing top-level file: {rel}"


def test_class_b_templates_present_and_parametrised(rendered):
    spec, _alloc, root = rendered
    assert (root / "templates" / "vault-example.yml").is_file()
    ansible_vars = _read(root, "templates/ansible-vars.yml")
    assert f'INFRASTRUCTURE_SCENARIO: "{spec.name}"' in ansible_vars


# --- per-section / per-box shape ------------------------------------------

def test_sections_match_composed_roles(rendered):
    """admin box -> 02_admin, ctf box -> 04_ctf; no student section emitted."""
    _spec, _alloc, root = rendered
    assert (root / "02_admin_infrastructure").is_dir()
    assert (root / "04_ctf_infrastructure").is_dir()
    assert not (root / "03_student_infrastructure").exists()
    for section in ("02_admin_infrastructure", "04_ctf_infrastructure"):
        assert (root / section / "_main.reinstall.sh").is_file()


def test_each_box_has_stage00_and_stage01_playbooks(rendered):
    _spec, alloc, root = rendered
    section_of = {"admin": "02_admin_infrastructure", "ctf": "04_ctf_infrastructure"}
    for box in alloc.boxes:
        section = section_of[box.role]
        assert (root / section / "stage_00" / f"{box.vm_name}.yml").is_file()
        assert (root / section / "stage_01" / f"{box.vm_name}.yml").is_file()


def test_stage00_clone_is_parametrised_boilerplate(rendered):
    """stage_00 clones via the proxmox controller and references the secrets symlink."""
    _spec, _alloc, root = rendered
    stage00 = _read(root, "04_ctf_infrastructure/stage_00/vuln-box-00.yml")
    assert "- hosts: proxmox" in stage00
    assert "{{ global_template_vm_id }}" in stage00
    assert "{{ global_vm_name }}" in stage00
    # C1: references the deploy-time secrets symlink, never creates it
    assert "../../secrets/default_vault.yml" in stage00


def test_stage01_lists_role_names_not_copied_code(rendered):
    """The contract (§2): stage_01 references catalog roles BY NAME only."""
    _spec, _alloc, root = rendered
    stage01 = _read(root, "04_ctf_infrastructure/stage_01/vuln-box-00.yml")
    assert "roles:" in stage01
    assert "software.install.wazuh-agent" in stage01  # default_attachment
    assert "software.install.extra" in stage01        # spec attachments_add
    assert "hosts: r42.vuln-box-00" in stage01        # M5 naming contract
    # no role *code* was vendored (a real role would carry tasks/handlers)
    assert "include_role:" not in stage01
    assert "ansible.builtin." not in stage01


def test_stage01_without_roles_is_valid_noop_play(rendered):
    """A box with no role attachments gets a deployable no-op play, NOT a bare [].

    `_main.yml` imports stage_01 via import_playbook, which rejects `[]` with
    "a play definition must contain exactly one of hosts/import_playbook/roles/tasks".
    """
    import yaml
    _spec, _alloc, root = rendered
    text = _read(root, "02_admin_infrastructure/stage_01/admin-wazuh.yml")
    plays = yaml.safe_load(text)            # a playbook is one doc: a list of plays
    assert isinstance(plays, list) and len(plays) == 1
    play = plays[0]
    assert play["hosts"] == "r42.admin-wazuh"
    assert play.get("tasks") == []          # valid no-op
    assert "roles" not in play              # no roles attached


def test_stage01_renders_box_vars(rendered):
    """Box `vars` from the spec are emitted into the stage_01 play (not dropped)."""
    _spec, _alloc, root = rendered
    # valid_spec_dict sets vars={"difficulty": "hard"} on vuln-box
    stage01 = _read(root, "04_ctf_infrastructure/stage_01/vuln-box-00.yml")
    assert "vars:" in stage01
    assert "difficulty: hard" in stage01


def test_scenario_name_with_slash_keeps_files_in_leaf(fake_catalog, valid_spec_dict, tmp_path):
    """A '/'-nested scenario name nests the dir but file prefixes use the leaf."""
    from r42playbooks.core.spec import ScenarioSpec
    from r42playbooks.core.catalog import load_catalog
    from r42playbooks.core.allocate import allocate
    from r42playbooks.core.render import render_scenario
    spec = ScenarioSpec.model_validate({**valid_spec_dict, "name": "ctf/web1"})
    catalog = load_catalog(fake_catalog)
    root = render_scenario(allocate(spec, catalog), spec, dest=tmp_path / "scenarios")
    assert root == tmp_path / "scenarios" / "ctf" / "web1"
    assert (root / "web1.setup.sh").is_file()        # leaf prefix, not ctf/web1.setup.sh
    assert not (root / "ctf").exists()               # no extra nested dir inside root


def test_each_box_has_devkit_scripts(rendered):
    spec, _alloc, root = rendered
    devkit = root / "04_ctf_infrastructure" / "stage_01" / "vuln-box-00.devkit"
    assert (devkit / f"{spec.name}.vuln-box-00.install.sh").is_file()
    assert (devkit / f"{spec.name}.vuln-box-00.snapshot.sh").is_file()
    assert (devkit / f"{spec.name}.vuln-box-00.revert.sh").is_file()


# --- negative assertions (decision boundaries) ----------------------------

def test_secrets_dir_is_not_created(rendered):
    """§4.2 / C1: secrets/ is a deploy-time symlink, never generated."""
    _spec, _alloc, root = rendered
    assert not (root / "secrets").exists()


def test_no_group_level_richness_generated(rendered):
    """Plan §7.2: group playbooks, group devkits, _testing/, builder_* are NOT generated."""
    _spec, _alloc, root = rendered
    files = [str(p.relative_to(root)) for p in root.rglob("*")]
    assert not any("_testing" in f for f in files)
    assert not any("builder_" in f for f in files)
    # no group playbook like _r42_admin_group.yml / _r42_vuln_box_group.yml
    assert not any(Path(f).name.startswith("_r42_") and f.endswith(".yml") for f in files)


# --- reproducibility -------------------------------------------------------

def test_scenario_spec_roundtrips_into_tree(rendered):
    spec, _alloc, root = rendered
    reloaded = load_spec(root / "scenario.r42.yml")
    assert reloaded.name == spec.name
    assert reloaded.subnet_layout == spec.subnet_layout
    assert [b.template for b in reloaded.boxes] == [b.template for b in spec.boxes]


def test_init_proxmox_is_os_selective_debian(fake_catalog, tmp_path):
    """A Debian lab carries ONLY debian/ + downloads only the trixie image."""
    # add a debian box to the catalog
    layer = fake_catalog / "05_topology_layer" / "box_templates" / "deb-box" / "v1.0.0"
    layer.mkdir(parents=True)
    (layer / "template.yml").write_text(
        "id: deb-box\napi_version: 1\nrole: student\nos: debian\n"
        "default_inventory_group: r42_student\nspec: \"2cpu/4gb/32gb\"\n", encoding="utf-8",
    )
    spec = ScenarioSpec.model_validate({
        "name": "deb_lab", "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf", "boxes": [{"template": "deb-box"}],
    })
    root = render_scenario(allocate(spec, load_catalog(fake_catalog)), spec, dest=tmp_path / "s")
    templates = root / "01_init_proxmox" / "templates"
    assert (templates / "debian").is_dir()
    assert not (templates / "ubuntu_noble").exists()       # no inert ubuntu template files
    main = _read(root, "main.yml")
    assert "debian/_main_debian.yml" in main
    assert "ubuntu_noble" not in main
    download = _read(root, "01_init_proxmox/templates/_main_download_cloudinit_files.yml")
    assert "debian-13-genericcloud" in download
    assert "noble" not in download                         # no unused ubuntu image downloaded


def test_render_refuses_existing_dir_then_overwrites(fake_catalog, valid_spec_dict, tmp_path):
    """A second render into the same dir must not silently clobber (overwrite gate)."""
    import pytest
    from r42playbooks.core.errors import ScenarioExistsError
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    catalog = load_catalog(fake_catalog)
    alloc = allocate(spec, catalog)
    dest = tmp_path / "scenarios"
    render_scenario(alloc, spec, dest=dest)
    with pytest.raises(ScenarioExistsError):
        render_scenario(alloc, spec, dest=dest)                 # default: refuse
    root = render_scenario(alloc, spec, dest=dest, overwrite=True)  # explicit: ok
    assert (root / "main.yml").is_file()


def test_render_is_deterministic(fake_catalog, valid_spec_dict, tmp_path):
    """Two renders of the same composition produce byte-identical class-B files."""
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    catalog = load_catalog(fake_catalog)
    alloc = allocate(spec, catalog)
    a = render_scenario(alloc, spec, dest=tmp_path / "a")
    b = render_scenario(alloc, spec, dest=tmp_path / "b")
    files_a = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    assert files_a == files_b
    for rel in files_a:
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), f"non-deterministic: {rel}"
