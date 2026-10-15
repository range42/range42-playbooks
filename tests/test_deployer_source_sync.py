"""Run the actual native API/UI sync with local files and loopback SSH only."""
import copy
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import threading

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import paramiko
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = ["deployer_api_backend", "deployer_ui"]


def sync_task(bundle):
    source = ROOT / f"bundles/admin/software.install.{bundle}/main.yml"
    plays = yaml.safe_load(source.read_text())
    return copy.deepcopy(next(task for play in plays for task in play.get("tasks", [])
                              if "ansible.posix.synchronize" in task))


def run_sync(tmp_path, bundle, *, remote=False, environment=None):
    binary = shutil.which("ansible-playbook")
    if not binary or not shutil.which("rsync"):
        pytest.skip("Behavior tests require Ansible, ansible.posix and rsync")
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir(exist_ok=True)
    destination.mkdir(exist_ok=True)
    variables = {"LOCAL_CODE_PATH_RESOLVED": str(source) + "/",
                 "REMOTE_PROJECT_DIR_RESOLVED": str(destination)}
    name = "fixture.invalid" if remote else "localhost"
    inventory = {"all": {"hosts": {name: {"ansible_connection": "ssh" if remote else "local"},
        "localhost": {"ansible_connection": "local", "ansible_python_interpreter": sys.executable}}}}
    if remote:
        inventory["all"]["hosts"][name].update({
            "ansible_user": "fixture",
            "ansible_ssh_common_args": "-F " + shlex.quote(str(tmp_path / "private 'ssh config")),
            "ansible_ssh_extra_args": "-o LogLevel=ERROR",
        })
    hosts = tmp_path / "hosts.yml"
    hosts.write_text(yaml.safe_dump(inventory))
    playbook = tmp_path / "play.yml"
    playbook.write_text(yaml.safe_dump([{
        "hosts": name, "become": remote, "gather_facts": False,
        "vars": variables, "tasks": [sync_task(bundle)]}], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nhost_key_checking=True\nretry_files_enabled=False\n")
    return subprocess.run([str(binary), "-i", str(hosts), str(playbook)],
        env={**os.environ, "ANSIBLE_CONFIG": str(config), "ANSIBLE_HOST_KEY_CHECKING": "True",
             "PYTHONDONTWRITEBYTECODE": "1", **(environment or {})},
        capture_output=True, text=True, timeout=20)


@pytest.mark.parametrize("bundle", BUNDLES)
def test_native_sync_keeps_copy_delete_and_private_exclusion_behavior(tmp_path, bundle):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "Dockerfile").write_text("FROM scratch\n")
    (destination / "obsolete-build-file").write_text("old\n")
    protected = [".env", ".env.local"]
    if bundle == "deployer_api_backend":
        protected += [".container-secrets", "docker-compose.override.yml"]
    for name in protected:
        (source / name).write_text("PUBLIC_SOURCE_FIXTURE\n")
        (destination / name).write_text("PUBLIC_RETAINED_FIXTURE\n")
        (destination / name).chmod(0o600)
    before = {name: (destination / name).stat().st_ino for name in protected}
    result = run_sync(tmp_path, bundle)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / "Dockerfile").read_bytes() == (source / "Dockerfile").read_bytes()
    assert not (destination / "obsolete-build-file").exists()
    for name in protected:
        assert (destination / name).read_text() == "PUBLIC_RETAINED_FIXTURE\n"
        assert (destination / name).stat().st_ino == before[name]
        assert (destination / name).stat().st_mode & 0o777 == 0o600


def host_key():
    private = ed25519.Ed25519PrivateKey.generate()
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                               serialization.NoEncryption())
    return paramiko.Ed25519Key.from_private_key(io.StringIO(pem.decode()))


