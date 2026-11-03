# ad_lab

Active Directory scenario: one **Windows Server 2025 domain controller** for the domain
`range42.lab` (NetBIOS `RANGE42`), with the DNS server of the domain, and one **Windows 11
Enterprise client** joined to that domain. Both run on the SDN vnet `net151` and are reached over
OpenSSH with a PowerShell shell.

The two Windows VMs ARE the workload of this scenario: always deployed. One optional component,
off by default: a Wazuh manager on an admin LAN with the Wazuh agent on both Windows VMs
(`INSTALL_WAZUH=YES`, see "Wazuh (optional)"). The scenario started as a copy of `misp_lab`.

## Network architecture

```
Proxmox host (holds 192.168.151.1 and 192.168.142.1, routes, SNAT to the outside)
 |
 +-- net140  192.168.140.0/24  templating (build of 9250 and 9251 only)
 |
 +-- net151  192.168.151.0/24  ad_lab
 |     +-- ad-dc01      .201  (VMID 1201)  domain controller, DNS of range42.lab
 |     +-- ad-client01  .202  (VMID 1202)  domain member, DNS = 192.168.151.201
 |
 +-- net142  192.168.142.0/24  admin LAN, INSTALL_WAZUH=YES only, shared with other scenarios
       +-- ad-wazuh01   .204  (VMID 1204)  Wazuh manager (indexer, dashboard, manager)
```

All vnets have SNAT on. The Windows 11 template build downloads the OpenSSH server through
`net140`, the evaluation editions must activate online (see "Evaluation editions"), and the
Wazuh manager downloads its packages. The node routes between `net151` and `net142` without
address translation : the manager sees the agents with their own addresses.

## VM details

| VM name | VM ID | IP | vnet | Template | Role |
|---|---|---|---|---|---|
| ad-dc01 | 1201 | 192.168.151.201 | `net151` | template-vm-win2025-02-4g-64g (9250) | domain controller, DNS server |
| ad-client01 | 1202 | 192.168.151.202 | `net151` | template-vm-win11-02-4g-64g (9251) | domain member |
| ad-wazuh01 | 1204 | 192.168.142.204 | `net142` | template-vm-medium-02-8g-64g (9232) | Wazuh manager, `INSTALL_WAZUH=YES` only |

Source of truth: `manifest/scenario_vms.json`. Each Windows VM has 2 vCPU, 4 GB of RAM and a 64 GB
disk, inherited from its template. Host names stay at most 15 characters (NetBIOS limit).

With `INSTALL_WAZUH=YES` the scenario costs one more VM : 2 vCPU, 8 GiB of RAM and a 64 GiB disk,
from template 9232. The scenario does not build 9232 : it must exist on the node (other scenarios
use it too).

The templates come from `bundles/proxmox/template.build.windows` (unattended build from the
Microsoft evaluation ISOs). Read its README before the first deploy, in particular "Clone
contract" and "Operations" (build time).

## Accounts and passwords

| Account | Where | Password | SSH |
|---|---|---|---|
| `alice` | local administrator baked into both templates ; on the DC it becomes the domain account `RANGE42\alice` at the promotion | vault `default_admin_vm_ci_password` | yes, key only (deployer key) |
| built-in `Administrator` (RID 500) of ad-dc01 | set before the promotion, then **domain** Administrator `RANGE42\Administrator` | vault `default_windows_builtin_admin_password` (generated) | no key installed |
| `bob` | domain user, created on the DC ; the platform trainee user, so it shares the trainee password | vault `default_trainee_vm_ci_password` (generated) | no |
| built-in `Administrator` of ad-client01 | local, **disabled** (Windows 11 default ; the join role fails if it is enabled) | - | - |

**On the DC, `alice` and `Administrator` no longer share a password.** A clone of template 9250
carries the vault `alice` password on the built-in Administrator too, and cloudbase-init does not
change it. `software.install.ad_domain_controller` sets `default_windows_builtin_admin_password` on that
account before the promotion, so the domain Administrator gets its own value. ad-client01 joins
the domain with `Administrator@range42.lab`.

