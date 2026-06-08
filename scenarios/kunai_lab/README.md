# kunai_lab

Multi-VM training scenario that delivers 6 Ubuntu LTS hosts (1 trainer + 5 students) pre-provisioned with the Docker baseline plus the [kunai-project](https://github.com/kunai-project) ecosystem repositories pre-cloned in the operator home. Designed to run the kunai workshops out of the box.

The 6 VMs are cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk) onto the shared services bridge `vmbr142`. Single in-VM user `alice` on every VM (project convention - matches demo_lab and the blank scenarios). The kunai-project repos are pre-cloned into `/home/alice/kunai-project/` on the trainer and on each student VM.

## Scope

**In scope :**
- 6 Ubuntu LTS VMs on vmbr142 (1 trainer + 5 students)
- Docker engine + Docker Compose plugin on each VM
- zsh + vim dotfiles
- Basic utilities : curl, git, jq, vim, network diagnostic tools
- UFW firewall enabled with port 22 open
- NTP time sync
- 5 kunai-project repositories cloned into `/home/alice/kunai-project/` on every VM (trainer + 5 students) :
  - `workshops`
  - `kunai-doc`
  - `kunai-build-docker`
  - `community-rules`
  - `pykunai`

**Out of scope (follow-up step) :**
- Building the kunai binary (`kunai-build-docker` provides the build environment ; the trainer runs the build per workshop instructions)
- Live-tap demos and classroom dashboards
- TLS certificates / reverse proxy
- Application-level firewall openings (kept closed at scenario time on purpose)

Once kunai_lab is deployed, the trainer walks through the workshops with the students from `r42.admin-trainer-kunai`, and students follow along on their own `r42.student-kunai-NN` VM with the same repo layout.

## Network architecture

```
         Proxmox Host
              |
              +-- vmbr142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-trainer-kunai (.104)  ........  VMID 1104
                     +-- student-kunai-01    (.105)  ........  VMID 1105
                     +-- student-kunai-02    (.106)  ........  VMID 1106
                     +-- student-kunai-03    (.107)  ........  VMID 1107
                     +-- student-kunai-04    (.108)  ........  VMID 1108
                     +-- student-kunai-05    (.109)  ........  VMID 1109
```

No dedicated subnet. The 6 VMs live on `vmbr142`, the shared services bridge. The `.104`-`.109` slots are reserved by kunai_lab.

## VM details

| VM Name              | VM ID | IP                | Bridge   | In-VM user    | Role     | Template                              |
|----------------------|-------|-------------------|----------|---------------|----------|---------------------------------------|
| admin-trainer-kunai  | 1104  | 192.168.142.104   | vmbr142  | alice         | trainer  | template-vm-medium-02-8g-64g (9232)   |
| student-kunai-01     | 1105  | 192.168.142.105   | vmbr142  | alice         | student  | template-vm-medium-02-8g-64g (9232)   |
| student-kunai-02     | 1106  | 192.168.142.106   | vmbr142  | alice         | student  | template-vm-medium-02-8g-64g (9232)   |
| student-kunai-03     | 1107  | 192.168.142.107   | vmbr142  | alice         | student  | template-vm-medium-02-8g-64g (9232)   |
| student-kunai-04     | 1108  | 192.168.142.108   | vmbr142  | alice         | student  | template-vm-medium-02-8g-64g (9232)   |
| student-kunai-05     | 1109  | 192.168.142.109   | vmbr142  | alice         | student  | template-vm-medium-02-8g-64g (9232)   |

Single in-VM user `alice` on every VM (project convention - matches demo_lab and the blank scenarios). SSH transport user is also `alice` on every VM.

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1104 -> .104, 1105 -> .105, etc).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, and to audit for collisions, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## kunai-project repositories

The stage_01 software install step clones the 5 repositories below into `/home/<operator_user>/kunai-project/` on each VM (depth 1, force-updated on re-run).

| Repository           | Source                                                  | Purpose                                                        |
|----------------------|---------------------------------------------------------|----------------------------------------------------------------|
| `workshops`          | https://github.com/kunai-project/workshops              | Hands-on workshop material (the trainer drives, students follow) |
| `kunai-doc`          | https://github.com/kunai-project/kunai-doc              | Project documentation                                          |
| `kunai-build-docker` | https://github.com/kunai-project/kunai-build-docker     | Docker build environment for the kunai binary                  |
| `community-rules`    | https://github.com/kunai-project/community-rules        | Community-maintained detection rules                           |
| `pykunai`            | https://github.com/kunai-project/pykunai                | Python helpers and tooling                                     |