@pytest.mark.parametrize("bundle", BUNDLES)
@pytest.mark.parametrize("trust", ["known", "unknown", "changed"])
@pytest.mark.parametrize("wrapper", [False, True])
def test_native_rsync_retains_private_proxy_route_and_host_pins(tmp_path, bundle, trust, wrapper):
    real_ssh = shutil.which("ssh")
    assert real_ssh
    key = host_key()
    saved = host_key() if trust == "changed" else key
    pins = tmp_path / "private known hosts"
    pins.write_text("" if trust == "unknown" else "fixture-pin " + saved.get_name() + " " + saved.get_base64() + "\n")
    pins.chmod(0o600)
    original = pins.read_bytes()
    command_received, stop = threading.Event(), threading.Event()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    listener.settimeout(0.1)

    class Server(paramiko.ServerInterface):
        def check_auth_none(self, username):
            return paramiko.AUTH_SUCCESSFUL

        def check_channel_request(self, kind, channel_id):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_exec_request(self, channel, command):
            if b"rsync --server " in command:
                command_received.set()
                return True
            return False

    def serve():
        transport = None
        try:
            while not stop.is_set():
                try:
                    client, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            transport = paramiko.Transport(client)
            transport.add_server_key(key)
            transport.start_server(server=Server())
            channel = transport.accept(4)
            if channel is not None and command_received.wait(2):
                # Local transfer tests cover the rsync protocol. This endpoint
                # stops after the real SSH handshake/exec, without remote files.
                channel.send_stderr(b"fixture: authenticated rsync reached\n")
                channel.send_exit_status(23)
                channel.close()
        except (EOFError, OSError, paramiko.SSHException):
            pass
        finally:
            if transport is not None:
                transport.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    proxy = tmp_path / "proxy.py"
    proxy_marker = tmp_path / "proxy-used"
    proxy.write_text(
        "import os,select,socket,sys\nfrom pathlib import Path\n"
        f"Path({str(proxy_marker)!r}).touch()\n"
        f"s=socket.create_connection(('127.0.0.1',{listener.getsockname()[1]}))\n"
        "while True:\n"
        "    ready,_,_=select.select([s,sys.stdin.buffer],[],[],5)\n"
        "    if not ready: break\n"
        "    for item in ready:\n"
        "        data=os.read(0,65536) if item is sys.stdin.buffer else s.recv(65536)\n"
        "        if not data: sys.exit(0)\n"
        "        s.sendall(data) if item is sys.stdin.buffer else os.write(1,data)\n"
    )
    config = tmp_path / "private 'ssh config"
    config.write_text(
        "Host fixture.invalid\n  HostName 192.0.2.123\n  User fixture\n"
        "  HostKeyAlias fixture-pin\n  StrictHostKeyChecking yes\n  BatchMode yes\n"
        f"  UserKnownHostsFile {json.dumps(str(pins))}\n  GlobalKnownHostsFile /dev/null\n"
        "  IdentityFile none\n  IdentityAgent none\n  PreferredAuthentications none\n"
        f"  ProxyCommand {shlex.quote(sys.executable)} {shlex.quote(str(proxy))}\n"
    )
    capture = tmp_path / "ssh-argv.json"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ssh = bindir / "ssh"
    # Refuse missing fixture routing before exec, so even the broken bundle can
    # never contact a real host or read the operator's SSH configuration.
    prefix = ["-o", "ServerAliveInterval=2"] if wrapper else []
    ssh.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        f"Path({str(capture)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        f"if {str(config)!r} not in sys.argv: raise SystemExit(93)\n"
        f"os.execv({real_ssh!r},[{real_ssh!r}]+{prefix!r}+sys.argv[1:])\n"
    )
    ssh.chmod(0o700)
    try:
        result = run_sync(tmp_path, bundle, remote=True,
                          environment={"PATH": str(bindir) + ":" + os.environ["PATH"]})
        assert capture.is_file(), result.stdout + result.stderr
        args = json.loads(capture.read_text())
        assert str(config) in args, "rsync dropped the configured private SSH route: " + repr(args)
        assert "StrictHostKeyChecking=no" not in args and "UserKnownHostsFile=/dev/null" not in args
        assert "LogLevel=ERROR" in args
        effective = subprocess.run([real_ssh, "-G", *prefix, *args],
                                   capture_output=True, text=True, check=True)
        options = dict(line.split(" ", 1) for line in effective.stdout.splitlines())
        assert options["stricthostkeychecking"] == "true"
        assert options["userknownhostsfile"] == str(pins)
        assert str(proxy) in options["proxycommand"]
        if wrapper:
            assert options["serveraliveinterval"] == "2"
        assert proxy_marker.exists(), result.stdout + result.stderr
        assert command_received.is_set() is (trust == "known"), result.stdout + result.stderr
        assert result.returncode != 0  # The fixture ends before any remote transfer.
        if trust != "known":
            assert "Host key verification failed" in result.stdout + result.stderr
        assert pins.read_bytes() == original
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=6)
