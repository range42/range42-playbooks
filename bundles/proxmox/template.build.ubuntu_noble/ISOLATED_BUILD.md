# Isolated Noble template preparation

`isolated.yml` prepares one explicit owned template without invoking the fixed
twelve-template family or its shared proxy updater. It is an operator Ansible
entrypoint, not a deployer-UI template-creation feature. It has not been activated
or run against a real guest. A fresh template and successful three-guest content
acceptance remain unverified.

This work is based on installed playbooks
`a15086757d39648d5f4c772632c72830da622e05` and requires controller
`d4d74ed4b2170c88eeec1e5571f467a972517048`, an additive child of installed
`99fd63cfcf65a52eaed05af4404f81522acfaa52`. No newer SDN branch is pulled in. The
normal guest bootstrap continues to use catalog
`0b170a768b9603cf8f5b080e4eac780cbad07c75` and its unchanged500-second wait.

## Before an authorized build

Record a new32-character lowercase hex build ID and a fresh explicit VMID.
IDs below10000 are refused, protecting the historical template/service ranges.
Confirm that both the ID and every chosen address are free in current Proxmox
inventory, installed manifests/reservation files, and backend draft/committed
allocations. This CLI entrypoint does not create a backend allocation claim or
read its database. Acquire the installation's existing provisioning lock for the
entire operation on the actual backend controller and its shared workspace
filesystem, not a separate workstation lock. Coordinate external Proxmox writers. The source guards do
not claim to control external writers or reserve an otherwise unused address.

