#!/bin/bash

##
## vaultwarden_lab.poc.sh - run the OPT-IN Vaultwarden credential sync
##
## Runs the sync call-site on its own (INSTALL_VAULTWARDEN_SYNC forced YES) :
## pushes vw_demo_secret into Vaultwarden from the workspace vault, then pulls
## it straight back into the fact vw_demo_pulled.
##
## PREREQUISITES (see the README "Vaultwarden credential sync" section) :
##   - ./vaultwarden_lab.setup.sh has provisioned the host and the server is up.
##   - bw (Bitwarden CLI) and jq are installed on this control node.
##   - the one-time Vaultwarden account bootstrap is done and vault_vw_* are
##     filled in the vault.
##
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE
## to be exported - set by `range42-context use <codename> vaultwarden_lab`.
##

# -l must include localhost: the sync play runs on implicit localhost (bw on
# the control node), which is NOT part of the 'all' group - limiting to "all"
# alone silently skips the sync play. Extra args are forwarded so jump-only
# setups can override e.g. -e vaultwarden_url=https://127.0.0.1:18080 (tunnel).
ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all,localhost" \
	-e INSTALL_VAULTWARDEN_SYNC=YES \
	"./02_admin_infrastructure/stage_01-vm_configure/admin-vaultwarden-sync.yml" \
	--vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
