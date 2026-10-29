# systems.configure.rdp_access (bundle)

Thin bundle: invokes the catalog role `systems.configure.rdp_access` on a target group to enable
Remote Desktop : `fDenyTSConnections` 0, the Windows firewall rule group "Remote Desktop" enabled,
`TermService` running, the accounts of `RDP_USERS` added to "Remote Desktop Users". Network Level
Authentication, the port and the user rights are not changed. Works on domain members and on
domain controllers ; on a domain controller only administrators can log on through RDP by
default, whatever the group membership. A second run reports `ok`.

Caller vars: `TARGET_GROUP` (required) ; `RDP_USERS` (def `[]`). No secret, no vault. Details :
the role README in range42-catalog.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/generic/systems.configure.rdp_access/main.yml"
  vars:
    TARGET_GROUP: "r42_example_windows"
    RDP_USERS:
      - "EXAMPLE\\user"
```
