# bundles/admin/credentials.sync.vaultwarden

Credential sync wiring - 1 play, run on the **control node** (the deployer) :

1. drive the `range42-catalog` role
   [`credentials.vaultwarden`](../../../../range42-catalog/02_ansible_layer/admin/roles/credentials.vaultwarden/)
   to push/pull values between the scenario's Ansible vault and a self-hosted
   Vaultwarden server, entirely from the caller's `vaultwarden_sync_map`.

Spin the server up first with the companion bundle
[`admin/software.install.vaultwarden`](../software.install.vaultwarden/).

The role shells out to the Bitwarden CLI locally, so this play targets
`localhost` and needs no reachable inventory host - but **the control node must
reach `vaultwarden_url`** and have `bw` + `jq` installed. Both are checked ; the
role fails loudly rather than skipping.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `vaultwarden_url` | `https://192.168.142.189:8080` | server URL as seen **from the control node** |
| `vaultwarden_client_id` | `{{ vault_vw_client_id }}` | personal API-key client_id, **from the vault** |
| `vaultwarden_client_secret` | `{{ vault_vw_client_secret }}` | personal API-key secret, **from the vault** |
| `vaultwarden_master_password` | `{{ vault_vw_master_password }}` | account master password, **from the vault** |
| `vaultwarden_sync_map` | see below | the get/set entries to apply |

## Optional vars

| var | default | purpose |
|-----|---------|---------|
| `vaultwarden_ca_cert` | unset | path **on the control node** to a cert PEM `bw` should trust (required with the install bundle's self-signed TLS) |
| `vaultwarden_organization_id` | `""` | org scoping ; Vaultwarden requires a collection id too for org items |
| `vaultwarden_collection_id` | `""` | |
| `vw_sync_host` | `localhost` | play target |
| `vw_vault_file` | `<workspace>/secrets/default_vault.yml` | override the autoloaded vault |

## The sync map

`vaultwarden_sync_map` is yours to define - neither the bundle nor the role
hardcodes any credential name :

```yaml
vaultwarden_sync_map:
  # push a value from the vault into Vaultwarden ...
  - vault_var: misp_writer_api_key
    vw_item:   "range42-{{ lookup('env','RANGE42_INFRASTRUCTURE_CODENAME_LAB_NAMES') }}-misp"
    vw_field:  writer_api_key
    direction: set
  # ... or pull a centrally-managed value back into a fact
  - vault_var: shared_service_token
    vw_item:   "range42-org-shared"
    vw_field:  token
    direction: get
```

`direction: set` reads the Ansible var named by `vault_var` ; `direction: get`
**creates a fact** under that name (and collects everything into the dict fact
`vaultwarden_get_results`). Naming items after
`$RANGE42_INFRASTRUCTURE_CODENAME_LAB_NAMES` keeps each CODENAME-SCENARIO's
items distinct.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/credentials.sync.vaultwarden/main.yml"
  when: INSTALL_VAULTWARDEN_SYNC | default("NO") | upper == "YES"
  vars:
    vaultwarden_url:             "https://192.168.142.189:8080"
    vaultwarden_ca_cert:         "{{ lookup('env','RANGE42_ANSIBLE_ROLES__INVENTORY_DIR') ~ '/../secrets/vaultwarden-cert.pem' }}"
    vaultwarden_client_id:       "{{ vault_vw_client_id }}"
    vaultwarden_client_secret:   "{{ vault_vw_client_secret }}"
    vaultwarden_master_password: "{{ vault_vw_master_password }}"
    vaultwarden_organization_id: "{{ vault_vw_org_id | default('') }}"
    vaultwarden_collection_id:   "{{ vault_vw_collection_id | default('') }}"
    vaultwarden_sync_map: [...]
```

## Guarantees

- **Opt-in** - no effect on scenarios that don't import it.
- **Self-hosted only** - no public/cloud endpoint anywhere in the bundle or the role.
- **Fails loudly** - missing tooling, unreachable server, bad auth, ambiguous
  item name, or a missing/blank field on `get` aborts the run. Secrets never
  reach argv or logs (`no_log` throughout, values passed via env/stdin).

## Prerequisites

- `bw` and `jq` on the control node. Current `bw` CLIs (2026.x) work, but need
  the element's TLS enabled **and** `vaultwarden/server` >= 1.37.0 (the element
  pins it) - see "Client compatibility" in the catalog element README.
- A **one-time Vaultwarden bootstrap** (service account + personal API key),
  then those values in the scenario vault.
