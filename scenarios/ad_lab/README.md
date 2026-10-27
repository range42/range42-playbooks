# ad_lab

Active Directory scenario: one **Windows Server 2025 domain controller** for the domain
`range42.lab` (NetBIOS `RANGE42`), with the DNS server of the domain, and one **Windows 11
Enterprise client** joined to that domain. Both run on the SDN vnet `net151` and are reached over
OpenSSH with a PowerShell shell.

The two VMs ARE the workload of this scenario: always deployed, no feature flag
(`manifest/feature_flags.yml` has `features: []`). The scenario started as a copy of `misp_lab`.

## Network architecture

```
Proxmox host (holds 192.168.151.1, routes, SNAT to the outside)
 |
 +-- net140  192.168.140.0/24  templating (build of 9250 and 9251 only)
 |
 +-- net151  192.168.151.0/24  ad_lab
       +-- ad-dc01      .201  (VMID 1201)  domain controller, DNS of range42.lab
       +-- ad-client01  .202  (VMID 1202)  domain member, DNS = 192.168.151.201
```

Both vnets have SNAT on. The Windows 11 template build downloads the OpenSSH server through
`net140`, and the evaluation editions must activate online (see "Evaluation editions").

## VM details

| VM name | VM ID | IP | vnet | Template | Role |
|---|---|---|---|---|---|
| ad-dc01 | 1201 | 192.168.151.201 | `net151` | template-vm-win2025-02-4g-64g (9250) | domain controller, DNS server |
| ad-client01 | 1202 | 192.168.151.202 | `net151` | template-vm-win11-02-4g-64g (9251) | domain member |

Source of truth: `manifest/scenario_vms.json`. Each VM has 2 vCPU, 4 GB of RAM and a 64 GB disk,
inherited from its template. Host names stay at most 15 characters (NetBIOS limit).

The templates come from `bundles/proxmox/template.build.windows` (unattended build from the
Microsoft evaluation ISOs). Read its README before the first deploy, in particular "Clone
contract" and "Operations" (build time).

## Accounts and passwords

| Account | Where | Password | SSH |
|---|---|---|---|
| `alice` | local administrator baked into both templates ; on the DC it becomes the domain account `RANGE42\alice` at the promotion | vault `default_admin_vm_ci_password` | yes, key only (deployer key) |
| built-in `Administrator` (RID 500) of ad-dc01 | set before the promotion, then **domain** Administrator `RANGE42\Administrator` | vault `ad_lab_builtin_admin_password` | no key installed |
| `bob` | domain user, created on the DC | vault `ad_lab_user_password` | no |
| built-in `Administrator` of ad-client01 | local, **disabled** (Windows 11 default ; the join role fails if it is enabled) | - | - |

**On the DC, `alice` and `Administrator` no longer share a password.** A clone of template 9250
carries the vault `alice` password on the built-in Administrator too, and cloudbase-init does not
change it. `software.install.ad_domain_controller` sets `ad_lab_builtin_admin_password` on that
account before the promotion, so the domain Administrator gets its own value. ad-client01 joins
the domain with `Administrator@range42.lab`.

The DSRM password of the DC is `ad_lab_dsrm_password`. The three `ad_lab_*` values must be in the
scenario vault before the deploy (see `templates/vault-example.yml`). They must satisfy the
default domain password policy: at least 7 characters and three of the four classes (upper case,
lower case, digits, symbols).

## What the deploy does

`./ad_lab.setup.sh` runs `main.yml`:

1. `_firewall` stages 00 and 01: firewall status report, management access on the datacenter and
   node chains (rules only).
2. `00_sdn_bootstrap`: creates `net140` and `net151` when missing, never deletes.
3. `01_templates-bootstrap`: builds templates 9250 and 9251 when missing ; existing templates are
   skipped.
4. `02_ad_infrastructure` stage_00: clones ad-dc01 and ad-client01 with
   `bundles/proxmox/vm.bootstrap`, waits for SSH and for the end of cloudbase-init. The SSH wait
   makes up to 180 attempts, 5 s apart, each with a 5 s connect timeout: at least 15 minutes,
   25 minutes measured when SSH never answers. The first boot after sysprep takes up to about
   15 minutes.
5. `_firewall` stages 02 and 03: declares the AD and RDP accepts (below) and the SSH accept.
6. `02_ad_infrastructure` stage_01, in this order:
   - `admin/software.install.ad_domain_controller` on ad-dc01: built-in Administrator password,
     promotion to the first DC of a new forest with DNS, reboot, DNS forwarder `1.1.1.1` ;
   - `admin/systems.configure.ad_objects` on ad-dc01: the user `bob` ;
   - `generic/systems.configure.ad_domain_member` on ad-client01: DNS to the DC, join, reboot,
     checks (member of `range42.lab`, local built-in Administrator disabled).
7. `_firewall` stage 04: arming, only with `-e FIREWALL_ARM_VMS=YES` (default NO).

