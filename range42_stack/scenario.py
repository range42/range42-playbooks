"""Compile a stack into the existing source-owned native scenario format."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys

import yaml

from .install import request_json, validate_template, validate_target_permissions
from .install import validate_cli_workload
from .render import node
from .plan import PORTS, CORE


def validate_live(plan, resources, vnets, zones, subnets):
    intended = {vm["vm_id"]: vm for vm in plan["vms"]}
    for resource in resources:
        vmid = int(resource["vmid"])
        if vmid in intended:
            vm = intended[vmid]
            if (resource.get("name") != vm["vm_name"] or resource.get("node") != plan["node"]
                    or resource.get("config", {}).get("description") != f"range42-stack:{plan['id']}"):
                raise ValueError(f"VMID {vmid} is occupied by a different installation")
        elif any(vm["vm_name"] == resource.get("name") for vm in plan["vms"]):
            raise ValueError("A platform VM name is already in use")
        elif any(re.search(r"(?:^|,)bridge=" + re.escape(plan["bridge"]) + r"(?:,|$)", str(value))
                 for key, value in resource.get("config", {}).items() if re.fullmatch(r"net\d+", key)):
            raise ValueError("A foreign guest is attached to the platform network")
    for zone in zones:
        if zone["zone"] == plan["zone"] and zone.get("type") != "simple":
            raise ValueError("Existing SDN zone is not the expected isolated simple zone")
    own = [v for v in vnets if v["vnet"] == plan["bridge"]]
    for vnet in vnets:
        if vnet["vnet"] == plan["bridge"] or vnet["zone"] == plan["zone"]:
            if (vnet["vnet"] != plan["bridge"] or vnet["zone"] != plan["zone"]
                    or vnet.get("alias") != f"range42-stack:{plan['id']}"):
                raise ValueError("Existing VNet or zone belongs to another installation")
    if not own and any(z["zone"] == plan["zone"] for z in zones):
        raise ValueError("Existing unclaimed SDN zone requires an ownership review")
    desired = ipaddress.ip_network(plan["subnet"])
    for subnet in subnets:
        cidr = subnet.get("cidr")
        if not cidr:
            # Proxmox encodes zone-10.0.0.0-24 in the subnet field.
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)-(\d+)$", subnet.get("subnet", ""))
            if not match:
                raise ValueError("Cannot verify an existing SDN subnet")
            cidr = match[1] + "/" + match[2]
        if desired.overlaps(ipaddress.ip_network(cidr)) and (
                subnet.get("vnet") != plan["bridge"] or cidr != plan["subnet"]
                or subnet.get("gateway") != plan["gateway"] or int(subnet.get("snat", 0)) != 1):
            raise ValueError("Stack subnet overlaps existing SDN configuration")


SERVICES = {
    "gateway": ("kong", "KONG", "kong"),
    "backend": ("deployer_api_backend", "DEPLOYER_API_BACKEND", "deployer_backend_api"),
    "ui": ("deployer_ui", "DEPLOYER_UI", "deployer_ui"),
    "cli": ("deployer_cli", "DEPLOYER_CLI", "ssh"),
    "reporting": ("reporting", "REPORTING", "ssh_http"),
    "wazuh": ("wazuh", "WAZUH", "wazuh"),
    "gitea": ("gitea", "GITEA", "gitea"),
    "registry": ("gitea_registry", "GITEA_REGISTRY", "gitea"),
    "mattermost": ("mattermost", "MATTERMOST", "mattermost"),
    "rocketchat": ("rocketchat", "ROCKETCHAT", "rocketchat"),
    "nextcloud": ("nextcloud", "NEXTCLOUD", "nextcloud"),
}


def bundle(name, variables=None, when=None):
    call = {"import_playbook": "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/" + name + "/main.yml"}
    if variables:
        call["vars"] = variables
    if when:
        call["when"] = when
    return call


def _node_play(plan, service):
    vm = node(plan, service)
    app, flag, firewall = SERVICES[service]
    enabled = "INSTALL_" + flag + " | default('YES') | upper == 'YES'"
    root = vm["install_root"]
    staged = "{{ stack_staging_dir }}/" + plan["id"] + "/" + service
    variables = {"global_vm_ssh_name": vm["vm_name"], "global_vm_ci_ip": vm["ip"]}
    if service == "ui":
        variables.update(LOCAL_CODE_PATH=staged + "/source/range42-deployer-ui/",
                         REMOTE_PROJECT_DIR=root + "/source/range42-deployer-ui",
                         UI_PORT=80, BACKEND_API_URL=plan["endpoints"]["backend"],
                         PROXMOX_NODE_NAME=plan["node"], BUNDLE_COMPOSE_PROJECT=vm["project_name"])
    elif service == "backend":
        variables.update(BUNDLE_API_INSTANCE_DIR=root, BUNDLE_COMPOSE_PROJECT=vm["project_name"])
    elif service == "gateway":
        variables.update(BUNDLE_KONG_CONFIG_FILE=staged + "/kong.yml",
                         BUNDLE_KONG_TLS_DIR=staged + "/tls", BUNDLE_KONG_HTTPS_PORT=443)
    elif service == "wazuh":
        variables.update(BUNDLE_WAZUH_VARS_FILE=staged + "/private/wazuh.yml",
                         BUNDLE_WAZUH_CERTS_DIR="{{ ((stack_wazuh_certs_dir ~ '/" + plan['id']
                         + "') if stack_wazuh_certs_dir | default('') | length > 0 else "
                         + "stack_staging_dir ~ '/" + plan['id'] + "/wazuh/certificates') }}",
                         BUNDLE_WAZUH_API_PASSWORDS=True)
    elif service in {"cli", "reporting"}:
        variables.update(BUNDLE_INSTANCE_DIR=root, BUNDLE_COMPOSE_PROJECT=vm["project_name"],
                         BUNDLE_OPERATOR_USER=plan["ssh_user"])
    else:
        variables.update(BUNDLE_CATALOG_SOURCE_DIR=staged, BUNDLE_CATALOG_REMOTE_DIR=root,
                         BUNDLE_CATALOG_OPERATOR=plan["ssh_user"], BUNDLE_CATALOG_PRIVATE=True)
    if service == "cli":
        variables.pop("BUNDLE_COMPOSE_PROJECT")
        variables.pop("global_vm_ci_ip")
        variables["BUNDLE_INSTANCE_SOURCE_DIR"] = staged
    if service == "reporting":
        variables.pop("BUNDLE_OPERATOR_USER")
    if service == "registry":
        variables["BUNDLE_REGISTRY_SOURCE_DIR"] = variables.pop("BUNDLE_CATALOG_SOURCE_DIR")
    ports = [str(PORTS[service])] if service != "cli" else ["22"]
    if service == "wazuh":
        ports = ["443", "1514", "1515", "55000"]
    calls = [
        bundle("generic/systems.baseline.default", {"target_group": vm["vm_name"],
               "BASELINE_INSTALL_DOCKER": "YES", "BASELINE_INSTALL_DOCKER_COMPOSE": "YES",
               "BASELINE_OPERATOR_USER": plan["ssh_user"]}, enabled),
        bundle("admin/platform.prepare.node", {"global_vm_ssh_name": vm["vm_name"],
               "BUNDLE_INSTANCE_SOURCE_DIR": staged, "BUNDLE_INSTANCE_DIR": root,
               "BUNDLE_OPERATOR_USER": plan["ssh_user"]}, enabled),
        bundle("firewall/in_vm/os_firewall.isolate.platform", {"target_group": vm["vm_name"],
               "BUNDLE_INSTANCE_DIR": root, "BUNDLE_SERVICE": service,
               "BUNDLE_MANAGEMENT_CIDRS": "{{ stack_management_cidrs }}",
               "BUNDLE_CLIENT_CIDRS": "{{ stack_client_cidrs | default(['0.0.0.0/0']) }}",
               "BUNDLE_AGENT_CIDRS": "{{ stack_agent_cidrs | default([]) }}"}, enabled),
        bundle("firewall/in_proxmox/firewall.baseline." + firewall,
               {"BUNDLE_VM_ID": vm["vm_id"], "BUNDLE_FW_PORTS": ports}, enabled),
        bundle("admin/software.install." + app, variables, enabled),
    ]
    return calls


def render_scenario(plan):
    files = {}
    def write(path, data, is_json=False):
        files[path] = (json.dumps(data, indent=2) if is_json else yaml.safe_dump(data, sort_keys=False)) + "\n"
    write("manifest/stack.json", plan, True)
    write('manifest/platform.json', {
        'version': 1, 'id': plan['id'], 'profile': plan['profile'], 'domain': plan['domain'],
        'unavailable': plan['unavailable'],
        'presets': [{'id': profile, 'features': {SERVICES[v['service']][1]:
                    profile == 'full' or v['service'] in CORE for v in plan['vms']}}
                    for profile in ('core', 'full') if profile == 'core' or plan['profile'] == 'full'],
        'parameters': [{'name': name, 'label': label, 'type': kind, 'required': required}
            for name, label, kind, required in (
                ('stack_source_dir', 'Application release directory', 'path', True),
                ('stack_runtime_dir', 'Runtime release directory', 'path', True),
                ('stack_staging_dir', 'Persistent private staging directory', 'path', True),
                ('stack_credential_template_dir', 'Dedicated credential profile directory', 'path', True),
                ('stack_tls_dir', 'Gateway certificate directory', 'path', True),
                ('stack_provisioning_api_url', 'Provisioning Proxmox HTTPS URL', 'url', True),
                ('stack_management_cidrs', 'SSH management networks (JSON array)', 'cidrs', True),
                ('stack_client_cidrs', 'Gateway client networks (JSON array)', 'cidrs', False),
                ('stack_agent_cidrs', 'Wazuh agent networks (JSON array)', 'cidrs', False),
                ('stack_gateway_addresses', 'Gateway DNS addresses (JSON array)', 'string', False),
                ('stack_wazuh_certs_dir', 'Wazuh certificate directory', 'path', False))]}, True)
    write("manifest/scenario_vms.json", {"scenario": "range42_" + plan["id"], "version": 3,
          "description": "Isolated Range42 platform (" + plan["profile"] + ")",
          "vms": [{**vm, "template_vm_id": vm["template_vmid"]} for vm in plan["vms"]],
          "templates": [{"vm_id": plan["vms"][0]["template_vmid"]}]}, True)
    write("manifest/scenario_networks.json", {"mode": "sdn", "zone": plan["zone"], "vnets": [{
          "vnet": plan["bridge"], "subnet": plan["subnet"], "gateway": plan["gateway"], "snat": True}]}, True)
    write("manifest/feature_flags.yml", {"features": [{"id": SERVICES[v["service"]][1],
          "label": v["service"], "description": "Install " + v["service"] + " on its reserved VM",
          "default": True} for v in plan["vms"]]})
    hosts = {vm["vm_name"]: {"ansible_host": vm["ip"], "ansible_user": plan["ssh_user"],
             "ansible_ssh_common_args": "{{ stack_guest_ssh_args | default(lookup('env', 'ANSIBLE_SSH_COMMON_ARGS')) }}"}
             for vm in plan["vms"]}
    inventory = {"all": {"children": {"platform": {"hosts": hosts},
         "proxmox": {"hosts": {"r42-proxmox": {"ansible_connection": "local",
               "ansible_python_interpreter": "{{ ansible_playbook_python }}"}}},
         "proxmox_cli": {"hosts": {"r42-proxmox-cli": {
               "ansible_host": "{{ stack_proxmox_ssh_host | default('r42-proxmox-cli') }}",
               "ansible_user": "{{ stack_proxmox_ssh_user | default('root') }}",
               "ansible_ssh_common_args": "{{ lookup('env', 'ANSIBLE_SSH_COMMON_ARGS') }}"}}}}}}
    write("hosts.yml", inventory)
    files["templates/ansible-inventory.j2"] = "{% raw %}\n" + files["hosts.yml"] + "{% endraw %}\n"
    files["templates/ssh-config.j2"] = _ssh_template(plan)
    main = [{"import_playbook": p} for p in ("00_preflight.yml",
        "_firewall/stage_00-pre_scenario.report_status.yml",
        "_firewall/stage_01-pre_scenario.management_access.yml",
        "00_sdn_bootstrap/_main.yml", "01_vm_bootstrap.yml",
        "_firewall/stage_02-post_vm_bootstrap.vm_ssh_baseline.yml", "configure.yml",
        "_firewall/stage_03-end_scenario.arm_deployed_vms.yml")]
    write("main.yml", main)
    # This stack uses an operator-selected existing template. Both entry points
    # retain software and firewall configuration, as range42-context expects.
    write("main_vms_only.yml", main)
    flags = {v["service"]: "{{ INSTALL_" + SERVICES[v["service"]][1] + " | default('YES') | upper == 'YES' }}"
             for v in plan["vms"]}
    write("00_preflight.yml", [bundle("admin/platform.prepare.instance", {
        "BUNDLE_STACK_PLAN_FILE": "{{ lookup('env', 'RANGE42_ACTIVE_CONFIG_DIR') }}/scenario/manifest/stack.json",
        "BUNDLE_STACK_SOURCE_DIR": "{{ stack_source_dir }}",
        "BUNDLE_STACK_RUNTIME_DIR": "{{ stack_runtime_dir }}",
        "BUNDLE_STACK_TEMPLATE_DIR": "{{ stack_credential_template_dir }}",
        "BUNDLE_STACK_TLS_DIR": "{{ stack_tls_dir }}",
        "BUNDLE_STACK_STAGING_DIR": "{{ stack_staging_dir }}",
        "BUNDLE_STACK_ENABLED": flags,
        "BUNDLE_GATEWAY_ADDRESSES": "{{ stack_gateway_addresses | default([]) }}",
        "BUNDLE_PROVISIONING_API_URL": "{{ stack_provisioning_api_url }}"})])
    write("00_sdn_bootstrap/_main.yml", [bundle("proxmox/sdn_network.bootstrap", {
        "BUNDLE_SDN_ZONE": plan["zone"], "BUNDLE_SDN_VNETS": [{"vnet": plan["bridge"],
        "subnet": plan["subnet"], "gateway": plan["gateway"], "snat": True}]}),
        bundle("proxmox/sdn_network.claim.instance", {"BUNDLE_VNET": plan["bridge"], "BUNDLE_STACK_ID": plan["id"],
            "BUNDLE_PROVISIONING_API_URL": "{{ stack_provisioning_api_url }}",
            "BUNDLE_PROXMOX_CA_FILE": "{{ stack_runtime_dir }}/proxmox-ca.pem"})])
    write("01_vm_bootstrap.yml", [bundle("proxmox/vm.bootstrap", {
        "BUNDLE_REUSE_OWNED_VM": True,
        "global_vm_id": vm["vm_id"], "global_vm_name": vm["vm_name"], "global_vm_ssh_name": vm["vm_name"],
        "global_vm_ci_ip": vm["ip"], "global_vm_description": "range42-stack:" + plan["id"],
        "global_vm_tag_name": plan["ownership_tag"], "global_template_vm_id": vm["template_vmid"],
        "global_vm_net_virtio_bridge": plan["bridge"], "global_vm_ci_ip_gw": plan["gateway"],
        "global_vm_ci_netmask": plan["subnet"].split("/")[1], "global_vm_ci_dns_ips": plan["dns"]})
        for vm in plan["vms"]])
    order = [v["service"] for v in plan["vms"] if v["service"] != "gateway"] + ["gateway"]
    write("configure.yml", [{"import_playbook": "00_preflight.yml"}]
          + [{"import_playbook": "nodes/" + service + ".yml"} for service in order]
          + [{'import_playbook': 'ready.yml'}])
    write('ready.yml', [bundle('admin/platform.check.ready', {
        'global_vm_ssh_name': node(plan, 'gateway')['vm_name'],
        'BUNDLE_INSTANCE_DIR': node(plan, 'gateway')['install_root'],
        'BUNDLE_API_TOKEN_FILE': '{{ stack_staging_dir }}/' + plan['id'] + '/backend/private/api-token',
        'BUNDLE_STACK_ENABLED': flags}, "INSTALL_KONG | default('YES') | upper == 'YES'")])
    for service in order:
        write("nodes/" + service + ".yml", _node_play(plan, service))
    for stage, name in (("stage_00-pre_scenario.report_status", "firewall.report.status"),
                        ("stage_01-pre_scenario.management_access", "firewall.baseline.management_access"),
                        ("stage_02-post_vm_bootstrap.vm_ssh_baseline", "firewall.baseline.ssh_all_vms"),
                        ("stage_03-end_scenario.arm_deployed_vms", "firewall.enable.vms")):
        variables = {"BUNDLE_SCENARIO_NETWORKS": [plan["subnet"]]} if name.endswith("ssh_all_vms") else None
        write("_firewall/" + stage + ".yml", [bundle("firewall/in_proxmox/" + name, variables,
              "FIREWALL_ARM_VMS | default('NO') | upper == 'YES'" if name == "firewall.enable.vms" else None)])
    for action in ('stop', 'start', 'checkpoint', 'backup', 'restore', 'rollback', 'teardown'):
        write(action + '.yml', [bundle('admin/platform.lifecycle', {
            'BUNDLE_ACTION': action,
            'BUNDLE_STACK_PLAN_FILE': "{{ lookup('env', 'RANGE42_ACTIVE_CONFIG_DIR') }}/scenario/manifest/stack.json",
            'BUNDLE_STACK_RUNTIME_DIR': '{{ stack_runtime_dir }}',
            'BUNDLE_STACK_STAGING_DIR': '{{ stack_staging_dir }}',
            'BUNDLE_PROVISIONING_API_URL': '{{ stack_provisioning_api_url }}',
            'BUNDLE_CONFIRM_STACK': "{{ stack_confirm_id | default('') }}",
            'BUNDLE_BACKUP_DIR': "{{ stack_backup_dir | default('/var/backups/range42') }}",
            'BUNDLE_CHECKPOINT': "{{ stack_checkpoint | default('before-upgrade') }}"})])
    return files


def _ssh_template(plan):
    ssh = """Host r42-proxmox-cli
    Hostname {{ INFRASTRUCTURE_PROXMOX_ADDRESS }}
    User root
    IdentityFile {{ DEPLOYER_CLI__DST_SSH_KEYS_JUMP_DEST_DIR }}/px.{{ INFRASTRUCTURE_CODENAME }}-{{ INFRASTRUCTURE_SCENARIO }}-ssh_cli.root
    StrictHostKeyChecking yes

