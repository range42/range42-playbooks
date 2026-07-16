# bundles/ctf/misconfiguration/system/lpe-01

Deploys a SUID-misconfigured Linux container for local privilege escalation
training. Wraps the catalog docker-compose source at
`<RANGE42_INVENTORY__DOCKER__CTF>/misconfiguration/system/lpe-01/`.

## Misconfig summary

Linux user-space exercise : a SUID binary is misconfigured to allow an
unprivileged user to escalate to root. Beginner-difficulty, CWE-732
(incorrect permission assignment for critical resource), maps to
MITRE ATT&CK T1548.001. Not a CVE - a deliberate misconfig drill.

## Exposed port

| port | protocol | service |
|---|---|---|
| 2222 | tcp | SSH into the vulnerable container (host:2222 -> container:22) |

## Required vars

| var | meaning |
|---|---|
| `global_vm_ssh_name` | inventory hostname for the target VM |

## Optional vars (with defaults)

| var | default |
|---|---|
| `OPERATOR_USER` | `{{ default_admin_vm_ci_user }}` (group_vars) |
| `REMOTE_PROJECT_DIR` | `/tmp/deploy-lpe-01` |
| `CLEAN_UP_DEPLOY_DIR` | `NO` |
| `SEND_POC_DIR` | `NO` |

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/ctf/misconfiguration/system/lpe-01/main.yml"
  vars:
    global_vm_ssh_name: "r42.vuln-box-03"
```

## Catalog source

- Container layer : `range42-catalog/03_container_layer/docker/_ctf/misconfiguration/system/lpe-01/`
- Ansible role : `range42-catalog/02_ansible_layer/admin/roles/software.configure.docker-compose/`

## TODO

- `BUNDLE_PORTS_TCP: [2222]` for per-host firewall agregation (not consumed yet).
- Bundle-level firewall play (opt-in).
- Healthcheck probe post-deploy.
