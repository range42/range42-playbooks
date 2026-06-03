"""Renderer (part 1, S5b): a composed ``Allocation`` -> ``scenarios/<name>/``.

Emits the **class-(B)** files (plan §4.1): boilerplate copied from
``_init_lab``/``demo_lab`` with placeholders filled — per-box ``stage_00`` clone
playbooks, ``stage_01`` plays that list catalog roles **by name** (§2), per-box
devkits, per-section reinstall scripts, the top-level scripts, the class-B
``templates/`` files, the vendored ``01_init_proxmox/`` template-creation subtree
(plan H3), and the originating ``scenario.r42.yml`` (reproducibility).

What this part does NOT emit (left to S5a, the class-(A) manifest-derived
artifacts): each section's ``_main.yml``, ``templates/*.j2``, and
``manifest/scenario_vms.json``. It also does NOT generate ``secrets/`` — that is
a deploy-time symlink (plan §4.2). And per the §7.2 richness decision it emits a
**uniform per-box** structure only (no group playbooks / group devkits /
``_testing`` / ``builder_*``).

Pure + deterministic: every write goes through ``core.io.atomic_write_text`` and
output depends only on the ``Allocation`` + ``ScenarioSpec`` (no clock/randomness).
"""

import os
import shutil
from pathlib import Path

from r42playbooks.core import render_assets as A
from r42playbooks.core.allocate import Allocation, AllocatedBox, manifest_json
from r42playbooks.core.io import atomic_write_text
from r42playbooks.core.models import Attachment
from r42playbooks.core.spec import ScenarioSpec, dumps_spec

# Role -> emitted section directory (plan §7.1 / H4; 'team' shares the student
# section). 'template' is never a placed box (templates come from TEMPLATE_TABLE).
SECTION_BY_ROLE: dict[str, str] = {
    "admin": "02_admin_infrastructure",
    "student": "03_student_infrastructure",
    "team": "03_student_infrastructure",
    "ctf": "04_ctf_infrastructure",
}
# Human label used in stage_00 task names (cosmetic, mirrors demo_lab wording).
SECTION_LABEL: dict[str, str] = {
    "admin": "ADMIN INFRASTRUCTURE INIT",
    "student": "TRAINEE INFRASTRUCTURE INIT",
    "team": "TEAM INFRASTRUCTURE INIT",
    "ctf": "CTF INFRASTRUCTURE INIT",
}

_DEFAULT_PROXMOX_NODE = "px-testing"
_NETMASK = "24"
_EXEC_MODE = 0o755

# The vendored boilerplate copied verbatim into every scenario (plan H3).
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _write(text: str, path: Path, *, executable: bool = False) -> Path:
    """Atomic write; ``chmod +x`` for generated shell scripts."""
    atomic_write_text(text, path)
    if executable:
        os.chmod(path, _EXEC_MODE)
    return path


def _ssh_host(vm_name: str) -> str:
    """M5 naming contract: SSH/inventory host id for a VM."""
    return f"r42.{vm_name}"


def _gateway(box: AllocatedBox) -> str:
    """Box subnet gateway, or the conventional ``.1`` host if the layout omits it."""
    if box.gateway:
        return box.gateway
    prefix = box.ip.rsplit(".", 1)[0]
    return f"{prefix}.1"


def _role_names(attachments: tuple[Attachment, ...]) -> list[str]:
    """Catalog role names a stage_01 play should list (dedup, order-preserving).

    ``container`` attachments are applied through the shared docker-compose role
    (plan §2); ``role``/``gamification`` reference their catalog name directly.
    """
    names: list[str] = []
    for att in attachments:
        name = "software.configure.docker-compose" if att.kind == "container" else att.catalog_ref
        if name not in names:
            names.append(name)
    return names


# --- per-box -----------------------------------------------------------------

def _render_box(box: AllocatedBox, section_dir: Path, scenario: str, proxmox_node: str) -> None:
    """Emit stage_00 + stage_01 + devkit for one VM."""
    label = SECTION_LABEL[box.role]

    stage00 = A.fill(
        A.STAGE00_CLONE,
        SECTION_LABEL=label, VM_NAME=box.vm_name, VM_ID=box.vm_id, IP=box.ip,
        TEMPLATE_NAME=box.template_name, NETMASK=_NETMASK,
        GATEWAY=_gateway(box), BRIDGE=box.bridge,
    )
    _write(stage00, section_dir / "stage_00" / f"{box.vm_name}.yml")

    roles = _role_names(box.attachments)
    if roles:
        role_lines = "\n".join(f"    - {name}" for name in roles)
        stage01 = A.fill(
            A.STAGE01_WITH_ROLES,
            VM_NAME=box.vm_name, SSH_HOST=_ssh_host(box.vm_name), ROLE_LINES=role_lines,
        )
    else:
        stage01 = A.fill(A.STAGE01_PLACEHOLDER, VM_NAME=box.vm_name)
    _write(stage01, section_dir / "stage_01" / f"{box.vm_name}.yml")

    _render_devkit(box, section_dir / "stage_01" / f"{box.vm_name}.devkit", scenario, proxmox_node)


