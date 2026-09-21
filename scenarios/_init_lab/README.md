# _init_lab

Shared init scenario : it builds **every VM template the project declares** on the templating vnet, then deploys 5 small init VMs on 2 subnets (net143 + net144) plus an admin platform of 9 admin VMs, every one gated by its feature flag. Same shape as `blank_scenario_2_subnets`, the SDN pilot, which served as its model.

**Formerly the bridge-based `_init_lab`** (its own template playbooks on `vmbr140`, five init VMs on `vmbr142`) : rebuilt on the SDN pilot's shape on 2026-09-21, same purpose, same init vm_ids 900 to 904. The templates now come from the shared bundles `template.build.ubuntu_noble` and `template.build.alpine`, exactly as every other scenario builds them.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## Network architecture

```
                              +-----------------------+
                              |     Proxmox Host      |
                              +-----------+-----------+
                                          |
              +---------------+-----------+-----------+
              |               |                       |
           net142          net143                net144
        (admin band)    (init subnet 1)        (init subnet 2)
              |               |                       |
   +----------+-------+   +---+---+               +---+---+
   |        admin     |   | init  |               | init  |
   | wazuh    .90 *   |   | 143.90|               | 144.93|
   | misp     .94 *   |   | 143.91|               | 144.94|
   | deployer-* .91   |   | 143.92|               +-------+
   | deployer-* .92   |   +-------+
   | deployer-* .93   |
   +------------------+
       * optional (INSTALL_WAZUH / INSTALL_MISP, default NO)
```

## VM details

