# range42-vulnerable_inventory


## 📂 Repository Structure

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


