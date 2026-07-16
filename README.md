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
├── 01_init_proxmox         ← create VM templates (cloud-init)
├── 02_admin_infrastructure ← deploy admin VMs (wazuh, kong, docker, UI/API)
│   ├── stage_00            ← create VMs (Proxmox API + cloud-init)
│   ├── stage_01            ← install software (Ansible roles from catalog)
│   └── stage_02            ← post-install configuration (optional)
├── 03_student_infrastructure ← deploy student workstations
│   ├── stage_00
│   └── stage_01
└── 04_ctf_infrastructure   ← deploy vulnerable boxes (CTF targets)
    ├── stage_00
    └── stage_01
```

**Stages** are ordered deployment phases within each infrastructure section.
They separate concerns and allow partial re-runs — you can replay stage_01
(software install) without recreating the VM from stage_00.

Each stage contains:
- `*.yml` — Ansible playbooks (executed by the scenario's `_main.yml`)
- `*.devkit/` — Per-VM shell scripts for manual testing (install, snapshot, revert)

---

## First-time setup

Before using any scenario, you need to initialize the infrastructure once.
This generates SSH keys, passwords, vault secrets, configures Proxmox access,
and sets up the deployer-cli workspace.

```bash
# Interactive wizard (recommended)
python3 range42-init.py

# Or manually
ansible-playbook site.yml -i inventories/<your-infra>/ -e scenario=demo_lab -k
```

See the [range42](https://github.com/range42/range42) README for full setup instructions.

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
cd scenarios/demo_lab/02_admin_infrastructure/stage_01/mon_wazuh.devkit/

./demo_lab.mon_wazuh.install.sh     # (re)install software on this VM only
./demo_lab.mon_wazuh.snapshot.sh    # snapshot before a risky change
./demo_lab.mon_wazuh.revert.sh      # something broke? revert to last snapshot
```

Every VM has `install.sh`. VMs that support it also have `snapshot.sh` and `revert.sh`.

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

## Available scenarios

| Scenario | Status | Description | Details |
|----------|--------|-------------|---------|
| `demo_lab` | **functional** | Full cyber range — admin, student, CTF infrastructure | [README](scenarios/demo_lab/README.md) |
| `_init_lab` | **functional** | Shared init — VM templates + init VMs | [README](scenarios/_init_lab/README.md) |
| `forensics_lab` | coming soon | Forensics training | |
| `kunai_lab` | **in progress** | Kunai-based detection lab | [README](scenarios/kunai_lab/README.md) |
| `misp_lab` | **in progress** | MISP threat intel lab | [README](scenarios/misp_lab/README.md) |
| `dev_deployer_ui_lab` | **in progress** | Dev lab for deployer-ui integration | [README](scenarios/dev_deployer_ui_lab/README.md) |

Other scenario directories are placeholders — new scenarios are actively being developed.
Each scenario will get its own README with deployment details once available.

---

## Bundles (work in progress)

Bundles are **reusable, atomic actions** — the building blocks that the
[backend API](https://github.com/range42/range42-backend-api) and
[deployer UI](https://github.com/range42/range42-deployer-ui) will use
to trigger deployments from the web interface.

Instead of running a full scenario from the CLI, the UI will pick
individual bundles (create VMs, install software, snapshot, revert)
and compose them on the fly.

> Bundles are under active development. Scenarios currently contain
> their own playbooks directly. Once bundles are stable, scenarios
> will reference them instead of duplicating logic.

Bundles follow the same stage convention as scenarios.
Each bundle contains:
- `main.yml` — Entry point (callable by the API or standalone)
- `test.sh` — Manual test script
- `stage_*/` — Staged sub-tasks
- `*.devkit/` — Per-VM helper scripts (install, snapshot, revert)

### Current bundle structure

```text
bundles/                                       # grammar: <tier>/<subject>.<verb>.<object>/
├── admin/                                     # app stacks on dedicated VMs (docker-compose)
│   └── software.install.{gitea,mattermost,nextcloud,rocketchat,misp_standalone,
│                          wazuh,wazuh_agent,deployer_ui,deployer_api_backend,kong}/
├── proxmox/                                   # Proxmox-side provisioning
│   ├── vm.bootstrap/                          # shared per-VM stage_00 (clone + cloud-init + start)
│   ├── template.build.{ubuntu_noble,alpine,debian}/
│   └── cloud_init_image.download.{all,ubuntu_lts_minimal,ubuntu_lts_server,debian,alpine}/
├── generic/                                   # reusable, group-targeted composition primitives
│   ├── systems.baseline.{default,docker_host,with_utils}/
│   ├── systems.configure.{add_user,authorized_keys,ssh_keypair,sudo,os_auto_updates,dotfiles}/
│   ├── systems.checks.ping/                   # connectivity test (was the top-level ping bundle)
│   ├── network.baseline.{ssh,ssh_http,kong,deployer_ui,deployer_backend_api}/
│   ├── network.configure.{tailscale_client,ufw_rules}/
│   ├── repo.clone.{...,kunai_workshop}/
│   └── software.install.kunai_official_workshop/
├── decom/                                     # dead code staged for deletion (backend/UI-only)
│   ├── linux/ubuntu/{install/*,configure/add-user}/       # old API-driven primitives
│   └── vms/{create,delete,start-stop-pause-resume}-vms-* + snapshot/*   # legacy VM CRUD
└── ctf/                                       # CVE + misconfiguration taxonomy (unchanged)
    ├── cve/**
    └── misconfiguration/**
```

Bundles are imported at parse-time via the `RANGE42_BUNDLE_DIR` env var (exported by
`range42-context`), e.g. `{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/generic/network.baseline.ssh/main.yml`.

---

## Repository Structure

```text
scenarios/
├── demo_lab/                          # Reference scenario (functional)
│   ├── main.yml                       # Full deploy entry point
│   ├── main_vms_only.yml              # Fast redeploy (skip templates)
│   ├── 01_init_proxmox/              # VM templates (cloud-init)
│   ├── 02_admin_infrastructure/       # Admin VMs — stage_00, stage_01, stage_02
│   ├── 03_student_infrastructure/     # Student VMs — stage_00, stage_01
│   ├── 04_ctf_infrastructure/         # CTF VMs — stage_00, stage_01
│   ├── inventory/                     # Scenario-specific inventory
│   ├── secrets/                       # Symlink → workspace secrets (gitignored)
│   └── demo_lab.*.sh                 # Deploy, delete, reset scripts
├── forensics_lab/                     # Placeholder
├── kunai_lab/                         # In progress
├── misp_lab/                          # In progress
├── dev_deployer_ui_lab/               # In progress - deployer-ui integration
└── _init_lab/                         # Shared init playbooks

bundles/                               # Reusable actions, grammar <tier>/<subject>.<verb>.<object>
├── admin/                             # app stacks (docker-compose) on dedicated VMs
├── proxmox/                           # vm.bootstrap, template.build.*, cloud_init_image.download.*
├── generic/                           # systems/network/repo/software composition primitives
├── decom/                             # dead code staged for deletion (backend/UI-only)
└── ctf/                               # CVE + misconfiguration taxonomy
```

## Secrets

The `secrets/` directory in each scenario is a symlink to the workspace secrets
(`~/range42.config/<codename>-<scenario>/secrets/`). It contains vault files
and is gitignored — never committed.

---

## Contributing

GPL-3.0 license
