# proxmox bundles : images, templates, VMs and SDN networks on the hypervisor

Everything that talks to the Proxmox API through the `range42-ansible_roles-proxmox_controller` role : the cloud images, the VM templates, the per-VM bootstrap and its network cards, the SDN networks and the migration from the legacy bridges.

The SDN family has two layers. `sdn_network.bootstrap` is the composite a scenario imports from its `00_sdn_bootstrap/_main.yml` : it reads the live state, creates what is missing, updates what drifted, applies once and reconciles the live SNAT rules. The single actions (`sdn_network.{create,update,delete}.*`, `list.*`, `apply`) are raw API calls, one bundle one call, meant for the backend API and the UI : a create or a delete stays pending until `sdn_network.apply` runs, and an apply replays the `post-up` of every active subnet, which is why `reconcile.snat_rules` exists.

`template_net_bridge` is the parameter that puts a template build on the SDN templating network (`net140`) ; the manifest of the scenario (`manifest/scenario_vms.json`) drives which templates and which VMs exist.

33 bundles. Every bundle is a playbook, `main.yml`, imported at parse time through `RANGE42_BUNDLE_DIR` ; its caller-facing parameters are declared in `bundle_parameters.src.yml` and published as `bundle_parameters.json` (see [../README.md](../README.md)).

## Cloud images

| Bundle | What it does | Parameters |
|---|---|---|
| [`cloud_init_image.download.all`](cloud_init_image.download.all/) | Aggregator that downloads all base cloud images by importing the 4 per-image download bundles | 0, [json](cloud_init_image.download.all/bundle_parameters.json), [src](cloud_init_image.download.all/bundle_parameters.src.yml) |
| [`cloud_init_image.download.alpine`](cloud_init_image.download.alpine/) | Downloads the Alpine 3.21 nocloud cloud-init image onto the Proxmox local storage | 0, [json](cloud_init_image.download.alpine/bundle_parameters.json), [src](cloud_init_image.download.alpine/bundle_parameters.src.yml) |
| [`cloud_init_image.download.debian`](cloud_init_image.download.debian/) | Download the Debian 12 (bookworm) genericcloud image onto the Proxmox local storage. | 0, [json](cloud_init_image.download.debian/bundle_parameters.json), [src](cloud_init_image.download.debian/bundle_parameters.src.yml) |
| [`cloud_init_image.download.ubuntu_lts_minimal`](cloud_init_image.download.ubuntu_lts_minimal/) | Downloads the Ubuntu Noble LTS minimal cloud image onto the Proxmox local storage | 0, [json](cloud_init_image.download.ubuntu_lts_minimal/bundle_parameters.json), [src](cloud_init_image.download.ubuntu_lts_minimal/bundle_parameters.src.yml) |
| [`cloud_init_image.download.ubuntu_lts_server`](cloud_init_image.download.ubuntu_lts_server/) | Downloads the Ubuntu Noble LTS server cloud image onto the Proxmox local storage | 0, [json](cloud_init_image.download.ubuntu_lts_server/bundle_parameters.json), [src](cloud_init_image.download.ubuntu_lts_server/bundle_parameters.src.yml) |

## VM templates

| Bundle | What it does | Parameters |
|---|---|---|
| [`template.build.alpine`](template.build.alpine/) | Create the Alpine VM template family on a Proxmox hypervisor - clone-less inline build then convert to template. | 2, [json](template.build.alpine/bundle_parameters.json), [src](template.build.alpine/bundle_parameters.src.yml) |
| [`template.build.debian`](template.build.debian/) | Create the Debian VM template family on a Proxmox hypervisor (debian-nano, vm_id 9902), converting each VM to a Proxmox template inline. | 1, [json](template.build.debian/bundle_parameters.json), [src](template.build.debian/bundle_parameters.src.yml) |
| [`template.build.ubuntu_noble`](template.build.ubuntu_noble/README.md) | Creates the Ubuntu Noble VM template family on a Proxmox hypervisor (create, apt-update, convert) | 6, [json](template.build.ubuntu_noble/bundle_parameters.json), [src](template.build.ubuntu_noble/bundle_parameters.src.yml) |

## VMs and their network cards

