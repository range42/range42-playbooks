# misp_star_lab

MISP star scenario: one instructor **hub** and one **spoke per team** (2 teams), one SDN vnet per team. Each VM runs the `misp-star` catalog element (`range42-catalog/03_container_layer/docker/admin/misp-star/`), and the spokes are paired to the hub by MISP sync. Everything goes through the shared bundle `bundles/admin/software.install.misp_star/` (see its README for the `.env` staging, the secrets and the pairing).

**The star IS the workload** of this scenario: always deployed, no `INSTALL` flag for it. The only optional part is the admin tier (Wazuh SIEM + agents on the 3 star VMs), behind `INSTALL_WAZUH`, like `misp_lab`.

This scenario is distinct from `misp_lab` (single `misp-standalone` VM). It started as a copy of `misp_lab`.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.


## Network architecture

```
Proxmox host (holds the .1 of every vnet, routes between them, SNAT to the outside)
 |
 +-- net142  192.168.142.0/24  admin
 |     +-- admin-misp-star-hub  .195  (VMID 1195)  instructor hub
 |     +-- admin-wazuh          .198  (VMID 1198)  SIEM server, optional
 |
 +-- net149  192.168.149.0/24  team-01
 |     +-- misp-star-spoke-01   .196  (VMID 1196)
 |
 +-- net150  192.168.150.0/24  team-02
       +-- misp-star-spoke-02   .197  (VMID 1197)

MISP sync: each spoke -> hub, HTTPS 443.
```

## VM details

