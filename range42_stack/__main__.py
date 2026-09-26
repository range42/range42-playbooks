"""Export a reviewable native Range42 platform scenario without deploying it.

Example:
  python3 -m range42_stack --spec stack.json --output scenarios/range42_alpha

Deploy the export through the normal range42-context/native-scenario workflow,
using a pinned checkout matching the reviewed runtime bundles and helpers. Supply these Ansible inputs:
  stack_staging_dir: persistent private controller directory (0700), retained with its secrets
  stack_source_dir: clean application exports (backend-api, deployer-ui, reporting-tool)
  stack_runtime_dir: reviewed runtime export, collections, ansible.cfg and proxmox-ca.pem
  stack_credential_template_dir: dedicated private child credentials, outside both exports
  stack_tls_dir: cert.pem and key.pem for *.<stack domain>
  stack_management_cidrs: trusted SSH source networks (including the provisioner/jump host)
  stack_provisioning_api_url: provisioner's HTTPS Proxmox URL, including port 8006
  stack_proxmox_ssh_host / stack_proxmox_ssh_user: optional provisioner SSH overrides
  stack_wazuh_certs_dir: private controller directory for per-stack Wazuh certificates (full preset)

Create the source/runtime exports together with python3 -m range42_stack.release.
Preflight verifies release.lock.json and every exported file, plus DNS and TLS. The private template follows the backend's existing template
contract: secrets/default_vault.yml, secrets/vault_pass.txt, optional ssh_keys/,
and additionally stack.json {"stack_id":"alpha"}, cli.json {"scenario":"workload-name"},
workload/ (reviewed main.yml, hosts.yml, and inventory/SSH templates), and target.json:
  {"host":{"name":"alpha","api_url":"https://pve.example:8006","node_name":"pve",
   "default_bridge":"r42alpha","token_ref":"<dedicated child token>"},
   "allowed_paths":["/pool/r42-alpha","/storage/local-lvm","/nodes/pve"],
   "sources":[<optional catalog source registration objects>]}
Omit sources to register the backend's canonical public catalog/playbooks sources.
Set sources explicitly when the selected release uses different branches or credentials.
For the native UI's scalar parameters, pass CIDR lists as JSON-encoded strings.
All template directories must be 0700 and files 0600. The child token must be
different from the provisioning token, and its effective privileges must stay
within the declared paths. MISP is unavailable without its catalog payload;
EMP remains a preview. Neither is silently counted as installed.

Exports refuse to overwrite an existing directory. --peer checks other stack
plans on the same cluster; deployment checks live ownership again. Application
installation uses the shared bundles; INSTALL_<NAME>=YES|NO flags control software
installation on the reserved VMs. Changing releases requires an explicit upgrade.
Both entry points configure applications and firewalls; the source template must
already exist on the selected node. CPU, RAM and disk are inherited from that
template. FIREWALL_ARM_VMS defaults to NO, matching the shared scenario convention;
guest isolation rules are applied before application startup. Lifecycle entrypoints stop.yml/start.yml/checkpoint.yml/backup.yml/restore.yml/rollback.yml/teardown.yml
require stack_confirm_id matching this stack. Stop all stack VMs before checkpoints, backups,
rollback or teardown. stack_backup_dir and stack_checkpoint select the checkpoint.
backup.yml uses full Proxmox backups plus private controller state; state-only archives
do not include databases or attachments. Restore requires absent VMIDs. Network teardown
uses the shared SDN apply bundle and removes only this stack's outbound NAT rules.
Use range42_stack.lifecycle backup-state/restore-state for private state and
authorize-upgrade with a matching prior state backup before staging a new release.
"""
import argparse
import json
from pathlib import Path

from .plan import build_plan
from .scenario import export_scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--peer", action="append", default=[], type=Path,
                        help="Another exported manifest/stack.json on the same cluster; repeatable")
    args = parser.parse_args()
    try:
        plan = build_plan(json.loads(args.spec.read_text()), [json.loads(path.read_text()) for path in args.peer])
        export_scenario(plan, args.output)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Cannot export platform: {error}\n")
    print(f"Exported {plan['profile']} platform {plan['id']}: {len(plan['vms'])} VMs in {args.output}")


if __name__ == "__main__":
    main()