| Bundle | What it does | Parameters |
|---|---|---|
| [`vm.attach.sdn_vnet`](vm.attach.sdn_vnet/README.md) | Add a network card to a VM, on an SDN vnet or on any bridge. | 5, [json](vm.attach.sdn_vnet/bundle_parameters.json), [src](vm.attach.sdn_vnet/bundle_parameters.src.yml) |
| [`vm.bootstrap`](vm.bootstrap/README.md) | Shared per-VM stage_00 - clone template, wait proxmox unlock, set tag, set cloud-init, start the VM, wait for SSH + cloud-init. | 12, [json](vm.bootstrap/bundle_parameters.json), [src](vm.bootstrap/bundle_parameters.src.yml) |
| [`vm.detach.sdn_vnet`](vm.detach.sdn_vnet/README.md) | Remove one network card from a VM, addressed by its slot netN. | 3, [json](vm.detach.sdn_vnet/bundle_parameters.json), [src](vm.detach.sdn_vnet/bundle_parameters.src.yml) |
| [`vm.list.interfaces`](vm.list.interfaces/README.md) | Read the network cards of one VM and leave them in the fact network_list_interfaces_vm, one dict per card. | 2, [json](vm.list.interfaces/bundle_parameters.json), [src](vm.list.interfaces/bundle_parameters.src.yml) |
| [`vm.replace.sdn_vnet`](vm.replace.sdn_vnet/README.md) | Move one network card of a VM to another bridge - a vnet or a legacy vmbr. | 5, [json](vm.replace.sdn_vnet/bundle_parameters.json), [src](vm.replace.sdn_vnet/bundle_parameters.src.yml) |

## SDN networks

