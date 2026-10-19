"""Reject replacement and cross-instance resources before native lifecycle writes."""
import re
from collections.abc import Mapping


def verify(current, expected, receipt):
    vmid = expected['vm_id']
    if (type(vmid) is not int or not 1000 <= vmid <= 999999999
            or not re.fullmatch(r'range42-workshop:[a-f0-9]{16,32}:user(?:0[1-9]|10):(?:proxmox|deployer)', expected['owner'])
            or receipt.get('vmid') != vmid
            or current.get('name') != expected['vm_name']
            or current.get('description') != expected['owner']
            or receipt.get('owner') != expected['owner']
            or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', current.get('vmgenid', ''))
            or current['vmgenid'] != receipt.get('vmgenid')
            or current.get('template') or current.get('lock')
            or current.get('cpu') != 'host'
            or int(current.get('memory', 0)) != expected['memory_mib']
            or int(current.get('cores', 0)) != expected['cores']
            or current.get('ipconfig0') != f"ip={expected['ip']}/28,gw={expected['gateway']}"
            or [key for key in current if re.fullmatch(r'net[0-9]+', key)] != ['net0']
            or not re.search(r'(?:^|,)bridge=' + re.escape(expected['bridge']) + r'(?:,|$)', current.get('net0', ''))
            or any(re.match(r'^(?:hostpci|usb|unused)[0-9]+$', key) for key in current)
            or 'args' in current):
        raise ValueError('Workshop ownership, generation, network or hardware differs; refusing mutation')
    disks = ['ide2', 'scsi0'] + (['scsi1'] if expected['role'] == 'proxmox' else [])
    if sorted(key for key in current if re.fullmatch(r'(?:ide|sata|scsi|virtio)[0-9]+', key)) != disks:
        raise ValueError('Workshop disk attachments differ')
    for key in ['scsi0'] + (['scsi1'] if expected['role'] == 'proxmox' else []):
        disk = current[key]
        size = 128 if key == 'scsi1' else 32
        if (not re.match(rf'^{re.escape(expected["storage"])}:vm-{vmid}-disk-[0-9]+,', disk)
                or not re.search(rf'(?:^|,)size={size}G(?:,|$)', disk)):
            raise ValueError('Workshop disk belongs to another resource or has changed size')
    if not re.match(rf'^{re.escape(expected["storage"])}:vm-{vmid}-cloudinit,media=cdrom(?:,|$)', current['ide2']):
        raise ValueError('Workshop cloud-init volume differs')
    return True


def verify_bootstrap(current, expected, receipt):
    if receipt.get('phase', 'active') != 'active' or receipt.get('vmid') != expected['vm_id']:
        raise ValueError('Only the original active generation can resume bootstrap')
    try:
        return verify(current, expected, receipt)
    except ValueError:
        if receipt.get('bootstrap_complete', False):
            raise ValueError('A completed bootstrap must retain its final seat allocation')
        baseline = receipt.get('bootstrap_network')
        if (not isinstance(baseline, Mapping) or set(baseline) != {'net0', 'ipconfig0'}
                or any(current.get(key) != value for key, value in baseline.items())):
            raise ValueError('Network is neither the original recorded clone nor the final seat allocation')
        if not re.search(r'(?:^|,)bridge=[A-Za-z][A-Za-z0-9_.-]{0,14}(?:,|$)', baseline.get('net0', '')):
            raise ValueError('Recorded clone network is not the declared template network')
        normalized = dict(current)
        normalized['net0'] = re.sub(r'(?<=bridge=)vmbr[0-9]+', expected['bridge'], current['net0'])
        normalized['ipconfig0'] = f"ip={expected['ip']}/28,gw={expected['gateway']}"
        return verify(normalized, expected, receipt)


def needs_cloudinit(current, expected, receipt):
    verify_bootstrap(current, expected, receipt)
    try:
        verify(current, expected, receipt)
        return False
    except ValueError:
        return True


def retirement_state(current, expected, receipt, globally_absent):
    if current is not None:
        verify(current, expected, receipt)
        return False
    if (globally_absent is True and receipt == {'phase': 'uncreated',
            'owner': expected['owner'], 'vmid': expected['vm_id']}):
        return True
    if (globally_absent is not True or receipt.get('phase') not in ('retiring', 'retired')
            or receipt.get('owner') != expected['owner'] or receipt.get('vmid') != expected['vm_id']
            or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', receipt.get('vmgenid', ''))):
        raise ValueError('Absent resource has no original owned retirement intent or independent absence proof')
    return True


def first_configuration(marker, expected):
    if marker is None:
        return True
    if not isinstance(marker, Mapping) or any(marker.get(key) != expected[key] for key in ('username', 'role', 'owner')):
        raise ValueError('Existing guest identity does not match this owned workshop instance')
    return False


class FilterModule:
    def filters(self):
        return {'workshop_owned': verify, 'workshop_retirement_state': retirement_state,
                'workshop_bootstrap_owned': verify_bootstrap,
                'workshop_needs_cloudinit': needs_cloudinit, 'workshop_first_configuration': first_configuration}
