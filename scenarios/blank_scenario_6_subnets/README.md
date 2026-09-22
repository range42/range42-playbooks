# blank_scenario_6_subnets

Multi-subnet lab with 24 team VMs on 6 subnets (net143-148, 4 VMs per subnet)
plus an admin platform (3 always-on deployer VMs + 2 optional admin VMs gated
by feature flags). Bundle-driven shape (mirror of `blank_scenario_4_subnets`).

> Admin subnet uses dense IPs `.140-.144` on `192.168.142.0/24` (vs bs2's
> `.120-.124`, bs4's `.130-.134`). All three blank scenarios use non-overlapping
> admin IP ranges, so they can be deployed in parallel on the same Proxmox host.
>
> bs6 is the only blank sibling using net147 + net148. These bridges are
> also used by `debug_scenario_a` (.147.250) and `debug_scenario_b` (.148.250) ;
> bs6 team IPs are .220-.223 so no collision with the debug scenarios.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## VM details (29 VMs)

| Tier | VM Name | VM ID | IP | Bridge | Template | Gated by |
|---|---|---|---|---|---|---|
| team | bs6-team-143-01..04 | 6001-6004 | 192.168.143.220-223 | net143 | small-01 (9221) | always |
| team | bs6-team-144-01..04 | 6005-6008 | 192.168.144.220-223 | net144 | small-01 (9221) | always |
| team | bs6-team-145-01..04 | 6009-6012 | 192.168.145.220-223 | net145 | small-01 (9221) | always |
| team | bs6-team-146-01..04 | 6013-6016 | 192.168.146.220-223 | net146 | small-01 (9221) | always |
| team | bs6-team-147-01..04 | 6017-6020 | 192.168.147.220-223 | net147 | small-01 (9221) | always |
| team | bs6-team-148-01..04 | 6021-6024 | 192.168.148.220-223 | net148 | small-01 (9221) | always |
| admin | bs6-admin-deployer-api-gateway | 6141 | 192.168.142.141 | net142 | small-01 (9221) | always |
| admin | bs6-admin-deployer-api-backend | 6142 | 192.168.142.142 | net142 | small-01 (9221) | always |
| admin | bs6-admin-deployer-ui | 6143 | 192.168.142.143 | net142 | small-01 (9221) | always |
| admin | bs6-admin-wazuh | 6140 | 192.168.142.140 | net142 | medium-02 (9232) | `INSTALL_WAZUH` |
| admin | bs6-admin-misp | 6144 | 192.168.142.144 | net142 | medium-02 (9232) | `INSTALL_MISP` |

Source of truth : `manifest/scenario_vms.json`.

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                            | Default |
|---------------------|-------------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on the 27 non-server VMs    | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                          | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                                | NO      |

## Behavior change vs legacy `blank_scenario_6_subnets`

The legacy scenario created `bs6-admin-wazuh` unconditionally. The `_bundles`
variant gates this behind `INSTALL_WAZUH=YES` (default `NO`). Operator who
wants the OLD behavior must pass `-e INSTALL_WAZUH=YES`.

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the eight vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the admin tier |
| `net143` | `192.168.143.0/24` | `.1` | yes | team subnet 1 |
| `net144` | `192.168.144.0/24` | `.1` | yes | team subnet 2 |
| `net145` | `192.168.145.0/24` | `.1` | yes | team subnet 3 |
| `net146` | `192.168.146.0/24` | `.1` | yes | team subnet 4 |
| `net147` | `192.168.147.0/24` | `.1` | yes | team subnet 5 |
| `net148` | `192.168.148.0/24` | `.1` | yes | team subnet 6 |

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
range42-context use <codename> blank_scenario_6_subnets
range42-context deploy

# enable Wazuh SIEM :
./blank_scenario_6_subnets.setup.sh -e INSTALL_WAZUH=YES

# enable both :
./blank_scenario_6_subnets.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script | Action |
|---|---|
| `blank_scenario_6_subnets.setup.sh` | Full deploy (templates + VMs + optional admin) |
| `blank_scenario_6_subnets.setup_vms_only.sh` | VMs only (skip templates) |
| `blank_scenario_6_subnets.reset.setup.sh` | Delete + redeploy |
| `blank_scenario_6_subnets.reset.ssh_keys.sh` | Clear known_hosts for manifest IPs |
| `blank_scenario_6_subnets.delete_vms_only.sh` | Delete VMs only, keep templates |
| `blank_scenario_6_subnets.delete_all.sh` | Delete VMs + templates (WARNING - shared) |