| VM name               | VM ID | IP                | vnet     | Template                            | Role / gate              |
|-----------------------|-------|-------------------|----------|-------------------------------------|--------------------------|
| admin-misp-star-hub   | 1195  | 192.168.142.195   | `net142` | template-vm-medium-02-8g-64g (9232) | hub, always created      |
| misp-star-spoke-01    | 1196  | 192.168.149.196   | `net149` | template-vm-medium-02-8g-64g (9232) | team-01, always created  |
| misp-star-spoke-02    | 1197  | 192.168.150.197   | `net150` | template-vm-medium-02-8g-64g (9232) | team-02, always created  |
| admin-wazuh           | 1198  | 192.168.142.198   | `net142` | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`          |

Source of truth: `manifest/scenario_vms.json`. Project convention: the last 3 digits of the VMID match the last IP octet.

The wazuh slot is 1198, not misp_lab's 1187: 1187 / `192.168.142.187` already collides between `misp_lab` and `admin_services_lab` in `scenarios/_reserved.json`.

**Resource cost.** The star is 3 VMs from template 9232: 24 GB of RAM allocated on the node (3 x 8 GB), 2 vCPU each. `INSTALL_WAZUH=YES` adds one more VM from the same template: 32 GB allocated in total. Allocated is not used: measured on a test deployment (MISP v2.5.50 stack idle and healthy), each star VM used about 1.05 GB of RAM and 13 GB of disk.

## Feature flags

See `manifest/feature_flags.yml`. The only flag defaults to `NO`.

| Flag            | Effect                                                                     | Default |
|-----------------|----------------------------------------------------------------------------|---------|
| `INSTALL_WAZUH` | Deploy admin-wazuh (SIEM server) + the wazuh-agent on the 3 star VMs       | NO      |

The star pairing options are bundle parameters, set in `03_misp_star_lab_infrastructure/stage_01-vm_configure/misp-star.yml` as real YAML booleans: inter-team sharing off, team users can publish, sync logs quiet.

## Credentials: one seed for the whole star

The MISP secrets of the hub and of both spokes (`MISP_SALT`, the DB passwords, the admin, reader and writer passwords) come from one operator-editable seed, like the admin service bundles (nextcloud, rocketchat, gitea, mattermost): the catalog element `.env`, `$RANGE42_INVENTORY/03_container_layer/docker/admin/misp-star/.env`. If it is absent, the deploy copies `.env.example` to it; an existing `.env` is kept. Each star VM gets its own `.env` from that seed, with its own identity (mode, org, base URL, teams) written over it. This is a deliberate choice for a training lab. The bundle README ("Credentials") lists which keys come from the seed.

**Populate the catalog `.env` BEFORE running for stronger creds.** Each VM copies the seed once, at its first deploy; editing the seed afterwards changes nothing on a running star.

**Residual risk when the seed is not edited.** The hub and both team spokes then share the same static credentials, published in `.env.example` (admin `admin@misp.local` / `Admin1234!XYZ`, reader and writer of the same family). The hub admin is a MISP site admin, and the hub HTTPS port stays open from each spoke host even once armed (the sync path, see below). So root on a spoke, or anyone who can open the hub's 443, can log in to the hub as site admin and read the other team's data. The boundary between the teams then rests on the Proxmox firewall and MISP org scoping alone, and the published site-admin password bypasses org scoping on the hub. Edit the seed before the first deploy whenever the teams must not read each other's data.

## Team isolation: firewall declared, not armed

**Without an armed firewall, the teams reach each other.** The host routes between `net142`, `net149` and `net150`. Team isolation requires the Proxmox per-NIC firewall **armed** at all three levels: the datacenter switch, the guest switch and the card flag. `range42-context networks-firewall-on --scope scenario` sets all three. `-e FIREWALL_ARM_VMS=YES` at deploy sets only the guest switches and the card flags: on a node whose datacenter switch is off, it filters nothing until `firewall.enable.datacenter_and_nodes` (or `networks-firewall-on --scope proxmox`) runs. This scenario never arms by itself.

What the deploy declares (`_firewall/stage_02-post_vm_bootstrap.misp_star_rules.yml`, rules only, before the scenario-wide SSH stage):

- hub: IN 443 from `192.168.149.196` and `192.168.150.197` only (the spoke hosts, the sync path), IN 22 + 443 from `192.168.142.1` (the node);
- each spoke: IN 22 + 443 from the `.1` of its own vnet (the node, the jump host);
- `admin-wazuh` (1198), only with `INSTALL_WAZUH=YES`: IN 1514 (agent events) + 1515 (agent enrollment) from each star host (`192.168.142.195`, `192.168.149.196`, `192.168.150.197`), one `/32` per host;
- `ipfilter` on the `net0` of the 3 star VMs: the ipset `ipfilter-net0` holds the VM's own address and the option `ipfilter: 1` is set, so each star NIC may only send from its own address.

**Isolation once armed: 443 only.** Armed, a team cannot reach the other team's spoke on 443, and the spoke-to-hub 443 path is the only MISP path open between the vnets. **SSH (22) stays open between teams**: the next stage, `firewall.baseline.ssh_all_vms`, declares its own SSH accept on every VM of the manifest (open, or restricted to every scenario network), as in every other scenario. So the node-only SSH rules above add nothing while that baseline accept is there. Narrowing that is the shared subnet isolation work, not this scenario.

**Measured on a test deployment (Proxmox VE 9.2.21, fresh deploy with `INSTALL_WAZUH=YES`, then datacenter + node + the 4 guests armed).** Each probe is a new TCP connection with a 4 s timeout, from the VM itself; "dropped" means no answer at all.

| From \ to (port) | hub 443 | spoke 443 | any other star VM 22 | admin-wazuh 1514 / 1515 | admin-wazuh 443 / 55000 |
|---|---|---|---|---|---|
| spoke-01, spoke-02 | open | other spoke: **dropped (I1)** | open | open | dropped |
| hub | - | dropped | open | open | dropped |
| admin-wazuh | dropped | dropped | open | - | - |
| node (`.1` of each vnet) | open | open (from the spoke's own `.1`) | open | dropped | dropped |

- I1: spoke-01 and spoke-02 cannot open 443 on each other. Before arming, the same probes were open: the test detects reachability.
- I2: armed, both spokes call MISP `servers/testConnection` on their hub entry and get `status=1`.
- The Wazuh agents of the 3 star VMs were restarted while armed: each opened a new connection to 1198 on 1514 and the manager lists all 3 agents `Active`.
- SSH: 22 answers with the `sshd` banner between every pair of VMs, teams included, as described above. This matches what this README states.
- `admin-wazuh` 443 (the dashboard) and 55000 (the API) are dropped once armed, from the VMs and from the node: this scenario declares no rule for them.

The hub 443 sources are the spoke hosts (`/32`), not the team subnets: this is the narrowest source consistent with the design, because the spoke is the only host of a team that syncs. The rule matches the source address of the packet, so the `/32` alone means "a packet that claims this address". `ipfilter` binds each address to its NIC. Measured on a test deployment (armed): root on spoke-01 added `192.168.150.197` (spoke-02's address, another vnet) to its interface and opened 443 to the hub from it. Without `ipfilter`, the spoofed SYN reached the hub's NIC (the node's reverse-path filter is loose, `rp_filter=2`); the handshake never completes, because the hub answers the real spoke-02. With `ipfilter`, the spoofed SYN left the guest and was dropped on its own card, while spoke-01 still synced (`testConnection` `status=1`) and its Wazuh agent stayed connected.

Limits of `ipfilter` here: it filters only once armed, like every rule above. It covers the 3 star NICs, not `admin-wazuh` and not a VM that another scenario or an operator attaches to a team vnet later. The deploy only adds: an address already in an `ipfilter-net0` ipset stays there. The declare action only adds rules too: a hub deployed with older, wider sources keeps them until VM 1195 is rebuilt or the old rules are deleted by hand.

**Shared `alice` account.** `vm.bootstrap` gives the `alice` admin account the same SSH public key and the same password on every VM, with `NOPASSWD` sudo. With 22 open between teams even once armed, anyone who holds the `alice` key for a spoke can SSH to the hub as `alice` and become root there. Do not give the `alice` key to a team: team access is the MISP web account of its spoke. No private key is stored on the guests, so root on a spoke cannot use the `alice` key. Root on a spoke can read the salted `sha256crypt` hash of the shared password (in `/etc/shadow` and the cloud-init user-data): treat that password as exposed once a team holds root on a spoke, because the hash can be cracked offline. The cracked password does not open SSH to the hub only as long as the hub `sshd` keeps `PasswordAuthentication` off. Template 9232 sets that, not this scenario or any bundle, so a template change can silently open it. `su`, the Proxmox console and any other host that accepts the password stay exposed.

**Wazuh agents once armed.** With `INSTALL_WAZUH=YES`, the deploy declares 1514 and 1515 on `admin-wazuh` (1198) from each star host. These are the ports of the `software.install.wazuh-agent` role as the agent bundle calls it: events on `wazuh_managers[].port` 1514, and registration through the agent's own enrollment (`wazuh_agent_enrollment.enabled: 'yes'`, port 1515). The REST registration on 55000 runs only when enrollment is off, so the agents do not need 55000. `bundles/firewall/in_proxmox/firewall.baseline.wazuh_server_agents_access` declares 1514 + 55000, not 1515, so this scenario does not use it. Re-enrollment of an agent while armed was not tested: 1515 was shown open from the 3 star hosts, the enrollment itself ran before arming.

**SSH source list in restricted mode.** When the init chose `range42_fw_vm_ssh_sources`, `firewall.baseline.ssh_all_vms` restricts the SSH accept of every VM of this scenario to every network the manifest names: `192.168.140.0/24`, `192.168.142.0/24`, `192.168.149.0/24` and `192.168.150.0/24`. So a spoke accepts SSH from the other team's vnet. The manifest drives this list, not a flag. In open mode (the default) the accept is open to any source anyway.

The guest `ufw` that the bundle opens on each star VM (22 + the published MISP ports) is not a team isolation control: root on a spoke can disable it.

The firewall bundles that sweep the manifest (`firewall.report.status`, `firewall.baseline.ssh_all_vms`, `firewall.enable.vms`, `range42-context networks-firewall-on --scope scenario`) act on every manifest VM that runs on the node, `admin-wazuh` (1198) included when it runs.

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the four vnets. They are declared unconditionally: the star is the workload.

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the MISP star hub, the optional admin-wazuh |
| `net149` | `192.168.149.0/24` | `.1` | yes | the team-01 spoke (it builds its MISP image, so it needs the SNAT) |
| `net150` | `192.168.150.0/24` | `.1` | yes | the team-02 spoke (same) |

The vnet name follows the third octet of its subnet: `net143` carries `192.168.143.0/24`. The zone is `simple`, which means it is host-local - the Proxmox holds the `.1` of every subnet and routes between them, and outbound internet comes from the SNAT rule, not from the physical network knowing these ranges exist.

**It creates, it never deletes.** Each object is looked up first and only what is missing is written, so a second run is a no-op and an existing object is left alone. A vnet name is global to the cluster: deleting one here would take away a network other scenarios attach to. `misp_star_lab.delete_vms_only.sh` and `misp_star_lab.delete_all.sh` remove VMs (and the template) only. `misp_star_lab.delete_networks.sh` removes the vnets the manifest names, `net142` included, which around 14 other scenarios also use: do not run it on a shared node.

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


## Usage

```bash
range42-context use <codename> misp_star_lab
range42-context deploy

