# bundles/core/proxmox/configure/templates/ubuntu_noble

Shared playbook that creates the Ubuntu Noble VM template family on a Proxmox
hypervisor. Lifted from `scenarios/blank_scenario_2_subnets/01_init_proxmox/templates/`
during the shared-bundles POC follow-up. Idempotent : templates already
finalized on the hypervisor are skipped entirely.

## Pipeline

The bundle runs in 3 sequential stages :

1. **Per-template create** (12 plays in `00..04-template-vm-*.yml`) - each
   probes `qm config <vm_id>` for `^template:` ; if already a template,
   the whole play is skipped. Otherwise the VM is created via the
   `range42-ansible_roles-proxmox_controller` role, then a cloud-init disk
   is imported, then cloud-init variables and the `template` Proxmox tag
   are set. VMs end this stage as plain VMs (not yet converted).
2. **`_apply_apt_proxy.yml`** - attaches `cicustom vendor=local:snippets/range42-apt-proxy.yaml`
   to each template VM (when `apt_proxy_url` is set), or detaches if
   `apt_proxy_url` is empty. No-op when the cicustom is already in the
   desired state.
3. **`_update_templates.yml`** - reads the scenario's manifest, probes each
   template VM, and for those still in `vm` state : renders the bootstrap
   snippet (apt update + dist-upgrade + poweroff), attaches it, starts the
   VMs in parallel, polls until each auto-powers-off, detaches the
   bootstrap snippet (re-attaches the persistent apt-proxy snippet if
   `apt_proxy_url` was set), then converts each VM to a template via
   `qm template`.

## Required vars (caller passes via `import_playbook vars:`)

| var                   | purpose                                                                                       |
|-----------------------|-----------------------------------------------------------------------------------------------|
| `manifest_path`       | absolute path to the scenario's `manifest/scenario_vms.json` (manifest enumerates the targets) |
| `template_bundle_dir` | absolute path to this bundle's `ubuntu_noble/` dir (used to render the bootstrap snippet)      |

If either is missing, `_update_templates.yml` aborts early with an explicit
assertion message - no silent failure.

## Optional vars

| var                       | default | effect                                                                                 |
|---------------------------|---------|----------------------------------------------------------------------------------------|
| `templates_whitelist`     | `[]`    | if empty, install the full family ; else only the short codes listed (see table below) |
| `template_subnet_octet`   | `142`   | third octet of the template subnet on `vmbr140` (bs2/bs4/bs6 override to `140`)        |
| `apt_proxy_url`           | unset   | if set, bootstrap snippet runs apt update through this proxy AND persistent cicustom is attached for clones |

## Template family

| short code | file                                  | vm_id | cpu | ram | disk | ip last octet |
|------------|---------------------------------------|-------|-----|-----|------|----------------|
| nano       | 00-template-vm-nano.yml               | 9901  | 1   | 1G  | 16G  | .201           |
| micro-01   | 01-template-vm-micro-01-2g-24g.yml    | 9211  | 1   | 2G  | 24G  | .211           |
| micro-02   | 01-template-vm-micro-02-2g-24g.yml    | 9212  | 2   | 2G  | 24G  | .212           |
| small-01   | 02-template-vm-small-01-4g-32g.yml    | 9221  | 1   | 4G  | 32G  | .221           |
| small-02   | 02-template-vm-small-02-4g-32g.yml    | 9222  | 2   | 4G  | 32G  | .222           |
| small-04   | 02-template-vm-small-04-4g-32g.yml    | 9224  | 4   | 4G  | 32G  | .224           |
| medium-02  | 03-template-vm-medium-02-8g-64g.yml   | 9232  | 2   | 8G  | 64G  | .232           |
| medium-04  | 03-template-vm-medium-04-8g-64g.yml   | 9234  | 4   | 8G  | 64G  | .234           |
| medium-06  | 03-template-vm-medium-06-8g-64g.yml   | 9236  | 6   | 8G  | 64G  | .236           |
| large-04   | 04-template-vm-large-04-8g-64g.yml    | 9244  | 4   | 16G | 100G | .244           |
| large-06   | 04-template-vm-large-06-8g-64g.yml    | 9246  | 6   | 16G | 100G | .246           |
| large-08   | 04-template-vm-large-08-8g-64g.yml    | 9248  | 8   | 16G | 100G | .248           |

VM IDs are globally coherent across all range42 scenarios. The full IP is
`192.168.{{ template_subnet_octet }}.<last_octet>` ; with the default `142`,
template-vm-nano lives at `192.168.142.201`.

## Vault loading

Each template play loads the scenario's vault from
`$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml` (env var exported by
`range42-context use`). Same pattern as `bundles/wazuh/main.yml`.

## Idempotence

Re-running the bundle on a hypervisor that already has the templates is safe :

- Per-template plays check `qm config | grep '^template:'` and skip when true.
- `_apply_apt_proxy.yml` is idempotent on both attach (qm set updates) and
  detach (failed_when relaxed, since cicustom may already be absent).
- `_update_templates.yml` probes per-template state and end-plays early if
  every entry is already a template (so the heavy start-wait-convert pipeline
  is skipped entirely).

## Calling pattern (example from `scenarios/demo_lab_bundles/main.yml`)

```yaml
- import_playbook: ../../bundles/core/proxmox/configure/templates/_main_download_cloudinit_files.yml

- import_playbook: ../../bundles/core/proxmox/configure/templates/ubuntu_noble/main.yml
  vars:
    manifest_path:       "{{ playbook_dir }}/manifest/scenario_vms.json"
    template_bundle_dir: "{{ playbook_dir }}/../../bundles/core/proxmox/configure/templates/ubuntu_noble"
```

Scenarios that need a subset of the family + a different subnet (e.g. bs2 once
migrated) override the optional vars :

```yaml
- import_playbook: ../../bundles/core/proxmox/configure/templates/ubuntu_noble/main.yml
  vars:
    manifest_path:         "{{ playbook_dir }}/manifest/scenario_vms.json"
    template_bundle_dir:   "{{ playbook_dir }}/../../bundles/core/proxmox/configure/templates/ubuntu_noble"
    template_subnet_octet: 140
    templates_whitelist:   [medium-02]    # only the medium-02 template
    apt_proxy_url:         "http://apt-proxy.lan:3142"
```

## Files in this directory

- `main.yml` - bundle entry (orchestrates the 3 stages described above)
- `00..04-template-vm-*.yml` - per-template create plays (12 files)
- `_apply_apt_proxy.yml` - attach/detach cicustom apt proxy
- `_update_templates.yml` - start + apt update + auto-poweroff + convert pipeline
- `range42-template-bootstrap.yaml.j2` - cloud-init bootstrap snippet (templated by `_update_templates.yml`)
- `test_setup_templates.yml` + `.sh` - ad-hoc test runner for a single throwaway VM (vm_id 8001)
- `README.md` - this file
