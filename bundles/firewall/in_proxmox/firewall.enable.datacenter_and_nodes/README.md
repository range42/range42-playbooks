# firewall.enable.datacenter_and_nodes

Arm the host firewall - the datacenter switch and the node switch - without locking the operator out.

## Why this bundle exists

Arming the Proxmox firewall by hand means knowing three things that are not guessable, and getting any of them wrong costs a physical or console visit to the node.

**Nothing filters until the datacenter switch is on.** It is the master switch: with it off, no chain is installed anywhere, whatever the node and guest switches say. Measured.

**The host chain is ONE chain.** Proxmox concatenates the node rules and the datacenter rules into a single chain, node rules first, first match wins. Measured on a live node: four returns, 22 and 8006 from the node, then the same two from the datacenter. A deny on a node therefore beats an accept at the datacenter.

**An accept sitting below a deny accepts nothing.** Both management rules are posted at the top of the chain, with explicit positions.

That knowledge lives in this bundle instead of in the operator's head.

## The order, and it is not a preference

```
1. the two management accepts, at the DATACENTER and at the NODE
2. the DATACENTER switch
3. the NODE switch
```

**Accepts first, always.** Posting an accept can never cut anything, and both switch guards refuse to arm a level whose management ports are not reachable. Arming before posting would simply be refused - by design, not by accident.

**The datacenter goes on before the node**, which reads backwards until you see why: from a clean state no guest is armed, so arming the datacenter filters no guest yet. Only the host chain comes alive, and its accepts are already in place. The other order works too, both guards being level-aware, but this one keeps every later step incremental and observable.

## What is protected

| port | what it is |
|---|---|
| `8006/tcp` | the web interface **and the api this very role talks to** |
| `22/tcp` | ssh |

Losing 8006 loses the tool that would repair it. Measured during the campaign: the api being on that port, an arming that drops it leaves no way back in except ssh on the node itself.

## The source is deliberately not restricted

The management accepts are posted **without a source restriction**, and this bundle does not offer to add one. That is an assumed trade-off, not an oversight: a rule that is too wide is narrowed later by anyone who can read a chain, while a lockout costs console access to every node. Narrowing needs the administrator's own topology - where the deployer sits, which gateways the guest networks use - which this bundle cannot infer.

## The verdict is read from the switch

The last tasks read both switches back and the run fails if either stayed off. Never from a return code: an action can apply its change and still fail afterwards, which happened during the measurement campaign and cost ten readings before the rule was adopted.

A switch that stayed at 0 means **a guard refused**, and the refusal message names the port that has no accepted path. Nothing is left half done - a refusal happens before the switch moves.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

**No caller-passed parameter, and that is the point.** The ports and their positions all have sane defaults in the role - 8006 and 22, positions 0 and 1 at the top of the chain. Exposing them would hand back the knobs this bundle exists to hide.

## Not in scope

**The guests.** Arming the host firewall does not filter a single guest by itself: a guest needs its own switch **and** its card flag, on top of the datacenter one. Those are the four `firewall.*.vm` and `firewall.*.vms` bundles.

## Related

- `firewall.disable.datacenter_and_nodes` - the mirror. Datacenter first, and it keeps the management accepts in place.
- `proxmox_firewall.vm_id.effective_filtering_state.to.jsons.sh` - the devkit that reports all four levels with a verdict and the list of what is missing. Use it to see the state rather than infer it.
