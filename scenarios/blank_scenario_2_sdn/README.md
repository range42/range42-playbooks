# blank_scenario_2_sdn

Multi-subnet lab with 4 team VMs on 2 subnets (net143 + net144) plus an admin platform (3 always-on deployer VMs + 2 optional admin VMs gated by feature flags). Bundle-driven shape (mirror of `kunai_lab` / `demo_lab`).

**The SDN variant of `blank_scenario_2_subnets`**: same 13 VMs, same vm_ids, same IPs, same VM names. The two differ by their network layer and nothing else - `vmbrXXX` bridges there, Proxmox SDN vnets here. That is what makes them comparable.

## Read this before deploying

**It is mutually exclusive with `blank_scenario_2_subnets`.** Identical vm_ids (`2001-2004`, `2120-2128`) and identical IPs, so the two cannot coexist on one hypervisor. Delete the VMs of one before deploying the other.

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
        (admin band)     (team subnet 1)        (team subnet 2)
              |               |                       |
   +----------+-------+   +---+---+               +---+---+
   |        admin     |   |  team |               |  team |
   | wazuh   .120 *   |   | 143.200|              | 144.200|
   | misp    .124 *   |   | 143.201|              | 144.201|
   | deployer-* .121  |   +-------+               +-------+
   | deployer-* .122  |
   | deployer-* .123  |
   +------------------+
       * optional (INSTALL_WAZUH / INSTALL_MISP, default NO)
```

## VM details

| VM Name                              | VM ID | IP              | Bridge  | Template                            | Gated by         |
|--------------------------------------|-------|-----------------|---------|-------------------------------------|------------------|
| bs2-team-143-01                      | 2001  | 192.168.143.200 | net143 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-team-143-02                      | 2002  | 192.168.143.201 | net143 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-team-144-01                      | 2003  | 192.168.144.200 | net144 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-team-144-02                      | 2004  | 192.168.144.201 | net144 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-deployer-api-gateway       | 2121  | 192.168.142.121 | net142 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-deployer-api-backend       | 2122  | 192.168.142.122 | net142 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-deployer-ui                | 2123  | 192.168.142.123 | net142 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-wazuh                      | 2120  | 192.168.142.120 | net142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`  |
| bs2-admin-misp                       | 2124  | 192.168.142.124 | net142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_MISP`   |

Source of truth : `manifest/scenario_vms.json`.

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                          | Default |
|---------------------|-----------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on the 8 non-server VMs   | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                        | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                              | NO      |

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the four vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the admin tier |
| `net143` | `192.168.143.0/24` | `.1` | yes | team subnet 1 |
| `net144` | `192.168.144.0/24` | `.1` | yes | team subnet 2 |

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

While the bridge-creating tooling is still in place, `00_sdn_bootstrap/` ships a workaround that removes the duplicate address from the conflicting bridges - the address only, nothing written to disk, so `ifreload -a` puts it back. It refuses to run if a live VM is still attached to one of those bridges, rather than cutting that VM off mid-deployment. Disable it with `-e sdn_free_legacy_subnets=false` once the bridges are gone for good.

## Subnet isolation

**Not implemented yet.** Today the subnets reach each other: the host holds a gateway in each and routes between them. That is the expected state of this scenario, not a defect - a VM in `net143` can open a connection to a VM in `net144`.

Isolating them is a firewall matter, not a topology one: putting each vnet in its own zone would change nothing, because the host would still route. The work is in progress and will use per-NIC filtering with address sets, so that team subnets are isolated from each other while the deployer keeps reaching the VMs it manages - without that exception, no deployment could run at all.

## Usage

```bash
range42-context use <codename> blank_scenario_2_sdn
range42-context deploy

# enable Wazuh SIEM :
./blank_scenario_2_sdn.setup.sh -e INSTALL_WAZUH=YES

# enable both Wazuh + MISP (MISP requires .env populated in the catalog
# before this command - see admin-misp.yml documentation) :
./blank_scenario_2_sdn.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script                                                          | Action                                                              |
|-----------------------------------------------------------------|---------------------------------------------------------------------|
| `blank_scenario_2_sdn.setup.sh`                     | Run main playbook (templates + VMs + optional admin)                |
| `blank_scenario_2_sdn.setup_vms_only.sh`            | Run main_vms_only.yml (skip template creation)                      |
| `blank_scenario_2_sdn.reset.setup.sh`               | Delete + redeploy VMs                                               |
| `blank_scenario_2_sdn.reset.ssh_keys.sh`            | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `blank_scenario_2_sdn.delete_vms_only.sh`           | Delete VMs only, keep templates                                     |
| `blank_scenario_2_sdn.delete_all.sh`                | Delete VMs + templates (WARNING - affects other scenarios)          |

## Verified on SDN

Full deployment on a Proxmox 8.3 host, with `INSTALL_WAZUH=YES`:

```
PLAY RECAP *********************************************************************
px-testing                          : ok=298  changed=0   unreachable=0  failed=0
px-testing-cli                      : ok=40   changed=19  unreachable=0  failed=0
r42.bs2-admin-wazuh                 : ok=183  changed=76  unreachable=0  failed=0
r42.bs2-team-143-01                 : ok=70   changed=22  unreachable=0  failed=0
r42.bs2-team-143-02                 : ok=70   changed=22  unreachable=0  failed=0
r42.bs2-team-144-01                 : ok=70   changed=22  unreachable=0  failed=0
r42.bs2-team-144-02                 : ok=70   changed=22  unreachable=0  failed=0
```

What that run established, end to end on SDN vnets:

- the two templates of the whitelist were **rebuilt on `net140`**, `apt` included - so the SNAT of the templating subnet works;
- the 4 team VMs booted on `net143` / `net144`, took their cloud-init static IP, and are reachable over SSH through the Proxmox jump host;
- `bs2-admin-wazuh` came up on `net142` at `192.168.142.120` with internet, and the **full Wazuh stack installed on it** - 183 tasks, 76 changed.

Reachability measured from `bs2-team-143-01`.

| from `bs2-team-143-01` | to | result |
|---|---|---|
| TCP 22 | `192.168.143.201` - peer, same subnet | reachable |
| TCP 22 | `192.168.144.200` and `.201` - other subnet | reachable (expected today) |
| TCP 443 | `1.1.1.1` | reachable |
| DNS | `deb.debian.org` | resolved |

The 8 remaining admin VMs stay behind their feature flags and were not exercised by this run.
