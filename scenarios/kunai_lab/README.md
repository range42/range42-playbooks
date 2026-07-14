# kunai_lab

Multi-VM training scenario that delivers 6 Ubuntu LTS hosts (1 trainer + 5 students) pre-provisioned with the Docker baseline plus the [kunai-project](https://github.com/kunai-project) ecosystem repositories pre-cloned in the operator home. Designed to run the kunai workshops out of the box.

The 6 VMs are cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk) onto the shared services bridge `vmbr142`. **User model** : `alice` is the deploy/transport user (ansible connects as alice, unchanged) ; on top, each VM gets a **human sudo account** - `trainer` on the trainer VM, `student` on each student VM (per-VM unique credentials). The kunai-project repos + toolchain are installed in the **human user's** home (`/home/trainer/`, `/home/student/`). See the [User model](#user-model-phase-1b) section.

## Scope

**In scope :**
- 6 Ubuntu LTS VMs on vmbr142 (1 trainer + 5 students)
- Docker engine + Docker Compose plugin on each VM
- zsh + vim dotfiles
- Basic utilities : curl, git, jq, vim, network diagnostic tools
- UFW firewall enabled with port 22 open
- NTP time sync
- human sudo accounts on every VM : `trainer` (trainer VM) + `student` (each student VM), per-VM unique creds
- 5 kunai-project repositories cloned into the human user's home (`/home/trainer/kunai-project/` on the trainer, `/home/student/kunai-project/` on each student) :
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

## User model (Phase 1B)

Three roles, cleanly separated :

- **`alice`** - the DEPLOY user. Ansible connects (SSH transport) as alice on every VM, as during provisioning. Unchanged. Not a workshop account.
- **`student`** - the human sudo account on each student VM. Same username on all 5 VMs, but **UNIQUE credentials per VM** : a per-VM SSH key (`bob_1..5`, one per VM) + a derived password. Students log in with their key (handed off out-of-band by the trainer) or the password.
- **`trainer`** - the human sudo account. Present on the trainer VM AND on every student VM (so the trainer can `ssh student-kunai-0X` to reach any student). On the trainer VM a **passphrase-less `trainer-student-access` key** is generated (stays ONLY on the trainer VM) ; its pubkey is authorized on the students' `trainer` account. `~trainer/.ssh/config` maps `student-kunai-01..05` to their IPs.

**Credentials reference** : every created human account + its derived password + the SSH key it uses are recorded at deploy in `<workspace>/secrets/created_users.json`. The keys themselves live under `<workspace>/ssh_keys/student_keys/`.

**Security notes (intentional)** :
- `student` and `trainer` both have **NOPASSWD sudo** (passwordless root) - intended for a training lab.
- the `trainer-student-access` private key lives **only on the trainer VM**, never on a student VM - a student (even root on their own VM) cannot use it to hop to other VMs.
- passwords are DERIVED from the per-VM public key + a secret vault salt : unique per VM, non-predictable. Override at deploy with `-e STUDENT_PASSWORD=...` (common to all students) / `-e TRAINER_PASSWORD=...`.

> Enabling this tier makes the wizard generate the per-student keys, so it needs a workspace **re-init** (not just a redeploy) the first time. A re-init rotates the keys, so re-deploy afterwards.

> If a student VM is **rebuilt** (new SSH host key), the trainer's `~/.ssh/config` uses `StrictHostKeyChecking accept-new`, which accepts unknown hosts but rejects a *changed* key. Clear the stale entry on the trainer VM before reconnecting : `ssh-keygen -R <student-ip>` (e.g. `ssh-keygen -R 192.168.142.105`).

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