The DSRM password of the DC is `default_ad_dsrm_password`. The bootstrapper generates the AD
passwords in the workspace vault when the workspace is created (`range42-context init`), like the
`alice` and `bob` passwords: nothing to type. The stage_01 files read these vault keys directly. Read
them with `range42-context show-vault`. The two Windows keys are 32 characters of a-z A-Z 0-9 - _
ending with a fixed upper case letter, lower case letter and digit, so they satisfy the default
domain password policy (at least 7 characters and three of the four classes) by construction. The
trainee password used for `bob` is 32 random characters of the same set without that guarantee:
about 1 workspace in 770 gets a value with fewer than three classes, and the creation of `bob` then
fails.

## What the deploy does

`./ad_lab.setup.sh` runs `main.yml`:

1. `_firewall` stages 00 and 01: firewall status report, management access on the datacenter and
   node chains (rules only).
2. `00_sdn_bootstrap`: creates `net140` and `net151` when missing, never deletes. With
   `INSTALL_WAZUH=YES`, `net142` too.
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
     "Remote Desktop Users" of ad-client01 (see "RDP through the jump host") ;
   - `INSTALL_WAZUH=YES` only : the Proxmox accepts of ad-wazuh01, the Linux baseline
     (`generic/systems.baseline.default`, `generic/network.baseline.ssh`) and
     `admin/software.install.wazuh` on ad-wazuh01 (see "Wazuh (optional)").
7. `INSTALL_WAZUH=YES` only : `admin/software.install.wazuh_agent_windows` on both Windows VMs,
   after every stage_01 step (the promotion and the join reboot the hosts).
8. `_firewall` stage 04: arming, only with `-e FIREWALL_ARM_VMS=YES` (default NO). Arming raises
   the guest level only : the rules filter only when the Proxmox datacenter firewall is enabled
   too (see "Firewall").

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
- every VM of the scenario that runs: the SSH accept of `firewall.baseline.ssh_all_vms` ;
- ad-wazuh01 (1204), `INSTALL_WAZUH=YES` only : see "Wazuh (optional)".

The source `192.168.151.0/24` covers the domain members. `192.168.151.1` is the node itself, from
which the jump-host forwards below arrive: RDP accepts only that address. The armed state of the
AD and RDP accepts above is not tested yet ; the Wazuh accepts are (see "Measured results").

