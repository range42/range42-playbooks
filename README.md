# Table of Contents

- [Project Overview](#Project-Overview)
- [Repository Content](#Repository-Content)
- [Contributing](#Contributing)
- [License](#License)

---

# Project Overview

**RANGE42** is a modular cyber range platform designed for real-world readiness.
We build, deploy, and document offensive, defensive, and hybrid cyber training environments using reproducible, infrastructure-as-code methodologies.

## What we build

- Proxmox-based cyber ranges with dynamic catalog 
- Ansible roles for automated deployments (Wazuh, Kong, Docker, etc.)
- Private APIs for range orchestration and telemetry
- Developer and testing toolkits and JSON transformers for automation pipelines
- ...

## Repository Overview

- **RANGE42 deployer UI** : A web interface to visually design infrastructure schemas and trigger deployments.
- **RANGE42 deployer backend API** : Orchestrates deployments by executing playbooks and bundles from the catalog.
- **RANGE42 catalog** : A collection of Ansible roles and Docker/Docker Compose stacks, forming deployable bundles.
- **RANGE42 playbooks** : Centralized playbooks that can be invoked by the backend or CLI.
- **RANGE42 proxmox role** : An Ansible role for controlling Proxmox nodes via the Proxmox API.
- **RANGE42 devkit** : Helper scripts for testing, debugging, and development workflows.
- **RANGE42 kong API gateway** : A network service in front of the backend API, handling authentication, ACLs, and access control policies.
- **RANGE42 swagger API spec** : OpenAPI/Swagger JSON definition of the backend API.

### Putting it all together

These repositories provide a modular and extensible platform to design, manage and deploy infrastructures automatically  either from the UI (coming soon) or from the CLI through the playbooks repository.

---

# Repository Content

This repository contains Ansible playbooks used by the backend API or CLI to deploy infrastructure bundles and full scenarios from the catalog.

## Repository Structure

```text
playbooks/
├─ scenarios/                 # Complete scenarios (entrypoints)
│  ├─ demo_lab.yml
│  ├─ forensics_lab.yml
│  └─ ...
│
└─ bundles/                   # Reusable unit bundles actions
   ├─ ping.yml
   ├─ software/
   │  ├─ configure/
   │  │  └─ firewalls.yml
   │  └─ install/
   │     └─ docker_compose.yml
   └─ ...
```

### `scenarios/`

- Contains top-level playbooks executed directly.  
- Each scenario chains multiple bundles to deploy a complete lab or environment.  

To run scenario from CLI : 

### `bundles/`
- Contains atomic, reusable bundles actions.  
- Each bundles actions represents one clear intent (install, configure, verify, list, …).  
- Organized by domain, for example:  
  - `ping.yml` → connectivity test  
  - `software/configure/firewalls.yml` → firewall configuration  
  - `software/install/docker_compose.yml` → docker-compose installation  

Scenarios import these bundles actions via `import_playbook`.

---

## Naming Conventions
- Use `snake_case` for files (`docker_compose.yml`, `firewalls.yml`).  
- Use `verb_object` for bundle actions:  
  - `install_docker_compose.yml`  
  - `configure_firewalls.yml`  
  - `ping.yml`  
- Use descriptive names for scenarios that reflect the lab’s purpose:  
  - `demo_lab.yml`  
  - `forensics_lab.yml`  

---


## Contributing

This is a collaborative initiative, developed for applied security training, community integration, and internal capability building.
We use centralized community health files in Range42 community health.

## License

- GPL-3.0 license


