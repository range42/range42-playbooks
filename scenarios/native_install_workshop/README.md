# Native installation workshop

Each participant installs Range42 in an independent nested Proxmox VM, using
their own Linux deployer VM. They then deploy a practice lab with the CLI and
install their own backend API and Deployer UI. Central platform services are
retained between runs.

Open this scenario in the Catalog, create a project and choose Deploy. Review
the participant count, expiry, source templates, target storage, guest VMIDs
and isolated networks, then reserve the VM IDs and addresses on the selected
target. Creation transfers the browser-owned draft lease into durable run
ownership. The backend generates the exact run plan used by both
the diagram and this native recipe. Each participant receives a separate /28,
two VMs and fresh private credentials.

The selected native context supplies verified Proxmox credentials, the installed
controller/catalog runtime and SSH trust. Source templates need cloud-init and
an enabled guest agent. The nested Proxmox template has a 32 GiB system disk,
a separate empty 128 GiB lab disk and host CPU support. Participant bridges,
gateway/DNS/egress and laptop access must be qualified for the selected installation.

`full` creates and configures the selected resources. `configure` resumes only
recorded original clone generations and preserves already installed participant
software. `reset` replaces one explicitly selected participant's pair.
`teardown` retires the selected original generations and their authenticated SSH
pins. Source templates and platform networking remain owned by their respective
lifecycles. Replacement guests, changed disks and altered ownership receipts are
refused before mutation.
For a partial deployment, cleanup skips a guest that was never created only
after independently proving its VMID absent across the cluster. A live guest
without its original receipt remains blocked.

The run's immutable ID, resource plan, credentials and receipt directory are
provided by the backend through private native execution inputs. The repository
contains no attendee passwords, enrollment keys or installation-specific target
addresses. Identity-provider subjects, application permissions and network
enrollment belong to separately selected integration capabilities.

Local tests exercise dynamic inventory, clone-generation ownership, native
participant-helper bindings and selective SSH-pin retirement. With reviewed
controller/catalog role paths, they also execute real Ansible syntax checks for
all four lifecycle entrypoints. Infrastructure preparation, laptop connectivity,
browser trust, repeat/concurrent runs and installer load require live acceptance
before this recipe is advertised as ready for an event.
