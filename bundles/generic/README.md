# generic bundles : group-targeted system, network and repository primitives

Reusable primitives applied on an inventory group of the scenario (`target_group`), from the roles of range42-catalog : system baselines and their variants, user and access configuration, network policies inside the VM, repository clones and the Kunai workshop toolchain.

`network.baseline.*` and [firewall/in_vm/os_firewall.baseline.*](../firewall/README.md) are the same five ufw profiles under two names ; the firewall tier is the newer home, both are imported by the scenarios today.

21 bundles. Every bundle is a playbook, `main.yml`, imported at parse time through `RANGE42_BUNDLE_DIR` ; its caller-facing parameters are declared in `bundle_parameters.src.yml` and published as `bundle_parameters.json` (see [../README.md](../README.md)).

## Systems

| Bundle | What it does | Parameters |
|---|---|---|
| [`systems.baseline.default`](systems.baseline.default/) | Group-level baseline - basic packages plus vim/zsh dotfiles for the operator user | 12, [json](systems.baseline.default/bundle_parameters.json), [src](systems.baseline.default/bundle_parameters.src.yml) |
| [`systems.baseline.docker_host`](systems.baseline.docker_host/) | Docker-host baseline - basic packages with Docker and compose plus vim/zsh dotfiles for the operator user | 12, [json](systems.baseline.docker_host/bundle_parameters.json), [src](systems.baseline.docker_host/bundle_parameters.src.yml) |
| [`systems.baseline.with_utils`](systems.baseline.with_utils/) | Group-level baseline with a CLI debug toolkit - basic packages plus vim/zsh dotfiles, JSON utils on by default | 12, [json](systems.baseline.with_utils/bundle_parameters.json), [src](systems.baseline.with_utils/bundle_parameters.src.yml) |
| [`systems.checks.ping`](systems.checks.ping/) | Ansible ping against the targeted hosts/group (reachability check). | 0, [json](systems.checks.ping/bundle_parameters.json), [src](systems.checks.ping/bundle_parameters.src.yml) |
| [`systems.configure.add_user`](systems.configure.add_user/README.md) | Create a user (home, shell, hashed password) on a target group via the catalog role systems.configure.add_user | 6, [json](systems.configure.add_user/bundle_parameters.json), [src](systems.configure.add_user/bundle_parameters.src.yml) |
| [`systems.configure.authorized_keys`](systems.configure.authorized_keys/README.md) | Manage a public key in a user's authorized_keys on a target group | 5, [json](systems.configure.authorized_keys/bundle_parameters.json), [src](systems.configure.authorized_keys/bundle_parameters.src.yml) |
| [`systems.configure.dotfiles`](systems.configure.dotfiles/README.md) | Deploy oh-my-zsh + zshrc dotfiles for a user on a target group and set the login shell to zsh | 5, [json](systems.configure.dotfiles/bundle_parameters.json), [src](systems.configure.dotfiles/bundle_parameters.src.yml) |
| [`systems.configure.os_auto_updates`](systems.configure.os_auto_updates/README.md) | Disable or enable the OS background auto-updater on a target group before provisioning | 2, [json](systems.configure.os_auto_updates/bundle_parameters.json), [src](systems.configure.os_auto_updates/bundle_parameters.src.yml) |
| [`systems.configure.ssh_keypair`](systems.configure.ssh_keypair/README.md) | Deploy an SSH keypair (private + optional public) into a user's ~/.ssh via the catalog role. | 5, [json](systems.configure.ssh_keypair/bundle_parameters.json), [src](systems.configure.ssh_keypair/bundle_parameters.src.yml) |
| [`systems.configure.sudo`](systems.configure.sudo/README.md) | Grant or revoke sudo for a user on a target group, via a validated /etc/sudoers.d drop-in. | 4, [json](systems.configure.sudo/bundle_parameters.json), [src](systems.configure.sudo/bundle_parameters.src.yml) |
| [`systems.configure.terminfo`](systems.configure.terminfo/README.md) | Install the alacritty terminfo entry and allow sshd to accept the client TERM value on a target group | 1, [json](systems.configure.terminfo/bundle_parameters.json), [src](systems.configure.terminfo/bundle_parameters.src.yml) |

## Network policies inside the VM

| Bundle | What it does | Parameters |
|---|---|---|
| [`network.baseline.deployer_backend_api`](network.baseline.deployer_backend_api/) | Firewall baseline opening SSH (22) and the deployer-backend-api FastAPI port (8000) on the target group. | 1, [json](network.baseline.deployer_backend_api/bundle_parameters.json), [src](network.baseline.deployer_backend_api/bundle_parameters.src.yml) |
| [`network.baseline.deployer_ui`](network.baseline.deployer_ui/) | Firewall baseline opening SSH (22) and the range42-deployer-ui Vite/Node port (3000) on the target group. | 1, [json](network.baseline.deployer_ui/bundle_parameters.json), [src](network.baseline.deployer_ui/bundle_parameters.src.yml) |
| [`network.baseline.kong`](network.baseline.kong/) | Network baseline policy that opens 22/tcp plus Kong proxy ports 8000/tcp and 8443/tcp on the target group | 1, [json](network.baseline.kong/bundle_parameters.json), [src](network.baseline.kong/bundle_parameters.src.yml) |
| [`network.baseline.ssh`](network.baseline.ssh/) | Network baseline policy that opens 22/tcp on the target group (SSH-only minimum for any managed VM) | 1, [json](network.baseline.ssh/bundle_parameters.json), [src](network.baseline.ssh/bundle_parameters.src.yml) |
| [`network.baseline.ssh_http`](network.baseline.ssh_http/) | Open the standard web-facing firewall profile (ports 22, 80, 443 tcp) on a target group. | 1, [json](network.baseline.ssh_http/bundle_parameters.json), [src](network.baseline.ssh_http/bundle_parameters.src.yml) |
| [`network.configure.tailscale_client`](network.configure.tailscale_client/) | Install tailscale on a target group and clean up its stale tailnet client entries on the wazuh server | 5, [json](network.configure.tailscale_client/bundle_parameters.json), [src](network.configure.tailscale_client/bundle_parameters.src.yml) |
| [`network.configure.ufw_rules`](network.configure.ufw_rules/) | Apply a caller-provided list of UFW allow-rules on a target group (default-deny incoming). | 2, [json](network.configure.ufw_rules/bundle_parameters.json), [src](network.configure.ufw_rules/bundle_parameters.src.yml) |

## Repositories

| Bundle | What it does | Parameters |
|---|---|---|
| [`repo.clone`](repo.clone/) | Clone a caller-provided list of git repositories on a target group of VMs, owned by an operator user. | 5, [json](repo.clone/bundle_parameters.json), [src](repo.clone/bundle_parameters.src.yml) |
| [`repo.clone.kunai_workshop`](repo.clone.kunai_workshop/) | Static-URL wrapper that clones the 5 kunai-project ecosystem repos into the operator kunai-project directory | 3, [json](repo.clone.kunai_workshop/bundle_parameters.json), [src](repo.clone.kunai_workshop/bundle_parameters.src.yml) |

## Software

| Bundle | What it does | Parameters |
|---|---|---|
| [`software.install.kunai_official_workshop`](software.install.kunai_official_workshop/README.md) | Installs the CIRCL Kunai official workshop toolchain on a target group | 8, [json](software.install.kunai_official_workshop/bundle_parameters.json), [src](software.install.kunai_official_workshop/bundle_parameters.src.yml) |

Regenerate this index with `_tools/generate-bundle-index.py` after adding or re-describing a bundle.
