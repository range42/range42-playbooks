# systems.configure.windows_eval_activation (bundle)

Thin bundle: invokes the catalog role `systems.configure.windows_eval_activation` on a target group
to activate Windows evaluation editions online : `slmgr.vbs /ato` with retries until Windows is
licensed with more than one day left. When no attempt succeeds, the bundle fails with the `hr=0x...`
code of the last Software Protection event 8200, or says that no event 8200 was found. A host already licensed reports `ok`.

A clone of an evaluation template must complete one online activation : otherwise the Windows
Licensing Monitoring Service shuts it down every hour. The hosts need outbound HTTPS and a DNS
server that resolves external names.

Caller vars: `TARGET_GROUP` (required) ; `WIN_EVAL_ACTIVATION_RETRIES` (def `10`),
`WIN_EVAL_ACTIVATION_DELAY` (def `60` seconds). No secret, no vault. Details : the role README in
range42-catalog.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/generic/systems.configure.windows_eval_activation/main.yml"
  vars:
    TARGET_GROUP: "r42_example_windows"
```
