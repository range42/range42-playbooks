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
from collections.abc import Mapping
from pathlib import Path

import yaml

from r42playbooks.core import render_assets as A
from r42playbooks.core.allocate import Allocation, AllocatedBox, manifest_json
from r42playbooks.core.catalog import Catalog
from r42playbooks.core.errors import ScenarioExistsError, ValidationError
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

# 01_init_proxmox uses the _init_lab STAGED layout, keyed by versioned image name
# (``<distro>_<codename>``), which IS the templates/<image>/ dir:
#   _main.yml                         -> imports stage_00 + stage_01
#   stage_00-download_cloudinit_files/ cloudinit_<image>.yml  (rendered from catalog)
#   stage_01-create_templates/        templates/<image>/<main> + per-size files
# A scenario only downloads/creates the image sets its composition uses
# (image-selective): the two stage _main.yml are generated with just those
# imports, and only the matching cloudinit_<image>.yml + templates/<image>/ are
# emitted. Per image: "main" is the stage_01 orchestrator (vendored asset).
# The download play (stage_00) is rendered from the catalog's cloud_image spec —
# NOT copied from a static asset file.
_IMAGE_SETS: dict[str, dict] = {
    "ubuntu_noble": {"main": "_main_ubuntu_noble.yml"},
    "debian_trixie": {"main": "_main_debian_trixie.yml"},
}
_INIT_MAIN_IMPORT = "- import_playbook: ./01_init_proxmox/_main.yml"
_DOWNLOAD_DIR = "stage_00-download_cloudinit_files"
_TEMPLATES_STAGE = "stage_01-create_templates"

# The vendored boilerplate copied verbatim into every scenario (plan H3).
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _parse_spec(spec: str) -> tuple[int, int, str]:
    """Parse ``'Xcpu/Ygb/Zgb'`` into ``(cores, memory_mb, disk_size)``.

    ``memory_mb`` is ``Y * 1024``; ``disk_size`` is ``'Zg'`` (qemu-img / Proxmox format).
    """
    parts = spec.split("/")
    cores = int(parts[0].replace("cpu", ""))
    ram_mb = int(parts[1].replace("gb", "")) * 1024
    disk = parts[2].replace("gb", "g")
    return cores, ram_mb, disk


def _write(text: str, path: Path, *, executable: bool = False) -> Path:
    """Atomic write; ``chmod +x`` for generated shell scripts."""
    atomic_write_text(text, path)
    if executable:
        os.chmod(path, _EXEC_MODE)
    return path


def _ssh_host(vm_name: str) -> str:
    """M5 naming contract: SSH/inventory host id for a VM."""
    return f"r42.{vm_name}"


def _file_prefix(scenario: str) -> str:
    """Filename-safe scenario prefix (SCENARIO_NAME_RE permits '/' for nesting).

    The directory tree keeps the full ``scenario`` name (so ``ctf/web1`` nests),
    but per-file prefixes use only the leaf so a slash never spawns extra dirs in
    a script/devkit filename (e.g. ``ctf/web1.setup.sh``).
    """
    return scenario.rsplit("/", 1)[-1]


def _vars_block(box_vars: Mapping[str, object]) -> str:
    """Render a box's free-form vars as an indented ``vars:`` block (or '')."""
    if not box_vars:
        return ""
    dumped = yaml.safe_dump(dict(box_vars), default_flow_style=False, sort_keys=True)
    indented = "\n".join("    " + line for line in dumped.rstrip("\n").splitlines())
    return f"  vars:\n{indented}\n"


def _gateway(box: AllocatedBox) -> str:
    """Box subnet gateway, or the conventional ``.1`` host if the layout omits it."""
    if box.gateway:
        return box.gateway
    prefix = box.ip.rsplit(".", 1)[0]
    return f"{prefix}.1"


def _attachment_role(att: Attachment) -> str:
    """The catalog role an attachment applies (container -> shared docker-compose)."""
    return "software.configure.docker-compose" if att.kind == "container" else att.catalog_ref


