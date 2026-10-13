# Native platform network modes

The platform generator exports the usual Range42 scenario, bundles and private
installation inputs. Add its component to a project through the backend preview
and the UI's Add Range42 stack dialog, or review a local export:

```sh
python3 -m range42_stack --spec reviewed-stack.json --output reviewed-stack
```

The default `network_mode` is `sdn`. It creates and owns the stack's dedicated
SDN network and preserves the existing single-node SDN restrictions. Omitting the
new fields preserves the previous plan and export contract.

Use `existing_bridge` when an operator has already prepared a private Linux
bridge on the selected Proxmox node:

```json
{
  "id": "platform",
  "domain": "platform.example.test",
  "profile": "core",
  "vmid_start": 31000,
  "template_vmid": 9221,
  "node": "pve01",
  "ssh_user": "alice",
  "subnet": "10.81.0.0/24",
  "gateway": "10.81.0.1",
  "dns": "10.81.0.1",
  "bridge": "vmbr321",
  "network_mode": "existing_bridge",
  "network_peers": [
    {
      "vm_id": 40000,
      "vm_name": "trusted-gateway",
      "description": "operator-owned gateway"
    }
  ]
}
```

The bridge must be active, have no physical ports, host IP addresses or host
gateway, and use a `vmbr` name followed by a nonzero number. `vmbr0` is refused.
Before provisioning, start or restore, the native runtime reads its actual node
network configuration. The operator supplies and qualifies routing, DNS, ingress
and network isolation; selecting a bridge does not install these services or prove
packet forwarding. Guest firewall installation and existing VM ownership checks
still run.

`network_peers` is optional (empty by default), bounded to 32 existing QEMU VMs,
and available only in existing-bridge mode. Each entry identifies an external VM
by its exact ID, name and Proxmox description. The native check requires that VM
on the selected node with an interface on the reviewed bridge. Extra gateway
interfaces are permitted for explicitly approved peers. Missing, renamed,
relocated or differently described peers block deployment. Unlisted guests
attached to the bridge also block it. Peer IDs cannot overlap the source template
or stack-owned IDs. These entries grant no ownership of external VMs.

An existing bridge has an `existing_bridge` network manifest and no generated SDN
bootstrap or ownership claim. Stop, checkpoint, backup, rollback and teardown keep
their original VM scope. Restore and teardown do not create, apply, delete or
reconcile SNAT for the borrowed network, and do not operate on approved external
VMs. Recovery operations can proceed when the bridge is unavailable, subject to
the usual exact VM ownership and peer checks.

This mode places the stack's guests on one selected node of an existing cluster.
It does not automate multi-node bridge provisioning, guest placement, migration
or high availability. It also keeps the current `core` and `full` service sets;
independent permanent-service selection, per-service network/resource settings
and shared-service access bindings are further platform-profile work.

Use matching playbooks, backend and UI releases for existing-bridge authoring.
The backend delegates export to its operator-installed playbooks release; it
never runs source chosen by a preview request. Store credentials, certificates,
runtime bindings and local ownership evidence in private installation inputs,
outside authored project files.
