"""Check isolated allocations against source-owned scenario declarations.

The registry and current manifests form a conservative union. This is a read-only
check, not a reservation or a substitute for live Proxmox ownership checks.
"""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import re
import stat

import yaml

FILE_LIMIT = 2 * 1024 * 1024
ROW_LIMIT = 32768


def _declarations(root):
    root = Path(root).resolve(strict=True)
    consumed = 0

    def read(path):
        nonlocal consumed
        if not path.resolve().is_relative_to(root) or any(
                part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(root)):
            raise ValueError('Linked reservation input')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > FILE_LIMIT:
            raise ValueError('Invalid reservation input size or type')
        data = path.read_bytes()
        consumed += len(data)
        if len(data) > FILE_LIMIT or consumed > 16 * FILE_LIMIT:
            raise ValueError('Reservation inputs exceed size limit')
        return data.decode('utf-8')

    rows = [json.loads(line) for line in read(root / 'scenarios/_reserved.json').splitlines() if line.strip()]
    if not rows:
        raise ValueError('Empty reservation registry')
    networks = []
    manifests = sorted((root / 'scenarios').glob('*/manifest/scenario_vms.json'))
    if len(manifests) > 1024:
        raise ValueError('Too many scenario manifests')
    for path in manifests:
        base = path.parents[1]
        manifest = json.loads(read(path))
        for key in ('vms', 'templates'):
            entries = manifest.get(key, [])
            if not isinstance(entries, list):
                raise ValueError('Invalid scenario reservations')
            rows.extend({**row, 'scenario': base.name, **({'role': 'template'} if key == 'templates' else {})}
                        for row in entries)
        if len(rows) > ROW_LIMIT:
            raise ValueError('Too many scenario reservations')
        network_manifest = base / 'manifest/scenario_networks.json'
        if network_manifest.exists() or network_manifest.is_symlink():
            document = json.loads(read(network_manifest))
            networks.extend((base.name, row) for row in document['vnets'])
        bootstrap = base / '00_sdn_bootstrap/_main.yml'
        if bootstrap.exists() or bootstrap.is_symlink():
            for play in yaml.safe_load(read(bootstrap)):
                for task in play.get('tasks', []):
                    facts = task.get('ansible.builtin.set_fact', task.get('set_fact', {}))
                    networks.extend((base.name, row) for row in facts.get('_sdn_vnets', []))
    if len(rows) > ROW_LIMIT or len(networks) > ROW_LIMIT:
        raise ValueError('Too many scenario reservations')
    return rows, networks


def validate_reserved_allocations(plan, source_root):
    """Reject overlap with native guests, template references and SDN networks."""
    try:
        rows, networks = _declarations(source_root)
        reserved = []
        for row in rows:
            if (not isinstance(row, dict) or type(row.get('vm_id')) is not int
                    or not 100 <= row['vm_id'] <= 999999999
                    or not isinstance(row.get('scenario'), str) or not row['scenario']):
                raise ValueError('Invalid reservation row')
            nics = row.get('nics', [])
            if not isinstance(nics, list) or len(nics) > 32:
                raise ValueError('Invalid reservation interfaces')
            for nic in [row, *nics]:
                bridge, address = nic.get('bridge'), nic.get('ip')
                if bridge is None and address is None:
                    continue
                if not isinstance(bridge, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,14}', bridge):
                    raise ValueError('Invalid reservation bridge')
                if not isinstance(address, str):
                    raise ValueError('Invalid reservation address')
                reserved.append((row['scenario'], bridge, ipaddress.ip_interface(address).ip))
        declared = [(owner, row['vnet'], ipaddress.ip_network(row['subnet'], strict=True)) for owner, row in networks]
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, yaml.YAMLError):
        raise ValueError('Cannot validate scenario reservations. Check scenarios/_reserved.json and the VM and network declarations.') from None

    vmids = {vm['vm_id'] for vm in plan['vms']}
    templates = {vm['template_vmid'] for vm in plan['vms']}
    for row in rows:
        if row['vm_id'] in vmids or (row['vm_id'] in templates and row.get('role') != 'template'):
            raise ValueError(f"VMID {row['vm_id']} is reserved by scenario {row['scenario']}")
    subnet = ipaddress.ip_network(plan['subnet'])
    for owner, bridge, address in reserved:
        if bridge == plan['bridge']:
            raise ValueError(f"Dedicated VNet {bridge} is reserved by scenario {owner}")
        if address in subnet:
            raise ValueError(f"Stack subnet contains address {address} reserved by scenario {owner}")
    for owner, bridge, network in declared:
        if bridge == plan['bridge'] or (network.version == subnet.version and subnet.overlaps(network)):
            raise ValueError(f"Stack network overlaps {bridge} ({network}) reserved by scenario {owner}")
