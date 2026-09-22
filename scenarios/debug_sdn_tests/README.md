# debug_sdn_tests

The SDN chain, replayed through the **bundles**.

A faithful duplication of the devkit test `_tests/07.sdn_network_chain_tests.sh` - same six sections, same
assertions, same order - driving the 22 `sdn_network.*` / `vm.*` bundles instead of the devkits. Plus a
**seventh section** that covers the eleven bundles those six never execute.

## Why it exists

Everything about those bundles had been validated **statically**: the parameter contracts against their
schema, the playbooks against `--syntax-check`, the Jinja against fixtures, and every task against the
PXC role's real required vars. That static work found the defects that mattered - a silent `firewall=0`,
a `| default(omit)` that breaks a role default, a play name that breaks the syntax gate, a `subnet_zone`
key that is absent when the API omits it. But **none of it had ever touched a Proxmox.**

This scenario closes that gap. It also gives the bundles their **first real call-site**: until now they
were "true orphans" to `check-callsites.py`, which reads the call-site `vars:` block. Adding this
scenario dropped that orphan count from 30 to **8** - the 8 that predate this work. All 22 are out of it,
and section 7 is what finished the job: it calls directly the eleven the main sections only reached
through a composite.

## Read before running

- it **deletes the test zone** at the start and at the end. Point it at a zone you own.
- section 5 **moves a network card** of the VM, twice. The card is deleted and recreated, so **its MAC
  changes**. Never point it at a VM you reach *through* that card.
- the default range is `192.168.199.0/24`, deliberately away from the production `vmbr14x` bands.

## Structure

Conformant to `blank_scenario_2_subnets` - same root files, same `manifest/`, `templates/` and
`01_templates-bootstrap/`, same multi-level `_main` + `_main_stage_NN` per tier.

```
main.yml                       01 -> stage_00 -> stage_01
main_vms_only.yml              same, minus 01
debug_sdn_tests.setup.sh       run the chain - THE ONLY ENABLED ENTRY POINT
debug_sdn_tests.setup_vms_only.sh.disabled     redundant : identical minus a no-op
debug_sdn_tests.delete_all.sh.disabled         deleted the SDN zone
debug_sdn_tests.delete_vms_only.sh.disabled    was a no-op, owns no VM
debug_sdn_tests.reset.setup.sh.disabled        redundant : setup.sh already starts with a delete
debug_sdn_tests.reset.ssh_keys.sh.disabled     was a no-op, SSHes into no VM
manifest/scenario_vms.json     vms[] and templates[] EMPTY, deliberately
manifest/feature_flags.yml     features: [] - nothing to toggle
templates/                     ansible-inventory.j2, ansible-vars.yml, ssh-config.j2, vault-example.yml
01_templates-bootstrap/        documented no-op, builds no template
03_sdn_tests_infrastructure/
  _main_stage_00.yml           THE RUN PARAMETERS, one editable block - and a no-op VM notice
  _main_stage_01.yml           the table of contents : the 11 files below, in order
  _main.yml                    runs both stages, for driving the tier alone
  stage_00-vm_bootstrap/       empty today - README explains what lands here
  stage_01-sdn_network_configure/
    00-preflight.yml                      proxmox_cli group, parameters, coherence
    01-delete_from_unknown_state.yml      removing what is absent is a no-op
    02-create_and_apply.yml               zone + vnet + subnet, one live SNAT rule
    03-create_again_is_noop.yml           the second create writes nothing
    04-outgoing_nat_switch.yml            off / on / toggle / toggle
    05-move_vm_card.yml                   the card moves onto the vnet, and back
    06-delete_leaves_nothing.yml          nothing survives, and it replays
    07a-raw_create_and_apply.yml          raw create, not live, replay refused, apply, live
    07b-raw_update_gateway.yml            the raw update, on the gateway
    07c-bootstrap_on_one_entry.yml        bootstrap recognises what raw built
    07d-attach_second_card.yml            attach is additive, then the raw deletes
```