def _attachment_vars(att: Attachment) -> dict:
    """The vars a stage_01 play passes to the attachment's role.

    role/gamification → the attachment's ``params`` verbatim. container → docker
    wiring derived from the stack path (env-based project dir, labels), overlaid
    with any explicit ``params`` (mirrors the demo_lab / bundle docker plays).
    """
    if att.kind != "container":
        return dict(att.params)
    name = att.catalog_ref.rsplit("/", 1)[-1]
    wiring = {
        "LABEL_PROJECT_TYPE": "CTF",
        "LABEL_PROJET_NAME": name,
        "LOCAL__PROJECT_DIR": "{{ lookup('env', 'RANGE42_INVENTORY__DOCKER__CTF') }}/" + att.catalog_ref + "/",
        "REMOTE_PROJECT_DIR": f"/tmp/deploy-{name}",
        "OPERATOR_USER": "{{ default_admin_vm_ci_user }}",
    }
    wiring.update(att.params)
    return wiring


def _render_stage01(box: AllocatedBox) -> str:
    """One play per attachment (role + its params), or a no-op placeholder."""
    ssh = _ssh_host(box.vm_name)
    box_vars = dict(box.box_vars)
    plays = [
        A.fill(
            A.STAGE01_PLAY, VM_NAME=box.vm_name, SSH_HOST=ssh,
            ROLE=_attachment_role(att),
            VARS_BLOCK=_vars_block({**box_vars, **_attachment_vars(att)}),
        )
        for att in box.attachments
    ]
    if not plays:
        return A.fill(A.STAGE01_PLACEHOLDER, VM_NAME=box.vm_name, SSH_HOST=ssh,
                      VARS_BLOCK=_vars_block(box_vars))
    return A.fill(A.STAGE01_HEADER, VM_NAME=box.vm_name) + "\n" + "\n".join(plays)


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

    _write(_render_stage01(box), section_dir / "stage_01" / f"{box.vm_name}.yml")

    _render_devkit(box, section_dir / "stage_01" / f"{box.vm_name}.devkit", scenario, proxmox_node)


def _render_devkit(box: AllocatedBox, devkit_dir: Path, scenario: str, proxmox_node: str) -> None:
    """Emit the per-box install / snapshot / revert scripts."""
    prefix = f"{_file_prefix(scenario)}.{box.vm_name}"
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

