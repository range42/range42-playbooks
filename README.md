# range42-playbooks

Ansible playbooks and scenarios for deploying cyber range environments on Proxmox.
Part of the [range42](https://github.com/range42/range42) platform.

---

## How it works

A **scenario** is a complete lab environment — it defines which VMs to create,
what software to install on each, and how to configure them. You deploy a scenario
with one command, iterate on individual VMs during development, and tear it all
down when you're done.

```
scenario (demo_lab)
├── 00_sdn_bootstrap           ← declare the scenario networks (SDN vnets), create what is missing
├── 01_templates-bootstrap     ← VM templates from the shared bundles (cloud-init), built on net140
├── 02_admin_infrastructure    ← admin VMs (wazuh, misp, deployer trio, gitea...), each gated by a flag
│   ├── stage_00               ← create VMs (Proxmox API + cloud-init, shared vm.bootstrap bundle)
│   └── stage_01               ← install software (Ansible roles from catalog, admin bundles)
├── 03_student_infrastructure  ← student workstations (stage_00, stage_01)
├── 04_ctf_infrastructure      ← vulnerable boxes, CTF targets (stage_00, stage_01)
├── _firewall                  ← hypervisor firewall anchors, one file per moment (see below)
├── manifest                   ← scenario_vms.json (VM ids, IPs, networks, templates) + feature_flags.yml
├── templates                  ← inventory, ssh config, vars and vault example, rendered into the workspace
└── demo_lab.*.sh              ← wrappers : setup, setup_vms_only, delete_all, delete_vms_only, reset.*, setup_networks, delete_networks
```

**Stages** are ordered deployment phases within each infrastructure section.
They separate concerns and allow partial re-runs — you can replay stage_01
(software install) without recreating the VM from stage_00.

Each stage contains:
- `*.yml` — Ansible playbooks (executed by the scenario's `_main.yml`)
- `*.devkit/` — Per-group or per-VM shell scripts to replay one stage by hand (install, delete ; snapshot and revert where the VM supports it)

---

## First-time setup

Before using any scenario, you need to initialize the infrastructure once.
This generates SSH keys, passwords, vault secrets, configures Proxmox access,
and sets up the deployer-cli workspace.

```bash
# Interactive wizard (recommended), from a clone of the range42 repo
./range42-init.py
```

The wizard is documented step by step in [GETTING_STARTED.md](https://github.com/range42/range42/blob/main/GETTING_STARTED.md) of the range42 repo, with the manual flow (the four playbooks by hand) in its "Manual setup (advanced)" section.

---

## Daily workflow

### 1. Deploy the full scenario

```bash
range42-context use <codename> <scenario>
range42-context deploy          # full deploy (templates + VMs + software)
range42-context deploy-vms      # VMs only (skip templates — fast redeploy)
```

### 2. Work on a single VM

Each VM in each stage has its own `*.devkit/` directory with helper scripts.
This is the fastest way to iterate without replaying the full scenario:

```bash
cd scenarios/demo_lab/02_admin_infrastructure/stage_01-vm_configure/deployer_ui.devkit/

./demo_lab.deployer_ui.install.sh     # (re)install software on this VM only
./demo_lab.deployer_ui.snapshot.sh    # snapshot before a risky change
./demo_lab.deployer_ui.revert.sh      # something broke? revert to last snapshot
```

Every stage_00 group has `install.sh` and `delete.sh`, every stage_01 VM has `install.sh` ; the VMs that support it also have `snapshot.sh` and `revert.sh`.

### 3. Tear down

```bash
range42-context delete          # destroy everything
range42-context delete-vms      # destroy VMs only (keep templates)
```

Or use the shell scripts directly:

```bash
cd ~/range42/range42-playbooks/scenarios/demo_lab/
./demo_lab.setup.sh             # full deploy
./demo_lab.setup_vms_only.sh    # fast redeploy (skip templates)
./demo_lab.delete_all.sh        # destroy everything + clean SSH known_hosts
./demo_lab.delete_vms_only.sh   # destroy VMs only
./demo_lab.reset.setup.sh       # delete all + redeploy from scratch
./demo_lab.reset.ssh_keys.sh    # reset SSH keys only
```

---

## Networks (Proxmox SDN)

Every scenario runs on **Proxmox SDN vnets**, never on Linux bridges. The host holds one zone (`r42zone` by default) with one vnet per lab network : `net140` is the templating network, `net142` the admin band, `net143` and above the team, student and CTF subnets ; `netNNN` carries `192.168.NNN.0/24` with the gateway `.1` on the host, and outbound internet comes from the SNAT flag of each subnet.

- The init of a host (range42 wizard) creates the twelve networks once. Each scenario then declares the ones it uses in `00_sdn_bootstrap/_main.yml` (the `_sdn_vnets` list, derived from the `bridge` fields of its manifest) and imports the `proxmox/sdn_network.bootstrap` bundle : it creates what is missing, updates what drifted, applies once and reconciles the live SNAT rules. It never deletes : a vnet name is global to the cluster and shared between scenarios.
- The template stage passes `template_net_bridge: "net140"` to the template bundles : the builds run `apt`, they need the templating network's egress.
- A deployment sets each subnet's NAT to the value the scenario declares, so a `range42-context networks-internet-off` played earlier is undone by the next deployment : the last writer wins, a durable change is made in the init declaration.
- `<scenario>.setup_networks.sh` and `<scenario>.delete_networks.sh` wrap creation and teardown ; the teardown refuses while a VM of the scenario is still attached, since Proxmox would remove a vnet from under a running card.
- A host that still carries the legacy `vmbr14x` bridges must be cleaned once (`range42-context networks-legacy-clean`) : a bridge and a vnet cannot both hold the same `.1`, and the failure is silent (`No route to host`). Every scenario README has a "Migrating from the bridge-based scenarios" section.

The VM ids and the (network, IP) pairs of every scenario are reserved in `scenarios/_reserved.json`, regenerated from the manifests by `scenarios/_regenerate_reserved.sh` and checked by `scenarios/_check_reserved.sh` (sync with the manifests, no collision between VMs, consistent templates). Run the check before adding a VM to a scenario.

## Hypervisor firewall

Each scenario wires the **Proxmox firewall** through four anchors in `_firewall/`, byte-identical across scenarios and imported by both `main.yml` and `main_vms_only.yml` :

| Anchor | Moment | What it does |
|---|---|---|
| `stage_00-pre_scenario.report_status.yml` | before everything | reads the datacenter, node and guest switches, read only |
| `stage_01-pre_scenario.management_access.yml` | before everything | declares the anti-lockout accepts (ssh and the Proxmox API) on the datacenter and the node |
| `stage_02-post_vm_bootstrap.vm_ssh_baseline.yml` | once the VMs exist | declares the ssh accept on every deployed VM of the scenario (`firewall.baseline.ssh_all_vms`), inert until the guest is armed |
| `stage_03-end_scenario.arm_deployed_vms.yml` | last | arms the deployed guests, only with `-e FIREWALL_ARM_VMS=YES` (default NO) |

The ssh accept of stage 02 is open to any source by default. When the workspace vault carries `range42_fw_vm_ssh_sources` (a list of IPv4 `/32` chosen at init in the range42 wizard), the accept is restricted to those addresses plus every network of the scenario, so the deployer, which reaches the VMs through the Proxmox jump host, and the lab VMs among themselves keep their access. This is the firewall on the VM's card, not the firewall inside the VM (`firewall/in_vm/os_firewall.*` bundles handle that one). Arming is refused for a guest whose chain would cut ssh ; `range42-context networks-firewall-on` and `-off` (`--scope scenario`, `proxmox`, `vm_id <id>`, `all` for off) and `networks-show-firewall [--rules]` are the day-to-day gestures.

---

## Available scenarios

All the scenarios below run on the SDN vnets. "Deployed on SDN" means deployed and read back on a real Proxmox host in September 2026.

| Scenario | Status | Description | Details |
|----------|--------|-------------|---------|
| `demo_lab` | **functional**, deployed on SDN | Full cyber range : admin, student and CTF infrastructure, twelve templates built | [README](scenarios/demo_lab/README.md) |
| `blank_scenario_2_subnets` | **functional**, deployed on SDN | The SDN pilot : 4 team VMs on two subnets + 9 optional admin VMs, every one gated by a flag | [README](scenarios/blank_scenario_2_subnets/README.md) |
| `blank_scenario_4_subnets` | **functional**, deployed on SDN | 16 team VMs on four subnets + the optional admin tier | [README](scenarios/blank_scenario_4_subnets/README.md) |
| `blank_scenario_6_subnets` | **functional**, deployed on SDN | 24 team VMs on six subnets + the optional admin tier | [README](scenarios/blank_scenario_6_subnets/README.md) |
| `init_lab` | **functional**, deployed on SDN | Shared init : builds every VM template of the project, 5 small init VMs on two subnets | [README](scenarios/init_lab/README.md) |
| `kunai_lab` | **functional**, deployed on SDN | Kunai-based detection lab : trainer + 5 students, workshop toolchain | [README](scenarios/kunai_lab/README.md) |
| `misp_lab` | **functional**, deployed on SDN | MISP standalone server | [README](scenarios/misp_lab/README.md) |
| `gitea_lab` | **functional**, deployed on SDN | Gitea server + a student client | [README](scenarios/gitea_lab/README.md) |
| `mattermost_lab` | **functional**, deployed on SDN | Mattermost standalone | [README](scenarios/mattermost_lab/README.md) |
| `nextcloud_lab` | **functional**, deployed on SDN | Nextcloud standalone | [README](scenarios/nextcloud_lab/README.md) |
| `rocketchat_lab` | **functional**, deployed on SDN | Rocket.Chat standalone | [README](scenarios/rocketchat_lab/README.md) |
| `dev_deployer_ui_lab` | **functional**, deployed on SDN | The deployer trio (UI, backend API, Kong) for development ; the clones must be on `dev` | |
| `debug_scenario_a`, `debug_scenario_b` | **functional**, deployed on SDN | One Alpine VM each, for fast debugging | [README](scenarios/debug_scenario_a/README.md), [README](scenarios/debug_scenario_b/README.md) |
| `catalog_try` | tool | A disposable VM to try one catalog element (`range42-context catalog-try <path>`) | [README](scenarios/catalog_try/README.md) |
| `debug_sdn_tests` | tool | SDN test harness, no VM | [README](scenarios/debug_sdn_tests/README.md) |
| `admin_services_lab`, `gitea_registry_lab_to_migrate` | migrated, not deployed | Contributed scenarios moved to the SDN shape, set aside by their authors' pace | |

Each scenario README says which networks it declares, its VM ids and IPs, its feature flags and how to deploy it.

---

## Bundles

Bundles are **reusable, atomic actions** : the building blocks the scenarios are made of, and the interface the
[backend API](https://github.com/range42/range42-backend-api) and
[deployer UI](https://github.com/range42/range42-deployer-ui) use
to trigger deployments from the web interface.

The full index, one line per bundle with its description and the links to its parameter contract, is in [bundles/README.md](bundles/README.md), with one README per tier (`admin`, `proxmox`, `firewall`, `generic`, `ctf`).

> The scenarios already import the shared bundles for everything Proxmox-side : the SDN
> networks (`proxmox/sdn_network.bootstrap`), the templates (`proxmox/template.build.*`),
> the VM creation (`proxmox/vm.bootstrap`), the hypervisor firewall (`firewall/in_proxmox/*`)
> and the admin stacks (`admin/software.install.*`). The single-action SDN bundles
> (`sdn_network.create.*`, `list.*`, `update.*`, `delete.*`, `apply`) are the interface meant
> for the backend API and the UI : one bundle, one API call, one result.

Each bundle directory contains:
- `main.yml` : the playbook, entry point for a scenario import, the API or a standalone run, its header stating the required variables and an example call site
- `bundle_parameters.src.yml` : the hand-written parameter contract (name, type, from the vault or not, default and where it lives)
- `bundle_parameters.json` : the same contract generated by `bundles/_tools/generate-bundle-params.py`, consumed by the backend API and the UI, never edited by hand
- `README.md` : for the bundles that need more than their header

### Current bundle structure

```text
bundles/                                       # grammar: <tier>/<subject>.<verb>.<object>/
├── admin/                                     # app stacks on dedicated VMs (docker-compose)
│   └── software.install.{gitea,mattermost,nextcloud,rocketchat,misp_standalone,
│                          wazuh,wazuh_agent,deployer_ui,deployer_api_backend,kong}/
├── proxmox/                                   # Proxmox-side provisioning
│   ├── vm.bootstrap/                          # shared per-VM stage_00 (clone + cloud-init + start)
│   ├── vm.{attach,detach,replace}.sdn_vnet/   # move a VM card between vnets ; vm.list.interfaces/
│   ├── template.build.{ubuntu_noble,alpine,debian}/   # manifest-driven, template_net_bridge picks the build network
│   ├── cloud_init_image.download.{all,ubuntu_lts_minimal,ubuntu_lts_server,debian,alpine}/
│   ├── sdn_network.bootstrap/                 # what a scenario imports : create, update, apply once, reconcile SNAT
│   ├── sdn_network.{create,delete}.sdn_{zone,vnet,subnet}/   # single actions, one API call each
│   ├── sdn_network.list.sdn_{zones,vnets,subnets}/        # cluster-level reads, one fact each
│   ├── sdn_network.{update.sdn_subnet,apply,reconcile.snat_rules,bootstrap.sdn_vnet,delete.all}/
│   ├── sdn_network.internet_{on,off,toggle}/  # egress gestures : update, apply once, reconcile every declared subnet
│   └── legacy_bridge.{workaround,cleaning}.shadowed_subnet/   # migration from the vmbr bridges
├── firewall/                                  # segmentation
│   ├── in_proxmox/                            # the hypervisor firewall : firewall.baseline.{management_access,ssh_all_vms,ssh,wazuh,...},
│   │                                          #   firewall.{enable,disable}.{datacenter_and_nodes,vm,vms}, firewall.report.status
│   └── in_vm/                                 # the firewall inside the VM : os_firewall.baseline.{ssh,ssh_http,kong,...}
├── generic/                                   # reusable, group-targeted composition primitives
│   ├── systems.baseline.{default,docker_host,with_utils}/
│   ├── systems.configure.{add_user,authorized_keys,ssh_keypair,sudo,os_auto_updates,dotfiles,terminfo}/
│   ├── systems.checks.ping/                   # connectivity test (was the top-level ping bundle)
│   ├── network.baseline.{ssh,ssh_http,kong,deployer_ui,deployer_backend_api}/
│   ├── network.configure.{tailscale_client,ufw_rules}/
│   ├── repo.clone/ repo.clone.kunai_workshop/   # a list of repositories, or the five kunai repos
│   └── software.install.kunai_official_workshop/
├── ctf/                                       # CVE + misconfiguration taxonomy (unchanged)
│   ├── cve/**
│   └── misconfiguration/**
└── _tools/                                    # parameter contracts : schema, generator, call-site check, and the README index generator
```

Bundles are imported at parse-time via the `RANGE42_BUNDLE_DIR` env var (exported by
`range42-context`), e.g. `{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/generic/network.baseline.ssh/main.yml`.

---

## Repository Structure

```text
scenarios/
├── _reserved.json                     # VM ids and (network, IP) pairs of every scenario, regenerated from the manifests
├── _check_reserved.sh                 # the gate : sync + collisions ; _regenerate_reserved.sh, _check_reserved_search.sh
├── demo_lab/                          # Reference scenario (functional)
│   ├── main.yml                       # Full deploy entry point
│   ├── main_vms_only.yml              # Fast redeploy (skip templates), same firewall anchors
│   ├── 00_sdn_bootstrap/              # The scenario networks, declared once
│   ├── 01_templates-bootstrap/        # VM templates from the shared bundles (cloud-init)
│   ├── 02_admin_infrastructure/       # Admin VMs, flag-gated : stage_00, stage_01
│   ├── 03_student_infrastructure/     # Student VMs : stage_00, stage_01
│   ├── 04_ctf_infrastructure/         # CTF VMs : stage_00, stage_01
│   ├── _firewall/                     # Hypervisor firewall anchors, byte-identical across scenarios
│   ├── manifest/                      # scenario_vms.json + feature_flags.yml
│   ├── templates/                     # Inventory, ssh config, vars and vault example (rendered into the workspace)
│   ├── secrets/                       # Symlink → workspace secrets (gitignored)
│   └── demo_lab.*.sh                  # Deploy, delete, reset, networks scripts
├── blank_scenario_{2,4,6}_subnets/    # The SDN pilot and its two larger siblings
├── init_lab/                          # Shared init : every template + 5 init VMs
├── kunai_lab/ misp_lab/ gitea_lab/ mattermost_lab/ nextcloud_lab/ rocketchat_lab/ dev_deployer_ui_lab/
├── debug_scenario_a/ debug_scenario_b/ catalog_try/ debug_sdn_tests/
└── admin_services_lab/ gitea_registry_lab_to_migrate/   # migrated, not deployed

bundles/                               # Reusable actions, grammar <tier>/<subject>.<verb>.<object>
├── README.md                          # the index : tiers, conventions, one README per tier
├── admin/                             # app stacks (docker-compose) on dedicated VMs
├── proxmox/                           # vm.bootstrap, template.build.*, cloud_init_image.download.*, sdn_network.*, legacy_bridge.*
├── firewall/                          # in_proxmox (hypervisor firewall) and in_vm (ufw inside the VM)
├── generic/                           # systems/network/repo/software composition primitives
├── ctf/                               # CVE + misconfiguration taxonomy
└── _tools/                            # bundle_parameters schema and generators, README index generator
```

## Secrets

The `secrets/` directory in each scenario is a symlink to the workspace secrets
(`~/range42.config/<codename>-<scenario>/secrets/`). It contains vault files
and is gitignored — never committed.

---

## Contributing

GPL-3.0 license
