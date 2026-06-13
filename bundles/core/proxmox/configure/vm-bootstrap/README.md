# vm-bootstrap

Shared per-VM stage_00 playbook. One bundle, N call-sites.

Replaces the duplicated `scenarios/*/stage_00/<vm>.yml` files where each per-VM
playbook re-implemented the same five-step pattern :

1. `vm_clone` from the source template
2. wait for the proxmox unlock to clear (post-clone)
3. `vm_set_tag` (admin / student / ctf)
4. `cloudinit_set_variables` (user / password / ssh key / IP / netmask / dns / gateway / bridge)
5. `vm_start`

Then a second play on the VM's ssh alias :

6. `ansible.utils` with `wait/openssh_server/is_reachable.yml` + `wait/cloudinit/is_boot_finished.yml`

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/core/proxmox/configure/vm-bootstrap/main.yml"
  vars:
    global_vm_id:          1100
    global_vm_name:        "admin-wazuh"
    global_vm_description: ""
    global_vm_tag_name:    "admin"
    global_vm_ci_ip:       "192.168.142.100"
    global_vm_ssh_name:    "r42.admin-wazuh"
    global_template_vm_id: 9232
    global_template_name:  "03-template-vm-medium-02-8g-64g"
    vm_net_virtio_bridge:  "vmbr142"
    vm_ci_ip_gw:           "192.168.142.1"
```

## Required vars

| var | meaning |
|---|---|
| `global_vm_id` | proxmox vm id of the new VM |
| `global_vm_name` | hostname / proxmox name |
| `global_vm_tag_name` | proxmox tag (`admin` / `student` / `ctf`) |
| `global_vm_ci_ip` | cloud-init IP of the new VM |
| `global_vm_ssh_name` | ssh alias used by the second play (`r42.<hostname>`) |
| `global_template_vm_id` | proxmox vm id of the source template |
| `vm_net_virtio_bridge` | proxmox bridge (`vmbr142` admin / `vmbr143` student / `vmbr144` ctf) |
| `vm_ci_ip_gw` | default gateway for the subnet |

## Optional vars (with defaults)

| var | default |
|---|---|
| `global_vm_description` | `''` |
| `global_template_name` | unset (used only in task names for readability) |
| `vm_ci_dns_ips` | `1.1.1.1` |
| `vm_ci_netmask` | `24` |

## Cloud-init credentials

Pulled from the scenario vault under `$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml`
(loaded by `range42-context use <codename> <scenario>` then sourced into the env) :

- `vm_ci_user` = `default_admin_vm_ci_user` (fallback `alice`)
- `vm_ci_password` = `default_admin_vm_ci_password` (fallback `supersecret`)
- `vm_ci_ssh_key` = `default_admin_vm_ci_ssh_key`

## Paths

The bundle resolves :

- The scenario vault via `RANGE42_ACTIVE_CONFIG_DIR` (exported by `range42-context use`)
- Itself (call-site) via `RANGE42_GITDIR__ROOT_DIR`

No `playbook_dir` quirks, no relative `../../` traversal.
