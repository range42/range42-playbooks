# vm.bootstrap

Shared per-VM stage_00 playbook. One bundle, N call-sites.

Replaces the duplicated `scenarios/*/stage_00/<vm>.yml` files where each per-VM
playbook re-implemented the same five-step pattern :

1. `vm_clone` from the source template
2. wait for the proxmox unlock to clear (post-clone)
3. verify the exact `range42-deployment:<id>` description marker when `r42_deployment_id` is supplied, before any tag/configuration mutation
4. `vm_set_tag` (admin / student / ctf)
5. `cloudinit_set_variables` (user / password / ssh key / IP / netmask / dns / gateway / bridge)
6. optional CPU/RAM, secondary NIC configuration and cloned VM disk growth
7. `vm_start`

Then a second play on the VM's ssh alias :

8. `ansible.utils` with `wait/openssh_server/is_reachable.yml` + `wait/cloudinit/is_boot_finished.yml`

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/proxmox/vm.bootstrap/main.yml"
  vars:
    global_vm_id:                 1100
    global_vm_name:               "admin-wazuh"
    global_vm_description:        ""
    global_vm_tag_name:           "admin"
    global_vm_ci_ip:              "192.168.142.100"
    global_vm_ssh_name:           "r42.admin-wazuh"
    global_template_vm_id:        9232
    global_template_name:         "03-template-vm-medium-02-8g-64g"
    global_vm_net_virtio_bridge:  "vmbr142"
    global_vm_ci_ip_gw:           "192.168.142.1"
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
| `global_vm_net_virtio_bridge` | proxmox bridge (`vmbr142` admin / `vmbr143` student / `vmbr144` ctf) |
| `global_vm_ci_ip_gw` | default gateway for the subnet |

## Optional vars (with defaults)

| var | default |
|---|---|
| `global_vm_description` | `''` |
| `global_template_name` | unset (used only in task names for readability) |
| `global_vm_ci_dns_ips` | `1.1.1.1` |
| `global_vm_ci_netmask` | `24` |
| `global_vm_extra_config` | `{}`; permits `cores`, `memory`, `net1`–`net31`, `ipconfig1`–`ipconfig31` |
| `global_vm_disk` | `{}`; e.g. `{disk: scsi0, size_gb: 40}` |

All caller-input vars use the `global_*` prefix convention. The bundle internally
maps them to the un-prefixed names the `range42-ansible_roles-proxmox_controller`
role expects (e.g. `global_vm_ci_ip_gw` -> `vm_ci_ip_gw`). This avoids the
self-reference anti-pattern that would otherwise cause Ansible templating loops.

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


## Configuration and ownership guarantees

New UI scenarios pass `r42_deployment_id` and the corresponding description into the clone API call. After the clone unlocks, this bundle reads the VM configuration and requires an exact ownership-marker line before tagging, cloud-init or startup. An unrelated VM that appears at the requested VMID and causes the controller's idempotent clone to skip is therefore rejected.

Optional CPU, memory and secondary NIC updates use the current Proxmox configuration digest. Primary `net0`/`ipconfig0` remain controlled by the existing cloud-init arguments. Additional NIC changes regenerate cloud-init before startup. `global_vm_extra_config` accepts no other Proxmox configuration keys.

Disk growth reads a fresh digest after configuration updates, uses the Proxmox VM `/resize` API, and waits for its task to complete before startup. It rejects shrinking, CD-ROM/cloud-init/ISO paths, template volumes, missing sizes and disks belonging to other VMIDs. The volume must use Proxmox's standard `vm-<vmid>-disk-<n>` naming. An already-correct disk size does not issue another resize. This path never runs `qemu-img` or changes the downloaded cloud image. Filesystem growth inside the guest remains the responsibility of cloud-init or guest orchestration.

New API calls verify certificates and accept `RANGE42_PROXMOX_CA_FILE` as a PEM CA bundle. Existing inventories can set `proxmox_api_validate_certs` explicitly. `capabilities.json` advertises `extra_nics`, `resources` and `disk_resize` so the backend can reject extended manifests against an older installed bundle.

The integration tests run the actual bundle and controller role against a local HTTPS Proxmox simulator. They check ownership refusal before mutation, NIC/CPU/memory updates, digest-protected disk growth, cloud-init ordering, and rejection of shrinking/ISO/template-source disks. Run with a Python environment providing pytest, cryptography and ansible-playbook, setting `RANGE42_CONTROLLER_TEST_ROOT` to the controller checkout.
