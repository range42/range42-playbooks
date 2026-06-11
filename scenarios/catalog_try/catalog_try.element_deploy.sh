#!/bin/bash
##
## catalog_try.element_deploy.sh - copy + run + smoke check via Ansible
##
## Wrapper around catalog_try.element_deploy.yml. Invoked from _r42_catalog_try
## (range42-context.sh) after deploy-vms completes. Replaces the previous shell
## ssh / scp / docker calls with a single Ansible playbook invocation.
##
## Required env (set by `range42-context use`) :
##   RANGE42_ANSIBLE_ROLES__INVENTORY_DIR
##   RANGE42_VAULT_PASSWORD_FILE
## Required env (set by _r42_catalog_try before invocation) :
##   CATALOG_TRY_ELEMENT_SRC      - absolute path to the catalog element dir
##   CATALOG_TRY_MODE             - "oneshot" | "service"
##   CATALOG_TRY_USE_MAKEFILE     - "true" | "false"
##   CATALOG_TRY_VM_IP            - VM IP for HTTP smoke check
## Optional env :
##   CATALOG_TRY_EXIT_SIGNATURE   - oneshot mode signature to grep
##   CATALOG_TRY_PORT             - service mode port
##   CATALOG_TRY_ENDPOINT         - service mode endpoint (default "/")
##   CATALOG_TRY_INIT_TIMEOUT     - service mode max wait (default 60, max 600)
##

set -e

: "${CATALOG_TRY_ELEMENT_SRC:?must be set (absolute path to catalog element)}"
: "${CATALOG_TRY_MODE:?must be set (oneshot|service)}"
: "${CATALOG_TRY_VM_IP:?must be set (VM IP for HTTP smoke check)}"

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "r42_catalog_try_group" \
	-e "catalog_try_element_src=${CATALOG_TRY_ELEMENT_SRC}" \
	-e "catalog_try_mode=${CATALOG_TRY_MODE}" \
	-e "catalog_try_use_makefile=${CATALOG_TRY_USE_MAKEFILE:-false}" \
	-e "vm_ip=${CATALOG_TRY_VM_IP}" \
	-e "catalog_try_exit_signature=${CATALOG_TRY_EXIT_SIGNATURE:-}" \
	-e "catalog_try_port=${CATALOG_TRY_PORT:-}" \
	-e "catalog_try_endpoint=${CATALOG_TRY_ENDPOINT:-/}" \
	-e "catalog_try_init_timeout=${CATALOG_TRY_INIT_TIMEOUT:-60}" \
	"./catalog_try.element_deploy.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}"
