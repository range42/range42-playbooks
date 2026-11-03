# bundles/proxmox/template.build.windows

Builds two Windows VM templates on a Proxmox VE hypervisor, fully unattended, from the
Microsoft evaluation ISOs:

| code      | vm_id | name                            | OS                                                      | build IP (default)  |
|-----------|-------|---------------------------------|---------------------------------------------------------|---------------------|
| `win2025` | 9250  | `template-vm-win2025-02-4g-64g` | Windows Server 2025 Standard Evaluation (Desktop Experience) | 192.168.140.250 |
| `win11`   | 9251  | `template-vm-win11-02-4g-64g`   | Windows 11 Enterprise Evaluation                        | 192.168.140.251     |

Both: 2 vCPU (`cpu host`), 4 GB RAM (no ballooning), 64 GB disk. A full clone of a template
is bootstrapped by `bundles/proxmox/vm.bootstrap` exactly like a Linux clone (see
[Clone contract](#clone-contract)).

## Pipeline

`main.yml` holds the template table and imports `_build_templates.yml`:

1. **ISO download** (play on `proxmox`, Proxmox API). For each selected template that is not a
   template yet, the Windows ISO and the virtio-win ISO are downloaded onto the `local` ISO
   store with the role action `storage_download_iso` (Proxmox `download-url`, which follows
   the Evaluation Center redirects). A file that already exists is not downloaded again. The
   play waits until no `download` task is active on the node, then checks that each file exists.
2. **Probe** (play on `proxmox_cli`, `qm` as root, like
   `template.build.ubuntu_noble/_update_templates.yml`). Per template:

   | state found                                   | action                                    |
   |-----------------------------------------------|-------------------------------------------|
   | template                                      | skipped                                   |
   | missing                                       | built                                     |
   | stopped, payload CD still on `sata0`          | finalized only (sysprep finished earlier) |
   | running                                       | left alone ; the run fails at the end with inspection pointers |
   | stopped, no payload CD                        | the run fails (not left behind by this bundle) |

3. **Payload ISO** per template, in `/var/lib/vz/template/range42-win/<vm_id>/` (mode 0700):
   `Autounattend.xml` at the root, `$WinPEDriver$/{vioscsi,NetKVM,Balloon}` copied from the
   virtio-win ISO (loop mount, read-only), and `range42/` with `finalize.ps1`,
   `unattend-sysprep.xml`, `cloudbase-init.conf`, `cloudbase-init-unattend.conf`,
   `sshd_config` and the cloudbase-init MSI (downloaded, sha256 checked). `genisoimage` writes
   `/var/lib/vz/template/iso/range42-autounattend-<vm_id>.iso` (mode 0600).
4. **qm create** (hardware of the Proxmox "Windows 2025 guest best practices" page):
   `ostype win11`, `machine q35`, `bios ovmf` + `efidisk0` (`efitype=4m,pre-enrolled-keys=1`),
   `tpmstate0` v2.0, `scsihw virtio-scsi-single`, `scsi0` 64 GB `discard=on,iothread=1`,
   `net0` virtio on `template_net_bridge` with a MAC derived from the VM id
   (`52:54:00:42:<id high byte>:<id low byte>`), `agent enabled=1`; Windows ISO on `ide0`,
   virtio-win on `ide2`, payload on `sata0`, `boot order=ide0;scsi0`.
5. **Start** and send ENTER (`qm sendkey ret`) in a loop to pass the UEFI "Press any key
   to boot from CD or DVD" prompt and, on Windows Server, the Windows Boot Manager menu, until the VM has read more than 100 MB (Windows Setup
   loads `boot.wim`) or `win_bootkey_seconds` have passed ; in the second case the task fails
   and the VM stays at the prompt. Later reboots time out on that prompt and fall through to
   `scsi0`.
6. **Windows Setup** reads `Autounattend.xml`: GPT disk (EFI 100 MB, MSR 16 MB, `C:`), image
   index from the table, no product key (evaluation media), static build IP bound to the
   NIC MAC, no OOBE screen, local administrator `alice`, one automatic logon.
7. **finalize.ps1** (first logon, transcript `C:\range42-build.log`): virtio guest tools,
   QEMU guest agent, OpenSSH server (capability, `DefaultShell` = `powershell.exe`, firewall
   rule TCP 22), cloudbase-init (Authenticode check, service as LocalSystem), hibernation and
   automatic updates off, BitLocker off on `C:`, Windows hypervisor launch, VBS, HVCI and
   Credential Guard off (see [Nested virtualisation](#nested-virtualisation)), Winlogon password removed, SSH host keys
   deleted (each clone generates its own), then
   `sysprep /generalize /oobe /shutdown /unattend:unattend-sysprep.xml`. If sysprep fails
   because of an Appx package "installed for a user, but not provisioned", the package is
   removed and sysprep runs once more.
8. **Wait** until the VM is stopped (`win_build_timeout_min`).
9. **Finalize**: delete `ide0`, `ide2`, `sata0`; `ide2` = `local-lvm:cloudinit`; `boot order=scsi0`;
   `qm template`.
10. **Cleanup** on success: the payload directory and the payload ISO are deleted (they hold the
    password). The Windows ISOs and the virtio-win ISO stay on the store. After a failure the
    payload is kept for inspection.

## Variables

All optional. The caller passes them with `import_playbook vars:` or `-e`.

| variable                     | default | effect |
|------------------------------|---------|--------|
| `templates_whitelist`        | `[]`    | empty = both templates ; else the codes listed (`win2025`, `win11`) |
| `template_net_bridge`        | `net140` | bridge or SDN vnet of the build NIC ; must reach the internet |
| `template_subnet_octet`      | `140`   | build IP `192.168.<octet>.250/.251`, gateway `.1` |
| `win2025_iso_url`            | Evaluation Center link `https://go.microsoft.com/fwlink/?linkid=2345730&clcid=0x409&culture=en-us&country=us` | Windows Server 2025 ISO |
| `win2025_iso_name`           | `windows-server-2025-eval-en-us.iso` | file name on the `local` ISO store |
| `win2025_image_index`        | `2`     | `install.wim` index (see measured values) |
| `win2025_virtio_dir`         | `2k25`  | virtio-win driver directory |
| `win11_iso_url`              | Evaluation Center link `https://go.microsoft.com/fwlink/?LinkId=2382600&clcid=0x409&culture=en-us&country=us` | Windows 11 Enterprise ISO |
| `win11_iso_name`             | `windows-11-enterprise-eval-en-us.iso` | file name on the `local` ISO store |
| `win11_image_index`          | `1`     | `install.wim` index |
| `win11_virtio_dir`           | `w11`   | virtio-win driver directory |
| `virtio_win_iso_url`         | fedorapeople `archive-virtio/virtio-win-0.1.271-1/virtio-win-0.1.271.iso` | virtio-win ISO. 0.1.271 on purpose : the Proxmox wiki reports an I/O regression of 0.1.285 with Windows Server 2025 |
| `virtio_win_iso_name`        | `virtio-win-0.1.271.iso` | file name on the `local` ISO store |
| `virtio_win_iso_sha256`      | `bbe6166a…81656429` (see `bundle_parameters.src.yml`) | the build fails before the loop mount when the ISO does not match. Upstream publishes no checksum for the ISO : a new virtio-win version needs a newly measured value |
| `cloudbase_init_msi_url`     | `https://cloudbase.it/downloads/CloudbaseInitSetup_Stable_x64.msi` | cloudbase-init installer |
| `cloudbase_init_msi_sha256`  | `0e7fa42e…a0be19bd5` (see `bundle_parameters.src.yml`) | the build fails when the download does not match. A new "Stable" release changes the hash : measure the new file and update this value |
| `win_timezone`               | `W. Europe Standard Time` | Windows time zone id |
| `win_build_dns`              | `1.1.1.1` | DNS server of the build VM |
| `win_build_timeout_min`      | `150`   | wait for the sysprep shutdown ; the VM is left running after a timeout |
| `win_download_timeout_min`   | `120`   | wait for the ISO downloads |
| `win_bootkey_seconds`        | `900`   | maximum time during which ENTER is sent after the start |

Vault: `$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml`. The password of `alice` (and,
on Windows Server, of the built-in `Administrator`) is `default_admin_vm_ci_password`.

Calling pattern:

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/proxmox/template.build.windows/main.yml"
  vars:
    templates_whitelist: ["win2025", "win11"]
    template_net_bridge: "net140"
```

## Measured values

Measured with the default URLs, Proxmox VE 9.2 (`pve-manager` 9.2.21), nested
virtualisation (the Proxmox node itself runs as a VM). `download-url` followed the
Evaluation Center redirects (302/301) to these files:

| file on the store | upstream file name | size (bytes) | sha256 (measured) |
|---|---|---|---|
| `windows-server-2025-eval-en-us.iso` | `26100.32230.260111-0550.lt_release_svc_refresh_SERVER_EVAL_x64FRE_en-us.iso` | 8152356864 | `7b052573ba7894c9924e3e87ba732ccd354d18cb75a883efa9b900ea125bfd51` |
| `windows-11-enterprise-eval-en-us.iso` | `26300.9457.260913-1737.26h2_ge_release_svc_refresh_CLIENTENTERPRISEEVAL_OEMRET_x64FRE_en-us.iso` | 8225329152 | `bc3f24086ebadc94489066b5ad78089e2cf5c3491e90e790bb81a2b199c10e38` |
| `virtio-win-0.1.271.iso` | `virtio-win-0.1.271.iso` | 726501376 | `bbe6166ad86a490caefad438fef8aa494926cb0a1b37fa1212925cfd81656429` (enforced) |
| (payload) `CloudbaseInitSetup_x64.msi` | `CloudbaseInitSetup_1_1_8_x64.msi` | 64843776 | `0e7fa42e0cbc0ce7657f85730b0c6cc7afc4087a3639df0ff51a721a0be19bd5` (enforced) |

Microsoft publishes no checksum next to the evaluation links, and the links point to the
current build : a later download can be a different file. The Windows ISO sha256 values above
are a record of what was tested, not a check that the bundle enforces.

`install.wim` images (read from the WIM XML header):

| ISO | index | image | installation type |
|---|---|---|---|
| Windows Server 2025 | 1 | Standard Evaluation | Server Core |
| Windows Server 2025 | **2** | Standard Evaluation | Server (Desktop Experience) |
| Windows Server 2025 | 3 | Datacenter Evaluation | Server Core |
| Windows Server 2025 | 4 | Datacenter Evaluation | Server (Desktop Experience) |
| Windows 11 Enterprise | **1** | Enterprise Evaluation | Client |

The virtio-win 0.1.271 ISO contains `vioscsi`, `NetKVM` and `Balloon` for `w11`, `2k25`
and `2k22` (`amd64`).

## Clone contract

`bundles/proxmox/vm.bootstrap` needs no Windows-specific step. A full clone inherits the
whole hardware (`ostype`, `bios`, `efidisk0`, `tpmstate0`, `machine`, `agent`) ;
`cloudinit_set_variables` writes `ciuser`, `cipassword`, `sshkeys`, `ipconfig0`,
`nameserver` and a new `net0` (new MAC) ; `ostype win11` makes the cloud-init drive
`configdrive2` and keeps `cipassword` in clear for cloudbase-init.

Measured on Proxmox VE 9.2 with Windows Server 2025 clones (the last item also with a
Windows 11 clone):

- The cloud-init drive seen by the guest holds `openstack/latest/meta_data.json`
  (`uuid`, `network_config`, `public_keys`, `admin_pass`), `openstack/latest/user_data`
  (cloud-config with `hostname`, `user`, `password`, `ssh_authorized_keys`, ...) and
  `openstack/content/0000` (Debian `interfaces` syntax). `qm cloudinit dump <id> meta` shows
  only `uuid` and `network_config` : it does not show `public_keys` and `admin_pass`, which
  are on the drive.
- No `network_data.json` : cloudbase-init logs "V2 network metadata not found" and configures
  the static IP, gateway and DNS from `content/0000`.
- No `hostname` in `meta_data.json` : the hostname comes from the `hostname` key of the
  user data (`UserDataPlugin`), which then reboots the guest once. The other cloud-config keys
  are logged as "not supported" and ignored.
- `SetUserSSHPublicKeysPlugin` writes `public_keys` to `C:\Users\alice\.ssh\authorized_keys`
  and `SetUserPasswordPlugin` sets the `alice` password from `admin_pass`.
- The first run of the cloudbase-init service on a new clone fails several plugins, on both
  operating systems. Measured on one clone of each template (cloudbase-init 1.1.8):
  - "This operation is only allowed on the primary domain controller of the domain"
    (`NetUserGetInfo` error 2226) for `SetUserPasswordPlugin` and `SetUserSSHPublicKeysPlugin`
    on both, and for `CreateUserPlugin` on Windows 11 ; on Windows Server 2025
    `CreateUserPlugin` logs "User logon failed: 'The request is not supported.'" instead,
    without failing;
  - "The media is write protected" (`WinError 19`) for the hostname step, `UserDataPlugin`
    and `LocalScriptsPlugin`, on Windows Server 2025;
  - "Class not registered" for `NetworkConfigPlugin` and "A system shutdown is in progress"
    for `ExtendVolumesPlugin`, on Windows 11.

  The later runs execute the failed plugins again.
  After the hostname reboot the last run ends with "Plugins execution done", and the clone
  has its hostname, IP address and `alice` key. A healthy clone therefore has about
  150 `ERROR` lines in `cloudbase-init.log` (151 and 156 on the two measured clones). Judge a
  clone by its end state (the clone checks below), not by the error count of this log.

Therefore no LocalScripts fallback is needed. `LocalScriptsPlugin` stays in the plugin list as
an extension point for later scenarios ; its `local_scripts_path` is under
`C:\Program Files\Cloudbase Solutions\Cloudbase-Init\LocalScripts\`, which only
Administrators can write by default, and the bundle puts no script there.
The SSH host keys, the key of `alice` and the
hostname are set again on every new clone (measured by destroying and re-cloning).

The first boot of a clone runs the `oobeSystem` pass of `unattend-sysprep.xml`.
`HideLocalAccountScreen` applies only to Windows Server editions (Microsoft unattend
reference) ; there `AdministratorPassword` completes OOBE. On Windows 11 the answer file
therefore declares `alice` as a `LocalAccount` (group `Administrators`), the same block as in
`Autounattend.xml`. `alice` already exists in the generalized image : on a Windows 11 26H2
clone, the only `Shell Unattend` line of `C:\Windows\Panther\UnattendGC\setupact.log` about it
is `UserAccounts: Password set for 'alice'`, and OOBE then logs
`Section Account: could not find page LocalUser`. OOBE still creates the temporary account
`defaultuser0`, but it stays disabled and no session uses it.
The password is the vault value either way : the answer file and `cipassword` both carry
`default_admin_vm_ci_password`.

Clone checks : hostname, `Get-NetIPConfiguration`, SSH as `alice`, and the console
(`qm monitor <id>`, then `screendump <file>`, or noVNC) shows the Windows logon screen, not an
OOBE page. Registry and SSH checks cannot detect an OOBE page : the OS is fully configured
behind it.

A Windows 11 template built before the `LocalAccount` block gives clones whose console stays on
the OOBE page "Who's going to use this device?" (process `CloudExperienceHost`, session of the
temporary account `defaultuser0`, enabled, no password) ; `quser` and
`Get-LocalUser defaultuser0` in the clone show it. Rebuild the template (`qm destroy <id> --purge`,
then this bundle with `templates_whitelist: ["win11"]`) and re-clone.

For the bootstrap of a Windows clone, set `global_vm_ssh_wait_retries: 180` (the first boot
after sysprep takes several minutes) and give the inventory group of the Windows hosts
`ansible_shell_type: powershell` and `ansible_user: alice`. The connection stays `ssh` ;
`ansible.windows.win_ping` succeeds with `pipelining = True`. The `ansible.utils`
cloud-init wait detects `ansible_shell_type: powershell` and waits for the cloudbase-init
service to stop, probing over plain ssh from the controller so that the hostname reboot does
not fail the play.

## Nested virtualisation

The templates use `cpu host`, the CPU model that the Proxmox best-practice page recommends. The
clones therefore see VMX. When the Proxmox node is itself a VM (here a VMware guest with KVM
nested virtualisation on), a Windows guest that launches its own hypervisor runs a third level of
virtualisation. Windows 11 (build 26300) launches its hypervisor at boot for Virtualization-Based
Security (VBS) ; Windows Server 2025 does not.

Measured before the change below, on Proxmox VE 9.2 inside VMware with KVM nested virtualisation:

- A Windows 11 clone with `cpu host` stayed on the boot spinner for 35.6 hours (uptime 128118 s),
  both vCPUs busy, almost no disk I/O.
- The same clone with `qm set <id> --cpu x86-64-v3` (no VMX) answered the guest agent 46 s after
  `qm start`. The System log then holds event 41 of `Microsoft-Windows-Hyper-V-Hypervisor` (the
  hypervisor launch failed because VMX is missing).
- A Windows Server 2025 clone with `cpu host` logs no `Microsoft-Windows-Hyper-V-Hypervisor` event
  and boots normally.
`finalize.ps1` therefore disables, on both templates before sysprep: the hypervisor launch
(`bcdedit /set hypervisorlaunchtype off`), VBS (`HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard`
`EnableVirtualizationBasedSecurity` = 0, `RequirePlatformSecurityFeatures` = 0), memory integrity
(`...\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity` `Enabled` = 0) and Credential Guard
(`HKLM\SYSTEM\CurrentControlSet\Control\Lsa` `LsaCfgFlags` = 0). The CPU model stays `cpu host` :
the clones still see VMX, they do not use it.

Measured with templates built with this change, one clone of each, same platform:

- The four registry values are 0 on both clones, `Win32_DeviceGuard`
  `VirtualizationBasedSecurityStatus` is 0, and the System log holds no
  `Microsoft-Windows-Hyper-V-Hypervisor` event.
- The `bcdedit` setting does not reach the clones : the build log shows "The operation completed
  successfully.", but `bcdedit /enum all` on a clone has no `hypervisorlaunchtype` element.
  `sysprep /generalize` rewrites the BCD store (`Sysprep_Generalize_Bcd` in the sysprep log). So
  the element does not survive generalize : the `bcdedit` command in `finalize.ps1` has no effect
  on the clones.
- **The registry values are the control.** With them alone, the clones logged no hypervisor event
  and report VBS 0. This is consistent with the hypervisor staying off; no clone without the
  values was measured.
- If the boot entry must carry `hypervisorlaunchtype Off` on a clone, re-apply the command after
  sysprep, on the clone: for example `bcdedit /set hypervisorlaunchtype off` in
  `%WINDIR%\Setup\Scripts\SetupComplete.cmd`, which Windows Setup runs once at the end of the
  clone's setup. This bundle does not write that file.
- Windows 11 clone with `cpu host` : guest agent 36 s after `qm start`.
- Some reboots of both clones still took about 11 minutes between the shutdown of the OS (System
  event 13) and the start of the next kernel (event 12) : 11 min 50 s for the host name reboot of
  the Windows 11 clone, 10 min 51 s for the promotion reboot of the Windows Server 2025 domain
  controller. During the Windows 11 one the console was black, both vCPUs were busy and the disk
  read counter did not move during a 35 s sample. Other reboots of the same clones took 16 to
  31 s. The Windows Server 2025 clone did not launch the hypervisor in the measurement above, so
  these slow reboots most likely have another cause, which is not established.

A cyber-range client without VBS and without Credential Guard is the intended lab posture : LSASS
holds credentials in its own memory, which exercises on credential theft from LSASS need. Do not
reuse these templates where Credential Guard is required.

Memory integrity (HVCI) off has a separate consequence : the hypervisor no longer enforces kernel
code integrity, so unsigned drivers and vulnerable signed drivers load more easily on every clone of
both templates, the Windows Server 2025 domain controller included. Driver signature enforcement
still applies, but only the kernel itself protects it : code that runs in the kernel, for example
through a vulnerable signed driver, can turn it off and load unsigned code. The bundle applies all four
values unconditionally, to every template it builds ; there is no variable to keep VBS, HVCI or
Credential Guard on. Do not reuse these templates where kernel driver integrity matters.

## Constraints of the evaluation editions

- Windows Server 2025 evaluation: 180 days from activation. Windows 11 Enterprise evaluation:
  90 days from activation.
- `sysprep /generalize` rearms the licensing state, and a clone starts with an expired grace
  period (Software Protection status code `0xC004F009` in Application event 1003). The clone must
  complete one online activation. Windows tries it automatically at boot ; after a failure the next
  automatic attempt is one day later. Meanwhile `wlms.exe` (Windows Licensing Monitoring Service)
  shuts the clone down 60 minutes after each boot (System event 1074 by `wlms.exe`, WLMS event
  101). Measured on a Windows 11 clone whose DNS server did not resolve external names at boot :
  activation failure with event 8200 `hr=0x80072EE7`, shutdown 60 minutes after boot.
- The clones therefore need internet access (SNAT on their vnet) and a DNS server that resolves
  external names at their first boot. A scenario activates them explicitly with
  `bundles/generic/systems.configure.windows_eval_activation` once that DNS path exists ; a scenario
  without internet must take this into account.
- Windows host names are NetBIOS names : at most 15 characters. cloudbase-init truncates a
  longer Proxmox VM name (`netbios_host_name_compatibility=true`).

## Operations

- **The vault password is baked into the template.** After a change of
  `default_admin_vm_ci_password`, rebuild both templates (`qm destroy <id> --purge` on the
  Proxmox host, then rerun this bundle). The clones receive the vault password again through
  `cipassword` at clone time, but the template keeps the old one until it is rebuilt.
- **Build time** (Proxmox VE 9.2, nested virtualisation, from `qm create` to the last write of the bundle log):
  Windows Server 2025 from about 11 to 29 minutes ; Windows 11 from 29 to 103 minutes, of which
  14.5 to 66 minutes for the OpenSSH capability download in the builds where it was measured.
  The 29-minute upper values come from one bundle run that built both templates in parallel:
  28 minutes 48 seconds from the first `qm create` to the last write of the log, so each template
  took at most 29 minutes in that run. The OpenSSH download time varies most. Add the ISO downloads on the first run (about 17 GB).
- **Inspect a running build**: noVNC, or `qm guest cmd <id> ping` once `finalize.ps1` has
  installed the guest agent. Logs in the guest: `C:\range42-build.log`,
  `C:\Windows\Panther\setupact.log`, `C:\Windows\System32\Sysprep\Panther\setuperr.log`.
- **Restart a failed build**: on the Proxmox host
  `qm stop <id> ; qm destroy <id> --purge ; rm -rf /var/lib/vz/template/range42-win/<id> /var/lib/vz/template/iso/range42-autounattend-<id>.iso`,
  then rerun the bundle.
- **Proxmox controller role**: the role has no action that sets arbitrary VM keys, so this
  bundle uses `qm` over SSH for the Windows hardware. A generic `vm_set_config` role action
  (PUT `/nodes/<node>/qemu/<id>/config` with a key/value map) would replace most of these `qm`
  calls ; it is not written yet because this bundle is its only consumer.

## Security notes

- The rendered answer files carry the `alice` password in clear on the Proxmox host during the
  build only: payload directory mode 0700, payload ISO created with mode 0600 (`umask 077`),
  rendering tasks `no_log`, both deleted after a successful build. After a failure they stay
  until the operator deletes them with the VM.
- cloudbase-init logs with `verbose=false` and `debug=false` in both configuration files. For
  a diagnosis, set both to `true` in the clone (or in `files/` before a build). The debug log
  under `C:\Program Files\Cloudbase Solutions\Cloudbase-Init\log\` can then contain the
  metadata read from the cloud-init drive : treat it as sensitive and set the values back.
- Both cloudbase-init files accept the config drive only as an `iso` on a `cdrom`
  (`config_drive_types=iso`, `config_drive_locations=cdrom`), the only form Proxmox uses
  (iso9660 on `ide2`). `UserDataPlugin` and `LocalScriptsPlugin` run as LocalSystem : a wider
  search (`vfat`, `hdd`, `partition`) would also execute user data from any disk attached to
  the clone. Do not widen these values while debugging.
- Microsoft documents that Windows Setup hides the passwords of the answer files it caches
  under `C:\Windows\Panther` after use ; this bundle does not check it. `finalize.ps1` removes the Winlogon `DefaultPassword` of the automatic logon.
- `sysprep /unattend` caches `unattend-sysprep.xml` in the template disk until the first boot
  of each clone. It carries the vault value in clear : as the `Administrator` password on
  Windows Server, as the `alice` password on Windows 11. Whoever can read the template disk can
  read it, which on Proxmox means root on the hypervisor or `VM.Clone` rights on the template.
- sshd accepts public keys only. The SSH host keys are deleted before sysprep, so every clone
  has its own.
- The virtio-win ISO is pinned by sha256 before the loop mount (its drivers and MSIs run as
  SYSTEM in the guest).
- The cloudbase-init MSI is pinned by sha256 on the Proxmox side and its Authenticode signature
  is checked in the guest before installation.

## Failure table

Each row is a known failure point, the fallback, and what was measured on Proxmox VE 9.2
under nested virtualisation with the ISOs of [Measured values](#measured-values).

| step | symptom | fallback | measured |
|---|---|---|---|
| UEFI CD boot prompt | "Press any key to boot from CD or DVD" times out ; OVMF reports "No bootable option or device was found" | `qm sendkey ret` loop (`win_bootkey_seconds`) ; a "noprompt" ISO (`efisys_noprompt.bin`) is the documented alternative | the firmware delay before the prompt varied between builds : under 1 minute, 157 to 179 s, more than 275 s, and 495 to 501 s after `qm start` (5-second samples of the VM disk reads ; the screen stays black until the prompt). A fixed 45-second window, then a 300-second loop, each missed the prompt once : the console showed the prompt, then "No bootable option or device was found". The 900-second loop passed the prompt on the next two builds |
| Windows Boot Manager menu (Windows Server ISO) | the menu "Windows Setup [EMS Enabled]" waits for input ; the VM reads about 8 MB from the CD, then nothing more | the loop sends ENTER, which starts the default entry | with a loop that sent the space key, the menu showed no countdown and waited (Windows Server 2025 ; most likely a key press stopped the countdown, not proven). One ENTER started Windows Setup : the VM read 622 MB in the next 55 s |
| storage driver in Windows Setup | "We couldn't find any drives" | `$WinPEDriver$` on the payload ISO ; the alternative is `DriverPaths` in the windowsPE pass | `$WinPEDriver$` with `vioscsi`, `NetKVM`, `Balloon` : the disk was found on both builds |
| image selection | Setup stops at the edition choice, or installs Server Core | `win2025_image_index` / `win11_image_index` | index 2 (Server 2025 Standard, Desktop Experience) and 1 (Windows 11 Enterprise), read from the WIM XML header |
| OOBE | an OOBE screen waits for input | `OOBE` block of `Autounattend.xml` and `unattend-sysprep.xml` ; on Windows 11 also the `LocalAccount` `alice` in both files (`HideLocalAccountScreen` is Windows Server only) | build : no page waited for input (Panther `UnattendGC\setupact.log`: `Status for unattend pass [oobeSystem] = 0x0`). Windows Server 2025 clones : no page. Windows 11 clones of a template without the `LocalAccount` block in `unattend-sysprep.xml` : the console stayed on "Who's going to use this device?" (session `defaultuser0`) while hostname, IP, SSH and domain join were all applied, so the bootstrap and the registry checks passed. Windows 11 clone of a template with the block : the console showed the lock screen, no `CloudExperienceHost` process, no user session, `defaultuser0` disabled, `OOBEInProgress` 0 |
| OpenSSH server (Windows 11) | `Add-WindowsCapability` fails or never finishes | 3 attempts ; the alternative is the Win32-OpenSSH MSI from GitHub (not implemented) | the capability is downloaded from Windows Update : 14.5, 15 and 66 minutes (one attempt each, three builds) on Windows 11 26H2. The 66-minute download is the reason for the `win_build_timeout_min` default of 150 (Windows Server 2025 ships it installed) |
| cloudbase-init MSI signature check | the build stalls at this step (most likely in `Get-AuthenticodeSignature`, not proven) ; the build stops before sysprep and reaches `win_build_timeout_min` | the check runs in a child process with a 5-minute timeout, up to 3 attempts | on Windows 11 the build stalled for more than 90 minutes between the firewall step and the MSI installation (no msiexec log, no child process), right after the OpenSSH capability install ; the same call in a new process returned `Valid` in 10 seconds. On the next build the check in a child process returned `Valid` at the first attempt |
| Windows 11 first logon | the console stays on "Welcome", no disk or network I/O, both vCPUs busy in the guest kernel | none in the bundle : stop the build at the timeout and restart it (see Operations) | seen once in four Windows 11 builds : no I/O for 15 minutes, both vCPUs at a fixed kernel address. The next build did not hang. Cause not established |
| sysprep | sysprep fails on an Appx package "installed for a user, but not provisioned" | `finalize.ps1` removes the package and runs sysprep once more | Windows 11 : sysprep succeeded at the first attempt (`Sysprep_succeeded.tag`), the retry was not needed. Windows Server 2025 : sysprep shut the VM down and the template was created ; whether the retry ran was not recorded |
| clone first boot | `vm.bootstrap` fails on the SSH wait | `global_vm_ssh_wait_retries: 180` | the first boot of a Windows Server 2025 clone took up to 15 minutes until SSH answered (108 SSH wait retries), with several minutes of black console between the reboots of the specialize pass (the vCPUs were in System Management Mode, that is in the UEFI firmware). 108 retries are more than the default of 60. The first Windows 11 clone needed 15 retries |
| Windows 11 clone boot, nested virtualisation | the console stays on the boot spinner, both vCPUs busy, almost no disk I/O, no guest agent | `finalize.ps1` sets VBS, HVCI and Credential Guard to off (registry) and runs `bcdedit /set hypervisorlaunchtype off`, which does not reach the clones ; the alternative is a CPU model without VMX (`x86-64-v3`) on the clone | see [Nested virtualisation](#nested-virtualisation) : 35.6 hours on the spinner with `cpu host`, guest agent after 46 s with `x86-64-v3`, on a template without the change. With the change and `cpu host` : guest agent 36 s after `qm start`, no Hyper-V-Hypervisor event. Some later reboots of both editions still take about 11 minutes before the kernel starts, cause not established |
| clone configuration | hostname, key or network not applied | a cloudbase-init `LocalScripts` plugin reading the drive | not needed : see [Clone contract](#clone-contract) |

## Files in this directory

- `main.yml` - template table, imports `_build_templates.yml`
- `_build_templates.yml` - download, build, finalize pipeline
- `templates/autounattend.xml.j2` - Windows Setup answer file
- `templates/unattend-sysprep.xml.j2` - answer file of `sysprep /generalize /oobe` (clone first boot)
- `files/finalize.ps1` - first-logon build script
- `files/cloudbase-init.conf`, `files/cloudbase-init-unattend.conf` - cloudbase-init service and specialize-pass configuration
- `files/sshd_config` - OpenSSH server configuration
- `bundle_parameters.src.yml`, `bundle_parameters.json` - parameter annotation (generated JSON)
- `README.md` - this file
