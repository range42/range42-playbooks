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
    """One 9xxx clone-source template VM."""

    vm_id: int
    vm_name: str
    spec: str
    ip: str
    bridge: str


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
)


def select_template(spec: str, *, override_vm_id: int | None = None) -> ProxmoxTemplate:
    """Resolve a box ``spec`` to a clone template (plan §7.1 / H2).

    With ``override_vm_id`` the box pins an explicit template id. Otherwise the
    spec may match several templates (e.g. ``4cpu/8gb/64gb`` -> 9234 and 9244);
    the **lowest** matching vm_id is chosen for determinism.

    :raises ValidationError: if the override id or spec matches no template.
    """
    if override_vm_id is not None:
        for tmpl in TEMPLATE_TABLE:
            if tmpl.vm_id == override_vm_id:
                return tmpl
        raise ValidationError(f"template_vm_id override not in table: {override_vm_id}")
    matches = [t for t in TEMPLATE_TABLE if t.spec == spec]
    if not matches:
        raise ValidationError(f"no Proxmox template matches box spec {spec!r}")
    return min(matches, key=lambda t: t.vm_id)
