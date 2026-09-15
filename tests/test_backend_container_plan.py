"""Installer plans preserve bindings and reject ambiguous inputs before writes."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = (
    ROOT / "bundles/admin/software.install.deployer_api_backend/files/container_plan.py"
)


def module():
    assert FILE.exists(), "managed installer needs a validated plan before provisioning"
    spec = importlib.util.spec_from_file_location("container_plan", FILE)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def config(tmp_path):
    return {
        "root": str(tmp_path / "install"),
        "name": "fixture-api",
        "image": "sha256:" + "a" * 64,
        "uid": os.getuid(),
        "gid": os.getgid(),
    }


def test_fresh_plan_is_deterministic_and_does_not_create_state(tmp_path):
    raw = config(tmp_path)
    plan = module().validate_config(raw)
    assert plan == module().validate_config(raw)
    assert not (tmp_path / "install").exists()
    assert plan["database_host"] == str(
        tmp_path / "install/state/workspaces/.range42.db"
    )
    assert plan["workspace_container"] == "/var/lib/range42/workspaces"


@pytest.mark.parametrize(
    "change",
    [
        {"image": "backend:latest"},
        {"unknown": True},
        {"uid": True},
        {"port": 0},
        {"name": "bad/name"},
        {"listen_address": "$(unsafe)"},
        {"root": "relative"},
        {"workspace_container": "/run/secrets"},
        {"database_container": "/elsewhere/db"},
        {"cors_origins": ["https://ui.example/path"]},
    ],
)
def test_invalid_configuration_is_rejected_without_creating_state(tmp_path, change):
    with pytest.raises(ValueError):
        module().validate_config({**config(tmp_path), **change})
    assert not (tmp_path / "install").exists()


def test_original_legacy_workspace_and_database_paths_are_explicitly_preserved(
    tmp_path,
):
    plan = module().validate_config(
        {
            **config(tmp_path),
            "workspace_host": str(tmp_path / "old-workspaces"),
            "workspace_container": "/home/range42/range42.config",
            "database_container": "/home/range42/range42.config/.old.db",
        }
    )
    assert plan["database_host"] == str(tmp_path / "old-workspaces/.old.db")
    compose = module().compose_document(plan, "b" * 64)
    service = compose["services"]["api"]
    assert (
        service["environment"]["RANGE42_WORKSPACE_ROOT"]
        == "/home/range42/range42.config"
    )
    assert (
        service["environment"]["RANGE42_DB_URL"]
        == "sqlite+aiosqlite:////home/range42/range42.config/.old.db"
    )
    assert any(
        mount["source"] == str(tmp_path / "old-workspaces")
        and mount["target"] == "/home/range42/range42.config"
        for mount in service["volumes"]
    )
    assert (
        service["read_only"]
        and service["init"]
        and service["user"] == f"{os.getuid()}:{os.getgid()}"
    )
    assert "SSH_KEY_PATH" not in json.dumps(
        compose
    ) and "/home/range42/.ssh" not in json.dumps(compose)
    assert service["environment"]["RANGE42_AUTH_MODE"] == "required"
    assert "RANGE42_API_TOKEN" not in service["environment"]


def test_runtime_mounts_cover_pinned_dependencies_and_private_template(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    template = tmp_path / "template"
    template.mkdir()
    plan = module().validate_config(
        {
            **config(tmp_path),
            "runtime_dir": str(runtime),
            "workspace_template_dir": str(template),
        }
    )
    service = module().compose_document(plan, "b" * 64)["services"]["api"]
    mounts = {mount["target"]: mount for mount in service["volumes"]}
    assert (
        mounts["/runtime"]["read_only"]
        and not mounts["/runtime"]["bind"]["create_host_path"]
    )
    assert mounts["/run/range42-template"]["read_only"]
    assert service["environment"]["RANGE42_INVENTORY__DOCKER__CTF"].endswith(
        "/docker/_ctf"
    )
    assert (
        service["environment"]["RANGE42_PROXMOX_CA_FILE"] == "/runtime/proxmox-ca.pem"
    )
    assert len(service["environment"]["ANSIBLE_ROLES_PATH"].split(":")) == 4


def test_symlinked_host_paths_cannot_redirect_installer_state(tmp_path):
    destination = tmp_path / "elsewhere"
    destination.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic|symlink"):
        module().validate_config({**config(tmp_path), "state_dir": str(alias)})


@pytest.mark.parametrize(
    "binding",
    [
        "state_contains_installation",
        "workspace_contains_installation",
        "credentials_writable_through_state",
    ],
)
def test_writable_mounts_cannot_expose_installer_records_or_credentials(
    tmp_path, binding
):
    raw = config(tmp_path)
    if binding == "state_contains_installation":
        raw["state_dir"] = str(tmp_path)
    elif binding == "workspace_contains_installation":
        raw["workspace_host"] = str(tmp_path)
    else:
        raw["secrets_dir"] = raw["root"] + "/state/secrets"
    with pytest.raises(ValueError, match="writable|overlap"):
        module().validate_config(raw)


def runtime_config(tmp_path):
    return {
        **config(tmp_path),
        "runtime_dir": str(tmp_path / "runtime"),
        "workspace_template_dir": str(tmp_path / "template"),
    }


def test_systemd_sibling_database_maps_to_state_not_workspace(tmp_path):
    raw = {
        **config(tmp_path),
        "state_dir": str(tmp_path / "native-state"),
        "workspace_host": str(tmp_path / "separate-workspaces"),
        "database_container": "/var/lib/range42/state.db",
    }
    plan = module().validate_config(raw)
    assert plan["database_host"] == str(tmp_path / "native-state/state.db")
    service = module().compose_document(plan, "c" * 32)["services"]["api"]
    assert (
        service["environment"]["RANGE42_DB_URL"]
        == "sqlite+aiosqlite:////var/lib/range42/state.db"
    )
    assert (
        service["environment"]["RANGE42_WORKSPACE_ROOT"]
        == "/var/lib/range42/workspaces"
    )


@pytest.mark.parametrize(
    "database",
    [
        "/var/lib/range42",
        "/var/lib/range42/maintenance.lock",
        "/var/lib/range42/maintenance.lock-wal",
        "/var/lib/range42/home/identity.db",
        "/var/lib/range42/workspaces",
        "/var/lib/range42/workspaces/.locks/provisioning.lock",
        "/var/lib/range42/workspaces/./.range42.db",
        "/var/lib/range42/../other/state.db",
    ],
)
def test_database_cannot_replace_reserved_state_or_noncanonical_paths(
    tmp_path, database
):
    with pytest.raises(ValueError):
        module().validate_config({**config(tmp_path), "database_container": database})


def test_database_inside_overlay_workspace_uses_overlay_host(tmp_path):
    plan = module().validate_config(
        {
            **config(tmp_path),
            "workspace_host": str(tmp_path / "external"),
            "database_container": "/var/lib/range42/workspaces/nested/state.db",
        }
    )
    assert plan["database_host"] == str(tmp_path / "external/nested/state.db")


def test_database_host_symlink_or_directory_refused(tmp_path):
    root = tmp_path / "native-state"
    root.mkdir()
    original = tmp_path / "unrelated"
    original.write_text("keep")
    (root / "state.db").symlink_to(original)
    raw = {
        **config(tmp_path),
        "state_dir": str(root),
        "database_container": "/var/lib/range42/state.db",
    }
    with pytest.raises(ValueError):
        module().validate_config(raw)
    (root / "state.db").unlink()
    (root / "state.db").mkdir()
    with pytest.raises(ValueError):
        module().validate_config(raw)
    assert original.read_text() == "keep"


def test_native_runtime_layout_uses_individual_config_and_ca_mounts(tmp_path):
    raw = {
        **runtime_config(tmp_path),
        "runtime_container": "/opt/range42",
        "runtime_config_container": "/etc/range42",
        "runtime_ca_container": "/etc/ssl/certs/ca-certificates.crt",
        "workspace_template_container": "/etc/range42/workspace-template",
    }
    plan = module().validate_config(raw)
    service = module().compose_document(plan, "c" * 32)["services"]["api"]
    env = service["environment"]
    mounts = {row["target"]: row for row in service["volumes"]}
    assert env["RANGE42_BUNDLE_RUNTIME_MANIFEST"] == "/etc/range42/bundle-runtime.json"
    assert env["ANSIBLE_CONFIG"] == "/etc/range42/ansible.cfg"
    assert env["RANGE42_PROXMOX_CA_FILE"] == "/etc/ssl/certs/ca-certificates.crt"
    assert env["RANGE42_WORKSPACE_TEMPLATE_DIR"] == "/etc/range42/workspace-template"
    assert env["RANGE42_BUNDLE_DIR"] == "/opt/range42/range42-playbooks/bundles"
    assert env["ANSIBLE_COLLECTIONS_PATH"] == "/opt/range42/collections"
    assert env["ANSIBLE_ROLES_PATH"].split(":") == [
        "/opt/range42/range42-ansible_roles-proxmox_controller/roles",
        "/opt/range42/range42-catalog/02_ansible_layer/admin/roles",
        "/opt/range42/range42-catalog/02_ansible_layer/trainee/roles",
        "/opt/range42/range42/roles",
    ]
    for source, target in [
        ("ansible.cfg", "/etc/range42/ansible.cfg"),
        ("bundle-runtime.json", "/etc/range42/bundle-runtime.json"),
        ("proxmox-ca.pem", "/etc/ssl/certs/ca-certificates.crt"),
    ]:
        assert mounts[target]["source"] == str(tmp_path / "runtime" / source)
        assert (
            mounts[target]["read_only"]
            and not mounts[target]["bind"]["create_host_path"]
        )
    assert (
        mounts["/opt/range42"]["read_only"]
        and mounts["/etc/range42/workspace-template"]["read_only"]
    )
    assert "/etc" not in mounts and "/etc/range42" not in mounts


def test_default_runtime_layout_and_bridge_contract_remain_unchanged(tmp_path):
    plan = module().validate_config(runtime_config(tmp_path))
    service = module().compose_document(plan, "c" * 32)["services"]["api"]
    assert plan["network_mode"] == "bridge"
    assert "network_mode" not in service and "command" not in service
    assert service["ports"] == [
        {"target": 8000, "published": "8000", "host_ip": "127.0.0.1", "protocol": "tcp"}
    ]
    assert [v["target"] for v in service["volumes"]] == [
        "/var/lib/range42",
        "/var/lib/range42/workspaces",
        "/run/secrets/api_token",
        "/run/secrets/credential_key",
        "/runtime",
        "/run/range42-template",
    ]


def test_host_network_uses_reviewed_bind_and_port_without_port_mapping(tmp_path):
    plan = module().validate_config(
        {
            **config(tmp_path),
            "network_mode": "host",
            "listen_address": "0.0.0.0",
            "port": 8123,
        }
    )
    service = module().compose_document(plan, "c" * 32)["services"]["api"]
    assert service["network_mode"] == "host"
    assert "ports" not in service and "networks" not in service
    assert service["command"] == [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8123",
        "--workers",
        "1",
        "--log-level",
        "info",
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"network_mode": "container:foreign"},
        {"runtime_container": "/etc"},
        {"runtime_container": "/var/lib/range42/runtime"},
        {"runtime_container": "/app"},
        {"runtime_container": "/run/secrets"},
        {"runtime_container": "/runtime/../other"},
        {"runtime_config_container": "/run/secrets"},
        {"runtime_config_container": "/var/lib/range42"},
        {"runtime_config_container": "/runtime/nested"},
        {
            "runtime_ca_container": "/etc/range42/ansible.cfg",
            "runtime_config_container": "/etc/range42",
        },
        {
            "workspace_template_container": "/etc/range42",
            "runtime_config_container": "/etc/range42",
        },
        {"workspace_template_container": "/runtime/private"},
        {"runtime_ca_container": "/var/lib/range42/maintenance.lock"},
        {"runtime_ca_container": "/run/secrets/api_token"},
        {"runtime_ca_container": "/runtime/elsewhere.pem"},
    ],
)
def test_unsafe_or_ambiguous_container_layout_is_refused(tmp_path, change):
    with pytest.raises(ValueError):
        module().validate_config({**runtime_config(tmp_path), **change})
    assert not (tmp_path / "install").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"runtime_dir": "install/state/runtime"},
        {"runtime_dir": "install/secrets"},
        {"workspace_template_dir": "install/state/template"},
        {"workspace_template_dir": "runtime/private"},
    ],
)
def test_readonly_inputs_cannot_be_writable_or_expose_other_credentials(
    tmp_path, change
):
    raw = runtime_config(tmp_path)
    raw.update({key: str(tmp_path / value) for key, value in change.items()})
    with pytest.raises(ValueError, match="overlap"):
        module().validate_config(raw)


def test_explicit_inventory_is_preserved_inside_existing_state_mount(tmp_path):
    plan = module().validate_config(
        {
            **config(tmp_path),
            "inventory_container": "/var/lib/range42/inventory",
            "database_container": "/var/lib/range42/state.db",
        }
    )
    service = module().compose_document(plan, "c" * 32)["services"]["api"]
    assert plan["inventory_container"] == "/var/lib/range42/inventory"
    assert (
        service["environment"]["API_BACKEND_INVENTORY_DIR"]
        == "/var/lib/range42/inventory"
    )
    assert len(service["volumes"]) == 4
    assert plan["database_host"] == str(tmp_path / "install/state/state.db")


def test_inventory_default_does_not_override_application_default(tmp_path):
    plan = module().validate_config(config(tmp_path))
    assert plan["inventory_container"] == ""
    service = module().compose_document(plan, "c" * 32)["services"]["api"]
    assert "API_BACKEND_INVENTORY_DIR" not in service["environment"]


def test_inventory_in_legacy_workspace_stays_on_its_explicit_mount(tmp_path):
    plan = module().validate_config(
        {
            **config(tmp_path),
            "workspace_container": "/home/range42/range42.config",
            "inventory_container": "/home/range42/range42.config/inventory",
        }
    )
    assert (
        module().compose_document(plan, "c" * 32)["services"]["api"]["environment"][
            "API_BACKEND_INVENTORY_DIR"
        ]
        == "/home/range42/range42.config/inventory"
    )


@pytest.mark.parametrize(
    "inventory",
    [
        "/etc/range42",
        "/run/secrets",
        "/var/lib/range42",
        "/var/lib/range42/home/keys",
        "/var/lib/range42/maintenance.lock",
        "/var/lib/range42/workspaces/.locks",
        "/var/lib/range42/workspaces/.range42.db",
        "/var/lib/range42/workspaces",
        "/var/lib/range42/../inventory",
    ],
)
def test_inventory_cannot_overlap_unmounted_reserved_or_database_paths(
    tmp_path, inventory
):
    with pytest.raises(ValueError):
        module().validate_config({**config(tmp_path), "inventory_container": inventory})


@pytest.mark.parametrize(
    "database",
    [
        "/var/lib/range42/maintenance.lock/state.db",
        "/var/lib/range42/maintenance.lock-shm/state.db",
    ],
)
def test_database_cannot_turn_maintenance_file_into_directory(tmp_path, database):
    with pytest.raises(ValueError):
        module().validate_config({**config(tmp_path), "database_container": database})


@pytest.mark.parametrize(
    ("address", "expected_host"),
    [("0.0.0.0", "127.0.0.1"), ("::", "[::1]"), ("192.0.2.10", "192.0.2.10")],
)
def test_host_network_healthcheck_follows_actual_listen_address_and_port(
    tmp_path, address, expected_host
):
    plan = module().validate_config(
        {
            **config(tmp_path),
            "network_mode": "host",
            "listen_address": address,
            "port": 8123,
        }
    )
    service = module().compose_document(plan, "c" * 32)["services"]["api"]
    check = service.get("healthcheck", {}).get("test", [])
    assert check[:3] == ["CMD", "python", "-c"]
    assert f"http://{expected_host}:8123/v1/health" in check[3]
    assert "timeout=3" in check[3]


def test_recorded_default_layout_without_runtime_normalizes_for_unchanged_repeat(
    tmp_path,
):
    planner = module()
    first = planner.validate_config(config(tmp_path))
    recorded = {key: value for key, value in first.items() if key != "database_host"}
    assert (
        recorded["runtime_dir"] is None and recorded["workspace_template_dir"] is None
    )
    assert planner.validate_config(recorded) == first


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_container", "/opt/range42"),
        ("runtime_config_container", "/etc/range42"),
        ("runtime_ca_container", "/etc/ssl/certs/ca-certificates.crt"),
        ("workspace_template_container", "/etc/range42/workspace-template"),
    ],
)
def test_no_runtime_record_still_refuses_nondefault_layout(tmp_path, field, value):
    first = module().validate_config(config(tmp_path))
    recorded = {key: item for key, item in first.items() if key != "database_host"}
    recorded[field] = value
    with pytest.raises(ValueError, match="layout|runtime"):
        module().validate_config(recorded)