def _copy_file(src: Path, dst: Path) -> None:
    """Copy a single asset file, creating parent dirs."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _render_init_proxmox(root: Path, used_images: list[str], catalog: Catalog) -> None:
    """Emit 01_init_proxmox (staged) for ONLY the image sets the composition uses.

    Mirrors the ``_init_lab`` layout: a top ``_main.yml`` imports the download and
    template-creation stages, each of which imports only the used images. A
    ubuntu_noble-only lab never carries debian_trixie files, and vice versa (H3).

    The stage_00 ``cloudinit_<image>.yml`` is rendered from the catalog's
    ``01_image_layer/<image>.cloud_image`` spec instead of being copied from a
    static asset — keeping download coordinates in the catalog, not the playbooks.
    """
    asset = _ASSETS_DIR / "scenario" / "01_init_proxmox"
    init = root / "01_init_proxmox"
    used = [img for img in used_images if img in _IMAGE_SETS]

    # static top orchestrator (imports both stages) + a clean reinstall helper
    _copy_file(asset / "_main.yml", init / "_main.yml")
    _write(A.INIT_REINSTALL_SH, init / "_main.reinstall.sh", executable=True)

    # stage_00: download base images — one cloudinit_<image>.yml rendered per used image
    dl = init / _DOWNLOAD_DIR
    cloudinit_filename = "cloudinit_{image}.yml"
    dl_imports = "".join(
        f"- import_playbook: ./{cloudinit_filename.format(image=i)}\n" for i in used
    )
    _write(A.fill(A.STAGE_DOWNLOAD_MAIN, IMPORTS=dl_imports), dl / "_main.yml")
    for image_id in used:
        img_def = catalog.images.get(image_id)
        if img_def is None or img_def.cloud_image is None:
            raise ValidationError(
                f"image {image_id!r} has no cloud_image in the catalog's 01_image_layer "
                f"— add a cloud_image: {{url: ..., filename: ...}} block to its image.yml"
            )
        ci = img_def.cloud_image
        rendered = A.fill(
            A.CLOUDINIT_DOWNLOAD_YML,
            IMAGE_ID=image_id,
            ISO_URL=ci.url,
            ISO_FILE_NAME=ci.filename,
        )
        _write(rendered, dl / cloudinit_filename.format(image=image_id))

    # stage_01: create templates — rendered per-VM files + copied static helpers
    stage = init / _TEMPLATES_STAGE
    tpl_imports = "".join(
        f"- import_playbook: ./templates/{i}/{_IMAGE_SETS[i]['main']}\n" for i in used
    )
    _write(A.fill(A.STAGE_TEMPLATES_MAIN, IMPORTS=tpl_imports), stage / "_main.yml")
    for image_id in used:
        img_def = catalog.images.get(image_id)
        if img_def is None or not img_def.proxmox_templates:
            raise ValidationError(
                f"image {image_id!r} has no proxmox_templates in the catalog's 01_image_layer "
                f"— add a proxmox_templates list to its image.yml"
            )
        if img_def.cloud_image is None:
            raise ValidationError(
                f"image {image_id!r} has no cloud_image in the catalog's 01_image_layer"
            )
        img_dir = stage / "templates" / image_id
        image_path = f"/var/lib/vz/template/iso/{img_def.cloud_image.filename}"

        # render one play per template VM
        tpl_imports_img = ""
        for tpl in img_def.proxmox_templates:
            cores, memory_mb, disk_size = _parse_spec(tpl.spec)
            ip_prefix = ".".join(tpl.ip.split(".")[:3])
            rendered = A.fill(
                A.TEMPLATE_VM_YML,
                IMAGE_ID=image_id,
                VM_ID=str(tpl.vm_id),
                VM_NAME=tpl.vm_name,
                VM_CORES=str(cores),
                VM_MEMORY_MB=str(memory_mb),
                VM_NET_BRIDGE=tpl.bridge,
                VM_DISK_SIZE=disk_size,
                CLOUDINIT_IMAGE_PATH=image_path,
                VM_CI_IP=tpl.ip,
                VM_CI_IP_GW=f"{ip_prefix}.1",
            )
            filename = f"{tpl.vm_name}.yml"
            _write(rendered, img_dir / filename)
            tpl_imports_img += f"- import_playbook: ./{filename}\n"

        # render _apply_apt_proxy.yml with this image's vm_id list
        id_list = "".join(
            f"      - {t.vm_id}  # {t.vm_name}\n" for t in img_def.proxmox_templates
        )
        _write(A.fill(A.APPLY_APT_PROXY_YML, IMAGE_ID=image_id, VM_ID_LIST=id_list),
               img_dir / "_apply_apt_proxy.yml")

        # render _main_<image>.yml
        _write(
            A.fill(A.MAIN_IMAGE_YML, IMAGE_ID=image_id, TEMPLATE_IMPORTS=tpl_imports_img),
            img_dir / _IMAGE_SETS[image_id]["main"],
        )

        # copy the two static helpers (read from manifest / pure Jinja2 — no hardcoded ids)
        for static_file in ("_update_templates.yml", "range42-template-bootstrap.yaml.j2"):
            _copy_file(asset / _TEMPLATES_STAGE / "templates" / image_id / static_file,
                       img_dir / static_file)


def _render_main_playbooks(root: Path, scenario: str, sections: list[str]) -> None:
    """Top-level main.yml / main_vms_only.yml (only emitted sections)."""
    section_imports = "".join(f"- import_playbook: ./{s}/_main.yml\n" for s in sections)
    header = A.fill(A.MAIN_HEADER, SCENARIO=scenario)
    # main.yml: create the template images (01_init_proxmox) then deploy the sections.
    _write(header + _INIT_MAIN_IMPORT + "\n\n" + section_imports, root / "main.yml")
    # main_vms_only.yml: skip 01_init_proxmox (templates already exist).
    _write(A.fill(A.MAIN_VMS_ONLY_HEADER, SCENARIO=scenario) + section_imports,
           root / "main_vms_only.yml")


def _render_top_level_scripts(root: Path, scenario: str) -> None:
    """Emit the activate + setup/delete/reset + inventory scripts (all executable)."""
    prefix = _file_prefix(scenario)
    scripts = {
        "_activate.sh": A.ACTIVATE_SH,
        f"{prefix}.setup.sh": A.SETUP_SH,
        f"{prefix}.setup_vms_only.sh": A.SETUP_VMS_ONLY_SH,
        f"{prefix}.delete_all.sh": A.DELETE_ALL_SH,
        f"{prefix}.delete_vms_only.sh": A.DELETE_VMS_ONLY_SH,
        f"{prefix}.reset.setup.sh": A.RESET_SETUP_SH,
        f"{prefix}.reset.ssh_keys.sh": A.RESET_SSH_KEYS_SH,
        "devkit_ansible.show_ansible_inventory.to.text.sh": A.SHOW_INVENTORY_SH,
    }
    for name, body in scripts.items():
        _write(body, root / name, executable=True)


def _render_templates_class_b(root: Path, scenario: str) -> None:
    """Emit the class-B templates/ files (the .j2 inventory/ssh-config are S5a)."""
    _write(A.fill(A.ANSIBLE_VARS_YML, SCENARIO=scenario), root / "templates" / "ansible-vars.yml")
    _write(A.fill(A.VAULT_EXAMPLE_YML, SCENARIO=scenario), root / "templates" / "vault-example.yml")


def _render_readme(root: Path, spec: ScenarioSpec, alloc: Allocation) -> None:
    rows = ["| box | role | image | vm_id | ip |", "|---|---|---|---|---|"]
    rows += [f"| `{b.vm_name}` | {b.role} | {b.image} | {b.vm_id} | {b.ip} |" for b in alloc.boxes]
    _write(
        A.fill(
            A.README_MD, SCENARIO=spec.name, SUBNET_LAYOUT=spec.subnet_layout,
            BOX_TABLE="\n".join(rows),
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


def render_scenario(
    alloc: Allocation, spec: ScenarioSpec, *, catalog: Catalog, dest: Path, overwrite: bool = False
) -> Path:
    """Render *alloc*/*spec* into ``dest/<spec.name>/`` and return that path.

    Emits both class-(B) boilerplate (S5b) and the class-(A) manifest-derived
    artifacts (S5a: manifest, inventory/ssh-config templates, section _main.yml).
    Never creates ``secrets/`` (deploy-time symlink, §4.2). Deterministic.

    :param catalog: the loaded catalog; its ``01_image_layer`` cloud_image specs
        are used to render ``stage_00-download_cloudinit_files/<image>.yml``.
    :param overwrite: if False (default) and ``dest/<name>/`` already exists,
        raise :class:`ScenarioExistsError` rather than silently clobbering it.
    :raises ScenarioExistsError: target exists and ``overwrite`` is False.
    :raises ValidationError: if a used image has no cloud_image in the catalog.
    """
    root = Path(dest) / spec.name
    if root.exists() and not overwrite:
        raise ScenarioExistsError(f"scenario already exists at {root}")
    proxmox_node = spec.proxmox_node or _DEFAULT_PROXMOX_NODE

    # class B — verbatim-with-param boilerplate
    used_images = sorted({box.image for box in alloc.boxes})
    _render_init_proxmox(root, used_images, catalog)
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
