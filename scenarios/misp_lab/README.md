# misp_lab

Single-VM scenario that delivers an Ubuntu LTS host with the Docker baseline
and deploys the misp-standalone docker-compose stack on it. Bundle-driven
shape (mirror of `kunai_lab` / `demo_lab`) with an optional
admin tier (Wazuh SIEM) gated by a feature flag.

The lab VM (`admin-misp-standalone`, VMID 1180, IP `192.168.142.180` on
`net142`) is cloned from the project standard medium Ubuntu noble template
(VMID 9232 - 2cpu / 8gb RAM / 64gb disk).

**MISP IS the workload** of this scenario - always deployed via the shared
bundle `bundles/admin/software.install.misp_standalone/`. There is NO
`INSTALL_MISP` flag : if you don't want MISP, this is not the right scenario
(use `_init_lab` or a `blank_scenario_*` instead).

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## Network architecture

```
                              +-----------------------+
                              |     Proxmox Host      |
                              +-----------+-----------+
                                          |
                                       net142
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
| admin-misp-standalone  | 1180  | 192.168.142.180 | net142 | template-vm-medium-02-8g-64g (9232) | always created   |
| admin-wazuh            | 1187  | 192.168.142.187 | net142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`  |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1180 -> .180, 1187 -> .187).

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                                                                  | Default |
|---------------------|---------------------------------------------------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on admin-misp-standalone                                          | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                                                                      | NO      |

There is NO `INSTALL_MISP` flag - MISP is the workload, always deployed.

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the two vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the admin and misp-lab tiers |

The vnet name follows the third octet of its subnet: `net143` carries `192.168.143.0/24`. The zone is `simple`, which means it is host-local - the Proxmox holds the `.1` of every subnet and routes between them, and outbound internet comes from the SNAT rule, not from the physical network knowing these ranges exist.

**It creates, it never deletes.** Each object is looked up first and only what is missing is written, so a second run is a no-op and an existing object is left alone. A vnet name is global to the cluster: deleting one here would take away a network other scenarios attach to. The delete scripts of this scenario remove VMs only.

**The order is not a preference.** `net140` is the templating network and the template build runs `apt`. Without a live SNAT rule there, the templates come out empty and out of date - so a template tier that runs first produces broken templates.

## Migrating from the bridge-based scenarios

A `vmbrNNN` bridge and a `netNNN` vnet **cannot both carry the same `.1`**. If they do, the host resolves the route to the bridge, where no VM is attached, and ARPs into the void. Everything looks correct - the zone, the vnet, the subnet, the gateway and the SNAT rule are all there and stay there - but:

- SSH to the VM fails with `No route to host`, which reads like a timeout;
- the VM cannot reach the internet, because the NATed reply comes back and is lost the same way;
- cloud-init ends `degraded` after several minutes of network timeouts.

**No API check can see this.** The declaration is valid; the fault is in the host's routing table. The one command that tells you:

```bash
ip route get <the_vm_ip>      # must answer `dev netXXX`, not `dev vmbrXXX`
```

**So the switch to SDN is atomic per hypervisor.** Before deploying this scenario, the VMs of every bridge-based scenario using these ranges must be deleted and their `vmbrNNN` bridges freed. There is no gradual coexistence and no partial rollback.

While the bridge-creating tooling is still in place, `00_sdn_bootstrap/` imports the `proxmox/legacy_bridge.workaround.shadowed_subnet` bundle, which removes the duplicate address from the conflicting bridges - the address only, nothing written to disk, so `ifreload -a` puts it back. It refuses to run if a live VM is still attached to one of those bridges, rather than cutting that VM off mid-deployment. Skip it with `-e BUNDLE_LEGACY_SKIP=true` once the bridges are gone for good.

To clear those lines from the disk for good, so no `ifreload` can restore them, run `range42-context networks-legacy-clean` once - a migration step, not routine maintenance.

## Subnet isolation

**Not implemented yet.** Today the subnets reach each other: the host holds a gateway in each and routes between them. That is the expected state of this scenario, not a defect - a VM in `net143` can open a connection to a VM in `net144`.

Isolating them is a firewall matter, not a topology one: putting each vnet in its own zone would change nothing, because the host would still route. The work is in progress and will use per-NIC filtering with address sets, so that team subnets are isolated from each other while the deployer keeps reaching the VMs it manages - without that exception, no deployment could run at all.

## Usage

```bash
range42-context use <codename> misp_lab
range42-context deploy

# enable Wazuh SIEM on top of the MISP stack :
./misp_lab.setup.sh -e INSTALL_WAZUH=YES
```

## Wrapper scripts

| Script                                          | Action                                                              |
|-------------------------------------------------|---------------------------------------------------------------------|
| `misp_lab.setup.sh`                     | Run main playbook (template + VM + MISP stack + optional admin)     |
| `misp_lab.setup_vms_only.sh`            | Run main_vms_only.yml (skip template creation)                      |
| `misp_lab.reset.setup.sh`               | Delete + redeploy VMs                                               |
| `misp_lab.reset.ssh_keys.sh`            | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `misp_lab.delete_vms_only.sh`           | Delete VMs only, keep template                                      |
| `misp_lab.delete_all.sh`                | Delete VMs + shared template 9232 (WARNING - affects other scenarios) |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> misp_lab`.

## Structure

```
misp_lab/
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
      misp-standalone.yml             thin wrapper to bundles/admin/software.install.misp_standalone/
  templates/                          scenario-level j2 (inventory, ssh-config, ansible-vars, vault-example)
```

## Notes

- The admin tier is OPTIONAL. With `INSTALL_WAZUH=NO` (default), only the MISP VM is created and the admin tier plays skip silently.
- When `INSTALL_WAZUH=YES`, the wazuh-agent is installed on `admin-misp-standalone` (the lab VM) via the cross-tier finalize at the top of `main.yml`.
- The shared misp-standalone bundle handles `.env` materialization on the VM via `pre_tasks` (copies `.env.example` to `/home/alice/misp-standalone/.env` with `force: false`). Operator should customize the catalog `.env` before deploy for strong secrets.