The "In-VM user" column is the SSH transport / deploy user (`alice` on every VM, project convention). Each VM ALSO has a human sudo account - `trainer` on the trainer VM, `student` on each student VM - created by Phase 1B (see the [User model](#user-model-phase-1b) section).

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1104 -> .104, 1105 -> .105, etc).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, and to audit for collisions, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## kunai-project repositories

The stage_01 software install step clones the 5 repositories below into the human user's home (`/home/trainer/kunai-project/` on the trainer, `/home/student/kunai-project/` on each student ; depth 1, force-updated on re-run).

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
# operator (deploy transport) connects as alice :
ssh r42.admin-trainer-kunai   # trainer VM
ssh r42.student-kunai-01      # student 01 ... through student-kunai-05

# workshop accounts (passwords + key files -> secrets/created_users.json) :
#   trainer VM  -> user `trainer` (repos under /home/trainer/kunai-project/)
#   student VMs -> user `student` (repos under /home/student/kunai-project/)
# from the trainer VM, the trainer reaches each student directly :
#   ssh student-kunai-01      # ... through student-kunai-05 (via ~trainer/.ssh/config)
```

All 6 VMs reach via ProxyJump through the Proxmox jumper. Each has its own explicit `Host r42.*` entry in `~/.ssh/config_range42-*` (no wildcard pattern).

## Stages

| Stage | Purpose |
|---|---|
| `01_templates-bootstrap/` | Download Ubuntu noble cloud-init image + create template 9232 (`template-vm-medium-02-8g-64g`). Idempotent : skips if already present. |
| `02_admin_infrastructure/` | Scaffold for future Wazuh / MISP admin VMs. No VMs deployed by default ; gated via `manifest/feature_flags.yml`. |
| `03_trainer_infrastructure/stage_00-vm_bootstrap/` | Clone + cloud-init + start + wait-for-SSH for `admin-trainer-kunai` (1104, .104). Delegated to `bundles/proxmox/vm.bootstrap/`. |
| `03_trainer_infrastructure/stage_01-vm_configure/` | Docker baseline + dotfiles + firewall (port 22) + kunai-project repos clone on the trainer. Uses `systems.baseline.docker_host` + `network.baseline.ssh` + `network.configure.tailscale_client` (gated off). |
| `04_student_infrastructure/stage_00-vm_bootstrap/` | Same vm.bootstrap flow for 5 student VMs (1105..1109, .105..109). |
| `04_student_infrastructure/stage_01-vm_configure/` | Same Docker baseline + dotfiles + firewall + kunai-project repos clone on the 5 students. |

## Entry points

| Script | Purpose |
|---|---|
| `kunai_lab.setup.sh` | Full provisioning (template + 6 VMs + baseline + repos). Idempotent on the template stage. |
| `kunai_lab.setup_vms_only.sh` | Skips template creation. Faster on repeat runs assuming template 9232 is already present. |
| `kunai_lab.delete_vms_only.sh` | Destroys the 6 kunai_lab VMs, preserves the template. |
| `kunai_lab.delete_all.sh` | Alias of `delete_vms_only.sh` (template 9232 is shared, never owned by kunai_lab). |
| `kunai_lab.reset.setup.sh` | Convenience : delete the 6 VMs + redeploy in one shot. |
| `kunai_lab.reset.ssh_keys.sh` | Clear `~/.ssh/known_hosts` entries for every manifest IP after a redeploy reuses the same IPs (fixes REMOTE HOST IDENTIFICATION CHANGED). |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> kunai_lab`.

## Files

```
kunai_lab/
  main.yml                                   full deploy entrypoint
  main_vms_only.yml                          fast redeploy (skip templates)
  manifest/scenario_vms.json                 source of truth for VMID / IP / bridge
  manifest/feature_flags.yml                 optional gated components (Wazuh, MISP, Tailscale - off by default)
  README.md
  kunai_lab.setup.sh                         full deploy wrapper
  kunai_lab.setup_vms_only.sh                fast redeploy wrapper
  kunai_lab.delete_vms_only.sh               VM teardown
  kunai_lab.delete_all.sh                    alias
  kunai_lab.reset.setup.sh                   teardown + deploy
  kunai_lab.reset.ssh_keys.sh                clear known_hosts for all manifest IPs
  01_templates-bootstrap/                    Ubuntu noble cloud-init image + template 9232
  02_admin_infrastructure/                   scaffold for future Wazuh / MISP (gated off)
  03_trainer_infrastructure/                 trainer VM (admin-trainer-kunai) - stage_00 + stage_01
  04_student_infrastructure/                 5 student VMs - stage_00 + stage_01
  templates/                                 scenario-level templates (inventory, vars, ssh-config, vault example)
```