# add the Wazuh SIEM + agents on the star VMs :
./misp_star_lab.setup.sh -e INSTALL_WAZUH=YES

# arm the per-NIC firewall for team isolation on 443 :
range42-context networks-firewall-on --scope scenario
```

The workspace files `templates/ansible-inventory.j2` and `templates/ssh-config.j2` carry the 4 hosts. They are rendered at workspace init.

## More spokes

The topology is fixed at 2 teams. The `r42playbooks` generator cannot render this scenario shape yet (SDN vnets, `_firewall/`, feature flags, pinned slots); porting it is a separate issue. Until then, one more team means, by hand and in the same commit:

1. a vnet in `00_sdn_bootstrap/_main.yml` (`netNNN`, gateway `.1`, `snat: true`);
2. a VM entry in `manifest/scenario_vms.json`, then `scenarios/_regenerate_reserved.sh` and `scenarios/_check_reserved.sh`;
3. a `vm.bootstrap` block in `03_misp_star_lab_infrastructure/stage_00-vm_bootstrap/_misp_star_group.yml`;
4. an `add_host` with `misp_star_role: spoke` and a unique `misp_star_team` in `03_misp_star_lab_infrastructure/_build_misp_star_active_group.yml`;
5. in `_firewall/stage_02-post_vm_bootstrap.misp_star_rules.yml`: the hub 443 rule from the new spoke host (`/32`), the spoke's own rules, its two wazuh rules on 1198 (1514, 1515) and its `_star_ipfilter` entry;
6. the host in `templates/ansible-inventory.j2` (both groups), `templates/ssh-config.j2` and `02_admin_infrastructure/_build_wazuh_clients_active_group.yml`.

## Wrapper scripts

| Script                               | Action                                                                         |
|--------------------------------------|--------------------------------------------------------------------------------|
| `misp_star_lab.setup.sh`             | Run main.yml (template + star VMs + star stack + pairing + optional admin)     |
| `misp_star_lab.setup_vms_only.sh`    | Run main_vms_only.yml (skip template creation)                                 |
| `misp_star_lab.setup_networks.sh`    | Create the SDN objects declared in `00_sdn_bootstrap/_main.yml`                |
| `misp_star_lab.reset.setup.sh`       | Delete the manifest VMs + redeploy                                             |
| `misp_star_lab.reset.ssh_keys.sh`    | Clear `~/.ssh/known_hosts` for every IP in the manifest                        |
| `misp_star_lab.delete_vms_only.sh`   | Delete the manifest VMs (1195-1198), keep the template                         |
| `misp_star_lab.delete_all.sh`        | Delete the VMs + the shared template 9232 (WARNING - affects other scenarios)  |
| `misp_star_lab.delete_networks.sh`   | Delete the vnets the manifest names, `net142` included (WARNING - shared)      |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> misp_star_lab`.

