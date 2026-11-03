# systems.configure.ad_objects (bundle)

Thin bundle: invokes the catalog role `systems.configure.ad_objects` on a domain controller to
create the organizational units, groups and users of its domain, idempotently (state present,
user passwords written only when they change, memberships only added). Run it after
`admin/software.install.ad_domain_controller`.

Caller vars: `TARGET_GROUP` (required) ; `AD_OBJECTS_OUS`, `AD_OBJECTS_GROUPS`,
`AD_OBJECTS_USERS` (def `[]` each : nothing is created). User passwords are secrets : pass vault
variables, the bundle loads the scenario vault
(`$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml`). List formats : the role README in
range42-catalog.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/systems.configure.ad_objects/main.yml"
  vars:
    TARGET_GROUP: "r42_example_dc"
    AD_OBJECTS_USERS:
      - { name: "analyst1", password: "{{ example_user_password }}" }
```
