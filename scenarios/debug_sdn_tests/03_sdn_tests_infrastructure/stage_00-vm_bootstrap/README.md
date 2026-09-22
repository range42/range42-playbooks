# stage_00-vm_bootstrap

**Empty on purpose, and not for long.**

`debug_sdn_tests` reuses an existing VM today - the `sdn_test_vm_id` parameter, default `102`. It
therefore creates nothing here, and `_main_stage_00.yml` is a documented no-op that restates which VM
the run will touch.

When the scenario gains its own VM, this directory takes the per-VM file that every other tier has - one
`vm.bootstrap` import with the VM's name, id, ci_ip, tag, template and bridge in its `vars:` block - and
`_main_stage_00.yml` imports it. Nothing above this directory changes.

That VM will also need:

- an entry in `manifest/scenario_vms.json`, which declares none today
- an entry in `scenarios/_reserved.json`, checked by `scenarios/_check_reserved.sh` - this scenario
  allocates no `vm_id` today, so it has none
- a host line in `templates/ansible-inventory.j2`