Preserve9901 and the shared `noble-minimal-cloudimg-amd64.img` cache. The existing
`storage_download_iso` role can download to a separate plain filename using
`iso_url`, `iso_file_name`, `proxmox_storage` and `iso_file_content_type`. Select
a dated official Noble image and record its reviewed SHA256 first. Require that
checksum even when the download role would otherwise permit an unverified
cache; `isolated.yml` independently verifies it before VM creation and never
downloads or replaces the image itself. Current-image URLs are not immutable
pins. [Ubuntu image listings](https://cloud-images.ubuntu.com/minimal/releases/noble/)

Use an existing bridge/subnet with a usable literal IPv4 address, gateway and
DNS. This builder does not create SDN objects, change NAT or change mirrors.
Provide enough measured disk capacity for the complete requested virtual disk;
it does not treat thin provisioning as guaranteed free space. The reused import
role uses native `storage:vm-<id>-disk-0` volume names; directory-backed VM-image
storage and arbitrary disk layouts are not supported by this isolated path.
The preflight explicitly requires `lvmthin` for disks and `dir` for snippets,
with active/enabled status, correct content types and readable free bytes.

The inventory must contain exactly one `proxmox` host and exactly its
`<inventory_hostname>-cli` counterpart in `proxmox_cli`. The SSH endpoint must
be the declared node, with privileged access to `pvesh`, `qm` and selected
storage. The API uses verified TLS, and its unique cluster CA fingerprint must
match the privileged SSH certificate inventory before any create POST. The
guest inventory alias must resolve to the exact planned IP, with a matching
owner-specific SSH private key, explicit host-key policy and sudo permission.
Keep credentials in the existing private inventory/vault; never place them in
the public plan or evidence. The role loads
`$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml` as existing bundles do.

## Input and invocation

Provide only this literal plan plus the existing private Proxmox/SSH variables.
The example ID/address are illustrative, not a reservation. Replace the image
checksum with the reviewed64-character digest before use.

```yaml
template_build:
  build_id: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa # generate a new unique build ID
  vm_id: 62000
  name: r42-template-owned-noble
  node: pve01
  image_path: /var/lib/vz/template/iso/r42-noble-20260905.img
  image_sha256: REPLACE_WITH_REVIEWED_SHA256
  disk_storage: local-lvm
  snippet_storage: local
  disk_gb: 16
  cores: 1
  memory_mb: 1024
  bridge: r42smk
  address: 10.42.70.30/24
  gateway: 10.42.70.1
  dns: [1.1.1.1]
  guest_host: r42-template-owned-noble
  apt_proxy_url: '' # optional; only HTTP(S) without embedded credentials
```

```sh
ansible-playbook -i PRIVATE_INVENTORY \
  bundles/proxmox/template.build.ubuntu_noble/isolated.yml \
  -e @REVIEWED_PLAN.yml
```

Set `ANSIBLE_ROLES_PATH` to the exact controller checkpoint and use the existing
verified Proxmox CA environment. Do not provide the legacy global `vm_disk_size`
or `vm_iso_file`: the reused create role would allocate an unrelated initial
disk/ISO, so the isolated caller rejects them before writes. Guest credentials
come from `default_admin_vm_ci_user` and `default_admin_vm_ci_ssh_key` plus the
matching private SSH inventory configuration. The plan itself accepts no
password, private key, script, Jinja expression or arbitrary extra parameter.

## Completion, failure and resume

The initial create POST includes an exact ownership marker and a hash covering
the normalized complete plan. Existing IDs are refused by default. Subsequent
mutations require the same VM name, node, marker and plan hash; an external
same-ID create race cannot be silently adopted. The returned `qmcreate` UPID
must name this node and VM, finish, and report `OK` before disk preparation.
Missing, mismatched or failed workers leave the owned partial VM for inspection.
[Proxmox asynchronous VM creation](https://github.com/proxmox/qemu-server/blob/master/src/PVE/API2/Qemu.pm)

The image is imported into this
VM's owned disk using the existing controller role, leaving source bytes intact.
Only a private per-build snippet is attached; no fixed family or shared proxy
snippet is changed.

Package update and upgrade stay enabled. The new preparation snippet omits
automatic poweroff. Within the separate existing30-minute preparation budget,
the guest helper requires the current build/plan marker, error-free terminal
cloud-init state, a completed package-module semaphore and an empty successful
`dpkg --audit`. It never exports raw status, audit text, package names, argv,
environment or logs. Missing, malformed, degraded or incomplete evidence cannot
permit conversion. Captured subprocess output and time are bounded; child
process groups are cleaned safely on timeout.

After success is independently rechecked, the helper runs
`cloud-init clean --machine-id`, retains any custom-clean output privately and
verifies reset machine identity and removed instance cache. Only then does the
controller shut down and convert the VM. This occurs after cloud-init has
finished, unlike cleaning inside an earlier boot module. The documented purpose
is a fresh machine identity/cloud-init run for each clone, not a policy bypass.
[Cloud-init clean](https://docs.cloud-init.io/en/latest/reference/cli.html#clean)

If a proxy was configured, the selected template keeps its own snippet containing
only `#cloud-config` plus that apt proxy setting. Otherwise its bootstrap snippet
is detached and removed after successful conversion/readback. The header is
required for cloud-config interpretation. [Cloud-config format](https://docs.cloud-init.io/en/latest/explanation/format/cloud-config.html)

On failed readiness, the VM and snippet remain owned and the playbook fails; it
does not auto-delete diagnostic state or report a template success. To resume
an ordinary unfinished VM, pass `template_build_resume: true` with the identical
plan/build ID. A matching running build is observed without forced stop,
reconfiguration or restart. Stopped resumes must retain the original CPU, RAM,
NIC and any already-configured address. Unexpected disks, extra IDE/NIC devices,
shared/source-image references or ambiguous unfinished imports are refused
before another storage write. No automatic adoption or repair of such states is
claimed. A completed template is also refused rather than re-prepared.

A failure after clone-identity cleanup but before final conversion may need
explicit owned recovery: cached guest readiness has deliberately been cleared,
so a blind rerun cannot reuse that success proof. Retain the build/plan record
and inspect ownership/state before any recovery or cleanup. Remove only this
owned VM and its known volumes/snippet when cleanup is authorized; preserve the
original template, image and unrelated networks/guests.

## Validation and remaining limits

Focused local validation passed59checks in119.31seconds:27plan/ownership cases,
20readiness/bounds/cleanup cases and12actual Ansible orchestration cases using
the real roles against a TLS PVE fixture. Guest package/cleanup behavior is
simulated in the orchestration fixture; helper tests validate the parsing and
bounded subprocess behavior separately. Follow-up storage regressions passed
2 focused checks; asynchronous-create regressions and affected success/failure
paths passed 5 checks, then 2 additional missing/wrong-worker checks. Scoped
Ruff and YAML/diff checks passed. This is not real Ubuntu image acceptance.

The operator invocation and report remain native Ansible: named validation,
readiness, clone-cleanup and conversion tasks end with the standard play recap.
The guest helper returns a fixed proof under `no_log`; no raw cloud-init or
package report is exposed. The local orchestration tests execute that same
Ansible entrypoint with an isolated TLS API and local command fixtures.

Regressions reproduced false adoption/missing markers, active-resume forced
stop, extra IDE/stopped configuration drift, cross-cluster API/SSH mismatch,
missing proxy header and false success after a zero-exit conversion without
template readback. Existing family `main.yml`, `_apply_apt_proxy.yml` and
`_update_templates.yml` remain unchanged and retain their separately documented
scope/completion limitations. The repeated500-second failure's exact cause,
current9901package freshness and successful three-guest content deployment are
still unresolved. No live template/image download or mutation was performed.
