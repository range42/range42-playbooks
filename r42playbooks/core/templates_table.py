"""The fixed set of Proxmox 9xxx clone templates (the 01_init_proxmox set).

These are NOT part of 05_topology_layer — they are the cloud-init template VMs
created by ``01_init_proxmox/templates/ubuntu_noble/*`` and are the byte-level
reference taken from the demo_lab ``manifest/scenario_vms.json`` ``templates[]``.

A composed box selects one template by matching its catalog ``spec`` (e.g.
``4cpu/8gb/64gb``); the generated manifest lists the whole table so each
``stage_00`` clone can resolve ``global_template_vm_id`` (plan §7.1 / H1 / H2).
"""

from dataclasses import dataclass

from r42playbooks.core.errors import ValidationError


@dataclass(frozen=True)
class ProxmoxTemplate:
    """One 9xxx clone-source template VM.

    ``os`` is the base image family (``ubuntu``/``debian``/``fedora``); it must
    match the box's declared ``os`` so the cloned image and the role's runtime
    ``ansible_facts.distribution`` dispatch agree. Defaults to ``ubuntu`` — the
    only image set ``01_init_proxmox`` currently creates.
    """

    vm_id: int
    vm_name: str
    spec: str
    ip: str
    bridge: str
    os: str = "ubuntu"


# Verbatim from scenarios/demo_lab/manifest/scenario_vms.json -> templates[].
TEMPLATE_TABLE: tuple[ProxmoxTemplate, ...] = (
    ProxmoxTemplate(9901, "template-vm-nano", "1cpu/1gb/16gb", "192.168.140.201", "vmbr140"),
    ProxmoxTemplate(9211, "template-vm-micro-01-2g-24g", "1cpu/2gb/24gb", "192.168.140.211", "vmbr140"),
    ProxmoxTemplate(9212, "template-vm-micro-02-2g-24g", "1cpu/2gb/24gb", "192.168.140.212", "vmbr140"),
    ProxmoxTemplate(9221, "template-vm-small-01-4g-32g", "1cpu/4gb/32gb", "192.168.140.221", "vmbr140"),
    ProxmoxTemplate(9222, "template-vm-small-02-4g-32g", "1cpu/4gb/32gb", "192.168.140.222", "vmbr140"),
    ProxmoxTemplate(9224, "template-vm-small-04-4g-32g", "1cpu/4gb/32gb", "192.168.140.224", "vmbr140"),
    ProxmoxTemplate(9232, "template-vm-medium-02-8g-64g", "2cpu/8gb/64gb", "192.168.140.232", "vmbr140"),
    ProxmoxTemplate(9234, "template-vm-medium-04-8g-64g", "4cpu/8gb/64gb", "192.168.140.234", "vmbr140"),
    ProxmoxTemplate(9236, "template-vm-medium-06-8g-64g", "6cpu/8gb/64gb", "192.168.140.236", "vmbr140"),
    ProxmoxTemplate(9244, "template-vm-large-04-8g-64g", "4cpu/8gb/64gb", "192.168.140.244", "vmbr140"),
    ProxmoxTemplate(9246, "template-vm-large-06-8g-64g", "6cpu/8gb/64gb", "192.168.140.246", "vmbr140"),
    ProxmoxTemplate(9248, "template-vm-large-08-8g-64g", "8cpu/8gb/64gb", "192.168.140.248", "vmbr140"),
    # --- debian (trixie / 13) — created by 01_init_proxmox/templates/debian/. Two
    # sizes cover every current box spec via the ram/disk fallback (4gb/32gb and
    # 8gb/64gb). 93xx band + .140.12x/.13x IPs avoid the ubuntu rows above.
    ProxmoxTemplate(9321, "template-vm-debian-small", "1cpu/4gb/32gb", "192.168.140.121", "vmbr140", os="debian"),
    ProxmoxTemplate(9331, "template-vm-debian-medium", "2cpu/8gb/64gb", "192.168.140.131", "vmbr140", os="debian"),
)


def _ram_disk(spec: str) -> tuple[str, ...]:
    """The ram/disk suffix of a ``cpu/ram/disk`` spec (the template's baked size).

    A Proxmox template bakes only the disk image; cpu (and ram) are applied at
    clone time via cloud-init / ``qm set``. So when no template matches the full
    ``cpu/ram/disk`` spec, a template with the same ``ram/disk`` is a valid clone
    source (e.g. a box wanting ``2cpu/4gb/32gb`` clones the ``…/4gb/32gb`` image).
    """
    return tuple(spec.split("/")[1:])


def select_template(
    spec: str, *, os: str = "ubuntu", override_vm_id: int | None = None
) -> ProxmoxTemplate:
    """Resolve a box ``(os, spec)`` to a clone template (plan §7.1 / H2).

    With ``override_vm_id`` the box pins an explicit template id (any OS).
    Otherwise selection is scoped to the box's ``os`` image set, then an
    **exact** ``cpu/ram/disk`` match wins (lowest vm_id for determinism); failing
    that, a template with the same ``ram/disk`` is used (cpu/ram are clone-time
    settings — the image's baked dimension is the disk, see :func:`_ram_disk`).

    :raises ValidationError: if the override id is unknown, the OS has no image
        set yet (e.g. debian/fedora — only ``ubuntu`` is created today), or the
        spec matches no template for that OS.
    """
    if override_vm_id is not None:
        for tmpl in TEMPLATE_TABLE:
            if tmpl.vm_id == override_vm_id:
                return tmpl
        raise ValidationError(f"template_vm_id override not in table: {override_vm_id}")

    pool = [t for t in TEMPLATE_TABLE if t.os == os]
    if not pool:
        raise ValidationError(
            f"no Proxmox template image for os {os!r} "
            f"(only {sorted({t.os for t in TEMPLATE_TABLE})} are created today)"
        )

    exact = [t for t in pool if t.spec == spec]
    if exact:
        return min(exact, key=lambda t: t.vm_id)

    want = _ram_disk(spec)
    approx = [t for t in pool if _ram_disk(t.spec) == want]
    if approx:
        return min(approx, key=lambda t: t.vm_id)

    raise ValidationError(f"no {os} Proxmox template matches box spec {spec!r} (cpu/ram/disk or ram/disk)")