The stage is named `sdn_network_configure` and not `vm_configure`: nothing here configures a VM. The one
action that touches VM 102 moves a network card, which is SDN cabling - no SSH into the guest, no
package, no baseline. The stage stays `01` because the chain configures rather than provisions, and the
day this scenario creates its own VM that creation belongs to `stage_00`.

Three files are **deliberate no-ops rather than absent files**: `01_templates-bootstrap/_main.yml`,
`_main_stage_00.yml`, and two of the `.sh`. An `import_playbook` cannot point at nothing, and an absent
file reads as an oversight where an explicit no-op states a fact - this scenario builds no template and
creates no VM. When it gains its own VM, the content lands in those files and nothing above them changes.

## Only one script is enabled, on purpose

Five of the six are renamed `.disabled` to remove any chance of a wrong move. Two of them were pure
no-ops anyway, and `reset.setup.sh` was redundant - `setup.sh` already begins with a delete, which the
chain asserts as a property rather than assuming.

**What that costs, and the way out.** `delete_all.sh` was the recovery tool for a run that died mid-way
with the VM card still on the test vnet. In that state the chain cannot heal itself: section 1 deletes the
zone, and Proxmox REFUSES to delete a vnet that still carries a card - so every later run fails on
the same vnet. Bring the card back first, then re-run:

```bash
ansible-playbook -i "$RANGE42_ANSIBLE_ROLES__INVENTORY_DIR/inventory_default.yml" \
  "$RANGE42_BUNDLE_DIR/proxmox/vm.replace.sdn_vnet/main.yml" \
  --vault-password-file "$RANGE42_VAULT_PASSWORD_FILE" \
  -e BUNDLE_VM_ID=102 -e BUNDLE_VM_VMNET_ID=0 -e BUNDLE_VM_IFACE_BRIDGE=vmbr0
```

The card is the only thing that can wedge this scenario. The SDN objects never can - `sdn_network.delete.all`
is idempotent by lookup, so a half-built zone is deleted like a whole one.

## The guard in the delete scripts, and why it is not paranoia

The other scenarios' delete scripts build a `vm_id` filter from the manifest:

```bash
ID_REGEX=$(printf '|%s' "${SCENARIO_VM_IDS[@]}" | sed 's/^|//')
... | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|$)" | proxmox_vm.vm_id.delete.to.jsons.sh
```

With an **empty** `vms[]` array that regex is empty, `($ID_REGEX)` becomes `()`, and the grep matches
**every VM on the Proxmox**. Copying that pattern into a scenario that owns no VM would have turned
"delete nothing" into "delete everything".

So both delete scripts assert the manifest is empty and refuse to build any `vm_id` filter. And they fail
loudly if the manifest ever stops being empty - which is the day they must be rewritten properly.

## Usage

```bash
range42-context use <codename> debug_sdn_tests
./debug_sdn_tests.setup.sh
./debug_sdn_tests.setup.sh -e sdn_test_vm_id=104
```

| var | default | what it is |
|---|---|---|
| `sdn_test_zone` | `r42test` | the zone this scenario owns and wipes |
| `sdn_test_vnet` | `net199` | |
| `sdn_test_subnet` | `192.168.199.0/24` | |
| `sdn_test_gateway` | `192.168.199.1` | |
| `sdn_test_vm_id` | `102` | the VM whose card is moved |
| `sdn_test_vm_netid` | `0` | which card - `netN` - is moved |
| `sdn_test_vm_bridge` | `vmbr0` | where the card comes back to |
| `sdn_test_pause` | `15` | seconds held at each observable state change |

## The pauses are what make this a debug tool

The chain completes faster than a human can follow in the Proxmox UI, so it **stops** at each of the nine
moments where the state visibly changes, and prints where to look:

| pause | what to look at |
|---|---|
| the three SDN objects exist and are applied | Datacenter -> SDN |
| outgoing NAT is OFF | the subnet's SNAT box, unticked - and zero live iptables rule |
| outgoing NAT is back ON | the same box ticked - and exactly one rule, never two |
| the VM card is on the vnet | VM -> Hardware -> Network Device, and **the MAC has changed** |
| the card is back on its original bridge | the same, and the MAC changed a second time |
| everything is gone | Datacenter -> SDN, empty, and no rule outlived its declaration |
| the throwaway network is up | `net200` and its subnet, built by the RAW bundles one call at a time |
| the VM has TWO cards | `net0` on `vmbr0`, `net1` on `net200` - the first was left alone |
| the throwaway network is gone | removed one call at a time, in the order Proxmox imposes |

