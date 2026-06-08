"""Tests for compiler/services.py — post-allocation apt services wiring pass."""

import dataclasses
from types import MappingProxyType

import pytest

from r42playbooks.core.allocate import Allocation, AllocatedBox
from r42playbooks.core.catalog import Catalog
from r42playbooks.core.catalog_models import ImageDef
from r42playbooks.core.compiler.services import resolve_services
from r42playbooks.core.errors import CompileError
from r42playbooks.core.models import Attachment, Subnet
from r42playbooks.core.spec import ScenarioSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _box(
    *,
    vm_id: int,
    vm_name: str,
    ip: str,
    box_template: str,
    image: str,
    attachments: tuple[Attachment, ...] = (),
) -> AllocatedBox:
    return AllocatedBox(
        vm_id=vm_id,
        vm_name=vm_name,
        ip=ip,
        bridge="vmbr142",
        subnet_name="admin",
        section="02_admin_infrastructure",
        label="ADMIN INFRASTRUCTURE INIT",
        gateway="192.168.142.1",
        inventory_group="r42_admin_group",
        box_template=box_template,
        image=image,
        template_vm_id=9221,
        template_name="template-vm-debian-trixie-small",
        attachments=attachments,
        box_vars=MappingProxyType({}),
    )


def _alloc(*boxes: AllocatedBox) -> Allocation:
    return Allocation(
        scenario="test_lab",
        description="",
        boxes=tuple(boxes),
        templates=(),
        subnets=(
            Subnet(
                name="admin",
                cidr="192.168.142.0/24",
                bridge="vmbr142",
                gateway="192.168.142.1",
            ),
        ),
    )


def _spec_dict(*box_templates: str, services: dict | None = None) -> dict:
    base: dict = {
        "schema_version": 1,
        "name": "test_lab",
        "subnet_layout": "default-3zone",
        "boxes": [{"template": t, "subnet": "admin"} for t in box_templates],
    }
    if services is not None:
        base["services"] = services
    return base


def _catalog_with_images(**images: tuple[str, str]) -> Catalog:
    """Build a minimal Catalog with ImageDef entries.

    images: keyword mapping of image_id → (distro, codename).
    """
    cat = Catalog()
    for image_id, (distro, codename) in images.items():
        cat.images[image_id] = ImageDef(
            id=image_id,
            api_version=1,
            distro=distro,
            codename=codename,
            description=f"{distro} {codename}",
            proxmox_templates=[],
        )
    return cat


# ---------------------------------------------------------------------------
# Passthrough when no services declared
# ---------------------------------------------------------------------------

def test_no_services_returns_alloc_unchanged():
    server = _box(vm_id=1010, vm_name="admin-apt-cache-00", ip="192.168.142.10",
                  box_template="apt-cache", image="debian_trixie")
    alloc = _alloc(server)
    spec = ScenarioSpec.model_validate(_spec_dict("apt-cache"))

    result = resolve_services(alloc, spec, Catalog())

    assert result is alloc  # same object — no copy made


def test_services_apt_none_returns_alloc_unchanged():
    server = _box(vm_id=1010, vm_name="admin-apt-cache-00", ip="192.168.142.10",
                  box_template="apt-cache", image="debian_trixie")
    alloc = _alloc(server)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", services={"apt": None})
    )

    result = resolve_services(alloc, spec, Catalog())

    assert result is alloc


# ---------------------------------------------------------------------------
# Proxy mode — wire_to: all
# ---------------------------------------------------------------------------

def test_proxy_mode_injects_client_attachment():
    server = _box(vm_id=1010, vm_name="admin-apt-cache-00", ip="192.168.142.10",
                  box_template="apt-cache", image="debian_trixie")
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    alloc = _alloc(server, client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", "debian-jump",
                   services={"apt": {"box": "apt-cache", "mode": "proxy"}})
    )

    result = resolve_services(alloc, spec, Catalog())

    client_result = result.boxes[1]
    assert len(client_result.attachments) == 1
    att = client_result.attachments[0]
    assert att.catalog_ref == "software.configure.apt_mirror_client"
    assert att.params["apt_mirror_enabled"] is True
    assert att.params["apt_proxy_url"] == "http://192.168.142.10:3142"


def test_proxy_mode_server_box_unchanged():
    server = _box(vm_id=1010, vm_name="admin-apt-cache-00", ip="192.168.142.10",
                  box_template="apt-cache", image="debian_trixie")
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    alloc = _alloc(server, client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", "debian-jump",
                   services={"apt": {"box": "apt-cache", "mode": "proxy"}})
    )

    result = resolve_services(alloc, spec, Catalog())

    assert result.boxes[0].attachments == server.attachments


