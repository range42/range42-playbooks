"""Post-allocation services wiring pass.

Resolves ``ScenarioSpec.services.apt`` after IP addresses are known:
  - injects ``software.configure.apt_mirror_client`` into every wired client box;
  - for mirror mode: auto-detects which suite flags to enable on the server
    by inspecting client image distro/codename, then merges them into the
    server's ``software.install.apt_mirror`` attachment params.

Pure: returns a new Allocation (never mutates the input).
"""

import dataclasses
from typing import TYPE_CHECKING

from r42playbooks.core.allocate import Allocation, AllocatedBox
from r42playbooks.core.errors import CompileError
from r42playbooks.core.models import Attachment

if TYPE_CHECKING:
    from r42playbooks.core.catalog import Catalog
    from r42playbooks.core.spec import ScenarioSpec

_APT_MIRROR_ROLE = "software.install.apt_mirror"
_APT_CLIENT_ROLE = "software.configure.apt_mirror_client"


def resolve_services(
    alloc: Allocation,
    spec: "ScenarioSpec",
    catalog: "Catalog",
) -> Allocation:
    """Apply services wiring to *alloc* and return the patched allocation.

    If ``spec.services`` is None (the common case) the original allocation is
    returned unchanged — zero overhead for scenarios that don't use services.

    :raises CompileError: the declared server box template is not in the scenario.
    """
    if spec.services is None or spec.services.apt is None:
        return alloc

    apt_svc = spec.services.apt
    boxes: list[AllocatedBox] = list(alloc.boxes)

    # Locate the server box (first match by box_template id).
    server_idx = next(
        (i for i, b in enumerate(boxes) if b.box_template == apt_svc.box),
        None,
    )
    if server_idx is None:
        raise CompileError(
            f"services.apt.box {apt_svc.box!r} is not present in the scenario — "
            f"add a box with template: {apt_svc.box!r} to the scenario spec"
        )
    server = boxes[server_idx]

    # Determine client box indices.
    if apt_svc.wire_to == "all":
        client_indices = [i for i in range(len(boxes)) if i != server_idx]
    else:
        wire_set = set(apt_svc.wire_to)
        client_indices = [
            i for i, b in enumerate(boxes)
            if b.box_template in wire_set and i != server_idx
        ]

    if not client_indices:
        return alloc

    # Mirror mode: derive suite flags from client images and patch server attachment.
    if apt_svc.mode == "mirror" and client_indices:
        needed: dict[str, bool] = {}
        for i in client_indices:
            img_def = catalog.images.get(boxes[i].image)
            if img_def is None:
                continue
            needed[f"apt_mirror_{img_def.distro}_{img_def.codename}"] = True

        if needed:
            new_atts = list(server.attachments)
            patched = False
            for j, att in enumerate(new_atts):
                if att.kind == "role" and att.catalog_ref == _APT_MIRROR_ROLE:
                    # Merge: spec-authored params take precedence over auto-detected flags.
                    merged = {**needed, **att.params}
                    new_atts[j] = att.model_copy(update={"params": merged})
                    patched = True
                    break
            if patched:
                boxes[server_idx] = dataclasses.replace(
                    server, attachments=tuple(new_atts)
                )

    # Build and inject client attachment using the resolved server IP.
    if client_indices:
        if apt_svc.mode == "proxy":
            client_params: dict = {
                "apt_mirror_enabled": True,
                "apt_proxy_url": f"http://{server.ip}:3142",
            }
        else:
            client_params = {
                "apt_mirror_enabled": True,
                "apt_mirror_airgapped": True,
                "apt_mirror_vm_ip": server.ip,
                "apt_mirror_http_port": 80,
            }

        client_att = Attachment(
            kind="role",
            catalog_ref=_APT_CLIENT_ROLE,
            params=client_params,
        )
        for i in client_indices:
            b = boxes[i]
            boxes[i] = dataclasses.replace(b, attachments=b.attachments + (client_att,))

    return dataclasses.replace(alloc, boxes=tuple(boxes))
