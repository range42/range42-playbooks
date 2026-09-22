# blank_scenario_4_subnets

Multi-subnet lab with 16 team VMs on 4 subnets (net143-146, 4 VMs per subnet)
plus an admin platform (3 always-on deployer VMs + 2 optional admin VMs gated
by feature flags). Bundle-driven shape (mirror of `blank_scenario_2_subnets`).

> Admin subnet uses dense IPs `.130-.134` on `192.168.142.0/24` (vs bs2's
> `.120-.124`, bs6's `.140-.144`). All three blank scenarios use non-overlapping
> admin IP ranges, so they can be deployed in parallel on the same Proxmox host.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## VM details (21 VMs)

| Tier | VM Name | VM ID | IP | Bridge | Template | Gated by |
|---|---|---|---|---|---|---|
| team | bs4-team-143-01..04 | 4001-4004 | 192.168.143.210-213 | net143 | small-01 (9221) | always |
| team | bs4-team-144-01..04 | 4005-4008 | 192.168.144.210-213 | net144 | small-01 (9221) | always |
| team | bs4-team-145-01..04 | 4009-4012 | 192.168.145.210-213 | net145 | small-01 (9221) | always |
| team | bs4-team-146-01..04 | 4013-4016 | 192.168.146.210-213 | net146 | small-01 (9221) | always |
| admin | bs4-admin-deployer-api-gateway | 4131 | 192.168.142.131 | net142 | small-01 (9221) | always |
| admin | bs4-admin-deployer-api-backend | 4132 | 192.168.142.132 | net142 | small-01 (9221) | always |
| admin | bs4-admin-deployer-ui | 4133 | 192.168.142.133 | net142 | small-01 (9221) | always |
| admin | bs4-admin-wazuh | 4130 | 192.168.142.130 | net142 | medium-02 (9232) | `INSTALL_WAZUH` |
| admin | bs4-admin-misp | 4134 | 192.168.142.134 | net142 | medium-02 (9232) | `INSTALL_MISP` |

Source of truth : `manifest/scenario_vms.json`.

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                            | Default |
|---------------------|-------------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on the 19 non-server VMs    | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                          | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                                | NO      |

## Behavior change vs legacy `blank_scenario_4_subnets`

The legacy scenario created `bs4-admin-wazuh` unconditionally. The `_bundles`
variant gates this behind `INSTALL_WAZUH=YES` (default `NO`). Operator who
wants the OLD behavior must pass `-e INSTALL_WAZUH=YES`.

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the six vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the admin tier |
| `net143` | `192.168.143.0/24` | `.1` | yes | team subnet 1 |
| `net144` | `192.168.144.0/24` | `.1` | yes | team subnet 2 |
| `net145` | `192.168.145.0/24` | `.1` | yes | team subnet 3 |
| `net146` | `192.168.146.0/24` | `.1` | yes | team subnet 4 |

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
range42-context use <codename> blank_scenario_4_subnets
range42-context deploy

# enable Wazuh SIEM :
./blank_scenario_4_subnets.setup.sh -e INSTALL_WAZUH=YES

# enable both :
./blank_scenario_4_subnets.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script | Action |
|---|---|
| `blank_scenario_4_subnets.setup.sh` | Full deploy (templates + VMs + optional admin) |
| `blank_scenario_4_subnets.setup_vms_only.sh` | VMs only (skip templates) |
| `blank_scenario_4_subnets.reset.setup.sh` | Delete + redeploy |
| `blank_scenario_4_subnets.reset.ssh_keys.sh` | Clear known_hosts for manifest IPs |
| `blank_scenario_4_subnets.delete_vms_only.sh` | Delete VMs only, keep templates |
| `blank_scenario_4_subnets.delete_all.sh` | Delete VMs + templates (WARNING - shared) |