def _render_devkit(box: AllocatedBox, devkit_dir: Path, scenario: str, proxmox_node: str) -> None:
    """Emit the per-box install / snapshot / revert scripts."""
    prefix = f"{scenario}.{box.vm_name}"
    scripts = {
        f"{prefix}.install.sh": A.fill(A.DEVKIT_INSTALL, VM_NAME=box.vm_name),
        f"{prefix}.snapshot.sh": A.fill(A.DEVKIT_SNAPSHOT, VM_NAME=box.vm_name, PROXMOX_NODE=proxmox_node),
        f"{prefix}.revert.sh": A.fill(A.DEVKIT_REVERT, VM_NAME=box.vm_name, PROXMOX_NODE=proxmox_node),
    }
    for name, body in scripts.items():
        _write(body, devkit_dir / name, executable=True)


# --- sections ----------------------------------------------------------------

def _sections_for(alloc: Allocation) -> dict[str, list[AllocatedBox]]:
    """Group placed boxes by their emitted section dir (sorted by section number)."""
    grouped: dict[str, list[AllocatedBox]] = {}
    for box in alloc.boxes:
        section = SECTION_BY_ROLE[box.role]
        grouped.setdefault(section, []).append(box)
    return {name: grouped[name] for name in sorted(grouped)}


def _render_sections(alloc: Allocation, root: Path, scenario: str, proxmox_node: str) -> list[str]:
    """Emit every section dir + its boxes + reinstall script. Returns section names."""
    sections = _sections_for(alloc)
    for section, boxes in sections.items():
        section_dir = root / section
        for box in boxes:
            _render_box(box, section_dir, scenario, proxmox_node)
        _write(A.fill(A.SECTION_REINSTALL, SECTION=section),
                section_dir / "_main.reinstall.sh", executable=True)
    return list(sections)


# --- top level ---------------------------------------------------------------

def _render_init_proxmox(root: Path) -> None:
    """Copy the vendored 01_init_proxmox/ template-creation subtree (plan H3)."""
    src = _ASSETS_DIR / "scenario" / "01_init_proxmox"
    shutil.copytree(src, root / "01_init_proxmox", dirs_exist_ok=True)


def _render_main_playbooks(root: Path, scenario: str, sections: list[str]) -> None:
    """Top-level main.yml / main_vms_only.yml import skeleton (only emitted sections)."""
    imports = "".join(f"- import_playbook: ./{s}/_main.yml\n" for s in sections)
    _write(A.fill(A.MAIN_HEADER, SCENARIO=scenario) + imports, root / "main.yml")
    _write(A.fill(A.MAIN_VMS_ONLY_HEADER, SCENARIO=scenario) + imports, root / "main_vms_only.yml")


def _render_top_level_scripts(root: Path, scenario: str) -> None:
    """Emit the activate + setup/delete/reset + inventory scripts (all executable)."""
    scripts = {
        "_activate.sh": A.ACTIVATE_SH,
        f"{scenario}.setup.sh": A.SETUP_SH,
        f"{scenario}.setup_vms_only.sh": A.SETUP_VMS_ONLY_SH,
        f"{scenario}.delete_all.sh": A.DELETE_ALL_SH,
        f"{scenario}.delete_vms_only.sh": A.DELETE_VMS_ONLY_SH,
        f"{scenario}.reset.setup.sh": A.RESET_SETUP_SH,
        f"{scenario}.reset.ssh_keys.sh": A.RESET_SSH_KEYS_SH,
        "devkit_ansible.show_ansible_inventory.to.text.sh": A.SHOW_INVENTORY_SH,
    }
    for name, body in scripts.items():
        _write(body, root / name, executable=True)


def _render_templates_class_b(root: Path, scenario: str) -> None:
    """Emit the class-B templates/ files (the .j2 inventory/ssh-config are S5a)."""
    _write(A.fill(A.ANSIBLE_VARS_YML, SCENARIO=scenario), root / "templates" / "ansible-vars.yml")
    _write(A.fill(A.VAULT_EXAMPLE_YML, SCENARIO=scenario), root / "templates" / "vault-example.yml")


