# catalog_try

One usage single-VM scenario for fast catalog element validation.

Provides a quick way to spin up a Proxmox VM (`catalog-try-vm-docker`, VMID 1250, IP `192.168.142.250` on `vmbr142`) provisioned with the Docker baseline. The VM is the target of `range42-context catalog-try <path>` for iterating on individual `range42-catalog` elements without standing up a full scenario.

The VM is **overwritten on each `catalog-try` invocation** : `delete-vms` + `deploy-vms` + apply the element + smoke check.

> **This is not a regular scenario.** Unlike `demo_lab`, `debug_scenario_a`, `blank_scenario_*` etc., `catalog_try` is **a single-use validation playground**, not a deployment target. It exists only to provide a disposable VM for the `range42-context catalog-try <path>` switch. Nothing persists between runs.

> **Concurrency constraint** : **only one `catalog-try` invocation at a time per deployer-cli**. The VM (VMID 1250 / IP `192.168.142.250`) is fixed — two concurrent `range42-context catalog-try ...` calls from the same deployer-cli would clash on the same VM (the second one destroys the first one's VM mid-run). Run them sequentially.

> **Scope (current)** : Docker elements only — paths under `range42-catalog/03_container_layer/docker/`. The test VM is hostnamed `catalog-try-vm-docker` to signal this. Support for `02_ansible_layer/` and `lxc/` elements may come later (tracked in the catalog-try work plan).



## Usage

Once the workspace is configured (Proxmox connection set via `range42-context init`), the scenario is invoked transparently by the `catalog-try` switch.

**1. First, activate the `catalog_try` workspace (once per shell session)** :

```
range42-context use <codename> catalog_try
```

**2. Then spin up a one usage lab on demand** :

```
range42-context catalog-try docker/_ctf/hello
range42-context catalog-try docker/_ctf/cve/blank_template
```

The standard scenario operations stay available if you need them directly :

```
range42-context deploy            # full setup : template (if missing) + VM
range42-context deploy-vms        # VM only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
range42-context delete            # same as delete-vms here (the template 9221 is shared with demo_lab, never owned by catalog_try)
```


## Vulnerability-Lookup integration (motivation)

The broader idea behind `catalog-try` is to offer a way to **spin up a one usage vulnerable lab VM** that can be **linked directly from a Vulnerability-Lookup CVE insight** (a "sighting"), so an analyst can move from reading a CVE to running a reproduction VM in seconds.

Concrete pattern :

- A CVE page on Vulnerability-Lookup (e.g. [CVE-2018-15473](https://vulnerability.circl.lu/vuln/CVE-2018-15473#sightings), [CVE-2022-0778](https://vulnerability.circl.lu/vuln/CVE-2022-0778#sightings)) references a `range42-catalog` element that holds a reproducible vulnerable setup.
- The operator runs `range42-context catalog-try <path>` and gets a fresh VM with that element deployed, ready for testing or analysis.
- The VM is overwritten on the next invocation, so each CVE is investigated in isolation, with no cross-contamination.

In short : **read the vuln → click the lab link → reproduce → analyze**. `catalog_try` is the throwaway VM substrate that makes this loop fast.

## Structure

This scenario mirrors the `demo_lab` pattern :

- `01_init_proxmox/` — download Ubuntu noble cloud-init image + create template 9221 (`template-vm-small-01-4g-32g`). Idempotent : skips if already present.
- `02_catalog-try_infrastructure/stage_00/catalog_try_vm.yml` — VM clone from template 9221 + cloud-init + start + wait-for-SSH
- `02_catalog-try_infrastructure/stage_01/_r42_catalog_try_group.yml` — Docker baseline + zsh dotfiles + firewall
- `manifest/scenario_vms.json` — single VM allocation (vm_id 1250, ip 192.168.142.250, bridge vmbr142)
- `templates/` — scenario-specific templates (ansible-inventory.j2, ansible-vars.yml, ssh-config.j2, vault-example.yml)


## Self-contained

`catalog_try` creates its own template (VMID 9221, ubuntu noble, 1cpu/4gb/32gb) via `01_init_proxmox/`. No dependency on another scenario's setup. If the template already exists on the Proxmox (e.g. from a prior `demo_lab.setup.sh` run, which creates the same VMID 9221), the template creation tasks are skipped idempotently.


## Entry points

### Standard scenario scripts (same shape as other range42 scenarios)

| script | purpose |
|---|---|
| `catalog_try.setup.sh` | full provisioning (template + VM) ; idempotent on the template stage |
| `catalog_try.setup_vms_only.sh` | skips template creation (faster on repeated runs ; assumes template present) |
| `catalog_try.delete_vms_only.sh` | destroys the disposable VM, preserves the template |
| `catalog_try.delete_all.sh` | alias of `delete_vms_only.sh` (no scenario-specific templates beyond 9221, which is shared with `demo_lab`) |
| `catalog_try.reset.setup.sh` | convenience : delete VM + redeploy in one shot |

### Specific to catalog_try (no equivalent in other scenarios)

| script / playbook | purpose |
|---|---|
| `catalog_try.element_deploy.yml` | Ansible playbook : copies a single catalog element to the test VM (`ansible.builtin.copy`, SFTP), seeds `.env` from `.env.example` if absent, opens declared ports through UFW (service mode), runs it (`docker compose up` / `make up`), and smoke-checks per the element's `catalog_try.yml` contract (L2 oneshot signature grep / L2 service local port-binding check / L1 fallback) — see [Element contract](#element-contract--catalog_tryyml) below |
| `catalog_try.element_deploy.sh` | thin wrapper around the playbook ; invoked internally by `range42-context catalog-try` — translates env vars (mode, port, signature, etc.) into ansible `-e` extra-vars |


## IP / VMID allocation on `vmbr142`

This scenario shares the `vmbr142` bridge with `demo_lab`'s admin VMs (NAT egress to the internet for `apt` and `docker pull`). VMID and IP last octet are kept in sync per the project convention (last 3 digits of VMID = IP last octet).

Reserved by this scenario :

| VMID | IP | Owner | Notes |
|------|----|-------|-------|
| **1250** | **192.168.142.250** | **catalog_try** | **catalog-try-vm-docker (overwritten on each run)** |

Free range on `vmbr142` for future scenarios : `.104` to `.249` and `.251` to `.254` (the `.100`–`.103` slot is currently held by `demo_lab` admin VMs).


## Element contract : `catalog_try.yml`

Each catalog element that wants a stricter smoke check than the default L1 fallback (`docker ps -a` presence) can ship a `catalog_try.yml` file in its directory. The file is the **contract** between the element (in `range42-catalog`) and the playbook (`catalog_try.element_deploy.yml` in this repo) — a small declarative spec that tells the playbook what mode the element runs in, which ports to expect, and how long to wait.

The playbook loads it via `ansible.builtin.include_vars` from the element source path on the controller (before the copy step), so YAML is parsed natively — single ints, lists, anything supported by Ansible's YAML loader.

### Fields

| Field | Type | Required | Applies to | Default | Purpose |
|---|---|---|---|---|---|
| `catalog_try_mode` | string | yes | both | — | `oneshot` (compose runs to completion) or `service` (compose stays up) |
| `catalog_try_exit_signature` | string | no | oneshot | — | String to `grep -F` in `docker compose logs` ; presence ⇒ L2 oneshot smoke pass |
| `catalog_try_port` | int **or** list[int] | no | service | — | Host port(s) the element binds. Used for UFW opens + binding smoke check (see below) |
| `catalog_try_endpoint` | string | no | service | `/` | Reserved for future HTTP-based extensions ; currently inert (the smoke check verifies port binding, not HTTP response) |
| `catalog_try_init_timeout` | int (seconds, max 600) | no | service | 60 | Upper bound on the smoke retry loop (retries = timeout / 5s delay) |

`catalog_try_port` accepts **single int or list of ints** transparently — all three syntaxes below are valid :

```yaml
catalog_try_port: 8080                  # single port, legacy syntax
catalog_try_port: [3000, 2222]          # multi-port, list (flow) syntax
catalog_try_port:                       # multi-port, block syntax
  - 3000
  - 2222
```

The playbook normalises any of these to a list internally before consuming the value, so element authors pick whichever reads best for their case. The 5 admin elements currently use block-list syntax even when a single port is declared, for API-surface consistency and future-friendliness.

### Smoke check semantics

The playbook picks the strictest applicable check :

- **L2 oneshot** — `catalog_try_mode: oneshot` + `catalog_try_exit_signature` set : container runs to completion, smoke greps the exit signature in `docker compose logs`. A missing signature fails the smoke.
- **L2 service** — `catalog_try_mode: service` + `catalog_try_port` set : the playbook polls **locally on the VM** (no `delegate_to: localhost`, so cross-cutting filters like UFW, Host header trust, OAuth callbacks are out of scope) until two conditions hold simultaneously :
  1. `docker ps --filter status=running` lists at least one container of the compose stack.
  2. For **each** port in the declared list : `ss -tplln | grep ':<port>'` confirms the port is bound on the host. A single missing port fails the smoke.

  The check retries every 5s up to `catalog_try_init_timeout / 5` times.
- **L1 fallback** — no L2 fields applicable : `docker ps -a` is enough to prove the element produced *something*. Both running and exited containers count.

### Network behaviour (UFW)

The catalog-try VM hardening enables UFW with **only port 22 open**. For service-mode elements with declared ports, the playbook iterates the declared list and runs `ufw allow <port>/tcp` for each, **before** the smoke check fires. Rules persist for the lifetime of the disposable VM ; no cleanup needed since the VM is destroyed on the next `catalog-try` invocation.

If `catalog_try_port` is not declared, no UFW rule is added (and the L2 service check is not run — the element falls back to L1).

### Examples

**Single-port service** (Nextcloud) :

```yaml
catalog_try_mode: service
catalog_try_port:
  - 8080
catalog_try_endpoint: /status.php
catalog_try_init_timeout: 180
```

→ UFW opens `8080/tcp` ; smoke waits for `ss -tplln` to show `:8080` bound (up to 36 retries × 5s = 180s).

**Multi-port service** (Gitea : HTTP + SSH) :

```yaml
catalog_try_mode: service
catalog_try_port:
  - 3000      # HTTP (web UI + API)
  - 2222      # SSH (git clone)
catalog_try_endpoint: /api/v1/version
catalog_try_init_timeout: 90
```

→ UFW opens `3000/tcp` **and** `2222/tcp` ; smoke requires **both** ports bound on the host (single missing port fails the smoke).

**Oneshot with exit signature** :

```yaml
catalog_try_mode: oneshot
catalog_try_exit_signature: "All checks passed"
```

→ `docker compose up --abort-on-container-exit` runs the stack to completion, smoke greps the signature in logs.
