# misp_lab_bundles

Single-VM scenario that delivers an Ubuntu LTS host with the Docker baseline
and deploys the misp-standalone docker-compose stack on it. Bundle-driven
shape (mirror of `kunai_lab_bundles` / `demo_lab_bundles`) with an optional
admin tier (Wazuh SIEM) gated by a feature flag.

The lab VM (`admin-misp-standalone`, VMID 1180, IP `192.168.142.180` on
`vmbr142`) is cloned from the project standard medium Ubuntu noble template
(VMID 9232 - 2cpu / 8gb RAM / 64gb disk).

**MISP IS the workload** of this scenario - always deployed via the shared
bundle `bundles/admin/software.install.misp-standalone/`. There is NO
`INSTALL_MISP` flag : if you don't want MISP, this is not the right scenario
(use `_init_lab` or a `blank_scenario_*` instead).

## Network architecture

```
                              +-----------------------+
                              |     Proxmox Host      |
                              +-----------+-----------+
                                          |
                                       vmbr142
                                    (admin band, 192.168.142.0/24)
                                          |
                         +----------------+----------------+
                         |                                 |
                  admin-misp-standalone .180        admin-wazuh .187 (optional)
                  (VMID 1180, MISP stack)            (VMID 1187, SIEM server)
```

## VM details

| VM Name                | VM ID | IP              | Bridge  | Template                            | Gated by         |
|------------------------|-------|-----------------|---------|-------------------------------------|------------------|
| admin-misp-standalone  | 1180  | 192.168.142.180 | vmbr142 | template-vm-medium-02-8g-64g (9232) | always created   |
| admin-wazuh            | 1187  | 192.168.142.187 | vmbr142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`  |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1180 -> .180, 1187 -> .187).

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                                                                  | Default |
|---------------------|---------------------------------------------------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on admin-misp-standalone                                          | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                                                                      | NO      |

There is NO `INSTALL_MISP` flag - MISP is the workload, always deployed.

## Usage

```bash
range42-context use <codename> misp_lab
range42-context deploy

# enable Wazuh SIEM on top of the MISP stack :
./misp_lab_bundles.setup.sh -e INSTALL_WAZUH=YES
```

## Wrapper scripts

| Script                                          | Action                                                              |
|-------------------------------------------------|---------------------------------------------------------------------|
| `misp_lab_bundles.setup.sh`                     | Run main playbook (template + VM + MISP stack + optional admin)     |
| `misp_lab_bundles.setup_vms_only.sh`            | Run main_vms_only.yml (skip template creation)                      |
| `misp_lab_bundles.reset.setup.sh`               | Delete + redeploy VMs                                               |
| `misp_lab_bundles.reset.ssh_keys.sh`            | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `misp_lab_bundles.delete_vms_only.sh`           | Delete VMs only, keep template                                      |
| `misp_lab_bundles.delete_all.sh`                | Delete VMs + shared template 9232 (WARNING - affects other scenarios) |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> misp_lab`.

## Structure

```
misp_lab_bundles/
  main.yml                            full deploy entrypoint (global stage discipline)
  main_vms_only.yml                   fast redeploy (skip templates)
  manifest/
    scenario_vms.json                 source of truth for VMID / IP / bridge
    feature_flags.yml                 INSTALL_WAZUH (default NO) + INSTALL_TAILSCALE
  README.md
  6 wrapper scripts (see table above)
  01_templates-bootstrap/             Ubuntu noble cloud-init image + template 9232
  02_admin_infrastructure/            Optional admin-wazuh (gated INSTALL_WAZUH)
    _main.yml + _main_stage_00.yml + _main_stage_01.yml
    _build_admin_active_group.yml
    _build_wazuh_clients_active_group.yml
    stage_00-vm_bootstrap/_r42_admin_group.yml
    stage_01-vm_configure/
      _baseline_admin.yml
      admin-wazuh.yml                 thin wrapper to bundles/admin/software.install.wazuh/
      _finalize-baseline-admin_wazuh_client.yml
  03_misp_lab_infrastructure/         The MISP lab VM (always created)
    _main.yml + _main_stage_00.yml + _main_stage_01.yml
    stage_00-vm_bootstrap/misp_lab_vm.yml
    stage_01-vm_configure/
      _r42_misp_lab_group.yml         basics + dotfiles + firewall (22/80/443)
      misp-standalone.yml             thin wrapper to bundles/admin/software.install.misp-standalone/
  templates/                          scenario-level j2 (inventory, ssh-config, ansible-vars, vault-example)
```

## Notes

- The admin tier is OPTIONAL. With `INSTALL_WAZUH=NO` (default), only the MISP VM is created and the admin tier plays skip silently.
- When `INSTALL_WAZUH=YES`, the wazuh-agent is installed on `admin-misp-standalone` (the lab VM) via the cross-tier finalize at the top of `main.yml`.
- The shared misp-standalone bundle handles `.env` materialization on the VM via `pre_tasks` (copies `.env.example` to `/home/alice/misp-standalone/.env` with `force: false`). Operator should customize the catalog `.env` before deploy for strong secrets.