def _render_readme(root: Path, spec: ScenarioSpec, alloc: Allocation) -> None:
    rows = ["| box | role | vm_id | ip |", "|---|---|---|---|"]
    rows += [f"| `{b.vm_name}` | {b.role} | {b.vm_id} | {b.ip} |" for b in alloc.boxes]
    _write(
        A.fill(
            A.README_MD, SCENARIO=spec.name, SUBNET_LAYOUT=spec.subnet_layout,
            NETWORK_POLICY=spec.network_policy, BOX_TABLE="\n".join(rows),
        ),
        root / "README.md",
    )


# --- class-A: manifest-derived artifacts (reflect THIS composition) ----------

def _render_manifest(alloc: Allocation, root: Path) -> None:
    """Write manifest/scenario_vms.json (vms[] + populated templates[], H1)."""
    _write(manifest_json(alloc), root / "manifest" / "scenario_vms.json")


def _inventory_groups(alloc: Allocation) -> str:
    """Build the per-composition inventory group blocks (8/10/12-space indent)."""
    groups: dict[str, list[str]] = {}
    for box in alloc.boxes:
        groups.setdefault(box.inventory_group, []).append(box.vm_name)
    blocks: list[str] = []
    for group, names in groups.items():
        lines = [f"        {group}:", "          hosts:"]
        lines += [f"            {_ssh_host(n)}:" for n in names]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def _render_inventory_j2(alloc: Allocation, root: Path) -> None:
    """templates/ansible-inventory.j2 — groups + member hosts from the manifest."""
    body = A.fill(A.INVENTORY_J2, GROUPS=_inventory_groups(alloc))
    _write(body, root / "templates" / "ansible-inventory.j2")


def _render_ssh_config_j2(alloc: Allocation, root: Path) -> None:
    """templates/ssh-config.j2 — one Host/Hostname block per VM (M5 naming)."""
    blocks = "\n\n".join(
        f"Host {_ssh_host(b.vm_name)}\n    Hostname {b.ip}" for b in alloc.boxes
    )
    _write(A.fill(A.SSHCONFIG_J2, VM_BLOCKS=blocks), root / "templates" / "ssh-config.j2")


def _stage00_import(box: AllocatedBox) -> str:
    """One section-_main.yml stage_00 import + its per-VM global_* overrides."""
    return A.fill(
        A.SECTION_MAIN_STAGE00,
        VM_NAME=box.vm_name, VM_ID=box.vm_id, IP=box.ip, TAG=box.role,
        DESCRIPTION=box.box_template, TEMPLATE_VM_ID=box.template_vm_id,
        TEMPLATE_NAME=box.template_name,
    )


def _render_section_mains(alloc: Allocation, root: Path) -> None:
    """Each section's _main.yml: stage_00 imports (+global_*) then stage_01 imports."""
    for section, boxes in _sections_for(alloc).items():
        parts = [A.fill(A.SECTION_MAIN_HEADER, SECTION=section), "#### STAGE 00 ####\n"]
        parts += [_stage00_import(b) for b in boxes]
        parts.append("\n#### STAGE 01 ####\n")
        parts += [f"- import_playbook: ./stage_01/{b.vm_name}.yml\n" for b in boxes]
        _write("\n".join(parts), root / section / "_main.yml")


def render_scenario(alloc: Allocation, spec: ScenarioSpec, *, dest: Path) -> Path:
    """Render *alloc*/*spec* into ``dest/<spec.name>/`` and return that path.

    Emits both class-(B) boilerplate (S5b) and the class-(A) manifest-derived
    artifacts (S5a: manifest, inventory/ssh-config templates, section _main.yml).
    Never creates ``secrets/`` (deploy-time symlink, §4.2). Deterministic.
    """
    root = Path(dest) / spec.name
    proxmox_node = spec.proxmox_node or _DEFAULT_PROXMOX_NODE

    # class B — verbatim-with-param boilerplate
    _render_init_proxmox(root)
    sections = _render_sections(alloc, root, spec.name, proxmox_node)
    _render_main_playbooks(root, spec.name, sections)
    _render_top_level_scripts(root, spec.name)
    _render_templates_class_b(root, spec.name)
    _render_readme(root, spec, alloc)
    _write(dumps_spec(spec), root / "scenario.r42.yml")

    # class A — generated from the allocation (reflect THIS composition)
    _render_manifest(alloc, root)
    _render_inventory_j2(alloc, root)
    _render_ssh_config_j2(alloc, root)
    _render_section_mains(alloc, root)
    return root
