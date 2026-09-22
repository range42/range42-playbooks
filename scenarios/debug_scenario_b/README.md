# debug_scenario_b

Minimal debug/dev scenario - 1 Alpine VM on 1 subnet. Same shape as
debug_scenario_a but on a different subnet (net148), used to verify
multi-scenario coexistence on a single Proxmox. Bundle-driven shape (mirror
of `kunai_lab` / `demo_lab`) with optional admin tier (Wazuh
SIEM + MISP threat intel) gated by feature flags.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## Network architecture

```
                              +-----------------------+
                              |     Proxmox Host      |
                              +-----------+-----------+
                                          |
                          +---------------+---------------+
                          |                               |
                       net142                         net148
                    (admin band)                      (debug B)
                          |                               |
                  +-------+--------+              +-------+--------+
                  | 192.168.142/24 |              | 192.168.148/24 |
                  |                |              |                |
                  | admin-wazuh .155 (optional)   | dsb-vm-01 .250 |
                  | admin-misp  .156 (optional)   |                |
                  +----------------+              +----------------+
```

## VM details

| VM Name      | VM ID | IP              | Bridge  | Template                            | Gated by         |
|--------------|-------|-----------------|---------|-------------------------------------|------------------|
| dsb-vm-01    | 8501  | 192.168.148.250 | net148 | template-vm-alpine-nano (9903)      | always created   |
| admin-wazuh  | 8550  | 192.168.142.155 | net142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`  |
| admin-misp   | 8551  | 192.168.142.156 | net142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_MISP`   |

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                    | Default |
|---------------------|-----------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on dsb-vm-01        | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                  | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                        | NO      |

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the three vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the optional admin tier |
| `net148` | `192.168.148.0/24` | `.1` | yes | the debug VM |

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
range42-context use <codename> debug_scenario_b
range42-context deploy

# enable Wazuh SIEM :
./debug_scenario_b.setup.sh -e INSTALL_WAZUH=YES

# enable both Wazuh + MISP (MISP requires .env populated in the catalog
# before this command - see admin-misp.yml documentation) :
./debug_scenario_b.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script                                            | Action                                                              |
|---------------------------------------------------|---------------------------------------------------------------------|
| `debug_scenario_b.setup.sh`               | Run main playbook (templates + VMs + optional admin)                |
| `debug_scenario_b.setup_vms_only.sh`      | Run main_vms_only.yml (skip template creation)                      |
| `debug_scenario_b.reset.setup.sh`         | Delete + redeploy VMs                                               |
| `debug_scenario_b.reset.ssh_keys.sh`      | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `debug_scenario_b.delete_vms_only.sh`     | Delete VMs only, keep templates                                     |
| `debug_scenario_b.delete_all.sh`          | Delete VMs + templates (alpine-nano 9903 + medium 9232)             |
