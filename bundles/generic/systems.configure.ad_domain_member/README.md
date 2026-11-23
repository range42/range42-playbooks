# systems.configure.ad_domain_member (bundle)

Thin bundle: invokes the catalog role `systems.configure.ad_domain_member` on a target group to
join Windows hosts to an existing Active Directory domain : DNS to the domain controller, join,
reboot, then checks that each host is a member and that its local built-in Administrator is
disabled.

Caller vars: `TARGET_GROUP`, `AD_MEMBER_DOMAIN`, `AD_MEMBER_DC_IP`, `AD_MEMBER_JOIN_USER`,
`AD_MEMBER_JOIN_PASSWORD` (required) ; `AD_MEMBER_OU` (def `""` = default Computers container).
The join password is a secret : pass a vault variable, the bundle loads the scenario vault
(`$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml`). Details : the role README in
range42-catalog.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/generic/systems.configure.ad_domain_member/main.yml"
  vars:
    TARGET_GROUP: "r42_example_clients"
    AD_MEMBER_DOMAIN: "example.lab"
    AD_MEMBER_DC_IP: "192.0.2.10"
    AD_MEMBER_JOIN_USER: "Administrator@example.lab"
    AD_MEMBER_JOIN_PASSWORD: "{{ example_builtin_admin_password }}"
```