| Bundle | What it does | Parameters |
|---|---|---|
| [`sdn_network.apply`](sdn_network.apply/README.md) | Flush the pending SDN config into the running one - PUT /cluster/sdn, then poll the UPID to completion. | 1, [json](sdn_network.apply/bundle_parameters.json), [src](sdn_network.apply/bundle_parameters.src.yml) |
| [`sdn_network.bootstrap`](sdn_network.bootstrap/README.md) | Bring the declared SDN networks up on a Proxmox cluster - read the live state, create what is missing, update what has drifted, apply once, then reconcile the live SNAT rules. | 3, [json](sdn_network.bootstrap/bundle_parameters.json), [src](sdn_network.bootstrap/bundle_parameters.src.yml) |
| [`sdn_network.bootstrap.sdn_vnet`](sdn_network.bootstrap.sdn_vnet/README.md) | Bring up ONE vnet with its subnet, parameters given directly - zone if absent, vnet, subnet, one apply, then the live SNAT rules reconciled. | 6, [json](sdn_network.bootstrap.sdn_vnet/bundle_parameters.json), [src](sdn_network.bootstrap.sdn_vnet/bundle_parameters.src.yml) |
| [`sdn_network.create.sdn_subnet`](sdn_network.create.sdn_subnet/README.md) | Create a subnet on a vnet. Raw single API call - not idempotent, and what it writes stays pending until sdn_network.apply runs. | 5, [json](sdn_network.create.sdn_subnet/bundle_parameters.json), [src](sdn_network.create.sdn_subnet/bundle_parameters.src.yml) |
| [`sdn_network.create.sdn_vnet`](sdn_network.create.sdn_vnet/README.md) | Create an SDN vnet in a zone. Raw single API call - not idempotent, and what it writes stays pending until sdn_network.apply runs. | 3, [json](sdn_network.create.sdn_vnet/bundle_parameters.json), [src](sdn_network.create.sdn_vnet/bundle_parameters.src.yml) |
| [`sdn_network.create.sdn_zone`](sdn_network.create.sdn_zone/README.md) | Create an SDN zone. Raw single API call - not idempotent, and what it writes stays pending until sdn_network.apply runs. | 2, [json](sdn_network.create.sdn_zone/bundle_parameters.json), [src](sdn_network.create.sdn_zone/bundle_parameters.src.yml) |
| [`sdn_network.delete.all`](sdn_network.delete.all/README.md) | Delete one zone completely - its subnets, its vnets, the zone itself - then apply and reconcile every removed subnet's live SNAT rules down to zero. | 2, [json](sdn_network.delete.all/bundle_parameters.json), [src](sdn_network.delete.all/bundle_parameters.src.yml) |
| [`sdn_network.delete.sdn_subnet`](sdn_network.delete.sdn_subnet/README.md) | Delete one subnet of a vnet. Raw single API call - not idempotent, and what it writes stays pending until sdn_network.apply runs. | 3, [json](sdn_network.delete.sdn_subnet/bundle_parameters.json), [src](sdn_network.delete.sdn_subnet/bundle_parameters.src.yml) |
| [`sdn_network.delete.sdn_vnet`](sdn_network.delete.sdn_vnet/README.md) | Delete one vnet. Raw single API call - not idempotent, and what it writes stays pending until sdn_network.apply runs. | 2, [json](sdn_network.delete.sdn_vnet/bundle_parameters.json), [src](sdn_network.delete.sdn_vnet/bundle_parameters.src.yml) |
| [`sdn_network.delete.sdn_zone`](sdn_network.delete.sdn_zone/README.md) | Delete one zone. Raw single API call - not idempotent, and what it writes stays pending until sdn_network.apply runs. | 2, [json](sdn_network.delete.sdn_zone/bundle_parameters.json), [src](sdn_network.delete.sdn_zone/bundle_parameters.src.yml) |
| [`sdn_network.internet_off`](sdn_network.internet_off/README.md) | Turn outbound internet OFF for one subnet. Composite : sets the declaration, applies it, then brings the live iptables rules in line. | 2, [json](sdn_network.internet_off/bundle_parameters.json), [src](sdn_network.internet_off/bundle_parameters.src.yml) |
| [`sdn_network.internet_on`](sdn_network.internet_on/README.md) | Turn outbound internet ON for one subnet. Composite : sets the declaration, applies it, then brings the live iptables rules in line. | 2, [json](sdn_network.internet_on/bundle_parameters.json), [src](sdn_network.internet_on/bundle_parameters.src.yml) |
| [`sdn_network.internet_toggle`](sdn_network.internet_toggle/README.md) | Flip outbound internet for one subnet, whatever it is now. Composite : sets the declaration, applies it, then brings the live iptables rules in line. | 2, [json](sdn_network.internet_toggle/bundle_parameters.json), [src](sdn_network.internet_toggle/bundle_parameters.src.yml) |
| [`sdn_network.list.sdn_subnets`](sdn_network.list.sdn_subnets/README.md) | Read the SDN subnets of the cluster and leave them in the fact `network_list_sdn_subnets`, one dict per subnet. | 1, [json](sdn_network.list.sdn_subnets/bundle_parameters.json), [src](sdn_network.list.sdn_subnets/bundle_parameters.src.yml) |
| [`sdn_network.list.sdn_vnets`](sdn_network.list.sdn_vnets/README.md) | Read the SDN vnets of the cluster and leave them in the fact `network_list_sdn_vnets`, one dict per vnet. | 1, [json](sdn_network.list.sdn_vnets/bundle_parameters.json), [src](sdn_network.list.sdn_vnets/bundle_parameters.src.yml) |
| [`sdn_network.list.sdn_zones`](sdn_network.list.sdn_zones/README.md) | Read the SDN zones of the cluster and leave them in the fact `network_list_sdn_zones`, one dict per zone. | 1, [json](sdn_network.list.sdn_zones/bundle_parameters.json), [src](sdn_network.list.sdn_zones/bundle_parameters.src.yml) |
| [`sdn_network.reconcile.snat_rules`](sdn_network.reconcile.snat_rules/README.md) | Bring the LIVE iptables SNAT rules of one subnet down to a declared count. | 3, [json](sdn_network.reconcile.snat_rules/bundle_parameters.json), [src](sdn_network.reconcile.snat_rules/bundle_parameters.src.yml) |
| [`sdn_network.update.sdn_subnet`](sdn_network.update.sdn_subnet/README.md) | Update the gateway or the NAT flag of an existing subnet. Raw single API call - not idempotent, and what it writes stays pending until sdn_network.apply runs. | 5, [json](sdn_network.update.sdn_subnet/bundle_parameters.json), [src](sdn_network.update.sdn_subnet/bundle_parameters.src.yml) |

## Legacy bridges (migration)

| Bundle | What it does | Parameters |
|---|---|---|
| [`legacy_bridge.cleaning.shadowed_subnet`](legacy_bridge.cleaning.shadowed_subnet/README.md) | Removes from /etc/network/interfaces the legacy vmbr lines that shadow a vnet's subnet - DURABLE | 5, [json](legacy_bridge.cleaning.shadowed_subnet/bundle_parameters.json), [src](legacy_bridge.cleaning.shadowed_subnet/bundle_parameters.src.yml) |
| [`legacy_bridge.workaround.shadowed_subnet`](legacy_bridge.workaround.shadowed_subnet/README.md) | Frees a vnet's subnet from the legacy vmbr bridge that shadows it - RUNTIME only, undone by ifreload | 3, [json](legacy_bridge.workaround.shadowed_subnet/bundle_parameters.json), [src](legacy_bridge.workaround.shadowed_subnet/bundle_parameters.src.yml) |

Regenerate this index with `_tools/generate-bundle-index.py` after adding or re-describing a bundle.
