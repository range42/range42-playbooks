# admin bundles : the application stacks of the admin tier

Each bundle installs one application stack (docker-compose, from the matching element of range42-catalog) on the dedicated admin VM the scenario manifest reserves for it, on the admin network `net142`.

Every admin bundle is **optional** : the scenario imports it behind its feature flag (`INSTALL_<NAME>=YES` on `range42-context deploy -e ...`, or the checkbox of the `range42-context --tui` deploy panel), and the flags of a scenario are listed in its `manifest/feature_flags.yml`.

The hypervisor firewall profile of each stack (its open ports on the guest's Proxmox chain) lives in [firewall/in_proxmox](../firewall/README.md) under the `firewall.baseline.*` of the same service ; the firewall inside the VM comes from `firewall/in_vm` and `generic/network.baseline.*`.

10 bundles. Every bundle is a playbook, `main.yml`, imported at parse time through `RANGE42_BUNDLE_DIR` ; its caller-facing parameters are declared in `bundle_parameters.src.yml` and published as `bundle_parameters.json` (see [../README.md](../README.md)).

| Bundle | Feature flag | What it does | Parameters |
|---|---|---|---|
| [`software.install.deployer_api_backend`](software.install.deployer_api_backend/README.md) | `INSTALL_DEPLOYER_API_BACKEND` | Deploy range42-backend-api as a Docker container (FastAPI + SQLite + ansible-runner) with workspace, playbooks and source sync. | 15, [json](software.install.deployer_api_backend/bundle_parameters.json), [src](software.install.deployer_api_backend/bundle_parameters.src.yml) |
| [`software.install.deployer_ui`](software.install.deployer_ui/README.md) | `INSTALL_DEPLOYER_UI` | Deploy range42-deployer-ui as a Docker container (multi-stage build then nginx SPA on UI_PORT) with firewall, optional tailscale, and a /health probe. | 9, [json](software.install.deployer_ui/bundle_parameters.json), [src](software.install.deployer_ui/bundle_parameters.src.yml) |
| [`software.install.gitea`](software.install.gitea/README.md) | `INSTALL_GITEA` | Install the Gitea docker-compose stack (postgres + gitea + provisioner) on a dedicated VM. | 2, [json](software.install.gitea/bundle_parameters.json), [src](software.install.gitea/bundle_parameters.src.yml) |
| [`software.install.kong`](software.install.kong/README.md) | `INSTALL_KONG` | POC install of Kong API Gateway (community edition) in DB-less mode on a target host. | 2, [json](software.install.kong/bundle_parameters.json), [src](software.install.kong/bundle_parameters.src.yml) |
| [`software.install.mattermost`](software.install.mattermost/README.md) | `INSTALL_MATTERMOST` | Mattermost docker-compose stack (postgres + mattermost + provisioner) installed on a dedicated VM via the catalog element | 2, [json](software.install.mattermost/bundle_parameters.json), [src](software.install.mattermost/bundle_parameters.src.yml) |
| [`software.install.misp_standalone`](software.install.misp_standalone/README.md) | `INSTALL_MISP` | MISP standalone docker-compose stack (MariaDB + Redis + misp-modules + misp + provisioner) deployed on a dedicated VM from the catalog | 2, [json](software.install.misp_standalone/bundle_parameters.json), [src](software.install.misp_standalone/bundle_parameters.src.yml) |
| [`software.install.nextcloud`](software.install.nextcloud/README.md) | `INSTALL_NEXTCLOUD` | Nextcloud docker-compose stack (postgres + redis + nextcloud + provisioner) installed on a dedicated VM from the catalog element | 2, [json](software.install.nextcloud/bundle_parameters.json), [src](software.install.nextcloud/bundle_parameters.src.yml) |
| [`software.install.rocketchat`](software.install.rocketchat/README.md) | `INSTALL_ROCKETCHAT` | Rocket.Chat docker-compose stack (mongodb + rocketchat + provisioner) installed on a dedicated VM | 2, [json](software.install.rocketchat/bundle_parameters.json), [src](software.install.rocketchat/bundle_parameters.src.yml) |
| [`software.install.wazuh`](software.install.wazuh/README.md) | `INSTALL_WAZUH` | Install the Wazuh server stack (indexer, dashboard, manager, filebeat-oss) on the wazuh server host. | 3, [json](software.install.wazuh/bundle_parameters.json), [src](software.install.wazuh/bundle_parameters.src.yml) |
| [`software.install.wazuh_agent`](software.install.wazuh_agent/README.md) | `INSTALL_WAZUH` | Install and enrol the Wazuh agent on every host of the clients group, reporting to the Wazuh server | 2, [json](software.install.wazuh_agent/bundle_parameters.json), [src](software.install.wazuh_agent/bundle_parameters.src.yml) |

Regenerate this index with `_tools/generate-bundle-index.py` after adding or re-describing a bundle.
