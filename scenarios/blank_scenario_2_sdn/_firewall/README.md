# _firewall - the scenario's firewall wiring, one file per MOMENT

The firewall is not a stage: it intervenes at several moments of main.yml. Each file carries
its moment in its name - an ANCHOR - and main.yml stays the only source of order: the names
document, nothing reads them.

**THE ANCHOR VOCABULARY IS CLOSED.** Three anchors, and a new anchor is a decision, not an
improvisation:

| anchor | the moment, and the constraint it encodes |
|---|---|
| `pre_scenario` | before any infrastructure - state reading and dc/node protections, nothing that requires a VM |
| `post_vm_bootstrap` | the VMs exist - the guest firewall api REFUSES a vmid that does not run, measured |
| `end_scenario` | reserved: the arming decision (start/end/never) is not taken. The slot waits |

The `-NN` orders within one moment. Every file here is a thin wrapper: one comment, one or two
import_playbook toward bundles/firewall/, zero local logic.

The PER-SERVICE declares do not live here: they live in the admin-<service>.yml wrappers,
gated by the same flag as the install - flag=NO means the VM does not exist, so the api
would refuse.
