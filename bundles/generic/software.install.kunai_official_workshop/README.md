# software.install.kunai_official_workshop (bundle)

Thin bundle: invokes the catalog role `software.install.kunai_official_workshop`
(`range42-catalog/02_ansible_layer/admin/roles/`) on a target group. All the logic
lives in the role; this bundle only sets `hosts` + `become` and calls the role.

## Caller vars

- `KUNAI_TARGET_GROUP` (required) - the ansible group to target.
- `KUNAI_VERSION`, `KUNAI_ARCH`, `KUNAI_OPERATOR_USER`, `KUNAI_PYKUNAI_VERSION`,
  `KUNAI_MISP_LOCAL_ENABLE`, `KUNAI_MISP_URL`, `KUNAI_MISP_KEY` (optional - role
  defaults apply otherwise).

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/generic/software.install.kunai_official_workshop/main.yml"
  vars:
    KUNAI_TARGET_GROUP: "r42_kunai_lab_students_group"
```
