# Draft: `image` field on catalog box templates (versioned base image)

**Status:** applied on `range42-catalog` (`feat/topology-layer-templates`) — `image:`
added to the four existing boxes (`image: ubuntu_noble`) and a `debian-jump` example
(`image: debian_trixie`, Debian 13). Review before merge.
**Companion (done):** generator side in `r42playbooks` — `BoxTemplate.image`,
image-scoped `select_template`, `image` in `scenario_vms.json` + README + `show`;
staged `01_init_proxmox` keyed by image name; **debian_trixie image set**
(`assets/.../templates/debian_trixie/` + `cloudinit_debian_trixie.yml` +
`TEMPLATE_TABLE` rows 9321/9331). Debian boxes generate a deployable tree.

> **Naming convention:** the base image is `<distro>_<codename>` — `ubuntu_noble`
> (24.04), `debian_trixie` (13). It IS the `01_init_proxmox/.../templates/<image>/`
> directory. Adding e.g. `debian_forky` (14) = a new image set + table rows, no
> catalog box change beyond pointing `image:` at it. The field carries the
> **version** (not just the family), so the box is never OS-ambiguous.

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

Add an optional `image` field to the `box_template` schema:

```yaml
# 05_topology_layer/box_templates/<id>/v<x.y.z>/template.yml
id: <id>
api_version: 1
role: admin | ctf | team | student
image: ubuntu_noble   # NEW — versioned base image <distro>_<codename> (default: ubuntu_noble)
default_inventory_group: r42_<group>
spec: "<cpu>/<ram>/<disk>"
default_attachments: [...]
```

Rules:
- **Optional, defaults to `ubuntu_noble`.** Every existing box stays Ubuntu 24.04 —
  backward compatible, no migration.
- **Value = the image-set name** (`<distro>_<codename>` = the
  `01_init_proxmox/.../templates/<image>/` dir). The cloned disk and the role's
  runtime `ansible_facts.distribution` agree by construction:

  ```
  image=debian_trixie ─clone→ debian_trixie 9321/9331 ─boot→ ansible_facts.distribution=='Debian'
                                                             └─ role's debian/ task file runs
  ```
- **Versioned:** `debian_trixie` ≠ `debian_forky`; each is its own image set, so a
  box is never ambiguous about *which* Debian.

### Examples

Ubuntu (explicit, but `image:` may be omitted — it's the default):

```yaml
id: admin-wazuh
api_version: 1
role: admin
image: ubuntu_noble
default_inventory_group: r42_admin_group
spec: "4cpu/8gb/64gb"
default_attachments:
  - {kind: role, catalog_ref: software.configure.firewalls}
  - {kind: role, catalog_ref: software.install.wazuh}
```

Debian 13 (new capability):

```yaml
id: debian-jump
api_version: 1
role: student
image: debian_trixie
default_inventory_group: r42_student_box_group
spec: "2cpu/4gb/32gb"
default_attachments:
  - {kind: role, catalog_ref: software.configure.firewalls}
  - {kind: role, catalog_ref: software.install.warmup.basic_packages}
```

## Deployability note (the image set is the gate)

`01_init_proxmox/.../templates/` creates the `ubuntu_noble` set and (new) the
**`debian_trixie` set (Debian 13)**; `alpine` is an empty placeholder. So:

- `image: ubuntu_noble` → works.
- `image: debian_trixie` → **generates a deployable tree** (the trixie genericcloud
  image is downloaded and turned into the `9321`/`9331` templates). ⚠ The Debian
  template-creation playbooks were ported from `ubuntu_noble` and have **not yet
  been validated against a live Proxmox** — verify a real `range42-context deploy`.
- any other `image:` (e.g. `debian_forky`) → schema-valid but **not deployable**:
  the generator fails fast (`unknown base image 'debian_forky' (available: …)`)
  instead of silently cloning another image. Deployable once its image set + table
  rows land.

## Generator side (already done in r42playbooks)

- `BoxTemplate.image: str = "ubuntu_noble"` (pattern `<distro>_<codename>`).
- `ProxmoxTemplate.image` (default `ubuntu_noble`); `select_template(spec, *, image=…)`
  scopes candidates to the box's image set, then matches `cpu/ram/disk` (exact,
  else `ram/disk` since cpu/ram are clone-time). Unknown image → clear error.
- `scenario_vms.json` records `image` on every `vms[]`/`templates[]` row; the
  generated `README.md` shows an `image` column; `show` prints it.

To add a new image (e.g. `debian_forky` / Debian 14): create
`01_init_proxmox/.../templates/debian_forky/` + `cloudinit_debian_forky.yml`, add
its `9xxx` rows to `templates_table.py` (`image="debian_forky"`), register it in
`render._IMAGE_SETS`, then point a box's `image:` at it.

## 01_init_proxmox layout (generator)

The generator's vendored `01_init_proxmox/` now mirrors the **`_init_lab` STAGED
layout** (not the flat `templates/` one):

```
01_init_proxmox/
  _main.yml                              # imports stage_00 + stage_01
  stage_00-download_cloudinit_files/
    _main.yml                            # generated: import cloudinit_<image>.yml per used image
    cloudinit_<image>.yml                # copied per used image (downloads base image)
  stage_01-create_templates/
    _main.yml                            # generated: import templates/<image>/<main> per used image
    templates/<image>/…                  # copied per used image
```

It stays **image-selective**: a `ubuntu_noble` lab carries only `ubuntu_noble/` +
`cloudinit_ubuntu_noble.yml`; a `debian_trixie` lab only `debian_trixie/` +
`cloudinit_debian_trixie.yml`.

**Content:** the staged layout uses the `_init_lab` *structure* but the **richer
`blank_scenario` template content** (path depth fixed `../../../` → `../../../../`):
both OS sets carry the **idempotence guards** ("skip if already a template",
lock-aware waits) and the **apt-proxy + update-templates** steps:
- per-template files probe `qm config … | grep '^template:'` and skip if done;
- `_apply_apt_proxy.yml` attaches the apt-proxy cicustom (no-op if `apt_proxy_url`
  empty) — Ubuntu and Debian each loop their own template ids;
- `_update_templates.yml` is **manifest-driven** (reads `manifest/scenario_vms.json`,
  probes template/vm/missing state) — boots each template, runs apt update +
  dist-upgrade via cloud-init, then converts to template. Idempotent + OS-agnostic.

## bundles/core/linux/debian (examples)

`bundles/core/linux/debian/` mirrors `…/ubuntu/` (install/configure example
playbooks + tests). Because the roles self-detect the OS at runtime, the
`main.yml` bodies are identical to ubuntu's; only the `test.sh` target host
differs (a Debian box). A future cleanup may collapse `ubuntu/`+`debian/` into a
single `linux/` set once the roles are confirmed fully OS-agnostic.

## Out of scope / explicitly NOT changing

- The warmup roles' runtime fact dispatch — keep `feat/local-apt-mirror`'s pattern.
- `alpine` — not a value yet (no role support / no image). Add when both exist.
