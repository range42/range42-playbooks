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

1. Seeds the catalog `.env` (see [Credentials](#credentials)), stages one element copy per host
   under `$RANGE42_ACTIVE_CONFIG_DIR/misp_star/<host>/` (without the catalog `.env`) and
   renders `<host>/.env` **once** (mode 0600): a copy of the seed, then the host identity
   written over it - star mode, org, `MISP_BASEURL` = the VM IP, teams, ports, the shared uuid5
   namespace, `MISP_DEFAULT_DISTRIBUTION=4`. The namespace lives in
   `$RANGE42_ACTIVE_CONFIG_DIR/secrets/misp_star/org_uuid_namespace` (random, created once per
   star, 0600): it is identity, not an operator credential, and it is not part of the seed.
2. Installs Docker, opens the guest ufw (22 + the published MISP ports), deploys the stack with
   `software.configure.docker-compose` from the staged copy, and requires the provisioner
   container exit code 0 (the `Provisioning complete.` log line is not a completion signal).
3. Runs `software.configure.misp_sync` in one play over hub + spokes (linear strategy, no
   `serial`, no `--limit` that excludes the hub, no `--check`). The role is idempotent and
   enforces the M1/M2/L1 hardening; see its README in the catalog.

## Credentials

The star follows the convention of the admin service bundles (nextcloud, rocketchat, gitea,
mattermost): the secrets come from an operator-editable seed, not from random generation by
the bundle. This is a deliberate choice for a training lab: one place to read and set the
credentials of the whole star.

- **The seed** is the catalog element `.env`:
  `$RANGE42_INVENTORY/03_container_layer/docker/admin/misp-star/.env` (same place as the admin
  bundles). If it is absent, the bundle copies `.env.example` to it (`force: false`: an
  existing, operator-edited `.env` is kept). Git ignores it (`**/.env` in the catalog
  `.gitignore`).
- **Seed values used:** `MISP_SALT`, `MISP_DB_PASSWORD`, `DB_ROOT_PASSWORD`, the admin, reader
  and writer e-mails and passwords, and every other key the bundle does not render. The
  identity keys (`MISP_STAR_MODE`, `MISP_ORG`, `MISP_BASEURL`, `MISP_HOSTNAME`, `MISP_TEAMS`,
  `MISP_INSTRUCTOR_ORG`, ports, `MISP_HOST_ORG_UUID`, `MISP_ORG_UUID_NAMESPACE`,
  `MISP_DEFAULT_DISTRIBUTION`, `MISP_TEAM_USERS_CAN_PUBLISH`) are always written per host over
  the seed values.
- **Populate the catalog `.env` BEFORE running for stronger creds.** Edit the seed before the
  first deploy: each host `.env` copies it once, at first render. Editing the seed later
  changes nothing on a deployed star (see "Do not delete a staged `.env`" below).
- Not from the seed: the element itself creates the team and instructor account passwords
  at first boot (random per instance, in `/keys/api-keys.txt` of its `keys` volume), and MISP
  creates the sync keys during pairing.

**Residual risk (accepted for this training lab).** With the seed left untouched, the hub and
every team spoke run with the same static credentials, and these values are public (they are
in `.env.example`): admin `admin@misp.local` / `Admin1234!XYZ`, reader and writer of the same
family, DB passwords and `MISP_SALT`. Root on any star VM reads them in that VM's `.env`. The
hub admin is a MISP site admin: anyone who can open the hub's HTTPS port can log in with it
and read every team's data on the hub. The boundary between teams then rests only on the
Proxmox per-NIC firewall and on MISP org scoping, and the firewall leaves the hub's HTTPS port
open to each spoke host (the sync path). Set unique values in the seed before deploying when
the teams must not be able to read each other's data.

## Operational notes

- **Re-runs are idempotent.** A second run changes nothing in the staged `.env` files or the
  MISP pairing, and repairs a broken pairing (missing server entry, failed `testConnection`,
  wrong sync-key count).
- **Do not delete a staged `.env` while its stack lives** — the database was initialised with
  those secrets. Rebuild one host: `docker compose down -v` on the VM, delete the staged
  `.env`, re-run the bundle (the new `.env` takes the current seed values).
- **Star membership is fixed at first deploy.** The hub `.env` records `MISP_TEAMS` at
  first render; adding a team later needs a manual hub `.env` update plus a hub
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
