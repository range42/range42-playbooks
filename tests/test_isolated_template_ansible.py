"""Run the isolated entrypoint locally with its real roles and a TLS fake PVE."""

from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundles/proxmox/template.build.ubuntu_noble"
CONTROLLER = Path(
    os.environ.get(
        "RANGE42_CONTROLLER_TEST_ROOT", "/tmp/r42-template-controller-next-wave"
    )
)


def controller_fixture():
    spec = importlib.util.spec_from_file_location(
        "owned_create_test", CONTROLLER / "tests/test_owned_vm_create.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def fixture(tmp_path, *, status=500):
    """Use real role HTTPS for create; fail gates must not send a POST."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    image = tmp_path / "image.img"
    image.write_bytes(b"fresh verified image")
    import hashlib

    plan = {
        "build_id": "a" * 32,
        "vm_id": 62000,
        "name": "r42-template-test",
        "node": "pve01",
        "image_path": str(image),
        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "disk_storage": "local-lvm",
        "snippet_storage": "local",
        "disk_gb": 16,
        "cores": 1,
        "memory_mb": 1024,
        "bridge": "r42smk",
        "address": "10.42.70.30/24",
        "gateway": "10.42.70.1",
        "dns": ["1.1.1.1"],
        "guest_host": "r42-template-test",
    }
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "commands": [],
                "exists": status == 200,
                "config": {"name": "foreign", "template": 0},
            }
        )
    )
    fake = binaries / "fake"
    fake.write_text(f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
p=Path(os.environ['TEMPLATE_TEST_STATE']); s=json.loads(p.read_text()); a=sys.argv[1:]; exe=Path(sys.argv[0]).name
if exe=='hostname': print('pve01')
elif exe=='pvesm':
 print(os.environ['TEMPLATE_TEST_SNIPPET'])
elif exe=='pvesh' and a[:2]==['get','/cluster/resources']:
 print(json.dumps([{{'vmid':62000,'type':'qemu','node':'pve01'}}] if s['exists'] else []))
elif exe=='pvesh' and a[1].endswith('/certificates/info'):
 print(json.dumps([{{'filename':'pve-root-ca.pem','fingerprint':':'.join(['AA']*32)}}]))
elif exe=='pvesh' and a[1].endswith('/content'):
 volumes=[{{'volid':v.split(',')[0],'vmid':62000}} for k,v in s['config'].items() if k in ('scsi0','ide2')]
 if os.environ.get('TEMPLATE_TEST_ORPHAN')=='1':volumes.append({{'volid':'local-lvm:vm-62000-disk-0','vmid':62000}})
 print(json.dumps(volumes))
elif exe=='pvesh' and '/storage/' in a[1]:
 kind=os.environ.get('TEMPLATE_TEST_DISK_TYPE','lvmthin') if '/local-lvm/' in a[1] else 'dir'
 print(json.dumps({{'type':kind,'active':1,'enabled':1,'avail':100000000000,'content':'images,snippets'}}))
elif exe=='pvesh' and a[1].endswith('/config'):
 print(json.dumps(s['config']))
elif exe=='pvesh' and a[1].endswith('/status/current'):
 print(json.dumps({{'status':s.get('status','stopped')}}))
elif exe=='qm':
 if a[0]=='config':
  for key,value in s['config'].items():print(str(key)+': '+str(value))
 elif a[0]=='status': print('status: '+s.get('status','stopped'))
 elif a[0]=='disk' and a[1]=='import': pass
 elif a[0]=='resize':s['config']['scsi0']='local-lvm:vm-62000-disk-0,size='+a[-1]
 elif a[0]=='set':
  for i in range(2,len(a),2):
   if a[i]=='--delete':s['config'].pop(a[i+1],None)
   else:s['config'][a[i][2:]]=a[i+1]
 elif a[0]=='start':s['status']='running'
 elif a[0]=='shutdown':s['status']='stopped'
 elif a[0]=='template':
  assert s.get('ready'), 'Conversion must follow successful guest proof'
  if os.environ.get('TEMPLATE_TEST_CONVERT_FAIL')!='1':s['config']['template']=1
 else:sys.exit(2)
 if a[0] not in ['config','status']:
  s['commands'].append([exe]+a);p.write_text(json.dumps(s))
elif exe=='cloud-init' and a==['clean','--machine-id']:
 assert s.get('ready'), 'Guest cleanup must follow successful upgrade proof'
 s['commands'].append(['guest-clean']);p.write_text(json.dumps(s))
else:
 s['commands'].append([exe]+a);p.write_text(json.dumps(s));sys.exit(2)
""")
    fake.chmod(0o700)
    for name in ("hostname", "pvesh", "pvesm", "qm", "cloud-init"):
        (binaries / name).symlink_to(fake)
    guest_python = binaries / "guest-python"
    guest_python.write_text(f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
if len(sys.argv)>1 and 'template_ready.py' in sys.argv[1]:
 p=Path(os.environ['TEMPLATE_TEST_STATE']);s=json.loads(p.read_text());clean='--clean' in sys.argv
 s['commands'].append(['guest-clean' if clean else 'guest-ready'])
 good=os.environ.get('TEMPLATE_TEST_READY','success')=='success';s['ready']=good;p.write_text(json.dumps(s))
 marker=s['config']['description'].splitlines()
 proof={{'version':1,'build_id':marker[0].split(':')[1],'plan_sha256':marker[1].split(':')[1]}}
 proof.update({{'clone_identity':'reset'}} if clean else {{'cloud_init':'done' if good else 'running','package_audit':'clean','package_module':'completed'}})
 print(json.dumps(proof))
 sys.exit(0 if good else 1)
os.execv({sys.executable!r},[{sys.executable!r}]+sys.argv[1:])
""")
    guest_python.chmod(0o700)
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(
        yaml.safe_dump(
            {
                "all": {
                    "children": {
                        "proxmox": {
                            "hosts": {
                                "pve": {
                                    "ansible_connection": "local",
                                    "ansible_python_interpreter": sys.executable,
                                }
                            }
                        },
                        "proxmox_cli": {
                            "hosts": {
                                "pve-cli": {
                                    "ansible_connection": "local",
                                    "ansible_python_interpreter": sys.executable,
                                }
                            }
                        },
                        "guests": {
                            "hosts": {
                                "r42-template-test": {
                                    "ansible_connection": "local",
                                    "ansible_host": "10.42.70.30",
                                    "ansible_become": False,
                                    "ansible_python_interpreter": str(guest_python),
                                }
                            }
                        },
                    }
                }
            }
        )
    )
    config = tmp_path / "config/secrets"
    config.mkdir(parents=True)
    (config / "default_vault.yml").write_text("{}\n")
    with controller_fixture().api(tmp_path, status, state_path=state) as (
        port,
        ca,
        calls,
    ):
        variables = {
            "template_build": plan,
            "proxmox_node": "pve01",
            "proxmox_api_host": f"127.0.0.1:{port}",
            "proxmox_api_validate_certs": True,
            "proxmox_api_user": "test@pve",
            "proxmox_api_token_id": "test",
            "proxmox_api_token_secret": "test",
            "default_admin_vm_ci_user": "alice",
            "default_admin_vm_ci_ssh_key": "ssh-ed25519 AAAATEST",
        }
        environment = {
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "TEMPLATE_TEST_STATE": str(state),
            "TEMPLATE_TEST_SNIPPET": str(tmp_path / "snippet.yaml"),
            "ANSIBLE_NOCOLOR": "1",
            "RANGE42_ACTIVE_CONFIG_DIR": str(config.parent),
            "RANGE42_PROXMOX_CA_FILE": str(ca),
            "SSL_CERT_FILE": str(ca),
            "ANSIBLE_ROLES_PATH": str(CONTROLLER / "roles"),
        }
        yield variables, environment, inventory, calls, state


def invoke(tmp_path, variables, environment, inventory):
    assert (BUNDLE / "isolated.yml").is_file(), (
        "An isolated build must enforce scope before any mutation"
    )
    extra = tmp_path / "vars.json"
    extra.write_text(json.dumps(variables))
    return subprocess.run(
        [
            str(Path(sys.executable).with_name("ansible-playbook")),
            "-i",
            str(inventory),
            str(BUNDLE / "isolated.yml"),
            "-e",
            f"@{extra}",
        ],
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    "problem",
    [
        "protected_id",
        "foreign_existing",
        "wrong_hash",
        "wrong_node",
        "wrong_guest",
        "legacy_disk",
        "wrong_cluster",
        "unsupported_storage",
    ],
)
def test_invalid_ownership_or_input_cannot_touch_any_template(tmp_path, problem):
    with fixture(tmp_path, status=200 if problem == "foreign_existing" else 500) as (
        variables,
        environment,
        inventory,
        calls,
        state,
    ):
        if problem == "protected_id":
            variables["template_build"]["vm_id"] = 9901
        elif problem == "wrong_hash":
            variables["template_build"]["image_sha256"] = "c" * 64
        elif problem == "wrong_node":
            variables["template_build"]["node"] = "different"
        elif problem == "wrong_guest":
            variables["template_build"]["address"] = "10.42.70.31/24"
        elif problem == "legacy_disk":
            variables["vm_disk_size"] = "10"
        elif problem == "wrong_cluster":
            current = json.loads(state.read_text())
            current["api_fingerprint"] = ":".join(["BB"] * 32)
            state.write_text(json.dumps(current))
        elif problem == "unsupported_storage":
            environment["TEMPLATE_TEST_DISK_TYPE"] = "dir"
        result = invoke(tmp_path, variables, environment, inventory)
        assert result.returncode != 0
        assert not calls
        assert not json.loads(state.read_text())["commands"]


@pytest.mark.parametrize("ready", ["success", "failed"])
def test_conversion_requires_fresh_guest_success_and_never_changes_family(
    tmp_path, ready
):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        environment["TEMPLATE_TEST_READY"] = ready
        result = invoke(tmp_path, variables, environment, inventory)
        current = json.loads(state.read_text())
        if ready == "success":
            assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-1000:]
            assert current["config"]["template"] == 1
            operations = [row[:2] for row in current["commands"]]
            assert (
                operations.index(["guest-ready"])
                < operations.index(["guest-clean"])
                < operations.index(["qm", "shutdown"])
                < operations.index(["qm", "template"])
            )
            assert not (tmp_path / "snippet.yaml").exists()
        else:
            assert result.returncode != 0
            assert "Template upgrade success was not verified" in result.stdout
            assert current.get("ready") is False, result.stdout[-6000:]
            assert current["config"]["template"] == 0
            assert (tmp_path / "snippet.yaml").is_file(), (
                "Failure retains owned retry state"
            )
        assert current["config"]["description"].startswith(
            "range42-template-build:" + "a" * 32
        )
        assert (tmp_path / "image.img").read_bytes() == b"fresh verified image"
        assert all(
            "9901" not in row and "range42-apt-proxy.yaml" not in str(row)
            for row in current["commands"]
        )


def test_failed_owned_running_build_resumes_without_forced_stop_or_reconfiguration(
    tmp_path,
):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        environment["TEMPLATE_TEST_READY"] = "failed"
        first = invoke(tmp_path, variables, environment, inventory)
        assert first.returncode != 0
        before = json.loads(state.read_text())
        assert before.get("ready") is False, first.stdout[-4000:]
        variables["template_build_resume"] = True
        environment["TEMPLATE_TEST_READY"] = "success"
        second = invoke(tmp_path, variables, environment, inventory)
        assert second.returncode == 0, second.stdout[-5000:] + second.stderr[-1000:]
        after = json.loads(state.read_text())
        resumed = after["commands"][len(before["commands"]) :]
        assert ["qm", "start", "62000"] not in resumed
        assert not any("/status/stop" in str(row) for row in resumed)
        assert not any(row[:2] == ["qm", "resize"] for row in resumed)


def test_proxy_is_retained_only_in_the_selected_template_snippet(tmp_path):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        variables["template_build"]["apt_proxy_url"] = "http://10.42.42.1:3142"
        result = invoke(tmp_path, variables, environment, inventory)
        assert result.returncode == 0, result.stdout[-5000:]
        assert yaml.safe_load((tmp_path / "snippet.yaml").read_text()) == {
            "apt": {"http_proxy": "http://10.42.42.1:3142"}
        }
        assert (tmp_path / "snippet.yaml").read_text().startswith("#cloud-config\n")
        current = json.loads(state.read_text())
        assert (
            current["config"]["cicustom"]
            == "vendor=local:snippets/range42-template-" + "a" * 32 + ".yaml"
        )


def test_zero_exit_without_template_readback_does_not_claim_success(tmp_path):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        environment["TEMPLATE_TEST_CONVERT_FAIL"] = "1"
        result = invoke(tmp_path, variables, environment, inventory)
        assert result.returncode != 0
        assert json.loads(state.read_text()).get("ready") is True, result.stdout[-4000:]


def test_failed_create_worker_cannot_proceed_to_disk_import(tmp_path):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        current = json.loads(state.read_text())
        current["create_task_exit"] = "create failed"
        state.write_text(json.dumps(current))
        result = invoke(tmp_path, variables, environment, inventory)
        assert result.returncode != 0
        commands = json.loads(state.read_text())["commands"]
        assert calls, "The fixture must exercise the accepted asynchronous create"
        assert "Require successful creation before disk preparation" in result.stdout
        assert not any(row[0] == "qm" for row in commands)


@pytest.mark.parametrize(
    "task_id", [None, "UPID:pve01:00000001:00000001:00000001:qmcreate:62001:test@pve:"]
)
def test_missing_or_wrong_create_worker_cannot_import_disk(tmp_path, task_id):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        current = json.loads(state.read_text())
        current["create_task_id"] = task_id
        state.write_text(json.dumps(current))
        result = invoke(tmp_path, variables, environment, inventory)
        assert result.returncode != 0
        assert calls
        assert "Wait for the exact create worker to finish" not in result.stdout
        assert not any(
            row[0] == "qm" for row in json.loads(state.read_text())["commands"]
        )


def test_actual_storage_type_zfspool_uses_the_same_owned_native_volume(tmp_path):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        environment["TEMPLATE_TEST_DISK_TYPE"] = "zfspool"
        result = invoke(tmp_path, variables, environment, inventory)
        assert result.returncode == 0, result.stdout[-3000:]
        current = json.loads(state.read_text())
        assert current["config"]["template"] == 1
        assert current["config"]["scsi0"] == "local-lvm:vm-62000-disk-0,size=16G"


def test_orphan_storage_volume_refuses_creation_and_disk_import(tmp_path):
    with fixture(tmp_path) as (variables, environment, inventory, calls, state):
        environment["TEMPLATE_TEST_ORPHAN"] = "1"
        result = invoke(tmp_path, variables, environment, inventory)
        assert result.returncode != 0
        assert calls == []
        assert json.loads(state.read_text())["commands"] == []
