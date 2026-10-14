# admin/software.install.misp_star

Deploys the MISP star topology: one instructor hub and one MISP spoke per player team, from the
`misp-star` catalog element (`range42-catalog/03_container_layer/docker/admin/misp-star/`), then
pairs hub and spokes with the catalog role `software.configure.misp_sync` (native MISP
server-to-server sync, spoke → hub HTTPS only).

Optional bundle: call-site gated by `INSTALL_MISP_STAR` (default `NO`).

## Target group contract

The bundle targets the runtime group `r42_misp_star_active` (override with
`misp_star_target_group`). The scenario builds it with the `add_host` pattern
(`scenarios/demo_lab/02_admin_infrastructure/_build_admin_active_group.yml`):

```yaml
- name: add the star hub
  ansible.builtin.add_host:
    name: r42.admin-misp-star-hub
    groups: r42_misp_star_active
    misp_star_role: hub
  when: INSTALL_MISP_STAR | default("NO") | upper == "YES"
  changed_when: false

- name: add the team-01 spoke
  ansible.builtin.add_host:
    name: r42.misp-star-spoke-team-01
    groups: r42_misp_star_active
    misp_star_role: spoke
    misp_star_team: team-01
  when: INSTALL_MISP_STAR | default("NO") | upper == "YES"
  changed_when: false
```

Exactly one hub; each spoke needs a unique `misp_star_team` (`[A-Za-z0-9_-]`, becomes that
spoke's `MISP_ORG`). The white cell org is `instructors` (= the hub host org).

## What it does

1. Stages one element copy per host under `$RANGE42_ACTIVE_CONFIG_DIR/misp_star/<host>/` and
   renders `<host>/.env` **once**: star mode, org, `MISP_BASEURL` = the VM IP, the shared
   uuid5 namespace, `MISP_DEFAULT_DISTRIBUTION=4`, and per-host generated secrets (mode 0600).
   The namespace lives in `$RANGE42_ACTIVE_CONFIG_DIR/secrets/misp_star/org_uuid_namespace`,
   generated once per star. Each host gets distinct secrets: a student who is root on a spoke
   reads only that spoke's `.env`, never the hub credentials.
2. Installs Docker, opens the guest ufw (22 + the published MISP ports), deploys the stack with
   `software.configure.docker-compose` from the staged copy, and requires the provisioner
   container exit code 0 (the `Provisioning complete.` log line is not a completion signal).
3. Runs `software.configure.misp_sync` in one play over hub + spokes (linear strategy, no
   `serial`, no `--limit` that excludes the hub, no `--check`). The role is idempotent and
   enforces the M1/M2/L1 hardening; see its README in the catalog.

## Operational notes

- **Re-runs are idempotent.** A second run changes nothing in the staged `.env` files or the
  MISP pairing, and repairs a broken pairing (missing server entry, failed `testConnection`,
  wrong sync-key count).
- **Do not delete a staged `.env` while its stack lives** — the database was initialised with
  those secrets. Rebuild one host: `docker compose down -v` on the VM, delete the staged
  `.env`, re-run the bundle.
- **Star membership is fixed at first deploy.** The hub `.env` records `MISP_TEAMS` at
  generation time; adding a team later needs a manual hub `.env` update plus a hub
  re-provision before the sync play can pair the new spoke.
- **The guest ufw is not team isolation** (a student root on a spoke can disable it). Isolation
  needs the Proxmox per-NIC firewall, armed through the scenario firewall flow
  (`FIREWALL_ARM_VMS=YES` or `range42-context networks-firewall-on --scope scenario`);
  `INSTALL_MISP_STAR=YES` declares, it does not arm.
- `MISP_STAR_SYNC_NO_LOG=false` prints MISP API results that contain site admin and sync keys.
  Debug only.

## Parameters

See `bundle_parameters.src.yml`. All have safe defaults; the sharing/sync switches
(`MISP_STAR_INTER_TEAM_SHARING`, `MISP_STAR_SIGHTINGS_SYNC`, `MISP_STAR_GALAXY_CLUSTERS_SYNC`,
`MISP_STAR_TEAM_USERS_CAN_PUBLISH`) implement the configurable values of the MISP star tracking
issue. Booleans must be passed as real YAML booleans at the call-site; the bundle casts them
with `| bool` before they reach the role.