def test_proxy_mode_wire_to_subset():
    server = _box(vm_id=1010, vm_name="admin-apt-cache-00", ip="192.168.142.10",
                  box_template="apt-cache", image="debian_trixie")
    client_a = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                    box_template="debian-jump", image="debian_trixie")
    client_b = _box(vm_id=1030, vm_name="admin-ubuntu-jump-00", ip="192.168.142.30",
                    box_template="ubuntu-jump", image="ubuntu_resolute")
    alloc = _alloc(server, client_a, client_b)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", "debian-jump", "ubuntu-jump",
                   services={"apt": {"box": "apt-cache", "mode": "proxy",
                                     "wire_to": ["debian-jump"]}})
    )

    result = resolve_services(alloc, spec, Catalog())

    assert any(a.catalog_ref == "software.configure.apt_mirror_client"
               for a in result.boxes[1].attachments)
    assert not any(a.catalog_ref == "software.configure.apt_mirror_client"
                   for a in result.boxes[2].attachments)


def test_proxy_mode_wire_to_all_skips_server():
    server = _box(vm_id=1010, vm_name="admin-apt-cache-00", ip="192.168.142.10",
                  box_template="apt-cache", image="debian_trixie")
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    alloc = _alloc(server, client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", "debian-jump",
                   services={"apt": {"box": "apt-cache", "wire_to": "all"}})
    )

    result = resolve_services(alloc, spec, Catalog())

    # Server must never receive the client attachment.
    assert not any(a.catalog_ref == "software.configure.apt_mirror_client"
                   for a in result.boxes[0].attachments)


# ---------------------------------------------------------------------------
# Mirror mode — suite auto-detection
# ---------------------------------------------------------------------------

def test_mirror_mode_patches_server_suite_flags():
    mirror_att = Attachment(
        kind="role",
        catalog_ref="software.install.apt_mirror",
        params={"apt_mirror_http_port": 80},
    )
    server = _box(vm_id=1010, vm_name="admin-apt-mirror-00", ip="192.168.142.10",
                  box_template="apt-mirror", image="debian_trixie",
                  attachments=(mirror_att,))
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    alloc = _alloc(server, client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-mirror", "debian-jump",
                   services={"apt": {"box": "apt-mirror", "mode": "mirror"}})
    )
    catalog = _catalog_with_images(debian_trixie=("debian", "trixie"))

    result = resolve_services(alloc, spec, catalog)

    server_atts = {a.catalog_ref: a for a in result.boxes[0].attachments}
    params = server_atts["software.install.apt_mirror"].params
    assert params.get("apt_mirror_debian_trixie") is True
    assert params.get("apt_mirror_http_port") == 80  # original param preserved


def test_mirror_mode_multiple_distros():
    mirror_att = Attachment(kind="role", catalog_ref="software.install.apt_mirror", params={})
    server = _box(vm_id=1010, vm_name="admin-apt-mirror-00", ip="192.168.142.10",
                  box_template="apt-mirror", image="debian_trixie",
                  attachments=(mirror_att,))
    deb_client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                      box_template="debian-jump", image="debian_trixie")
    ubuntu_client = _box(vm_id=1030, vm_name="admin-ubuntu-jump-00", ip="192.168.142.30",
                         box_template="ubuntu-jump", image="ubuntu_noble")
    alloc = _alloc(server, deb_client, ubuntu_client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-mirror", "debian-jump", "ubuntu-jump",
                   services={"apt": {"box": "apt-mirror", "mode": "mirror"}})
    )
    catalog = _catalog_with_images(
        debian_trixie=("debian", "trixie"),
        ubuntu_noble=("ubuntu", "noble"),
    )

    result = resolve_services(alloc, spec, catalog)

    server_atts = {a.catalog_ref: a for a in result.boxes[0].attachments}
    params = server_atts["software.install.apt_mirror"].params
    assert params.get("apt_mirror_debian_trixie") is True
    assert params.get("apt_mirror_ubuntu_noble") is True
    assert "apt_mirror_ubuntu_jammy" not in params  # jammy not in scenario


