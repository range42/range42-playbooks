# legacy_bridge.cleaning.shadowed_subnet

Removes from `/etc/network/interfaces`, on the hypervisor, the legacy `vmbrNNN` lines that shadow a vnet's subnet. **Durable** - no `ifreload` can bring them back.

## Two lines, two symptoms, one intent

| line in the `vmbr` stanza | what it causes |
|---|---|
| `address 192.168.143.1/24` | the host routes the subnet to this bridge, where no VM is attached - the VM is unreachable and its return traffic is lost |
| `post-up ... MASQUERADE` | replayed by every `ifreload -a`, so it silently undoes an `internet-off` - including an `ifreload` triggered by another scenario's deploy |

Both are removed, because both come from the same thing: a bridge still armed on a subnet the SDN now owns. `inject_nat_rules.sh REMOVE` only ever removed the second.

## Why a script and not an inline awk

The removal is `disarm_legacy_bridge.sh`, shipped with this bundle and dropped on the hypervisor for the duration. Called from Ansible, an inline `awk` crosses four levels of escaping - Jinja, YAML, shell, awk - and one quoting mistake edits the wrong line of a hypervisor's network config. A script is read as-is, testable on its own, reviewable.

It does not extend `inject_nat_rules.sh`: that script belongs to the mechanism being dismantled, and adding to it would prolong it.

## What the script guarantees

- a **timestamped backup** before any write, with its path printed, so a rollback is a `cp`
- `--dry-run` printing the exact lines and the exact diff
- the rewrite happens on a **copy**, is validated, then moved - never in place
- three validations before the move: non-empty output, a line count matching exactly what was targeted, and a file `ifupdown2` still parses
- **only the named stanza** is touched, verified against neighbouring bridges
- idempotent: a second run reports `already disarmed` and changes nothing
- the bridge and its stanza are **never deleted** - we disarm, we do not demolish

## On a clean host: nothing, and no question

The confirmation is conditioned on the **detection**. An absent bridge, or a stanza that carries neither the address nor a NAT rule, exits reporting `nothing-to-do`. No prompt, no noise - a scenario deploy is never interrupted by this bundle.

When something **is** found, the bundle prints the exact lines and asks on the deployer's console before writing. It asks there and not in the script because Ansible closes stdin on shell tasks: a `read` inside the script would see no terminal. The script keeps its own `--yes` plus terminal check and **refuses** rather than assuming a yes, which is what protects it when a human runs it by hand.

## What it does not do

The **live** address and rules. The disk is clean afterwards, but the running state still holds them until something reconciles it - run `sdn_network.bootstrap` after this, or the workaround bundle for the address alone.

## Parameters

See `bundle_parameters.json`. `BUNDLE_SDN_VNETS` is the **same list** `sdn_network.bootstrap` takes. `BUNDLE_LEGACY_BUNDLE_DIR` is this directory's absolute path, used to find the script - same shape as `template_bundle_dir` on the template build bundle.

## Related

- `legacy_bridge.workaround.shadowed_subnet` - the runtime counterpart, touches no disk
- `sdn_network.bootstrap` - declares the vnets this bundle reads