Re-deploying a star VM: the bundle keeps each host's staged `.env` under `$RANGE42_ACTIVE_CONFIG_DIR/misp_star/<host>/`. After a VM is destroyed, delete that host's staged `.env` before the redeploy (the bundle README explains why); the new `.env` takes the current seed values.

## Structure

```
misp_star_lab/
  main.yml                            full deploy entrypoint (global stage discipline)
  main_vms_only.yml                   fast redeploy (skip templates)
  manifest/
    scenario_vms.json                 source of truth for VMID / IP / vnet
    feature_flags.yml                 INSTALL_WAZUH (default NO)
  README.md
  8 wrapper scripts (see table above)
  00_sdn_bootstrap/                   vnets net140 + net142 + net149 + net150
  01_templates-bootstrap/             Ubuntu noble cloud-init image + template 9232
  02_admin_infrastructure/            Optional admin-wazuh (gated INSTALL_WAZUH)
    _main.yml + _main_stage_00.yml + _main_stage_01.yml
    _build_admin_active_group.yml
    _build_wazuh_clients_active_group.yml   runtime group: the 3 star VMs
    stage_00-vm_bootstrap/_r42_admin_group.yml
    stage_01-vm_configure/
      _baseline_admin.yml
      admin-wazuh.yml                 thin wrapper to bundles/admin/software.install.wazuh/
      _finalize-baseline-admin_wazuh_client.yml
  03_misp_star_lab_infrastructure/    The MISP star (always created)
    _main.yml + _main_stage_00.yml + _main_stage_01.yml
    _build_misp_star_active_group.yml runtime group r42_misp_star_active (hub + spokes)
    stage_00-vm_bootstrap/_misp_star_group.yml   hub + 2 spokes (vm.bootstrap)
    stage_01-vm_configure/misp-star.yml          thin wrapper to bundles/admin/software.install.misp_star/
  _firewall/                          firewall wiring, one file per moment (see its README)
  templates/                          scenario-level j2 (inventory, ssh-config, ansible-vars, vault-example)
```
