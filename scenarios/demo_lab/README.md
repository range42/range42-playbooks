# demo_lab

POC clone of demo_lab that imports the wazuh stack from `bundles/wazuh/main.yml`
instead of the local `02_admin_infrastructure/stage_01/mon_wazuh.yml`. Same VM
IDs, IPs, and inventory groups as demo_lab - **destroy demo_lab before deploying
demo_lab to avoid Proxmox collisions on the same hypervisor**.

If this POC works, the next step is to migrate demo_lab itself to use the same
bundle (and then bs2/bs4/bs6). See `_TODO_bundle_actions.md` at the repo root.

> **Work in progress** - the deployer UI and backend API are not yet configured on their VMs.
> Docker registry, student infrastructure, and additional services will be added later.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## Network architecture

```
                            ┌───────────────────────────┐
                            │       Proxmox Host        │
                            │      (ip_forward=1)       │
                            └──┬───────┬───────┬─────┬──┘
                               │       │       │     │
                      net140  │ net142│ net143 net144
                   ┌───────────┘       │       │     └──────────────┐
                   │                   │       │                    │
    ┌──────────────┴──────────┐  ┌─────┴───────────────┐  ┌────────┴──────────────────┐
    │  Templates (ephemeral)  │  │  Admin               │  │  CTF / Vuln               │
    │  192.168.140.0/24       │  │  192.168.142.0/24    │  │  192.168.144.0/24         │
    │                         │  │                      │  │                           │
    │  clone source for       │  │  wazuh          .100 │  │  vuln-box-00        .170  │
    │  all VMs                │  │  api-gateway    .101 │  │  vuln-box-01        .171  │
    │                         │  │  api-backend    .102 │  │  vuln-box-02        .172  │
    │                         │  │  deployer-ui    .103 │  │  vuln-box-03        .173  │
    │                         │  │                      │  │  vuln-box-04        .174  │
    └─────────────────────────┘  └──────────────────────┘  └───────────────────────────┘

    Student bridge (net143, 192.168.143.0/24) — reserved in manifest, not deployed by default
    Reserved : student-box-01 (vm_id 1160, IP .160). Import is commented out in `main.yml` ;
    uncomment `03_student_infrastructure/_main.yml` to enable. More student boxes TBD.
```

Wazuh agents on student/ctf bridges reach the wazuh server (192.168.142.100) through the Proxmox gateway.

## Deployed VMs

### 02_admin_infrastructure (net142)

| VM | VM ID | IP |
|----|-------|----|
| admin-wazuh | 1100 | 192.168.142.100 |
| admin-deployer-api-gateway | 1101 | 192.168.142.101 |
| admin-deployer-api-backend | 1102 | 192.168.142.102 |
| admin-deployer-ui | 1103 | 192.168.142.103 |

### 04_ctf_infrastructure (net144)

| VM | VM ID | IP |
|----|-------|----|
| vuln-box-00 | 1170 | 192.168.144.170 |
| vuln-box-01 | 1171 | 192.168.144.171 |
| vuln-box-02 | 1172 | 192.168.144.172 |
| vuln-box-03 | 1173 | 192.168.144.173 |
| vuln-box-04 | 1174 | 192.168.144.174 |

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the four vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the admin tier |
| `net143` | `192.168.143.0/24` | `.1` | yes | the student tier |
| `net144` | `192.168.144.0/24` | `.1` | yes | the ctf tier |

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

## Stages

Each infrastructure section follows staged deployment:

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Software installation (Ansible roles from catalog)
- **stage_02** — Post-install configuration (optional)

## Scripts

| Script | What it does |
|--------|-------------|
| `demo_lab.setup.sh` | Full deploy (templates + VMs + software) |
| `demo_lab.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `demo_lab.delete_all.sh` | Destroy everything + clean SSH known_hosts |
| `demo_lab.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `demo_lab.reset.setup.sh` | Delete all + redeploy from scratch |
| `demo_lab.reset.ssh_keys.sh` | Reset SSH keys only |

## Optional components - feature flags

The optional components shipped with this scenario can be toggled on/off at deploy
time. The catalog lives in [`manifest/feature_flags.yml`](manifest/feature_flags.yml) ;
the deploy scripts forward any trailing `-e INSTALL_<NAME>=<YES|NO>` to `ansible-playbook`
(same convention as the pre-existing `INSTALL_TAILSCALE` variable used elsewhere
in the scenario).

Example - deploy everything except wazuh, and force tailscale off on all groups :

```bash
range42-context deploy      -e INSTALL_WAZUH=NO
range42-context deploy-vms  -e INSTALL_WAZUH=NO -e INSTALL_TAILSCALE=NO
```

The same flags surface as checkboxes in `range42-context --tui` (deploy / deploy-vms entries).