**Do not rerun `./ad_lab.setup.sh` on running VMs.** A second run does not clone again, but
`bundles/proxmox/vm.bootstrap` applies the cloud-init settings again through the action
`cloudinit_set_variables` of the Proxmox controller role, and that action **stops** a running VM
first (power off, not a guest shutdown), then starts it. This is the behaviour of every scenario
built on `vm.bootstrap`. Measured on this scenario: the domain controller logged an unexpected
shutdown (System event 6008) and came back ; the Windows 11 client stayed on the boot screen with
no CPU activity, never answered SSH, and the run failed after 180 SSH retries. To deploy again, run
`./ad_lab.delete_vms_only.sh` first, or `./ad_lab.reset.setup.sh`.

## Firewall

What the deploy declares on the Proxmox per-NIC firewall (rules only, inert until armed):

- ad-dc01 (1201): `firewall.baseline.ad_domain_controller` - tcp 53, 88, 135, 139, 389, 445,
  464, 636, 3268, 3269, 9389 and 49152:65535 (RPC dynamic range), udp 53, 88, 123, 137, 138, 389,
  464, each from `192.168.151.0/24` only ;
- ad-dc01 and ad-client01: tcp 3389 (RDP) from `192.168.151.0/24` only ;
- both: the SSH accept of `firewall.baseline.ssh_all_vms`.

The source `192.168.151.0/24` covers the domain members and the node itself (`192.168.151.1`), from
which the jump-host forwards below arrive. The armed state of this rule set is not tested yet.

## RDP through the jump host

The VMs have no route from the outside. Forward a local port through the jump host, then connect
an RDP client to it, for example for the client:

```bash
ssh -N -L 13389:192.168.151.202:3389 px.<codename>.jumper
# RDP client -> localhost:13389
```

## Evaluation editions

- Windows Server 2025 evaluation: 180 days from activation ; Windows 11 Enterprise evaluation:
  90 days from activation.
- The evaluation must activate online within 10 days, otherwise Windows Server shuts down every
  hour. Keep SNAT on `net151` during the first days.

## Usage

```bash
range42-context use <codename> ad_lab
./ad_lab.setup.sh                       # full deploy (templates built if missing)
./ad_lab.setup.sh -e FIREWALL_ARM_VMS=YES
```

## Wrapper scripts

| Script | Effect |
|---|---|
| `ad_lab.setup.sh` | `main.yml` : networks, templates, VMs, AD configuration |
| `ad_lab.setup_vms_only.sh` | `main_vms_only.yml` : same without the template build |
| `ad_lab.setup_networks.sh` | `00_sdn_bootstrap` only (`--dry-run` : read-only diff) |
| `ad_lab.delete_vms_only.sh` | stops and destroys 1201 and 1202 (from the manifest), keeps the templates |
| `ad_lab.delete_all.sh` | same, plus the templates 9250 and 9251 (rebuild : 30 minutes to more than one hour each) |
| `ad_lab.reset.setup.sh` | deletes the VMs, then runs `main.yml` |
| `ad_lab.reset.ssh_keys.sh` | removes the known_hosts entries of the VM addresses |
| `ad_lab.delete_networks.sh` | removes the subnets and vnets named in the manifest, `net140` included ; it refuses while a VM or template of the manifest still exists |

## Structure

```
ad_lab/
  main.yml / main_vms_only.yml
  00_sdn_bootstrap/_main.yml                     net140 + net151
  01_templates-bootstrap/_main.yml               template.build.windows (win2025, win11)
  02_ad_infrastructure/
    _main.yml                                    devkit-only wrapper
    _main_stage_00.yml / _main_stage_01.yml
    stage_00-vm_bootstrap/_ad_group.yml          two vm.bootstrap blocks
    stage_01-vm_configure/ad-dc.yml              promotion + user bob
    stage_01-vm_configure/ad-client.yml          domain join
  _firewall/                                     five moments, see its README
  manifest/scenario_vms.json, feature_flags.yml
  templates/                                     inventory, ssh-config, vars, vault example
```

The inventory group `r42_ad_windows` (`ansible_shell_type: powershell`, `ansible_user: alice`)
holds `r42_ad_dc` (`r42.ad-dc01`) and `r42_ad_clients` (`r42.ad-client01`).

## Notes

- The domain names come from `templates/ansible-vars.yml` (`ad_lab_domain`, `ad_lab_netbios`) ;
  the stage_01 files fall back to the same values.
- A change of `ad_lab_builtin_admin_password` after the first deploy is not applied by a rerun :
  the DC role sets it only before the promotion.
- A change of `default_admin_vm_ci_password` needs a rebuild of both templates (template bundle
  README, "Operations").
- A reboot of the Windows 11 clone can be slow on this kind of host: the reboot that cloudbase-init
  starts to set the host name was measured at 16 minutes. The wait for the end of cloudbase-init
  (`ansible.utils`, `wait/cloudinit/is_boot_finished.yml`) stops after 60 attempts 10 s apart, so
  the deploy can fail there while the VM comes up a few minutes later. In that case run
  `./ad_lab.delete_vms_only.sh`, then `./ad_lab.setup.sh` again. A new deploy can hit the same slow
  reboot: it was measured on one of the two fresh deploys of this scenario.