`-e sdn_test_pause=0` runs it flat out - which is what a CI would do.

These are **run parameters, not feature flags**. They do not switch a component on or off, they retarget
the whole chain - which is why `manifest/feature_flags.yml` declares `features: []` and does not list
them. Their defaults are also recorded in `templates/ansible-vars.yml`, so a workspace remembers what its
last run pointed at.

## What each section proves

| section | what it establishes |
|---|---|
| 0 | the `proxmox_cli` group exists - without it the SNAT reconciliation would run on the deployer and report zero |
| 1 | deleting from an **unknown** state succeeds; this is what makes every later run possible |
| 2 | zone + vnet + subnet are created, applied, and exactly **one** live SNAT rule exists |
| 3 | a second create writes nothing - the three diff lists come back empty - and the rule count does not climb |
| 4 | the NAT switch off / on / toggle / toggle, checking the **declaration and the live count** each time |
| 5 | a VM card moves onto the vnet, the replay is a no-op, and the card comes back |
| 6 | the delete leaves nothing, no rule outlives its declaration, and it replays cleanly |
| 7 | the **eleven bundles the six above never execute**, on a second throwaway network |

Sections 1 to 6 exercise 11 of the 22 bundles directly; the other 11 have their actions exercised through
the composites, but their own `main.yml` never runs - so their parameter bridging, their guards and their
refusals go unproven. `vm.attach` and `vm.detach` are not even reached indirectly.

**Section 7 closes that: all 22 are now called directly.** It uses a second network
(`sdn_test_vnet2`, default `net200` / `192.168.200.0/24`) and a second card slot
(`sdn_test_vm_netid2`, default `1`), so it cannot disturb what the six asserted. It starts from nothing,
since section 6 deleted the zone.

It also proves three things the bundle READMEs **claim** and that nothing verified:

| claim | how section 7 proves it |
|---|---|
| a raw write stays PENDING until apply | reads the subnet back **before** any apply and requires the marker |
| a second raw create is REFUSED | replays it inside a `block`/`rescue` - the run FAILS if it succeeds |
| `attach` is ADDITIVE | after adding `net1`, `net0` must still be on its own bridge |

The second one is worth the machinery: every raw bundle's README states the API answers
`500 already defined` and tells the caller to look the object up first or use a composite. If that ever
stops being true, either Proxmox changed or the documentation is wrong - both deserve to be loud rather
than silently tolerated.

## Two things about how it checks

**Every check re-reads.** A bundle's own reads happened *before* it wrote, so asserting on the facts it
left behind would assert the old state. Each check therefore imports the `list.*` bundles again.

**The live rules are counted with `want=99`.** Nothing is ever in excess of 99, so
`reconcile.snat_rules` deletes nothing and still reports `snat_before` - a pure counter. Same trick as
the devkit test.

That count is the whole point of sections 4 and 6. `snat=0` removes the subnet's post-down hook *before
that hook ever runs*, so the live MASQUERADE rule survives its own declaration: the declaration says no
NAT and the kernel still NATs. No API read shows it. Only the count does.

## What it does not do yet

It **reuses** an existing VM rather than creating one. It has its own `templates/` and `manifest/` like
every other scenario, so `range42-context use <codename> debug_sdn_tests` builds a proper workspace - but
that manifest declares no VM and no template, and the scenario needs no entry in
`scenarios/_reserved.json` since it allocates no `vm_id`.

Creating its own VM is the next step. What it will need is listed in
`03_sdn_tests_infrastructure/stage_00-vm_bootstrap/README.md`: a per-VM `vm.bootstrap` import, an entry
in the manifest, an entry in `_reserved.json`, a host line in `templates/ansible-inventory.j2` - and a
rewrite of the two delete scripts, which currently assert the manifest is empty.
