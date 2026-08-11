#!/bin/bash

##
## dev_deployer_ui_lab.setup.sh - run the main playbook (templates + 3 dev VMs + 3 app bundles [+ optional admin tier])
##
## Same shape as kunai_lab.setup.sh / demo_lab.setup.sh (bundle-driven scenario wrappers).
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE
## to be exported - set by `range42-context use <codename> dev_deployer_ui_lab`.
##
## Trailing "$@" propagates any extra args to ansible-playbook.
## Typical use : feature flag overrides from the TUI, e.g.
##   ./dev_deployer_ui_lab.setup.sh -e INSTALL_WAZUH=YES
## See ./manifest/feature_flags.yml for the list of toggleable features.
##

# Fail fast on a stale workspace. `RANGE42_BUNDLE_DIR` anchors every
# `import_playbook` in this scenario and is exported by `sourced_range42`. A
# workspace generated before that export exists resolves every bundle path to
# `/admin/...` and dies with an opaque "the playbook could not be found".
# Fix: re-run the workspace.credentials role (or `range42-context` re-init) to
# regenerate `sourced_range42`, then `range42-context use <codename> <scenario>`.
: "${RANGE42_BUNDLE_DIR:?RANGE42_BUNDLE_DIR is not set - your workspace predates the bundle-root export ; regenerate sourced_range42 and re-run: range42-context use <codename> dev_deployer_ui_lab}"
: "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR:?RANGE42_ANSIBLE_ROLES__INVENTORY_DIR is not set - run: range42-context use <codename> dev_deployer_ui_lab}"

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
