# bundles/ctf/misconfiguration/network/vsftpd/ftp_anon_server

Deploys a misconfigured vsftpd server (anonymous FTP enabled with writable
upload dir) for CTF training. Wraps the catalog docker-compose source at
`<RANGE42_INVENTORY__DOCKER__CTF>/misconfiguration/network/vsftpd/ftp_anon_server/`.

## Misconfig summary

vsftpd configured with `anonymous_enable=YES` + `anon_upload_enable=YES` and
a world-writable upload dir. Allows unauthenticated users to upload, list,
and retrieve files. Not a CVE - a configuration drift.

## Exposed port

| port | protocol | service |
|---|---|---|
| 21 | tcp | vsftpd FTP |

## Required vars

| var | meaning |
|---|---|
| `global_vm_ssh_name` | inventory hostname for the target VM |

## Optional vars (with defaults)

| var | default |
|---|---|
| `OPERATOR_USER` | `{{ default_admin_vm_ci_user }}` (group_vars) |
| `REMOTE_PROJECT_DIR` | `/tmp/deploy-ftp_anon_server` |
| `CLEAN_UP_DEPLOY_DIR` | `NO` |
| `SEND_POC_DIR` | `NO` |

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/ctf/misconfiguration/network/vsftpd/ftp_anon_server/main.yml"
  vars:
    global_vm_ssh_name: "r42.vuln-box-00"
```

## Catalog source

- Container layer : `range42-catalog/03_container_layer/docker/_ctf/misconfiguration/network/vsftpd/ftp_anon_server/`
- Ansible role : `range42-catalog/02_ansible_layer/admin/roles/software.configure.docker-compose/`

## TODO

- `BUNDLE_PORTS_TCP: [21]` for per-host firewall agregation (not consumed yet).
- Bundle-level firewall play (opt-in).
- Healthcheck probe post-deploy.