Host r42-stack-jump
    Hostname {{ INFRASTRUCTURE_PROXMOX_ADDRESS }}
    User jump_user
    IdentityFile {{ DEPLOYER_CLI__DST_SSH_KEYS_JUMP_DEST_DIR }}/px.{{ INFRASTRUCTURE_CODENAME }}-{{ INFRASTRUCTURE_SCENARIO }}-ssh_cli.jump_user
    StrictHostKeyChecking yes

"""
    for vm in plan["vms"]:
        ssh += f"Host {vm['vm_name']} {vm['ip']}\n    Hostname {vm['ip']}\n    User {plan['ssh_user']}\n"
        ssh += ("    IdentityFile {{ DEPLOYER_CLI__DST_SSH_KEYS_BACKEND_DEST_DIR }}/r42."
                "{{ INFRASTRUCTURE_CODENAME }}-{{ INFRASTRUCTURE_SCENARIO }}-deployer-key_" + plan["ssh_user"] + "\n"
                "    ProxyJump r42-stack-jump\n    StrictHostKeyChecking accept-new\n\n")
    return ssh


def export_scenario(plan, destination):
    destination = Path(destination)
    files = render_scenario(plan)
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    from .install import native_wrappers
    native_wrappers(destination)


def validate_tls(root, domain):
    root = Path(root)
    cert, key = root / "cert.pem", root / "key.pem"
    if any(p.is_symlink() or not p.is_file() for p in (cert, key)) or key.stat().st_mode & 0o077:
        raise ValueError("Use a regular certificate and private mode-0600 key")
    def openssl(*args):
        result = subprocess.run(["openssl", *map(str, args)], stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError("TLS certificate/key validation failed")
        return result.stdout
    certificate_key = openssl("x509", "-in", cert, "-pubkey", "-noout")
    private_key = openssl("pkey", "-in", key, "-passin", "pass:", "-pubout")
    if certificate_key != private_key:
        raise ValueError("The TLS private key does not match the certificate")
    for service in ("ui", "api", "reporting", "gitea", "registry", "wazuh", "nextcloud", "mattermost", "rocketchat"):
        openssl("verify", "-partial_chain", "-trusted", cert, "-verify_hostname", service + "." + domain, cert)


def validate_bundle_contracts(plan, directory):
    """Reject a release that would silently ignore generated bundle arguments."""
    directory = Path(directory)
    for filename, content in render_scenario(plan).items():
        if not filename.endswith('.yml'):
            continue
        plays = yaml.safe_load(content)
        if not isinstance(plays, list):
            continue
        for play in plays:
            imported = play.get('import_playbook', '')
            if 'RANGE42_BUNDLE_DIR' not in imported:
                continue
            relative = imported.split('}}/', 1)[1].removesuffix('/main.yml')
            root = directory / relative
            if not (root / 'main.yml').is_file() or not (root / 'bundle_parameters.src.yml').is_file():
                raise ValueError('Runtime lacks required bundle: ' + relative)
            contract = yaml.safe_load((root / 'bundle_parameters.src.yml').read_text())
            names = {p['name'] for p in contract['params']}
            if set(play.get('vars', {})) - names:
                raise ValueError('Runtime bundle does not support the instance parameters: ' + relative)


def validate_provisioning_context(plan, parent):
    if parent.get('node') != plan['node'] or parent.get('ssh_user') != plan['ssh_user']:
        raise ValueError('The active provisioning node and cloud-init user must match the stack plan')


def validate_runtime_selection(active, expected):
    """Native execution copies pinned repositories; location is not release identity."""
    import hashlib
    def content(root):
        if not root.is_dir():
            raise ValueError('The reviewed runtime directory is missing')
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                and 'preview' not in p.parts and p.suffix != '.pyc'}
    for left, right in ((Path(active), Path(expected)),
                        (Path(active).parent / 'range42_stack', Path(expected).parent / 'range42_stack')):
        if content(left) != content(right):
            raise ValueError('Active bundles/helpers do not match the reviewed runtime release')


def validate_controller_actions(directory):
    required = {
        'network_list_sdn_zones', 'network_list_sdn_vnets', 'network_list_sdn_subnets',
        'network_add_sdn_zone', 'network_add_sdn_vnet', 'network_add_sdn_subnet',
        'network_update_sdn_subnet', 'network_apply_sdn', 'network_list_snat_rules',
        'network_delete_extra_snat_rules', 'network_delete_sdn_subnet',
        'network_delete_sdn_vnet', 'network_delete_sdn_zone',
        'firewall_dc_enable_management_access', 'firewall_node_enable_management_access',
        'firewall_vm_declare_iptables_port', 'snapshot_vm_create', 'snapshot_vm_revert',
        'vm_clone', 'vm_start', 'vm_stop', 'vm_delete',
    }
    tasks = Path(directory) / 'roles/range42-ansible_roles-proxmox_controller/tasks'
    text = '\n'.join(p.read_text() for p in tasks.rglob('*') if p.suffix in {'.yml', '.yaml'})
    missing = sorted(name for name in required if name not in text)
    if missing:
        raise ValueError('Selected controller lacks required native actions: ' + ', '.join(missing))


def validate_context_runtime(directory):
    path = Path(directory) / 'roles/deployer.bootstrap/files/range42-context.sh'
    text = path.read_text() if path.is_file() else ''
    if ('${scenario_name}.setup.sh' not in text or
            re.search(r'if \[\[ -f "\$scenario_target/main.yml" \]\]; then\s*_r42_run_concrete main.yml', text)):
        raise ValueError('Select the native range42-context runtime used by the current playbooks')


def validate_template_capacity(plan, configuration, enabled):
    # The existing all-in-one Wazuh bundle reserves 4096 MiB for the indexer JVM.
    # Require headroom for its manager, dashboard, filebeat and guest OS before cloning.
    if (any(vm['service'] == 'wazuh' for vm in plan['vms']) and enabled.get('wazuh', True)
            and int(configuration.get('memory', 0)) < 8192):
        raise ValueError('Wazuh requires a source template with at least 8192 MiB for the shared installer')


def preflight(plan, runtime, sources, template, tls, parent):
    validate_provisioning_context(plan, parent)
    from .release import verify_release, validate_collections
    if sources.parent.resolve() != runtime.parent.resolve():
        raise ValueError('Application and runtime inputs must belong to one locked release')
    verify_release(runtime.parent)
    validate_collections(runtime / 'collections')
    validate_controller_actions(runtime / 'range42-ansible_roles-proxmox_controller')
    validate_context_runtime(runtime / 'range42')
    validate_bundle_contracts(plan, runtime / 'range42-playbooks/bundles')
    active_bundles = Path(os.environ.get('RANGE42_BUNDLE_DIR', ''))
    validate_runtime_selection(active_bundles, runtime / 'range42-playbooks/bundles')
    validate_template(template, plan["id"])
    if any(parent.get('enabled', {}).get(service, True) for service in ('cli', 'backend')):
        validate_cli_workload(template)
    validate_tls(tls, plan["domain"])
    from .readiness import validate_dns
    enabled = parent.get('enabled', {})
    addresses = parent.get('gateway_addresses') or [node(plan, 'gateway')['ip']]
    if isinstance(addresses, str):
        addresses = json.loads(addresses)
    validate_dns({**plan, 'endpoints': {k: v for k, v in plan['endpoints'].items() if enabled.get(k, True)}}, addresses)
    if template.resolve().is_relative_to(runtime.resolve()) or template.resolve().is_relative_to(sources.resolve()):
        raise ValueError("Dedicated credentials must be outside the public exports")
    for directory in (runtime / repo for repo in ("range42-playbooks", "range42-catalog", "range42", "range42-ansible_roles-proxmox_controller")):
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", (directory / ".range42-revision").read_text().strip()):
            raise ValueError("Runtime components need exact revision markers")
    for repo in ("range42-backend-api", "range42-deployer-ui", "range42-reporting-tool"):
        directory = sources / repo
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", (directory / ".range42-revision").read_text().strip()):
            raise ValueError("Application sources need exact revision markers")
        if (directory / ".git").exists() or any(directory.rglob(".env")):
            raise ValueError("Use clean application exports, not live working directories")
    for service in (v["service"] for v in plan["vms"]):
        if service in {"gitea", "registry", "mattermost", "rocketchat", "nextcloud"}:
            payload = "gitea-registry" if service == "registry" else service
            if not (runtime / "range42-catalog/03_container_layer/docker/admin" / payload / "compose.yml").is_file():
                raise ValueError(f"The selected catalog release does not contain {service}")
    for bundle in ("sdn_network.bootstrap", "vm.bootstrap"):
        if not (runtime / "range42-playbooks/bundles/proxmox" / bundle / "main.yml").is_file():
            raise ValueError("The runtime needs the current SDN and VM bootstrap bundles")
    for path in (runtime / "collections", runtime / "ansible.cfg", runtime / "proxmox-ca.pem",
                 tls / "cert.pem", tls / "key.pem"):
        if not path.exists():
            raise ValueError("A required runtime or TLS input is missing")
    child = json.loads((template / "target.json").read_text())
    if (child['host']['node_name'] != plan['node'] or child['host'].get('default_bridge') != plan['bridge']
            or child['host']['api_url'].rstrip('/') != parent['url'].rstrip('/')):
        raise ValueError('Dedicated child target must match the planned cluster, node and VNet')
    if child["host"]["token_ref"] == parent["token"]:
        raise ValueError("The platform must not inherit its provisioner's Proxmox token")
    context = ssl.create_default_context(cafile=str(runtime / "proxmox-ca.pem"))
    child_permissions = request_json(child["host"]["api_url"].rstrip("/") + "/api2/json/access/permissions",
                                    "PVEAPIToken=" + child["host"]["token_ref"], context=context)["data"]
    validate_target_permissions(child_permissions, child["allowed_paths"])
    def get(path):
        return request_json(parent["url"].rstrip("/") + "/api2/json/" + path,
                            "PVEAPIToken=" + parent["token"], context=context)["data"]
    resources = get("cluster/resources?type=vm")
    for resource in resources:
        resource["config"] = get(f"nodes/{resource['node']}/{resource['type']}/{resource['vmid']}/config")
    templates = [r for r in resources if int(r['vmid']) == plan['vms'][0]['template_vmid']]
    if (len(templates) != 1 or templates[0]['node'] != plan['node']
            or int(templates[0]['config'].get('template', 0)) != 1):
        raise ValueError('The selected source template must exist on the planned Proxmox node')
    validate_template_capacity(plan, templates[0]['config'], enabled)
    vnets = get("cluster/sdn/vnets")
    subnets = [{**subnet, "vnet": vnet["vnet"]} for vnet in vnets
               for subnet in get(f"cluster/sdn/vnets/{vnet['vnet']}/subnets")]
    validate_live(plan, resources, vnets, get("cluster/sdn/zones"), subnets)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight"])
    for name in ("plan", "runtime", "sources", "template", "tls"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    preflight(json.loads(args.plan.read_text()), args.runtime, args.sources, args.template, args.tls, json.load(sys.stdin))


if __name__ == "__main__":
    main()
