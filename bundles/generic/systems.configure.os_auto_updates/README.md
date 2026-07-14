# systems.configure.os_auto_updates (bundle)

Thin bundle: invokes the catalog role `systems.configure.os_auto_updates` on a target group to
disable (default) or enable the OS background auto-updater (`apt-daily` timers + `unattended-upgrades`
on Debian/Ubuntu). Run it EARLY in a baseline, before any `apt` task, so the auto-updater never holds
the dpkg lock during provisioning (and stopping it releases a lock that is already held).

Caller vars: `TARGET_GROUP` (required) ; `OS_AUTO_UPDATES_STATE` (def `disabled`, set `enabled` to
restore). The role reads `OS_AUTO_UPDATES_STATE` directly from play/extra-vars scope - the bundle does
not re-forward it (a role var of the same name would self-reference and trigger recursive templating).

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/generic/systems.configure.os_auto_updates/main.yml"
  vars:
    TARGET_GROUP: "r42_kunai_lab_students_group"
```