**Arming needs the datacenter firewall.** `FIREWALL_ARM_VMS=YES` runs `firewall.enable.vms`,
which sets the guest option `enable: 1` and `firewall=1` on net0. Proxmox applies no VM rule
while the datacenter firewall is disabled (`pve-firewall status` = `disabled/running`, no
`enable: 1` in `/etc/pve/firewall/cluster.fw`), and nothing in the deploy enables it
(range42-playbooks#186). Check `pve-firewall status` before you rely on the armed state.

**Known limit : SSH is open from any source once armed.** The tcp 22 accept of
`firewall.baseline.ssh_all_vms` has no source address on any VM of the scenario. Once the
firewall filters, tcp 22 of every VM accepts any address.

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

### RDP client note : Kerberos discovery delay (FreeRDP, Remmina)

FreeRDP 3 (Remmina) tries Kerberos before NTLM. The MIT Kerberos library first sends a DNS query
of type URI for `_kerberos.<DOMAIN>`. Some resolvers (home routers) never answer that query type
while they answer SRV queries normally : each Kerberos attempt then waits 2 servers x 2 retries x
5 s = 20 s, FreeRDP makes several attempts, and the connection ends with "cannot connect" or
`ERRCONNECT_ACTIVATION_TIMEOUT` before the NTLM fallback (measured with
`KRB5_TRACE=/tmp/krb5.trace remmina -c <profile>` : the URI query took 20.1 s, the SRV queries 7 ms).
The domain has no reachable KDC from the operator workstation anyway, so NTLM is the expected path.

Fix on the workstation, in `/etc/krb5.conf`:

```ini
[libdefaults]
    dns_uri_lookup = false
```

Remmina's own setting "FreeRDP auth-pkg-list" (`rdp_auth_filter=!kerberos`) did not stop the
Kerberos attempt with Remmina 1.4.43 / FreeRDP 3.32 ; cause not established.

## Wazuh (optional)

| Flag | Default | Effect of `YES` |
|---|---|---|
| `INSTALL_WAZUH` | `NO` | `net142` (when missing), VM ad-wazuh01 (1204), Wazuh 4.14.4 all-in-one on it, its Proxmox accepts, the Wazuh agent 4.14.4 on ad-dc01 and ad-client01 |

```bash
./ad_lab.setup.sh -e INSTALL_WAZUH=YES     # or the WAZUH checkbox of range42-context --tui
```

Without the flag, or with `INSTALL_WAZUH=NO`, the deploy creates no `net142`, no VM 1204 and no
agent, and runs no Wazuh task on the AD hosts.

- **Manager** : ad-wazuh01, 192.168.142.204 on `net142`, clone of template 9232. The deploy runs
  the Linux baseline, then `admin/software.install.wazuh`, the bundle demo_lab uses : indexer,
  dashboard, manager, filebeat-oss, dashboard user `admin` with the vault password
  `infrastructure_wazuh_admin_password`. Its DNS server is the first address of
  `AD_DC_DNS_FORWARDERS` (default `1.1.1.1`), the resolvers the DC forwards to.
- **Agents** : `admin/software.install.wazuh_agent_windows` on ad-dc01 and ad-client01, after
  every other configure step. Each agent enrolls with its host name (`ad-dc01`, `ad-client01`)
  on tcp 1515 of 192.168.142.204 and reports on tcp 1514. The agent configuration is the one of
  the MSI : the Security, System and Application event channels, no Sysmon, no change of the audit
  policy.
- **Enrollment password** : the server bundle makes the manager require the vault password
  `infrastructure_wazuh_authd_password` on tcp 1515 (authd `use_password`). The agent bundle
  passes the same vault key to the MSI as `WAZUH_REGISTRATION_PASSWORD`, with `no_log` ; a vault
  without that key gives no password, which only a manager without `use_password` accepts. The agent keeps the
  password on disk after the install, in `C:\Program Files (x86)\ossec-agent\authd.pass`, readable
  only by `SYSTEM` and `Administrators` (agent 4.14.4) : a domain user without administrator rights
  cannot read it, but an administrator of ad-dc01 or ad-client01 can, and can enroll other agents
  from that host.
- **API users** : the server bundle replaces the upstream default passwords of the manager API
  users `wazuh` and `wazuh-wui` with the vault keys `infrastructure_wazuh_api_password` and
  `infrastructure_wazuh_wui_password`, and checks that the defaults are refused.
- **Workspace** : `range42-context init` renders the inventory (`r42.ad-wazuh01`, group
  `r42_ad_wazuh`) and the SSH config from `templates/`. A workspace created before ad-wazuh01
  existed lacks both : recreate it before the first deploy with the flag.

Proxmox accepts on ad-wazuh01 (1204), declared by `stage_01-vm_configure/ad-wazuh.yml` (rules
only, inert until armed). Not `firewall.baseline.wazuh`, which accepts tcp 22, 443, 1514, 1515 and
55000 from any source :

| Port | Source | Why |
|---|---|---|
| tcp 1514 | `192.168.151.201/32`, `192.168.151.202/32` | agent events |
| tcp 1515 | `192.168.151.201/32`, `192.168.151.202/32` | agent enrollment, with the vault password |
| tcp 443 | `192.168.142.1/32` | dashboard ; the jump-host forward arrives from the node address on `net142` |
| tcp 22 | as for every VM : `firewall.baseline.ssh_all_vms`, any source (see "Firewall") | deploy and operator SSH |

No tcp 55000 : the agents enroll on 1515 and do not call the manager API.

**Isolation** : the admin LAN is isolated from `net151` only when the firewall is armed
(`FIREWALL_ARM_VMS=YES`) and the Proxmox datacenter firewall is enabled (see "Firewall").
Unarmed, the node routes freely between `net151` and `net142` : every
host of `net151`, a trainee session on ad-client01 included, reaches every port that ufw opens
on the manager to its address.
Inside the VM, ufw (`admin/software.install.wazuh`, default deny) accepts tcp 1514-1515 only from
`192.168.151.201` and `192.168.151.202`, tcp 443 only from `192.168.142.1`, tcp 22 from any
source, and closes tcp 55000. These rules apply armed or not. ad-client01 is an agent host : it
reaches tcp 1514-1515, and enrolling there needs the password. The Proxmox accepts above are a
second layer, active only once armed with the datacenter firewall enabled (see "Firewall").

Dashboard, from the deployer (or any host with the workspace SSH config) :

```bash
ssh -N -o ExitOnForwardFailure=yes -L 18443:192.168.142.204:443 px.<codename>.jumper
# browser -> https://127.0.0.1:18443, user admin,
# password: range42-context show-vault, key infrastructure_wazuh_admin_password
```

When another process already listens on 127.0.0.1:18443, ssh stops with
`bind [127.0.0.1]:18443: Address already in use` : choose another local port. Without
`ExitOnForwardFailure=yes`, ssh continues without the forward and the browser reaches that other
listener.

The dashboard certificate comes from a certificate authority that the server bundle generates on
the deployer : the browser does not trust it and warns.

### Measured results

Wazuh 4.14.4 manager and agents. The items below were measured before the enrollment password,
the API user passwords and the source-restricted ufw rules existed, except the last one, measured
on a from-empty deploy with them. The deploys with the flag ran with `BASELINE_INSTALL_NTP=NO`
(outbound udp 123 was blocked on that network) and `AD_DC_DNS_FORWARDERS` set to a reachable
resolver ; the armed checks ran with the Proxmox datacenter firewall enabled.

- **Agent hosts** : `/var/ossec/bin/agent_control -l` lists `ad-dc01` (Windows Server 2025
  Standard Evaluation, build 26100) and `ad-client01` (Windows 11 Enterprise Evaluation,
  build 26300) as `Active`. Windows Server 2025 is not in the vendor's list of supported agent
  systems ; the agent enrolls and reports on it.
- **Failed logon** : a network logon (type 3) of `RANGE42\bob` with a wrong password on
  ad-client01 raised rule 60122 (level 5, "Logon Failure - Unknown user or bad password",
  Windows event 4625) about 4 s after the logon (alert timestamp minus logon timestamp).
- **Kerberos** : ad-dc01 sends Windows event 4769 (service ticket), alerted by rule 60106
  (level 3). Event 4768 was not checked.
- **Second deploy** : with `INSTALL_WAZUH=YES`, the second run reports `changed=0` on ad-dc01,
  ad-client01 and the Proxmox host, and `changed=30` on ad-wazuh01, all in the shared
  `admin/software.install.wazuh` bundle (ufw reset and rules, indexer, dashboard and manager
  keystores, filebeat, `wazuh-passwords-tool.sh`). That bundle is not idempotent.
- **Armed** (`FIREWALL_ARM_VMS=YES`) : both agents return `Active` after a restart of
  `WazuhSvc` ; tcp 1515 from the node (192.168.142.1) gets no answer (dropped) ; tcp 443
  from ad-client01 does not connect ; the dashboard answers through the jump-host forward (HTTP 302 to its login page).
- **With the enrollment password and the ufw sources** (unarmed, from empty) : both agents
  `Active` ; one 4625 alert about 10 s after the failed logon ; on the manager, the API answers
  401 for `wazuh:wazuh` and `wazuh-wui:wazuh-wui` and 200 for the vault passwords ; from the
  node, tcp 55000 does not connect and only 443 is open ; from ad-client01, tcp 1514 and 1515
  connect, 55000 and 443 do not ; ufw allows 22 from any source, 443 from the node and
  1514:1515 from the two agent addresses ; the second run adds no changed task to the ones listed
  above.

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
launches its hypervisor at boot stayed on the boot spinner for hours. This scenario runs without
Credential Guard on purpose : it keeps credentials in the LSASS memory for the exercises. Details
and measurements : `bundles/proxmox/template.build.windows/README.md`, "Nested virtualisation".

## Known issues

### A VM start hangs in the firmware

Symptom : a VM start stays on a black console. Proxmox shows 0 bytes read from disk and a CPU
load of 0. The QEMU monitor shows CPU 0 in System Management Mode (`info registers` : `SMM=1`).
The hang is intermittent. It was seen on clones of the Windows Server 2025 template (OVMF,
`efitype 4m`, Secure Boot keys pre-enrolled, TPM v2, q35, `cpu host`) on Proxmox VE 9.2 nested
in VMware Workstation, three times. One hang lasted more than 95 minutes, another one, on the
first start of a fresh clone, more than 5 minutes ; `qm reset` ended both. The third one, on a
cold start after a Proxmox reboot, ended alone after about 2.5 minutes. No firmware hang was
recorded on the Windows 11 clone.

Workaround : stage_00 sets `global_vm_firmware_stall_reset_after: 240` on both VMs. The Windows
11 clone gets it too : `bundles/proxmox/template.build.windows` creates both templates with the
same `qm create` command (OVMF, `efitype=4m`, pre-enrolled Secure Boot keys, TPM v2), and the
cause is not established. When the play starts a VM and the VM reads 0 bytes from disk during
4 minutes of uptime, the play resets the VM through the Proxmox API (once,
`global_vm_firmware_stall_max_resets`) and prints one line with the VM id, the uptime and the
reset number. The reset task reports `changed`. When the VM
still reads nothing after the second window, the play fails. The play never resets a VM that
was already running. Details : the header of `bundles/proxmox/vm.bootstrap/main.yml`.

This is a workaround, not a fix : the cause of the hang is not established.

## Usage

```bash
range42-context use <codename> ad_lab
./ad_lab.setup.sh                       # full deploy (templates built if missing)
./ad_lab.setup.sh -e FIREWALL_ARM_VMS=YES
./ad_lab.setup.sh -e INSTALL_WAZUH=YES     # optional Wazuh manager + agents
```

The deploy first runs `_preflight.yml` : it stops before any change when the workspace vault lacks
`default_ad_dsrm_password`, `default_windows_builtin_admin_password` or
`default_trainee_vm_ci_password` (workspace created before the bootstrapper generated them ;
recreate it with `range42-context init`). With `INSTALL_WAZUH=YES` it checks
`infrastructure_wazuh_admin_password` too. The server bundle checks the other Wazuh vault keys
itself, before it changes anything on ad-wazuh01.

## Operator access

From the deployer, in a shell where the ad_lab workspace is active (`range42-context use
<codename> ad_lab`) :

```bash
range42-context ssh-reload           # load the workspace SSH keys into ssh-agent
range42-context ssh ad-dc01          # PowerShell session as alice on 192.168.151.201
range42-context ssh ad-client01      # PowerShell session as alice on 192.168.151.202
range42-context ssh ad-wazuh01       # INSTALL_WAZUH=YES : shell as alice on 192.168.142.204
range42-context show-vault           # the generated passwords (alice, Administrator, bob, DSRM, Wazuh admin)
```

`range42-context use` and `range42-context ssh-reload` run `ssh-add -D` first : they clear every key of the current ssh-agent.

Run `range42-context use` in the same shell before `range42-context deploy` : the deploy reads
`RANGE42_ACTIVE_CONFIG_DIR`, `RANGE42_ACTIVE_WORKSPACE` and `RANGE42_VAULT_PASSWORD_FILE`, which only
`use` exports. A fresh non-interactive shell does not have them, even when the workspace file is
sourced from the shell rc file.

`range42-context ssh <pattern>` looks the pattern up in the `Host r42.*` entries of the workspace
SSH config (`~/.ssh/config_range42-<codename>-ad_lab`) ; both hosts go through the jump host
`px.<codename>.jumper` (ProxyJump).

RDP to ad-client01 as `RANGE42\bob`, through the jump host :

```bash
ssh -N -L 13389:192.168.151.202:3389 px.<codename>.jumper
# RDP client -> localhost:13389, user RANGE42\bob, password: vault default_trainee_vm_ci_password
```

The other accounts and the DC forward are in "RDP through the jump host".

## Wrapper scripts

| Script | Effect |
|---|---|
| `ad_lab.setup.sh` | `main.yml` : networks, templates, VMs, AD configuration |
| `ad_lab.setup_vms_only.sh` | `main_vms_only.yml` : same without the template build |
| `ad_lab.setup_networks.sh` | `00_sdn_bootstrap` only (`--dry-run` : read-only diff) |
| `ad_lab.delete_vms_only.sh` | stops and destroys 1201, 1202 and 1204 when present (from the manifest), keeps the templates |
| `ad_lab.delete_all.sh` | same, plus the templates 9250 and 9251 (rebuild : 30 minutes to more than one hour each) |
| `ad_lab.reset.setup.sh` | deletes the VMs, then runs `main.yml` |
| `ad_lab.reset.ssh_keys.sh` | removes the known_hosts entries of the VM addresses |
| `ad_lab.delete_networks.sh` | removes the subnets and vnets named in the manifest, `net140` and `net142` included ; it refuses while a VM or template of the manifest still exists, and does not check the VMs of other scenarios : `net140` and `net142` are shared |

## Structure

```
ad_lab/
  main.yml / main_vms_only.yml
  00_sdn_bootstrap/_main.yml                     net140 + net151 (+ net142 with INSTALL_WAZUH)
  01_templates-bootstrap/_main.yml               template.build.windows (win2025, win11)
  02_ad_infrastructure/
    _main.yml                                    devkit-only wrapper
    _main_stage_00.yml / _main_stage_01.yml
    stage_00-vm_bootstrap/_ad_group.yml          two vm.bootstrap blocks (+ 1204 with INSTALL_WAZUH)
    stage_01-vm_configure/ad-dc.yml              promotion + user bob
    stage_01-vm_configure/ad-client.yml          domain join
    stage_01-vm_configure/eval-activation.yml    online activation of both VMs
    stage_01-vm_configure/rdp-access.yml         Remote Desktop on both VMs
    stage_01-vm_configure/ad-wazuh.yml           INSTALL_WAZUH : Wazuh manager + its Proxmox accepts
    stage_01-vm_configure/_finalize-ad_wazuh_agents.yml   INSTALL_WAZUH : agents, from main.yml
  _firewall/                                     five moments, see its README
  manifest/scenario_vms.json, feature_flags.yml
  templates/                                     inventory, ssh-config, vars, vault example
```

The inventory group `r42_ad_windows` (`ansible_shell_type: powershell`, `ansible_user: alice`)
holds `r42_ad_dc` (`r42.ad-dc01`) and `r42_ad_clients` (`r42.ad-client01`). The group
`r42_ad_wazuh` holds `r42.ad-wazuh01` (Linux). The Wazuh plays target the runtime groups
`r42_ad_wazuh_active` and `r42_ad_wazuh_agents_active`, filled only with `INSTALL_WAZUH=YES`.

## Notes

- The domain names come from `templates/ansible-vars.yml` (`ad_lab_domain`, `ad_lab_netbios`) ;
  the stage_01 files fall back to the same values.
- A change of `default_windows_builtin_admin_password` after the first deploy is not applied by a rerun :
  the DC role sets it only before the promotion.
- A change of `default_admin_vm_ci_password` needs a rebuild of both templates (template bundle
  README, "Operations").
- If a deploy still stops in the cloudbase-init wait (a reboot slower than 25 minutes), run
  `./ad_lab.delete_vms_only.sh`, then `./ad_lab.setup.sh` again.
