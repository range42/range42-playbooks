from pathlib import Path
import os
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scenarios/catalog_try/catalog_try.delete_vms_only.sh"


@pytest.mark.parametrize(
    "listing,code,expected",
    [("", 0, 0), ("", 1, 1), ("not json", 0, 1), ('{"vm_id":9221}', 0, 0)],
)
def test_catalog_try_first_deployment_accepts_verified_empty_inventory_without_deleting_templates(
    tmp_path, listing, code, expected
):
    binary = tmp_path / "bin"
    binary.mkdir()
    commands = {
        "proxmox_vm.list.to.jsons.sh": f"#!/bin/sh\nprintf '%s\\n' '{listing}'\nexit {code}\n",
        "proxmox_vm.vm_id.stop_force.to.jsons.sh": '#!/bin/sh\ncat > "$TEST_CALLED"\nexit 99\n',
        "proxmox_vm.vm_id.delete.to.jsons.sh": '#!/bin/sh\ncat > "$TEST_CALLED"\nexit 99\n',
    }
    for name, content in commands.items():
        path = binary / name
        path.write_text(content)
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(binary) + ":" + os.environ["PATH"],
        "HOME": str(tmp_path),
        "TEST_CALLED": str(tmp_path / "called"),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, env=env
    )
    assert (result.returncode == 0) == (expected == 0), result.stderr
    assert not (tmp_path / "called").exists()


@pytest.mark.parametrize("api_context,delete_code", [(True, 0), (True, 17), (False, 0)])
def test_catalog_try_cleanup_uses_only_the_active_context_pin_after_successful_deletion(
    tmp_path, api_context, delete_code
):
    import json

    binary = tmp_path / "bin"
    binary.mkdir()
    listing = json.dumps({"vm_id": 1250}) + "\n" + json.dumps({"vm_id": 9221})
    commands = {
        "proxmox_vm.list.to.jsons.sh": "#!/bin/sh\nprintf '%s\\n' "
        + __import__("shlex").quote(listing)
        + "\n",
        "proxmox_vm.vm_id.stop_force.to.jsons.sh": '#!/bin/sh\ncat > "$TEST_STOPPED"\n',
        "proxmox_vm.vm_id.delete.to.jsons.sh": '#!/bin/sh\ncat > "$TEST_DELETED"\nexit '
        + str(delete_code)
        + "\n",
    }
    for name, content in commands.items():
        p = binary / name
        p.write_text(content)
        p.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    context = tmp_path / "context"
    (context / "ssh_keys").mkdir(parents=True)
    subprocess.run(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-f",
            str(tmp_path / "fixture-key"),
        ],
        check=True,
    )
    public = (tmp_path / "fixture-key.pub").read_text().strip()
    pins = context / "ssh_keys/known_hosts"
    pins.write_text("10.77.32.2 " + public + "\n192.168.142.250 " + public + "\n")
    if api_context:
        (home / ".ssh").mkdir()
        (home / ".ssh/known_hosts").write_text(
            "another-context.example " + public + "\n"
        )
    env = {
        **os.environ,
        "PATH": str(binary) + ":" + os.environ["PATH"],
        "HOME": str(home),
        "RANGE42_SOURCE_CONTEXT_DIR": str(context) if api_context else "",
        "TEST_STOPPED": str(tmp_path / "stopped"),
        "TEST_DELETED": str(tmp_path / "deleted"),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, env=env
    )
    assert (result.returncode == 0) == (delete_code == 0), result.stderr
    assert json.loads((tmp_path / "stopped").read_text())["vm_id"] == 1250
    assert json.loads((tmp_path / "deleted").read_text())["vm_id"] == 1250
    if api_context:
        assert ("192.168.142.250" in pins.read_text()) == (delete_code != 0)
        assert "10.77.32.2" in pins.read_text()
        assert (
            home / ".ssh/known_hosts"
        ).read_text() == "another-context.example " + public + "\n"
