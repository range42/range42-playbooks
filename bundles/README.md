# bundles

A **bundle** is a reusable Ansible playbook with a declared interface : one action on the Proxmox host, one stack on a VM, one policy on a group of VMs. The scenarios of `scenarios/` are compositions of bundles, and the same bundles are the interface meant for the backend API and the deployer UI : one bundle, one call, one result.

## Layout and grammar

Paths follow `<tier>/<subject>.<verb>.<object>/` (the `ctf` tier is deeper, `ctf/cve/<domain>/<product>/<CVE-id>/`). A scenario imports a bundle at parse time through the `RANGE42_BUNDLE_DIR` environment variable, exported by `range42-context` :

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/generic/network.baseline.ssh/main.yml"
  vars:
    target_group: "r42_admin"
```

Each bundle directory holds :

- `main.yml`, the playbook, its header saying what it does, its required variables and an example call site
- `bundle_parameters.src.yml`, the hand-written contract : the caller-facing parameters, their type, whether they come from the vault, their default and where it lives
- `bundle_parameters.json`, generated from the source by [`_tools/generate-bundle-params.py`](_tools/README.md), never edited by hand, consumed by the backend API and the UI
- a `README.md` for the bundles that need more than their header

## Tiers

| Tier | Bundles | What lives there | Index |
|---|---|---|---|
| `admin/` | 10 | application stacks on the dedicated admin VMs, each behind an `INSTALL_<NAME>` feature flag | [admin/README.md](admin/README.md) |
| `proxmox/` | 33 | cloud images, VM templates, VM bootstrap and network cards, SDN networks, legacy bridge migration | [proxmox/README.md](proxmox/README.md) |
| `firewall/` | 26 | the Proxmox firewall (`in_proxmox`) and the firewall inside the VM (`in_vm`) | [firewall/README.md](firewall/README.md) |
| `generic/` | 21 | group-targeted primitives : system baselines, users and access, network policies, repositories, Kunai workshop | [generic/README.md](generic/README.md) |
| `ctf/` | 16 | vulnerable containers for training, one CVE or misconfiguration each | [ctf/README.md](ctf/README.md) |
| `_tools/` | | the parameter contract tooling : schema, generator, call-site check, reference annotations, and this index generator | [_tools/README.md](_tools/README.md) |

106 bundles in total.

## Where a scenario imports them

- `00_sdn_bootstrap/_main.yml` imports `proxmox/sdn_network.bootstrap` with the networks the scenario declares, then `proxmox/legacy_bridge.workaround.shadowed_subnet` for a host that still carries the old bridges
- `01_templates-bootstrap/_main.yml` imports `proxmox/cloud_init_image.download.all` and the `proxmox/template.build.*` bundles, driven by the scenario manifest and `template_net_bridge`
- every `stage_00` of a tier imports `proxmox/vm.bootstrap` once per VM : clone, cloud-init, start, wait for ssh
- `_firewall/` imports the `firewall/in_proxmox/*` anchors : status, management access, the ssh baseline of every VM, and the opt-in arming
- every `stage_01` imports `generic/*` primitives on its groups and, on the admin tier, one `admin/software.install.*` stack per feature flag, with its `firewall/in_proxmox/firewall.baseline.<name>` profile and its `firewall/in_vm` or `generic/network.baseline.*` policy

## Parameter contracts

`bundle_parameters.src.yml` is the source of truth of a bundle's interface. `_tools/generate-bundle-params.py` validates every source against `_tools/bundle_parameters.schema.json`, emits the `bundle_parameters.json` next to each `main.yml`, and `_tools/check-callsites.py` compares the declared parameters with what the scenarios really pass. Details and rules in [_tools/README.md](_tools/README.md).

Regenerate the six index files (this one and one per tier) with `_tools/generate-bundle-index.py` after adding, renaming or re-describing a bundle.
