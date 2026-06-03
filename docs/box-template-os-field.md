# Draft: `os` field on catalog box templates

**Status:** applied on `range42-catalog` (`feat/topology-layer-templates`) — `os:` added
to the four existing boxes (explicit `os: ubuntu`) and a `debian-jump` example box
(`os: debian`, Debian 13 / trixie). Review before merge.
**Companion (done):** generator side in `r42playbooks` — `BoxTemplate.os`, OS-aware
`select_template`, `os` in `scenario_vms.json` + README + `show`; OS-aware `main.yml`
image imports; **Debian trixie image set** (`assets/.../01_init_proxmox/templates/debian/`
+ `TEMPLATE_TABLE` rows 9321/9331). Debian boxes now generate a deployable tree.

## Why

`feat/local-apt-mirror` made the warmup roles multi-OS: they dispatch per
distribution at **runtime** via Ansible facts —

```yaml
- include_tasks: ./ubuntu/packages_basics.yaml
  when: ansible_facts.distribution == 'Ubuntu'
- include_tasks: ./debian/packages_basics.yaml
  when: ansible_facts.distribution == 'Debian'
- include_tasks: ./fedora/packages_basics.yaml
  when: ansible_facts.distribution == 'Fedora'
```

That is the right pattern for **role behaviour** (the role self-detects the OS of
the booted VM). Keep it as-is.

But the role's fact trick can't pick the **clone image**: facts only exist after a
VM boots, while the image must be chosen *before* the VM exists (chicken-and-egg).
Today a `box_template` only declares `spec: <cpu>/<ram>/<disk>` — there is no way
to say "this box is Debian", so every box is implicitly Ubuntu and a Debian box
can't be composed at all. The OS belongs in the **authoring layer** as a declared
field.

## The change

Add an optional `os` field to the `box_template` schema:

```yaml
# 05_topology_layer/box_templates/<id>/v<x.y.z>/template.yml
id: <id>
api_version: 1
role: admin | ctf | team | student
os: ubuntu            # NEW — ubuntu | debian | fedora  (default: ubuntu)
default_inventory_group: r42_<group>
spec: "<cpu>/<ram>/<disk>"
default_attachments: [...]
```

Rules:
- **Optional, defaults to `ubuntu`.** Every existing box template is unchanged and
  stays Ubuntu — fully backward compatible. No migration required.
- **Values match `ansible_facts.distribution`, lower-cased** (`ubuntu` / `debian`
  / `fedora`), so the declared image and the role's runtime dispatch agree by
  construction:

  ```
  box.os=debian ─clone→ debian 9xxx image ─boot→ ansible_facts.distribution=='Debian'
                                                  └─ role's debian/ task file runs
  ```

### Examples

Ubuntu (explicit, but `os:` may be omitted — it's the default):

```yaml
id: admin-wazuh
api_version: 1
role: admin
os: ubuntu
default_inventory_group: r42_admin_group
spec: "4cpu/8gb/64gb"
default_attachments:
  - {kind: role, catalog_ref: software.configure.firewalls}
  - {kind: role, catalog_ref: software.install.wazuh}
```

Debian (new capability):

```yaml
id: debian-jump
api_version: 1
role: student
os: debian
default_inventory_group: r42_student_box_group
spec: "2cpu/4gb/32gb"
default_attachments:
  - {kind: role, catalog_ref: software.configure.firewalls}
  - {kind: role, catalog_ref: software.configure.apt_mirror_client}   # from feat/local-apt-mirror
```

## Deployability note (the image set is the gate)

`01_init_proxmox/templates/` creates the `ubuntu_noble` set and (new) the **`debian`
set (Debian 13 / trixie)**; `alpine`/`fedora` are still empty placeholders. So:

- `os: ubuntu` → works.
- `os: debian` → **generates a deployable tree** (the genericcloud trixie image is
  downloaded and turned into the `9321`/`9331` templates). ⚠ The Debian
  template-creation playbooks were ported from `ubuntu_noble` and have **not yet
  been validated against a live Proxmox** — verify a real `range42-context deploy`
  before relying on them.
- `os: fedora` → schema-valid but **not deployable**: the generator fails fast and
  clearly (`no Proxmox template image for os 'fedora' …`) instead of silently
  cloning another OS. Becomes deployable once a `fedora/` image set + table rows land.

## Generator side (already done in r42playbooks)

- `BoxTemplate.os: Literal["ubuntu","debian","fedora"] = "ubuntu"`.
- `ProxmoxTemplate.os` (default `ubuntu`); `select_template(spec, *, os=...)`
  scopes candidates to the box's OS image set, then matches `cpu/ram/disk`
  (exact, else `ram/disk` since cpu/ram are clone-time). Unknown OS → clear error.
- `scenario_vms.json` records `os` on every `vms[]` and `templates[]` row; the
  generated `README.md` shows an `os` column.

When debian/fedora images exist, add their `9xxx` rows to
`r42playbooks/core/templates_table.py` with `os="debian"` / `os="fedora"`
(sourced, as today, from the `01_init_proxmox/templates/<family>/` definitions and
the reference manifest `templates[]`).

## 01_init_proxmox layout (generator)

The generator's vendored `01_init_proxmox/` now mirrors the **`_init_lab` STAGED
layout** (not the flat `templates/` one):

```
01_init_proxmox/
  _main.yml                              # imports stage_00 + stage_01
  stage_00-download_cloudinit_files/
    _main.yml                            # generated: import cloudinit_<os>.yml per used OS
    cloudinit_<os>.yml                   # copied per used OS (downloads base images)
  stage_01-create_templates/
    _main.yml                            # generated: import templates/<os>/_main_<os>.yml per used OS
    templates/<os>/…                     # copied per used OS
```

It stays **OS-selective**: a Ubuntu-only lab carries only `ubuntu_noble/` +
`cloudinit_ubuntu_noble.yml`; a Debian lab only `debian/` + `cloudinit_debian.yml`.

⚠ **Content note:** `_init_lab`'s template playbooks are an *older, simpler* set
than `blank_scenario_*`'s — they lack the **idempotence guards** ("skip if already
a template", lock-aware waits) and the **apt-proxy / update-templates** steps.
The generator currently vendors the `_init_lab` content (per the layout choice).
If the richer/idempotent content is wanted, port `blank_scenario`'s ubuntu_noble
files into the staged layout (fix the secrets depth `../../../` → `../../../../`)
and regenerate the Debian set from them.

## bundles/core/linux/debian (examples)

`bundles/core/linux/debian/` mirrors `…/ubuntu/` (install/configure example
playbooks + tests). Because the roles self-detect the OS at runtime, the
`main.yml` bodies are identical to ubuntu's; only the `test.sh` target host
differs (a Debian box). A future cleanup may collapse `ubuntu/`+`debian/` into a
single `linux/` set once the roles are confirmed fully OS-agnostic.

## Out of scope / explicitly NOT changing

- The warmup roles' runtime fact dispatch — keep `feat/local-apt-mirror`'s pattern.
- `alpine` — not a value yet (no role support / no image). Add when both exist.
