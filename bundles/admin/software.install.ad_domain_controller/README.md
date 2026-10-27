# software.install.ad_domain_controller (bundle)

Thin bundle: invokes the catalog role `software.install.ad_domain_controller` on a target group to
promote a Windows Server host to the first domain controller of a new Active Directory forest,
with DNS, then add the DNS forwarders. Promotion only : create the domain content with
`admin/systems.configure.ad_objects` and join other hosts with
`generic/systems.configure.ad_domain_member`.

Caller vars: `TARGET_GROUP`, `AD_DC_DOMAIN`, `AD_DC_NETBIOS`, `AD_DC_DSRM_PASSWORD`,
`AD_DC_BUILTIN_ADMIN_PASSWORD` (required) ; `AD_DC_DNS_FORWARDERS` (def `["1.1.1.1"]`). The two
passwords are secrets : pass vault variables, the bundle loads the scenario vault
(`$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml`). Details and security notes : the role
README in range42-catalog.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.ad_domain_controller/main.yml"
  vars:
    TARGET_GROUP: "r42_example_dc"
    AD_DC_DOMAIN: "example.lab"
    AD_DC_NETBIOS: "EXAMPLE"
    AD_DC_DSRM_PASSWORD: "{{ example_dsrm_password }}"
    AD_DC_BUILTIN_ADMIN_PASSWORD: "{{ example_builtin_admin_password }}"
```
