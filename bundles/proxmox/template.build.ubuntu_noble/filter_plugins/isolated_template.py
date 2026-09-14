"""Literal, fail-closed contracts shared by the isolated template playbook."""

import hashlib
import base64
from collections.abc import Mapping, Sequence
import ipaddress
import json
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit

import yaml


def _require(condition):
    if not condition:
        raise ValueError(
            "The isolated template plan or its ownership/success proof is invalid"
        )


def _text(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _number(value, minimum, maximum):
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def template_key_sha256(key):
    """One literal public key, with its SSH wire type bound to decoded bytes."""
    _require(isinstance(key, str) and len(key) <= 16384)
    lines = key.strip().splitlines()
    _require(len(lines) == 1)
    fields = lines[0].split()
    _require(
        len(fields) >= 2
        and fields[0]
        in {
            "ssh-ed25519",
            "ssh-rsa",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521",
        }
    )
    try:
        blob = base64.b64decode(fields[1], validate=True)
    except (ValueError, TypeError):
        _require(False)
    _require(base64.b64encode(blob).decode() == fields[1])
    parts = []
    position = 0
    while position < len(blob):
        _require(position + 4 <= len(blob))
        size = int.from_bytes(blob[position : position + 4], "big")
        position += 4
        _require(size > 0 and position + size <= len(blob))
        parts.append(blob[position : position + size])
        position += size
    _require(parts and parts[0] == fields[0].encode())
    if fields[0] == "ssh-ed25519":
        _require(len(parts) == 2 and len(parts[1]) == 32)
    elif fields[0] == "ssh-rsa":
        _require(len(parts) == 3)
    else:
        _require(
            len(parts) == 3
            and parts[1] == fields[0].removeprefix("ecdsa-sha2-").encode()
        )
    return hashlib.sha256(blob).hexdigest()


def template_builder_key(config, key, user):
    """Proxmox stores sshkeys URI-escaped; never adopt or erase other records."""
    fingerprint = template_key_sha256(key)
    _require(_text(user, r"[a-z_][a-z0-9_-]{0,31}"))
    _require(isinstance(config, Mapping) and config.get("ciuser") == user)
    supplied = config.get("sshkeys")
    _require(isinstance(supplied, str) and len(supplied) <= 49152)
    decoded = unquote(supplied, errors="strict")
    _require(decoded.strip() == key.strip())
    _require(template_key_sha256(decoded) == fingerprint)
    return fingerprint


def template_key_provisionable(config, key, user):
    """A stopped resume cannot overwrite unreviewed cloud-init authorization."""
    _require(isinstance(config, Mapping) and _text(user, r"[a-z_][a-z0-9_-]{0,31}"))
    template_key_sha256(key)
    if "sshkeys" in config:
        template_builder_key(config, key, user)
    else:
        _require(
            not {
                "ciuser",
                "cipassword",
                "cicustom",
                "nameserver",
                "searchdomain",
            }.intersection(config)
        )
        _require(not any(re.fullmatch(r"ipconfig\d+", name) for name in config))
    return True


def template_seed_clean(config, seed, key):
    """Conversion needs an empty generated authorization surface after removal."""
    template_key_sha256(key)
    _require(isinstance(config, Mapping) and "sshkeys" not in config)
    _require(isinstance(seed, str) and 0 < len(seed) <= 65536)
    try:
        document = yaml.compose(seed, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        _require(False)
    _require(isinstance(document, yaml.MappingNode))
    key_blob = key.split()[1]
    pending = [(document, 0)]
    seen = 0
    while pending:
        value, depth = pending.pop()
        seen += 1
        _require(depth <= 16 and seen <= 4096)
        if isinstance(value, yaml.MappingNode):
            names = []
            for name, entry in value.value:
                _require(
                    isinstance(name, yaml.ScalarNode)
                    and name.tag == "tag:yaml.org,2002:str"
                )
                names.append(name.value)
                if name.value in {"ssh_authorized_keys", "ssh_import_id"}:
                    _require(
                        isinstance(entry, yaml.SequenceNode)
                        and not entry.value
                        or isinstance(entry, yaml.ScalarNode)
                        and entry.tag == "tag:yaml.org,2002:null"
                    )
                pending.extend([(name, depth + 1), (entry, depth + 1)])
            _require(len(names) == len(set(names)))
        elif isinstance(value, yaml.SequenceNode):
            pending.extend((entry, depth + 1) for entry in value.value)
        elif isinstance(value, yaml.ScalarNode):
            _require(key_blob not in value.value)
    return True


def template_plan(value):
    required = {
        "build_id",
        "vm_id",
        "name",
        "node",
        "image_path",
        "image_sha256",
        "disk_storage",
        "snippet_storage",
        "disk_gb",
        "cores",
        "memory_mb",
        "bridge",
        "address",
        "gateway",
        "dns",
        "guest_host",
    }
    _require(
        isinstance(value, Mapping)
        and required <= value.keys() <= required | {"apt_proxy_url"}
    )
    plan = dict(value)
    _require(_text(plan["build_id"], r"[a-f0-9]{32}"))
    # Reserve the historical/template/service ID ranges for their existing callers.
    _require(_number(plan["vm_id"], 10000, 999999))
    _require(_text(plan["image_sha256"], r"[a-f0-9]{64}"))
    for field in (
        "name",
        "node",
        "disk_storage",
        "snippet_storage",
        "bridge",
        "guest_host",
    ):
        _require(_text(plan[field], r"[A-Za-z][A-Za-z0-9_.-]{0,62}"))
    _require(
        plan["guest_host"]
        not in {"all", "localhost", "proxmox", "proxmox_cli", "ungrouped"}
    )
    _require(_text(plan["image_path"], r"/[A-Za-z0-9/_.-]{1,240}"))
    _require(".." not in PurePosixPath(plan["image_path"]).parts)
    _require(
        _number(plan["disk_gb"], 8, 1024)
        and _number(plan["cores"], 1, 128)
        and _number(plan["memory_mb"], 512, 1048576)
    )
    interface = ipaddress.IPv4Interface(plan["address"])
    gateway = ipaddress.IPv4Address(plan["gateway"])
    _require(
        interface.network.prefixlen <= 30
        and interface.ip
        not in {interface.network.network_address, interface.network.broadcast_address}
    )
    _require(
        gateway in interface.network
        and gateway
        not in {
            interface.ip,
            interface.network.network_address,
            interface.network.broadcast_address,
        }
    )
    _require(
        isinstance(plan["dns"], Sequence)
        and not isinstance(plan["dns"], str)
        and 1 <= len(plan["dns"]) <= 3
    )
    plan["dns"] = [str(ipaddress.IPv4Address(item)) for item in plan["dns"]]
    proxy = plan.get("apt_proxy_url", "")
    _require(isinstance(proxy, str) and len(proxy) <= 512)
    if proxy:
        url = urlsplit(proxy)
        _require(
            url.scheme in {"http", "https"}
            and url.hostname
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
            and not any(char.isspace() for char in proxy)
            and "{{" not in proxy
        )
    plan["apt_proxy_url"] = proxy
    plan["address"] = str(interface)
    plan["gateway"] = str(gateway)
    digest = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    plan.update(
        plan_sha256=digest,
        ip=str(interface.ip),
        prefix=interface.network.prefixlen,
        description=f"range42-template-build:{plan['build_id']}\nrange42-template-plan:{digest}",
        snippet_name=f"range42-template-{plan['build_id']}.yaml",
    )
    return plan


def template_owned(config, plan, node):
    _require(
        isinstance(config, Mapping)
        and node == plan["node"]
        and config.get("name") == plan["name"]
        and config.get("description") == plan["description"]
        and config.get("template", 0) in (0, "0")
        and "lock" not in config
    )
    return True


def template_success(proof, plan):
    _require(isinstance(proof, Mapping))
    count = proof.get("cloud_init_warning_count")
    category = proof.get("cloud_init_warning_category")
    _require(
        type(count) is int
        and (
            (count == 0 and category == "none")
            or (1 <= count <= 32 and category == "proxmox_scalar_user_deprecation")
        )
    )
    expected = {
        "version": 1,
        "build_id": plan["build_id"],
        "plan_sha256": plan["plan_sha256"],
        "cloud_init": "done",
        "package_audit": "clean",
        "package_module": "completed",
        "cloud_init_warning_category": category,
        "cloud_init_warning_count": count,
    }
    _require(
        isinstance(proof, Mapping)
        and proof == expected
        and _number(proof.get("version"), 1, 1)
    )
    return True


def template_configured(config, plan):
    template_owned(config, plan, plan["node"])
    _require(
        not any(
            re.fullmatch(r"(?:net|ipconfig|scsi|sata|virtio|ide)\d+", key)
            and key not in {"net0", "ipconfig0", "scsi0", "ide2"}
            for key in config
        )
    )
    for field, expected in (
        ("cores", plan["cores"]),
        ("memory", plan["memory_mb"]),
        ("sockets", 1),
    ):
        _require(str(config.get(field)) == str(expected))
    nic = config.get("net0", "").split(",")
    _require(
        (nic[0] == "virtio" or nic[0].startswith("virtio="))
        and f"bridge={plan['bridge']}" in nic
    )
    _require(
        config.get("ipconfig0", "").strip()
        == f"ip={plan['address']},gw={plan['gateway']}"
    )
    disk = config.get("scsi0", "").split(",")
    _require(
        disk[0] == f"{plan['disk_storage']}:vm-{plan['vm_id']}-disk-0"
        and f"size={plan['disk_gb']}G" in disk
        and "media=cdrom" not in disk
    )
    _require(
        config.get("ciupgrade", 1) in (1, "1")
        and config.get("cicustom")
        == f"vendor={plan['snippet_storage']}:snippets/{plan['snippet_name']}"
    )
    return True


def template_disk_safe(config, plan):
    _require(isinstance(config, Mapping))
    _require(
        not any(
            re.fullmatch(r"(?:unused|scsi|sata|virtio|net|ipconfig|ide)\d+", key)
            and key not in {"scsi0", "net0", "ipconfig0", "ide2"}
            for key in config
        )
    )
    if "scsi0" in config:
        disk = config["scsi0"].split(",")
        size = [part[5:-1] for part in disk if re.fullmatch(r"size=[0-9]+G", part)]
        _require(
            disk[0] == f"{plan['disk_storage']}:vm-{plan['vm_id']}-disk-0"
            and len(size) == 1
            and 1 <= int(size[0]) <= plan["disk_gb"]
            and "media=cdrom" not in disk
        )
    if "ide2" in config:
        _require(
            config["ide2"].split(",")[0]
            in {
                f"{plan['disk_storage']}:vm-{plan['vm_id']}-cloudinit",
                f"{plan['disk_storage']}:cloudinit",
            }
        )
    if "cicustom" in config:
        _require(
            config["cicustom"]
            == f"vendor={plan['snippet_storage']}:snippets/{plan['snippet_name']}"
        )
    return True


def template_partial_config(config, plan):
    template_disk_safe(config, plan)
    for field, expected in (
        ("cores", plan["cores"]),
        ("memory", plan["memory_mb"]),
        ("sockets", 1),
    ):
        _require(str(config.get(field)) == str(expected))
    nic = config.get("net0", "").split(",")
    _require(
        (nic[0] == "virtio" or nic[0].startswith("virtio="))
        and f"bridge={plan['bridge']}" in nic
    )
    _require(
        "ipconfig0" not in config
        or config["ipconfig0"].strip() == f"ip={plan['address']},gw={plan['gateway']}"
    )
    _require(config.get("ciupgrade", 1) in (1, "1"))
    return True


def template_cluster_identity(certificates):
    # Same CA identity contract as the reviewed SDN cluster planner. No subject,
    # issuer, certificate bodies or credentials are exposed to task messages.
    _require(
        isinstance(certificates, Sequence)
        and not isinstance(certificates, str)
        and all(isinstance(row, Mapping) for row in certificates)
    )
    matches = [row for row in certificates if row.get("filename") == "pve-root-ca.pem"]
    _require(len(matches) == 1)
    fingerprint = matches[0].get("fingerprint")
    _require(_text(fingerprint, r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){31}"))
    return "pve-root-ca-sha256:" + fingerprint.replace(":", "").lower()


def template_storage(disk, snippets, plan):
    _require(isinstance(disk, Mapping) and isinstance(snippets, Mapping))
    _require(
        disk.get("type") in {"lvmthin", "zfspool"} and snippets.get("type") == "dir"
    )
    for storage, content in ((disk, "images"), (snippets, "snippets")):
        _require(
            storage.get("active") in (1, True)
            and storage.get("enabled") in (1, True)
            and isinstance(storage.get("content"), str)
            and content in storage["content"].split(",")
        )
    _require(_number(disk.get("avail"), plan["disk_gb"] * 1073741824, 2**63 - 1))
    return True


def template_volumes(rows, config, plan):
    """Refuse orphan volumes before the reused importer can select disk-0."""
    template_disk_safe(config, plan)
    _require(isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)))
    _require(len(rows) <= 2)
    expected = {
        config[key].split(",", 1)[0] for key in ("scsi0", "ide2") if key in config
    }
    actual = []
    for row in rows:
        _require(isinstance(row, Mapping))
        _require(row.get("vmid") == plan["vm_id"] and isinstance(row.get("volid"), str))
        actual.append(row["volid"])
    _require(len(set(actual)) == len(actual) and set(actual) == expected)
    return True


class FilterModule:
    def filters(self):
        return {
            "range42_template_plan": template_plan,
            "range42_template_owned": template_owned,
            "range42_template_success": template_success,
            "range42_template_configured": template_configured,
            "range42_template_disk_safe": template_disk_safe,
            "range42_template_partial_config": template_partial_config,
            "range42_template_cluster_identity": template_cluster_identity,
            "range42_template_storage": template_storage,
            "range42_template_volumes": template_volumes,
            "range42_template_key_sha256": template_key_sha256,
            "range42_template_builder_key": template_builder_key,
            "range42_template_key_provisionable": template_key_provisionable,
            "range42_template_seed_clean": template_seed_clean,
        }
