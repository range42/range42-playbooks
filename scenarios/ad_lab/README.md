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
   15 minutes. The cloudbase-init wait makes up to 150 attempts, at least 10 s apart: at least
   25 minutes. The reboot that cloudbase-init starts to set the host name of the Windows 11
   clone was measured at 16 minutes, more than the default budget of 60 attempts.
5. `_firewall` stages 02 and 03: declares the AD and RDP accepts (below) and the SSH accept.
6. `02_ad_infrastructure` stage_01, in this order:
   - `admin/software.install.ad_domain_controller` on ad-dc01: built-in Administrator password,
     promotion to the first DC of a new forest with DNS, reboot, DNS forwarder `1.1.1.1` ;
   - `admin/systems.configure.ad_objects` on ad-dc01: the user `bob` ;
   - `generic/systems.configure.ad_domain_member` on ad-client01: DNS to the DC, join, reboot,
     checks (member of `range42.lab`, local built-in Administrator disabled) ;
   - `generic/systems.configure.windows_eval_activation` on both VMs: online activation of the
     evaluation editions (see "Evaluation editions") ;
   - `generic/systems.configure.rdp_access` on both VMs: Remote Desktop, `RANGE42\bob` in
     "Remote Desktop Users" of ad-client01 (see "RDP through the jump host").
7. `_firewall` stage 04: arming, only with `-e FIREWALL_ARM_VMS=YES` (default NO).

A second `./ad_lab.setup.sh` on running VMs does not clone again and does not restart them:
`bundles/proxmox/vm.bootstrap` skips the cloud-init update when the VM is running and its
cloud-init user, SSH key, IP address, gateway, DNS server and net0 bridge already have the
requested values. When one of them differs, the action `cloudinit_set_variables` of the Proxmox
controller role **stops** the running VM (power off, not a guest shutdown), writes the settings,
and the VM is started again. Measured on this scenario before that check existed: the domain
controller logged an unexpected shutdown (System event 6008) and came back ; the Windows 11 client
never answered SSH again. Proxmox does not return the cloud-init password, so a change of the
password alone is not detected: stop the VM first, or redeploy with `./ad_lab.delete_vms_only.sh`
and `./ad_lab.setup.sh`.

## Firewall

What the deploy declares on the Proxmox per-NIC firewall (rules only, inert until armed):

- ad-dc01 (1201): `firewall.baseline.ad_domain_controller` - tcp 53, 88, 135, 139, 389, 445,
  464, 636, 3268, 3269, 9389 and 49152:65535 (RPC dynamic range), udp 53, 88, 123, 137, 138, 389,
  464, each from `192.168.151.0/24` only ;
- ad-dc01 and ad-client01: tcp 3389 (RDP) from `192.168.151.1/32` only ;
- both: the SSH accept of `firewall.baseline.ssh_all_vms`.

The source `192.168.151.0/24` covers the domain members. `192.168.151.1` is the node itself, from
which the jump-host forwards below arrive: RDP accepts only that address. The armed state of this
rule set is not tested yet.

## RDP through the jump host

`generic/systems.configure.rdp_access` enables Remote Desktop on both VMs : `fDenyTSConnections`
0, the Windows firewall rule group "Remote Desktop" enabled, `TermService` running, listener on
tcp 3389. Network Level Authentication stays on : the RDP client must authenticate before the
session opens.

Accounts that can log on:

| VM | Accounts | Why |
|---|---|---|
| ad-dc01 (192.168.151.201) | `RANGE42\alice`, `RANGE42\Administrator` | administrators of the domain (built-in `Administrators`) ; on a DC the RDP log-on right is granted to Administrators only |
| ad-client01 (192.168.151.202) | `RANGE42\bob` | member of the local group "Remote Desktop Users" (the deploy adds it) |
| ad-client01 | `RANGE42\Administrator` | member of `Domain Admins`, which is in the local Administrators group of the client |
| ad-client01 | `AD-CLIENT01\alice` (local account, `.\alice`) | local administrator from the template |

`RANGE42\alice` cannot log on to ad-client01 : it is a member of the domain built-in
`Administrators` group, not of `Domain Admins`. The local Administrators group of the client holds
the local Administrator, the local `alice` and `RANGE42\Domain Admins` ; "Remote Desktop Users"
holds `RANGE42\bob` only.

Two paths reach tcp 3389:

- **Direct route, while the Proxmox firewall is not armed.** The Proxmox firewall rules are
  declared but not armed (see "Firewall"), so the Proxmox firewall does not filter tcp 3389. An
  RDP client on a host with a route to `192.168.151.0/24` through the node connects directly to
  `192.168.151.201:3389` or `192.168.151.202:3389`.
- **Port forward through the jump host.** The forwarded connection leaves the node from
  `192.168.151.1`, the only source that the declared RDP rule allows once the firewall is armed
  (armed state not tested yet). Use this path from a host without a route to `192.168.151.0/24`,
  and after arming:

```bash
ssh -N -L 13389:192.168.151.202:3389 px.<codename>.jumper   # ad-client01
ssh -N -L 13390:192.168.151.201:3389 px.<codename>.jumper   # ad-dc01
# RDP client -> localhost:13389 or localhost:13390
```

## Evaluation editions

- Windows Server 2025 evaluation: 180 days from activation ; Windows 11 Enterprise evaluation:
  90 days from activation.
- A clone starts with an expired grace period (sysprep rearms it) and must activate online.
  Windows tries it at the first boot. When that attempt fails, the next automatic attempt is one
  day later, and `wlms.exe` (Windows Licensing Monitoring Service) shuts the VM down 60 minutes
  after each boot (System event 1074 by `wlms.exe`, WLMS event 101).
- The DNS path of the client to the Microsoft activation hosts is the DC : the only DNS server of
  ad-client01 is 192.168.151.201, which resolves external names through its forwarder `1.1.1.1`.
  Measured on an earlier deploy : the first-boot activation of the client failed with event 8200
  `hr=0x80072EE7` (name not resolved) because the DC did not resolve external names at that moment
  (before the DC role had set its forwarder), and the client shut down 60 minutes
  after boot.
- The deploy therefore activates both VMs explicitly in stage_01, after the client join
  (`systems.configure.windows_eval_activation` : `slmgr.vbs /ato`, 11 attempts 60 s apart by
  default), after the DC has its forwarder. When no attempt succeeds, it fails with the `hr=0x...`
  code of the last SPP event 8200, or says that no event 8200 was found. A rerun on activated VMs
  reports `ok`.
- Keep SNAT on `net151` : the activation needs outbound HTTPS.

## Nested virtualisation

The Windows templates keep `cpu host` (the VMs see VMX) but have VBS, HVCI and Credential Guard
turned off in the registry (the `bcdedit` hypervisor setting of the build does not reach the
clones). Under nested virtualisation a Windows 11 clone that
launches its hypervisor at boot stayed on the boot spinner for hours. The lab posture without
Credential Guard is intended : it keeps credentials in the LSASS memory for the exercises. Details
and measurements : `bundles/proxmox/template.build.windows/README.md`, "Nested virtualisation".

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
    stage_01-vm_configure/eval-activation.yml    online activation of both VMs
    stage_01-vm_configure/rdp-access.yml         Remote Desktop on both VMs
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
- If a deploy still stops in the cloudbase-init wait (a reboot slower than 25 minutes), run
  `./ad_lab.delete_vms_only.sh`, then `./ad_lab.setup.sh` again.
