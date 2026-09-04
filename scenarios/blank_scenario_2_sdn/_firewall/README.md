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
| `end_scenario` | the very end - arming, so nothing above gets filtered mid-deploy. OPT-IN: `FIREWALL_ARM_VMS=YES`, default NO (decision of 2026-09-04: the anchor exists, the default keeps arming an operator move) |

**FILE NAMING: `stage_XX-<anchor>.<what>.yml`** - the `stage_XX` prefix makes `ls` show the
execution order (same idiom as the tiers' stage_00/stage_01 directories), the anchor names the
constraint that pins the file to its moment. The numbering is INTERNAL to this directory - it
does not coincide with the tiers' global stages - and main.yml stays the only source of order:
a prefix out of line with the import order is a lie, and the delivery checks refuse it.

Every file here is a thin wrapper: one comment, one or two import_playbook toward
bundles/firewall/, zero local logic.

The PER-SERVICE declares do not live here: they live in the admin-<service>.yml wrappers,
gated by the same flag as the install - flag=NO means the VM does not exist, so the api
would refuse.