def test_mirror_mode_authored_params_override_auto_flags():
    mirror_att = Attachment(
        kind="role",
        catalog_ref="software.install.apt_mirror",
        # Author explicitly disables the flag even though a debian client is wired.
        params={"apt_mirror_debian_trixie": False},
    )
    server = _box(vm_id=1010, vm_name="admin-apt-mirror-00", ip="192.168.142.10",
                  box_template="apt-mirror", image="debian_trixie",
                  attachments=(mirror_att,))
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    alloc = _alloc(server, client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-mirror", "debian-jump",
                   services={"apt": {"box": "apt-mirror", "mode": "mirror"}})
    )
    catalog = _catalog_with_images(debian_trixie=("debian", "trixie"))

    result = resolve_services(alloc, spec, catalog)

    server_atts = {a.catalog_ref: a for a in result.boxes[0].attachments}
    assert server_atts["software.install.apt_mirror"].params["apt_mirror_debian_trixie"] is False


def test_mirror_mode_client_attachment_airgapped():
    mirror_att = Attachment(kind="role", catalog_ref="software.install.apt_mirror", params={})
    server = _box(vm_id=1010, vm_name="admin-apt-mirror-00", ip="192.168.142.10",
                  box_template="apt-mirror", image="debian_trixie",
                  attachments=(mirror_att,))
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    alloc = _alloc(server, client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-mirror", "debian-jump",
                   services={"apt": {"box": "apt-mirror", "mode": "mirror"}})
    )
    catalog = _catalog_with_images(debian_trixie=("debian", "trixie"))

    result = resolve_services(alloc, spec, catalog)

    client_atts = {a.catalog_ref: a for a in result.boxes[1].attachments}
    params = client_atts["software.configure.apt_mirror_client"].params
    assert params["apt_mirror_enabled"] is True
    assert params["apt_mirror_airgapped"] is True
    assert params["apt_mirror_vm_ip"] == "192.168.142.10"
    assert params["apt_mirror_http_port"] == 80


def test_mirror_mode_no_suite_flags_when_image_unknown():
    mirror_att = Attachment(kind="role", catalog_ref="software.install.apt_mirror", params={})
    server = _box(vm_id=1010, vm_name="admin-apt-mirror-00", ip="192.168.142.10",
                  box_template="apt-mirror", image="debian_trixie",
                  attachments=(mirror_att,))
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    alloc = _alloc(server, client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-mirror", "debian-jump",
                   services={"apt": {"box": "apt-mirror", "mode": "mirror"}})
    )
    # Empty catalog — image lookup will return None, so no suite flags set.
    result = resolve_services(alloc, spec, Catalog())

    server_atts = {a.catalog_ref: a for a in result.boxes[0].attachments}
    params = server_atts["software.install.apt_mirror"].params
    assert "apt_mirror_debian_trixie" not in params


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_missing_server_box_raises_compile_error():
    client = _box(vm_id=1020, vm_name="admin-debian-jump-00", ip="192.168.142.20",
                  box_template="debian-jump", image="debian_trixie")
    # Allocation has only debian-jump but spec declares services.apt.box = apt-cache.
    alloc = _alloc(client)
    spec = ScenarioSpec.model_validate(
        _spec_dict("debian-jump", "apt-cache",
                   services={"apt": {"box": "apt-cache", "mode": "proxy"}})
    )

    with pytest.raises(CompileError, match="apt-cache"):
        resolve_services(alloc, spec, Catalog())


# ---------------------------------------------------------------------------
# Spec schema validation
# ---------------------------------------------------------------------------

def test_spec_services_round_trips_yaml():
    import yaml
    from r42playbooks.core.spec import dumps_spec

    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", "debian-jump",
                   services={"apt": {"box": "apt-cache", "mode": "proxy", "wire_to": "all"}})
    )
    yaml_out = dumps_spec(spec)
    reloaded = ScenarioSpec.model_validate(yaml.safe_load(yaml_out))
    assert reloaded.services == spec.services


def test_spec_services_mode_default_is_proxy():
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", services={"apt": {"box": "apt-cache"}})
    )
    assert spec.services.apt.mode == "proxy"


def test_spec_services_wire_to_default_is_all():
    spec = ScenarioSpec.model_validate(
        _spec_dict("apt-cache", services={"apt": {"box": "apt-cache"}})
    )
    assert spec.services.apt.wire_to == "all"


def test_spec_services_unknown_field_rejected():
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(
            _spec_dict("apt-cache",
                       services={"apt": {"box": "apt-cache", "unknown_field": "boom"}})
        )


def test_spec_services_invalid_mode_rejected():
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(
            _spec_dict("apt-cache",
                       services={"apt": {"box": "apt-cache", "mode": "ftp"}})
        )


def test_spec_services_none_is_valid():
    # Omitting services is valid; auto-inject populates it when an apt provider is present.
    spec = ScenarioSpec.model_validate(_spec_dict("apt-cache"))
    assert spec.services is not None
    assert spec.services.apt is not None
    assert spec.services.apt.box == "apt-cache"