| VM Name                              | VM ID | IP              | Bridge  | Template                            | Gated by         |
|--------------------------------------|-------|-----------------|---------|-------------------------------------|------------------|
| init-vm-00                           | 900   | 192.168.143.90  | net143  | template-vm-small-01-4g-32g (9221)  | always created   |
| init-vm-01                           | 901   | 192.168.143.91  | net143  | template-vm-small-01-4g-32g (9221)  | always created   |
| init-vm-02                           | 902   | 192.168.143.92  | net143  | template-vm-small-01-4g-32g (9221)  | always created   |
| init-vm-03                           | 903   | 192.168.144.93  | net144  | template-vm-small-01-4g-32g (9221)  | always created   |
| init-vm-04                           | 904   | 192.168.144.94  | net144  | template-vm-small-01-4g-32g (9221)  | always created   |
| init-admin-deployer-api-gateway      | 991   | 192.168.142.91  | net142  | template-vm-small-01-4g-32g (9221)  | `INSTALL_DEPLOYER_UI` |
| init-admin-deployer-api-backend      | 992   | 192.168.142.92  | net142  | template-vm-small-01-4g-32g (9221)  | `INSTALL_DEPLOYER_UI` |
| init-admin-deployer-ui               | 993   | 192.168.142.93  | net142  | template-vm-small-01-4g-32g (9221)  | `INSTALL_DEPLOYER_UI` |
| init-admin-wazuh                     | 990   | 192.168.142.90  | net142  | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH` |
| init-admin-misp                      | 994   | 192.168.142.94  | net142  | template-vm-medium-02-8g-64g (9232) | `INSTALL_MISP` |
| init-admin-gitea                     | 995   | 192.168.142.95  | net142  | template-vm-medium-02-8g-64g (9232) | `INSTALL_GITEA` |
| init-admin-mattermost                | 996   | 192.168.142.96  | net142  | template-vm-medium-02-8g-64g (9232) | `INSTALL_MATTERMOST` |
| init-admin-nextcloud                 | 997   | 192.168.142.97  | net142  | template-vm-medium-02-8g-64g (9232) | `INSTALL_NEXTCLOUD` |
| init-admin-rocketchat                | 998   | 192.168.142.98  | net142  | template-vm-medium-02-8g-64g (9232) | `INSTALL_ROCKETCHAT` |

Source of truth : `manifest/scenario_vms.json`.

## Templates built by this scenario

`01_templates-bootstrap/` imports the shared bundles with **no whitelist** : every template of the manifest is built, on `net140`. That is what this scenario is for - a fresh hypervisor gets its full template set in one deployment, before any lab is deployed on it. A template already finalized is left as-is, so on a host that has them all the stage is a no-op.

| Template | VM ID | Spec | Bundle |
|---|---|---|---|
| template-vm-nano | 9901 | 1cpu/1gb/16gb | template.build.ubuntu_noble |
| template-vm-micro-01-2g-24g | 9211 | 1cpu/2gb/24gb | template.build.ubuntu_noble |
| template-vm-micro-02-2g-24g | 9212 | 1cpu/2gb/24gb | template.build.ubuntu_noble |
| template-vm-small-01-4g-32g | 9221 | 1cpu/4gb/32gb | template.build.ubuntu_noble |
| template-vm-small-02-4g-32g | 9222 | 1cpu/4gb/32gb | template.build.ubuntu_noble |
| template-vm-small-04-4g-32g | 9224 | 1cpu/4gb/32gb | template.build.ubuntu_noble |
| template-vm-medium-02-8g-64g | 9232 | 2cpu/8gb/64gb | template.build.ubuntu_noble |
| template-vm-medium-04-8g-64g | 9234 | 4cpu/8gb/64gb | template.build.ubuntu_noble |
| template-vm-medium-06-8g-64g | 9236 | 6cpu/8gb/64gb | template.build.ubuntu_noble |
| template-vm-large-04-8g-64g | 9244 | 4cpu/8gb/64gb | template.build.ubuntu_noble |
| template-vm-large-06-8g-64g | 9246 | 6cpu/8gb/64gb | template.build.ubuntu_noble |
| template-vm-large-08-8g-64g | 9248 | 8cpu/8gb/64gb | template.build.ubuntu_noble |
| template-vm-alpine-nano | 9903 | 1cpu/512mb/4gb | template.build.alpine |

The image download that precedes the build is asynchronous on the Proxmox side : on a host that has never downloaded an image, the build that follows may not find the file yet and the stage stops there. Deploy again once the image is on the host ; the templates already built are skipped.

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                          | Default |
|---------------------|-----------------------------------------------------------------|---------|
| `INSTALL_WAZUH`      | Deploy admin-wazuh SIEM + wazuh-agent on every deployed client VM (13 potential) | NO |
| `INSTALL_MISP`       | Deploy admin-misp (docker-compose stack)                       | NO      |
| `INSTALL_DEPLOYER_UI`| Deploy the deployer trio (api-gateway, api-backend, ui)        | NO      |
| `INSTALL_GITEA`      | Deploy admin-gitea (docker-compose stack)                      | NO      |
| `INSTALL_MATTERMOST` | Deploy admin-mattermost (docker-compose stack)                 | NO      |
| `INSTALL_NEXTCLOUD`  | Deploy admin-nextcloud (docker-compose stack)                  | NO      |
| `INSTALL_ROCKETCHAT` | Deploy admin-rocketchat (docker-compose stack)                 | NO      |
| `INSTALL_TAILSCALE`  | Tailscale VPN client on admin tier                             | NO      |

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the four vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the admin tier |
| `net143` | `192.168.143.0/24` | `.1` | yes | init subnet 1 (the team tier of this scenario) |
| `net144` | `192.168.144.0/24` | `.1` | yes | init subnet 2 |

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
range42-context use <codename> _init_lab
range42-context deploy

# enable Wazuh SIEM :
./_init_lab.setup.sh -e INSTALL_WAZUH=YES

# enable both Wazuh + MISP (MISP requires .env populated in the catalog
# before this command - see admin-misp.yml documentation) :
./_init_lab.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script                                                          | Action                                                              |
|-----------------------------------------------------------------|---------------------------------------------------------------------|
| `_init_lab.setup.sh`                     | Run main playbook (templates + VMs + optional admin)                |
| `_init_lab.setup_vms_only.sh`            | Run main_vms_only.yml (skip template creation)                      |
| `_init_lab.reset.setup.sh`               | Delete + redeploy VMs                                               |
| `_init_lab.reset.ssh_keys.sh`            | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `_init_lab.delete_vms_only.sh`           | Delete VMs only, keep templates                                     |
| `_init_lab.delete_all.sh`                | Delete VMs + templates (WARNING - affects other scenarios)          |
| `_init_lab.setup_networks.sh`            | Create the SDN zone, vnets and subnets declared in `00_sdn_bootstrap/_main.yml` (`--dry-run` compares without writing) |
| `_init_lab.delete_networks.sh`           | Remove those subnets and vnets - the shared zone is kept            |

## Verification

Not deployed yet in this shape. The first deployment on a host that already holds the templates should show the thirteen templates skipped, the five init VMs up on `net143` and `net144` and reached over SSH through the Proxmox jump host, and the admin tier skipped by its flags.
