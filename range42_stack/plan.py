"""Plan a platform on a private IPv4 bridge outside known scenario allocations.

No infrastructure credentials, environment variables or active workspace are
consulted. The generated scenario still checks live VM ownership before cloning.
"""
from __future__ import annotations

import ipaddress
import hashlib
import re
from pathlib import Path

from .reservations import validate_reserved_allocations


CORE = ("gateway", "backend", "ui", "cli", "reporting")
EXTRAS = ("wazuh", "gitea", "registry", "mattermost", "rocketchat", "nextcloud")
PORTS = {"gateway": 443, "backend": 8000, "ui": 80, "reporting": 80,
         "wazuh": 443, "gitea": 3000, "registry": 3000, "mattermost": 8065,
         "rocketchat": 3000, "nextcloud": 8080}


def _name(value, label, pattern=r"[a-z][a-z0-9-]{0,23}"):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid {label}")
    return value


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def build_plan(spec: dict, peers=(), *, source_root=None) -> dict:
    """Return a deterministic plan checked against scenarios and peer stacks."""
    allowed = {"id", "domain", "vmid_start", "subnet", "gateway", "bridge", "template_vmid",
               "node", "ssh_user", "profile", "dns"}
    if not isinstance(spec, dict) or set(spec) - allowed:
        raise ValueError("Unknown stack parameters; credentials belong in private installation inputs")
    sid = _name(spec.get("id"), "stack id")
    domain = _name(spec.get("domain"), "domain",
                   r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
    if len(domain) > 220:
        raise ValueError("Stack domain is too long")
    profile = spec.get("profile", "full")
    if profile not in {"core", "full"}:
        raise ValueError("Profile must be core or full")
    services = CORE + (EXTRAS if profile == "full" else ())
    base = _integer(spec.get("vmid_start"), "First VMID", 1000, 999999999 - len(services))
    template = _integer(spec.get("template_vmid"), "Template VMID", 102, 999999999)
    if template in range(base, base + len(services)):
        raise ValueError("The template cannot be a platform VM")
    network = ipaddress.ip_network(spec.get("subnet", ""), strict=True)
    private = (ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    if network.version != 4 or not any(network.subnet_of(block) for block in private) or not 16 <= network.prefixlen <= 27:
        raise ValueError("Use a private IPv4 subnet between /16 and /27")
    gateway = ipaddress.ip_address(spec.get("gateway", ""))
    if gateway not in network or gateway in {network.network_address, network.broadcast_address}:
        raise ValueError("Gateway must be a usable address in the stack subnet")
    bridge = _name(spec.get("bridge"), "dedicated VNet", r"[a-z][a-z0-9]{1,7}")
    if re.fullmatch(r"vmbr\d+", bridge):
        raise ValueError("Use a dedicated platform bridge, not the host management bridge")
    node = _name(spec.get("node"), "Proxmox node", r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}")
    user = _name(spec.get("ssh_user"), "SSH user", r"[a-z_][a-z0-9_-]{0,31}")
    dns = spec.get("dns", "1.1.1.1")
    ipaddress.IPv4Address(dns)
    addresses = (ip for ip in network.hosts() if int(ip) >= int(network.network_address) + 10 and ip != gateway)
    vms = []
    for index, service in enumerate(services):
        name = f"r42-{sid}-{service}"
        vms.append({"service": service, "vm_id": base + index, "vm_name": name,
                    "ssh_alias": name, "ip": str(next(addresses)), "bridge": bridge,
                    "role": "admin", "template_vmid": template,
                    "project_name": name, "install_root": f"/opt/range42/{sid}/{service}"})
    endpoints = {service: f"https://{'api' if service == 'backend' else service}.{domain}"
                 for service in services if service not in {"gateway", "cli"}}
    result = {"version": 1, "id": sid, "profile": profile, "domain": domain,
              "subnet": str(network), "gateway": str(gateway), "bridge": bridge, "dns": dns,
              "node": node, "ssh_user": user, "vms": vms,
              "zone": "r" + hashlib.sha256(sid.encode()).hexdigest()[:7],
              "endpoints": endpoints, "ownership_tag": f"r42-stack-{sid}",
              "unavailable": {"emp": "preview", "misp": "catalog payload is not present in this release"}}
    for peer in peers:
        collision = (sid == peer["id"] or domain == peer["domain"]
                     or domain.endswith("." + peer["domain"]) or peer["domain"].endswith("." + domain))
        collision |= (bridge == peer["bridge"] or result["zone"] == peer["zone"]
                      or network.overlaps(ipaddress.ip_network(peer["subnet"]))
                      or bool({v["vm_id"] for v in vms} & {v["vm_id"] for v in peer["vms"]}))
        if collision:
            raise ValueError(f"Stack resources overlap with {peer['id']}")
    validate_reserved_allocations(result, source_root if source_root is not None else Path(__file__).resolve().parent.parent)
    return result


def project_component(spec, source_root):
    """Package an isolated stack beside a project's existing canvas and files."""
    import json
    import tempfile
    from .scenario import export_scenario

    source_root = Path(source_root)
    plan = build_plan(spec, source_root=source_root)
    relative = 'platforms/' + plan['id']
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / plan['id']
        export_scenario(plan, output)
        files = {relative + '/' + p.relative_to(output).as_posix(): p.read_text()
                 for p in output.rglob('*') if p.is_file()}
    files[relative + '/manifest/scenario_runtime.json'] = json.dumps({
        'version': 1, 'bundle_path': 'platform_runtime/bundles'}, indent=2) + '\n'
    for name in ('bundles', 'range42_stack'):
        for path in sorted((source_root / name).rglob('*')):
            if not path.is_file() or any(part in {'__pycache__', 'preview', '.git'} for part in path.parts):
                continue
            if path.is_symlink() or path.suffix in {'.pyc', '.pyo'}:
                continue
            files['platform_runtime/' + path.relative_to(source_root).as_posix()] = path.read_text()
    return {'version': 1, 'plan': plan, 'scenario': {'version': 1, 'path': relative}, 'files': files}