## Inventory groups

Two inventory groups are declared so stage_01 can apply role-specific tasks (different operator user, different repo clone destination) :

| Group                              | Hosts                                                     |
|------------------------------------|-----------------------------------------------------------|
| `r42_kunai_lab_trainer_group`      | `r42.admin-trainer-kunai`                                 |
| `r42_kunai_lab_students_group`     | `r42.student-kunai-01` through `r42.student-kunai-05`     |

## Usage

Activate the workspace and run the setup script :

```
range42-context use <codename> kunai_lab
./kunai_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + 6 VMs + Docker baseline + repos
range42-context deploy-vms        # VMs only (template assumed present)
range42-context delete-vms        # destroys the 6 VMs, keeps the template
range42-context delete            # same as delete-vms here (template 9232 is shared, never owned by kunai_lab)
```

Once the playbook completes :

```
ssh r42.admin-trainer-kunai   # trainer, SSH as alice, repos under /home/alice/kunai-project/
ssh r42.student-kunai-01      # student 01, SSH as alice, repos under /home/alice/kunai-project/
# ... and so on for student-kunai-02 .. 05
```

All 6 VMs reach via ProxyJump through the Proxmox jumper. Each has its own explicit `Host r42.*` entry in `~/.ssh/config_range42-*` (no wildcard pattern).

## Stages

| Stage | Purpose |
|---|---|
| `01_init_proxmox/` | Download Ubuntu noble cloud-init image + create template 9232 (`template-vm-medium-02-8g-64g`). Idempotent : skips if already present. |
| `02_kunai_lab_infrastructure/stage_00/admin_trainer_kunai_vm.yml` | VM clone from template 9232 + cloud-init + start + wait-for-SSH (admin-trainer-kunai, 1104, .104). |
| `02_kunai_lab_infrastructure/stage_00/student_kunai_01_vm.yml` | Same flow for student-kunai-01 (1105, .105). |
| `02_kunai_lab_infrastructure/stage_00/student_kunai_02_vm.yml` | Same flow for student-kunai-02 (1106, .106). |
| `02_kunai_lab_infrastructure/stage_00/student_kunai_03_vm.yml` | Same flow for student-kunai-03 (1107, .107). |
| `02_kunai_lab_infrastructure/stage_00/student_kunai_04_vm.yml` | Same flow for student-kunai-04 (1108, .108). |
| `02_kunai_lab_infrastructure/stage_00/student_kunai_05_vm.yml` | Same flow for student-kunai-05 (1109, .109). |
| `02_kunai_lab_infrastructure/stage_01/_r42_kunai_lab_group.yml` | Docker baseline + zsh dotfiles + firewall on all 6 VMs, then per-group repo clones (alice on the trainer, bob on the students). |

## Entry points

| Script | Purpose |
|---|---|
| `kunai_lab.setup.sh` | Full provisioning (template + 6 VMs + baseline + repos). Idempotent on the template stage. |
| `kunai_lab.setup_vms_only.sh` | Skips template creation. Faster on repeat runs assuming template 9232 is already present. |
| `kunai_lab.delete_vms_only.sh` | Destroys the 6 kunai_lab VMs, preserves the template. |
| `kunai_lab.delete_all.sh` | Alias of `delete_vms_only.sh` (template 9232 is shared, never owned by kunai_lab). |
| `kunai_lab.reset.setup.sh` | Convenience : delete the 6 VMs + redeploy in one shot. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> kunai_lab`.

## Files

```
kunai_lab/
  main.yml                                   full deploy entrypoint
  main_vms_only.yml                          fast redeploy (skip templates)
  manifest/scenario_vms.json                 source of truth for VMID / IP / bridge
  README.md
  kunai_lab.setup.sh                         full deploy wrapper
  kunai_lab.setup_vms_only.sh                fast redeploy wrapper
  kunai_lab.delete_vms_only.sh               VM teardown
  kunai_lab.delete_all.sh                    alias
  kunai_lab.reset.setup.sh                   teardown + deploy
  01_init_proxmox/                           Ubuntu noble cloud-init image + template 9232
  02_kunai_lab_infrastructure/               6-VM stage_00 + stage_01 (baseline + repo clones)
  templates/                                 scenario-level templates (inventory, vars, ssh-config, vault example)
```
