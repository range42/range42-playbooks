"""Exercise source deployment with a real Docker daemon and private records."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

FILES = Path(__file__).resolve().parents[1] / "bundles/admin/software.install.deployer_api_backend/files"


def source_module():
    path = FILES / "container_source.py"
    assert path.is_file(), "The scenario needs an automatic source-to-immutable-image producer"
    sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location("container_source", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_build_resolves_a_stable_immutable_image_without_operator_input(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM scratch AS runtime\nARG APP_UID\nARG APP_GID\nCOPY payload /payload\n")
    (source / "payload").write_text("showcase")
    module = source_module()
    first = module.prepare_request({"root": str(tmp_path / "installation")}, str(source))
    second = module.prepare_request({"root": str(tmp_path / "installation")}, str(source))
    assert first["config"]["image"].startswith("sha256:")
    assert second["config"]["image"] == first["config"]["image"]
    assert first["operation"] == "apply"


def test_existing_bindings_are_preserved_when_building_a_new_checkout(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM scratch AS runtime\nCOPY payload /payload\n")
    (source / "payload").write_text("new release")
    root = tmp_path / "installation"
    root.mkdir(mode=0o700)
    original = {"root": str(root), "name": "kept", "image": "sha256:" + "a" * 64,
                "uid": os.getuid(), "gid": os.getgid(), "port": 18391,
                "listen_address": "0.0.0.0", "state_dir": str(tmp_path / "state"),
                "secrets_dir": str(tmp_path / "private"), "runtime_dir": str(tmp_path / "runtime"),
                "database_host": str(tmp_path / "state/state.db")}
    record = root / "installation.json"
    record.write_text(json.dumps({"version": 1, "status": "ready", "config": original}))
    record.chmod(0o600)
    before = record.read_bytes()
    result = source_module().prepare_request({"root": str(root)}, str(source))
    assert result["operation"] == "update"
    assert result["config"]["image"] != original["image"]
    assert {key: value for key, value in result["config"].items() if key != "image"} == {
        key: value for key, value in original.items() if key not in ("image", "database_host")}
    assert record.read_bytes() == before


def test_source_failure_keeps_the_previous_record_and_sanitizes_build_output(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM scratch AS runtime\nCOPY confidential-missing-file /payload\n")
    root = tmp_path / "installation"
    root.mkdir(mode=0o700)
    record = root / "installation.json"
    record.write_text(json.dumps({"version": 1, "status": "ready", "config": {"root": str(root)}}))
    record.chmod(0o600)
    before = record.read_bytes()
    module = source_module()
    with pytest.raises(ValueError, match="Source image build failed") as error:
        module.prepare_request({"root": str(root)}, str(source))
    assert "confidential" not in str(error.value)
    assert record.read_bytes() == before


def test_source_producer_refuses_nonprivate_root_before_reading_its_record(tmp_path):
    root = tmp_path / "installation"
    root.mkdir(mode=0o777)
    root.chmod(0o777)
    record = root / "installation.json"
    record.write_text("untrusted malformed record")
    record.chmod(0o600)
    with pytest.raises(ValueError, match="Installation root must be private and owned"):
        source_module().prepare_request({"root": str(root)}, str(tmp_path / "not-built"))
    assert record.read_text() == "untrusted malformed record"
    assert list(root.iterdir()) == [record]
