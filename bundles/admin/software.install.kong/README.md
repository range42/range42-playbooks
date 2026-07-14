# bundles/admin/software.install.kong

POC install of Kong API Gateway (community edition) in DB-less mode.

## Scope

- DB-less mode (no Postgres / Cassandra)
- Declarative config in `/etc/kong/kong.yml`
- Proxy listeners : `0.0.0.0:8000` (HTTP) + `0.0.0.0:8443` (HTTPS)
- Admin API : `127.0.0.1:8001` (localhost-only, no external exposure)
- Firewall : opens 22 / 8000 / 8443 ; admin API not exposed
- Idempotent : APT repo added once, kong package installed, config files
  reapplied on each run, systemd unit enabled + started

## Required vars from caller

| var | meaning |
|---|---|
| `global_vm_ssh_name` | inventory hostname for the kong VM (e.g. `r42.admin-deployer-api-gateway`) |
| `global_vm_ci_ip` | IP of the kong VM (informational ; not consumed by the POC plays) |

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.kong/main.yml"
  vars:
    global_vm_ssh_name: "r42.admin-deployer-api-gateway"
    global_vm_ci_ip:    "192.168.142.101"
```

## What runs

1. **firewall** : applies a per-host firewall via `software.configure.firewalls` role with rules for 22 / 8000 / 8443
2. **install** : adds the Kong APT repo via the official setup script + installs the `kong` package
3. **configure** : drops `/etc/kong/kong.conf` (DB-less) and `/etc/kong/kong.yml` (empty declarative config)
4. **start** : enables + starts the `kong` systemd unit
5. **verify** : waits for the admin API on `127.0.0.1:8001` and probes `/status` (HTTP 200)

## Adding routes / services to the gateway

Edit `/etc/kong/kong.yml` directly on the kong host, then either :

- `kong reload` (graceful) for a config-only change
- `systemctl restart kong` for a full restart

The declarative format reference : <https://docs.konghq.com/gateway/latest/production/deployment-topologies/db-less-and-declarative-config/>

## Upgrade path to production (Postgres-backed)

Out of scope for this POC. To migrate :

1. Provision a Postgres database accessible from the kong host
2. Swap the relevant lines in `kong.conf` :
   ```
   database = postgres
   pg_host = ...
   pg_database = kong
   pg_user = kong
   pg_password = ...
   ```
   (remove `declarative_config`)
3. Run `kong migrations bootstrap` once
4. Restart kong

A separate `software.install.kong-postgres` bundle can be authored if this becomes the project's production target.

## Verification (manual)

From the kong host, after deploy :

```bash
curl -s http://127.0.0.1:8001/status | jq
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/   # expect 404 (no service yet)
```

From a peer host in the same subnet :

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://r42.admin-deployer-api-gateway:8000/   # expect 404
```
