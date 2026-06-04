"""Verbatim-with-param boilerplate strings for the S5b renderer (class B, §4.1).

These mirror the ``demo_lab`` / ``_init_lab`` shapes; the renderer fills the
``@@PLACEHOLDER@@`` sentinels with values from the composed ``Allocation``.
Sentinels are ``@@NAME@@`` (not ``str.format``) on purpose: the bodies are full
of Ansible Jinja ``{{ }}`` / ``{% %}`` that ``.format`` would choke on.

Every string is static; the only per-scenario content is what the renderer
substitutes. No catalog *role code* is ever embedded here — ``stage_01`` lists
role NAMES only (the catalog↔playbooks name-reference contract, plan §2).
"""


import re as _re

_SENTINEL_RE = _re.compile(r"@@[A-Z_]+@@")


def fill(template: str, **values: object) -> str:
    """Replace every ``@@KEY@@`` sentinel in *template* with ``str(value)``.

    :raises RuntimeError: if any ``@@KEY@@`` sentinel is left unfilled (a
        programming error — a call site misspelled or forgot a key). This keeps
        an unsubstituted sentinel from silently shipping into a generated file.
    """
    out = template
    for key, value in values.items():
        out = out.replace(f"@@{key}@@", str(value))
    leftover = _SENTINEL_RE.findall(out)
    if leftover:
        raise RuntimeError(f"unfilled render sentinel(s): {sorted(set(leftover))}")
    return out


# --- stage_00: parametrised Proxmox clone playbook -------------------------

STAGE00_CLONE = """\
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
#
# @@SECTION_LABEL@@ - CLONE + CLOUD-INIT
#
#   hostname : @@VM_NAME@@
#   vm_id    : @@VM_ID@@
#   ip       : @@IP@@
#   template : @@TEMPLATE_NAME@@
#
# global_* vars are supplied by ../_main.yml (kept here as Jinja references).
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

- hosts: proxmox
  gather_facts: false
  vars_files:
    - "../../secrets/default_vault.yml"

  tasks:
    - name: "@@SECTION_LABEL@@ - {{ global_vm_name }} - CLONE TEMPLATE - {{ global_template_name }}"
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "vm_clone"
        vm_id: "{{ global_template_vm_id }}"
        vm_new_id: "{{ global_vm_id }}"
        vm_name: "{{ global_vm_name }}"
        vm_description: "{{ global_vm_description }}"

    - name: "@@SECTION_LABEL@@ - {{ global_vm_name }} - WAIT FOR PROXMOX UNLOCK"
      ansible.builtin.shell: qm config {{ global_vm_id }} | grep -q '^lock:'
      register: clone_lock_check
      until: clone_lock_check.rc != 0
      retries: 60
      delay: 5
      failed_when: false
      changed_when: false
      delegate_to: "{{ inventory_hostname }}-cli"

    - name: "@@SECTION_LABEL@@ - {{ global_vm_name }} - SET PROXMOX TAG"
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "vm_set_tag"
        vm_id: "{{ global_vm_id }}"
        vm_tag_name: "{{ global_vm_tag_name }}"

    - name: "@@SECTION_LABEL@@ - {{ global_vm_name }} - SET CLOUD-INIT VARIABLES"
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "cloudinit_set_variables"
        vm_id: "{{ global_vm_id }}"
        vm_ci_user: "{{ default_admin_vm_ci_user | default('alice') }}"
        vm_ci_password: "{{ default_admin_vm_ci_password | default('supersecret') }}"
        vm_ci_ssh_key: "{{ default_admin_vm_ci_ssh_key }}"
        vm_ci_dns_ips: "1.1.1.1"
        vm_ci_ip: "{{ global_vm_ci_ip }}"
        vm_ci_netmask: "@@NETMASK@@"
        vm_ci_ip_gw: "@@GATEWAY@@"
        vm_net_virtio_bridge: "@@BRIDGE@@"

    - name: "@@SECTION_LABEL@@ - {{ global_vm_name }} - START VM"
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "vm_start"
        vm_id: "{{ global_vm_id }}"

- hosts: "{{ global_vm_ssh_name }}"
  gather_facts: false
  vars_files:
    - "../../secrets/default_vault.yml"
  vars:
    ARG_vm_ssh_name: "{{ global_vm_ssh_name }}"
    requested_tasks:
      - wait/openssh_server/is_reachable.yml
      - wait/cloudinit/is_boot_finished.yml
  tasks:
    - name: "@@SECTION_LABEL@@ - {{ global_vm_name }} - WAIT FOR SSH + CLOUD-INIT"
      include_role:
        name: ansible.utils
"""


# --- stage_01: software install — catalog roles BY NAME (§2) ---------------

STAGE01_HEADER = """\
##
## stage_01 — software install for @@VM_NAME@@
## catalog roles are referenced BY NAME (resolved via ANSIBLE_ROLES_PATH at deploy);
## one play per attachment so each carries its own params (firewall_rules, docker …).
##
"""

# One play per box attachment — its role + its params (merged box vars + attachment
# params) as a vars block. Containers map to the docker-compose role (see render).
STAGE01_PLAY = """\
- name: "@@VM_NAME@@ — @@ROLE@@"
  hosts: @@SSH_HOST@@
  become: true
  vars_files:
    - "../../secrets/default_vault.yml"
@@VARS_BLOCK@@  roles:
    - @@ROLE@@
"""

# A valid no-op play (NOT a bare `[]`, which `import_playbook` rejects with
# "A play definition must contain exactly one of hosts/import_playbook/roles/tasks").
STAGE01_PLACEHOLDER = """\
##
## stage_01 — @@VM_NAME@@ : placeholder (no catalog roles attached)
## This box clones + boots but installs nothing. Attach roles via the box's
## `attachments_add` in scenario.r42.yml, then re-generate.
##

- name: "@@VM_NAME@@ — placeholder (no catalog roles attached)"
  hosts: @@SSH_HOST@@
  gather_facts: false
@@VARS_BLOCK@@  tasks: []
"""


# --- per-box devkit scripts ------------------------------------------------

DEVKIT_INSTALL = """\
#!/bin/bash
##
## reinstall software on @@VM_NAME@@ only (fast single-VM iteration)
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \\
    -l "all" \\
    "../@@VM_NAME@@.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
"""

DEVKIT_SNAPSHOT = """\
#!/bin/bash
##
## snapshot @@VM_NAME@@ as "base"
##

VM_ID=$(devkit_manifest.find_vm_id.to.text.sh "$0" "@@VM_NAME@@") || exit 1
echo "{\\"proxmox_node\\":\\"@@PROXMOX_NODE@@\\",\\"vm_id\\":${VM_ID},\\"vm_snapshot_description\\":\\"base\\"}" | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
"""

DEVKIT_REVERT = """\
#!/bin/bash
##
## revert @@VM_NAME@@ to its latest snapshot and restart it
##

VM_ID=$(devkit_manifest.find_vm_id.to.text.sh "$0" "@@VM_NAME@@") || exit 1
echo "{\\"proxmox_node\\":\\"@@PROXMOX_NODE@@\\",\\"vm_id\\":${VM_ID} }" | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
echo "{\\"proxmox_node\\":\\"@@PROXMOX_NODE@@\\",\\"vm_id\\":${VM_ID} }" | proxmox_vm.vm_id.start.to.jsons.sh
"""


# --- per-section reinstall -------------------------------------------------

SECTION_REINSTALL = """\
#!/bin/bash
##
## re-run this section's playbooks (@@SECTION@@)
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \\
    -l "all" \\
    "./_main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
"""


# --- top-level scripts -----------------------------------------------------

ACTIVATE_SH = """\
#!/bin/bash

# deprecation algo issue with paramiko and ubuntu 24.04.2 LTS
# https://github.com/paramiko/paramiko/issues/2419

set -euo pipefail

VIRTUAL_ENV_DIR="$HOME/ansible_fix/venv"

if [ ! -d "$VIRTUAL_ENV_DIR" ]; then

    mkdir -p "$HOME/ansible_fix"
    python3 -m venv "$VIRTUAL_ENV_DIR"

    # shellcheck disable=SC1091
    source "$VIRTUAL_ENV_DIR/bin/activate"

    pip install --upgrade pip setuptools wheel
    pip install ansible paramiko cryptography
fi

# shellcheck disable=SC1091
source "$VIRTUAL_ENV_DIR/bin/activate"

echo "source \\"$VIRTUAL_ENV_DIR/bin/activate\\""
"""

SETUP_SH = """\
#!/bin/bash

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \\
	-l "all" \\
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
"""

SETUP_VMS_ONLY_SH = """\
#!/bin/bash

##
## deploy VMs only — skip template download and creation
## faster redeploy when templates already exist on proxmox
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \\
	-l "all" \\
	"./main_vms_only.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
"""

# delete_all / delete_vms_only / reset are manifest-driven and scenario-generic
# (they read vm_id / ip from manifest/scenario_vms.json — no hard-coded VMs).

DELETE_ALL_SH = """\
#!/bin/bash

##
## delete all — VMs + this scenario's ubuntu_noble templates
##
## ⚠ templates (9xxx) are shared across scenarios on the same Proxmox. Run this
## only when no other scenario relies on them, or use delete_vms_only.sh instead.
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t SCENARIO_VM_IDS  < <(jq -r '.vms[].vm_id'       "$MANIFEST")
mapfile -t TEMPLATE_VM_IDS  < <(jq -r '.templates[].vm_id' "$MANIFEST")
mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip'         "$MANIFEST")

ALL_IDS=("${SCENARIO_VM_IDS[@]}" "${TEMPLATE_VM_IDS[@]}")
ID_REGEX=$(printf '|%s' "${ALL_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting VMs + templates"
VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1 | grep '"vm_id":[0-9]')
if [ -z "$VM_LIST_JSON" ]; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned no VM data — aborting" >&2
    exit 1
fi
echo "$VM_LIST_JSON" | jq -c | grep -E "\\"vm_id\\":($ID_REGEX)([^0-9]|$)" | proxmox_vm.vm_id.stop_force.to.jsons.sh
echo "$VM_LIST_JSON" | jq -c | grep -E "\\"vm_id\\":($ID_REGEX)([^0-9]|$)" | proxmox_vm.vm_id.delete.to.jsons.sh

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ":: done — VMs and templates removed"
"""

DELETE_VMS_ONLY_SH = """\
#!/bin/bash

##
## delete VMs only — scenario VMs (filter by vm_id), keep templates
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t SCENARIO_VM_IDS  < <(jq -r '.vms[].vm_id' "$MANIFEST")
mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip'   "$MANIFEST")
ID_REGEX=$(printf '|%s' "${SCENARIO_VM_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting scenario VMs (keeping templates)..."
VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1 | grep '"vm_id":[0-9]')
if [ -z "$VM_LIST_JSON" ]; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned no VM data — aborting" >&2
    exit 1
fi
echo "$VM_LIST_JSON" | jq -c | grep -E "\\"vm_id\\":($ID_REGEX)([^0-9]|$)" | proxmox_vm.vm_id.stop_force.to.jsons.sh
echo "$VM_LIST_JSON" | jq -c | grep -E "\\"vm_id\\":($ID_REGEX)([^0-9]|$)" | proxmox_vm.vm_id.delete.to.jsons.sh

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ":: done — templates preserved"
"""

RESET_SETUP_SH = """\
#!/bin/bash

##
## reset — delete this scenario's VMs (from manifest) then re-deploy
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t SCENARIO_VM_IDS  < <(jq -r '.vms[].vm_id' "$MANIFEST")
mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip'   "$MANIFEST")
ID_REGEX=$(printf '|%s' "${SCENARIO_VM_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting scenario VMs (vm_ids: ${SCENARIO_VM_IDS[*]})..."
VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1 | grep '"vm_id":[0-9]')
if [ -z "$VM_LIST_JSON" ]; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned no VM data — aborting" >&2
    exit 1
fi
echo "$VM_LIST_JSON" | jq -c | grep -E "\\"vm_id\\":($ID_REGEX)([^0-9]|$)" | proxmox_vm.vm_id.stop_force.to.jsons.sh
echo "$VM_LIST_JSON" | jq -c | grep -E "\\"vm_id\\":($ID_REGEX)([^0-9]|$)" | proxmox_vm.vm_id.delete.to.jsons.sh

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \\
	-l "all" \\
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
"""

RESET_SSH_KEYS_SH = """\
#!/bin/bash

##
## remove known_hosts entries for every VM IP in this scenario (from manifest)
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip' "$MANIFEST")

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done
"""

SHOW_INVENTORY_SH = """\
#!/bin/bash

ansible-inventory -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" --graph
"""


# --- templates/ (class-B parametrised) -------------------------------------

ANSIBLE_VARS_YML = """\
---
################################################################################
# range42 — scenario-specific variables (@@SCENARIO@@)
#
# Generated by r42playbooks. Shared variables -> group_vars/all/vars.yml,
# secrets -> vault (see vault-example.yml).
################################################################################


#### SCENARIO IDENTIFICATION ####

INFRASTRUCTURE_SCENARIO: "@@SCENARIO@@"


#### CREDENTIAL GENERATION ####

context_auto_generate_ssh_keys: "YES"
context_auto_generate_vm_passwords: "YES"

student_additionnal_keys_count: 5


#### CLOUD-INIT USERNAMES ####

default_admin_vm_ci_user: "alice"
default_trainee_vm_ci_user: "bob"
"""

VAULT_EXAMPLE_YML = """\
---
################################################################################
# range42 — vault secrets (@@SCENARIO@@)
#
# Copy to vault.yml, fill real values, then: ansible-vault encrypt vault.yml
# Never commit the unencrypted version.
################################################################################


#### PROXMOX API SECRET ####
proxmox_api_token_secret: "REPLACE_ME"


#### JUMP HOST ####
jump_password: "REPLACE_ME"


#### CLOUD-INIT PASSWORDS ####
default_admin_vm_ci_password: "REPLACE_ME"
default_admin_vm_ci_ssh_key: "ssh-ed25519 AAAA... alice CODENAME-SCENARIO"
default_trainee_vm_ci_password: "REPLACE_ME"
default_trainee_vm_ci_ssh_key: "ssh-ed25519 AAAA... bob CODENAME-SCENARIO"


#### TAILSCALE ####
infrastructure_tailscale_authkey: "tskey-auth-REPLACE_ME"
infrastructure_tailscale_apikey: "tskey-api-REPLACE_ME"


#### MISC ####
deployer_cli_user_ssh_known_hosts: "/home/your_deployer_cli_username/.ssh/known_hosts"
"""


# --- main.yml / main_vms_only.yml import skeleton --------------------------

MAIN_HEADER = """\
---
##
## @@SCENARIO@@ — generated by r42playbooks
##

"""

MAIN_VMS_ONLY_HEADER = """\
---
##
## @@SCENARIO@@ — deploy VMs only (templates already exist; skip 01_init_proxmox)
##

"""

# Staged 01_init_proxmox sub-orchestrators, generated per scenario so each stage
# imports ONLY the OS families the composition uses (@@IMPORTS@@ = the import
# lines). The cloudinit_<os>.yml downloads and templates/<os>/ trees are copied
# from the vendored asset; these two files just wire up the used ones.

STAGE_DOWNLOAD_MAIN = """\
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
# PROMOX INIT - download cloud-init base images (only the OS families used)
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

@@IMPORTS@@"""

# Rendered per image from the catalog's 01_image_layer cloud_image spec.
# @@IMAGE_ID@@      — the image id (e.g. ubuntu_noble)
# @@ISO_URL@@       — download URL
# @@ISO_FILE_NAME@@ — filename on Proxmox local storage (/var/lib/vz/template/iso/)
CLOUDINIT_DOWNLOAD_YML = """\
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
#
# PROXMOX INIT - download cloud init image for @@IMAGE_ID@@
#
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

- hosts: proxmox
  gather_facts: false
  vars_files:
    - "../../secrets/default_vault.yml"

  tasks:
    - name: PROMOX INIT - DOWNLOAD - CLOUD INIT images
      include_role:
        name: range42-ansible_roles-proxmox_controller

      vars:
        proxmox_vm_action: "storage_download_iso"
        proxmox_storage: "local"
        iso_file_content_type: "iso"
        iso_url: "@@ISO_URL@@"
        iso_file_name: "@@ISO_FILE_NAME@@"

# The download-url API is async (returns a UPID immediately). Poll on
# proxmox-cli until the file is fully on disk before stage_01 imports it.
- hosts: proxmox-cli
  gather_facts: false
  vars_files:
    - "../../secrets/default_vault.yml"

  tasks:
    - name: PROMOX INIT - WAIT for @@ISO_FILE_NAME@@ to be fully downloaded
      ansible.builtin.stat:
        path: "/var/lib/vz/template/iso/@@ISO_FILE_NAME@@"
      register: _cloudinit_img
      until: _cloudinit_img.stat.exists and _cloudinit_img.stat.size > 100000000
      retries: 120   # 120 x 10 s = 20 min max
      delay: 10
      changed_when: false
"""

STAGE_TEMPLATES_MAIN = """\
---
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
# PROMOX INIT - create the Proxmox template images (only the OS families used)
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

@@IMPORTS@@"""

# --- stage_01 per-template-VM create play (rendered from catalog) ---
# One file per ProxmoxTemplateSpec entry in 01_image_layer/<image>/image.yml.
# Placeholders:
#   @@IMAGE_ID@@            — image id (e.g. ubuntu_noble)
#   @@VM_ID@@               — Proxmox vm_id (e.g. 9221)
#   @@VM_NAME@@             — vm_name (e.g. template-vm-small-01-4g-32g)
#   @@VM_CORES@@            — cpu cores (parsed from spec)
#   @@VM_MEMORY_MB@@        — memory in MB (parsed from spec)
#   @@VM_NET_BRIDGE@@       — network bridge (e.g. vmbr140)
#   @@VM_DISK_SIZE@@        — disk size string for qemu-img (e.g. 32g)
#   @@CLOUDINIT_IMAGE_PATH@@ — full path on Proxmox local storage
#   @@VM_CI_IP@@            — cloud-init IP
#   @@VM_CI_IP_GW@@         — cloud-init gateway (first 3 octets + .1)
TEMPLATE_VM_YML = """\
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
#
# PROXMOX INIT - create @@IMAGE_ID@@ template VM @@VM_NAME@@ (id @@VM_ID@@)
#
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

- hosts: proxmox
  gather_facts: false
  vars_files:
    - "../../../../secrets/default_vault.yml"

  tasks:
    #### IDEMPOTENCE - skip if already finalized as template ####
    - name: TEMPLATE @@VM_ID@@ - CHECK if already finalized as template
      ansible.builtin.shell: qm config @@VM_ID@@ 2>/dev/null | grep -q '^template:'
      register: tpl_@@VM_ID@@_is_template
      failed_when: false
      changed_when: false
      delegate_to: "{{ inventory_hostname }}-cli"

    - name: TEMPLATE @@VM_ID@@ - WAIT for unlock if a parallel deploy holds the VM
      ansible.builtin.shell: qm config @@VM_ID@@ | grep -q '^lock:'
      register: tpl_@@VM_ID@@_lock
      until: tpl_@@VM_ID@@_lock.rc != 0
      retries: 30
      delay: 10
      failed_when: false
      changed_when: false
      delegate_to: "{{ inventory_hostname }}-cli"
      when: tpl_@@VM_ID@@_is_template.rc != 0

    - name: TEMPLATE @@VM_ID@@ - SKIP all (already finalized as template)
      ansible.builtin.debug:
        msg: "Template @@VM_ID@@ is already a template - skipping. Run delete-everything to recreate."
      when: tpl_@@VM_ID@@_is_template.rc == 0

    #### vm_create idempotence: separate exists check ####
    - name: TEMPLATE @@VM_ID@@ - CHECK if VM exists (vm_create idempotence)
      ansible.builtin.shell: qm config @@VM_ID@@ 2>/dev/null
      register: tpl_@@VM_ID@@_exists
      failed_when: false
      changed_when: false
      delegate_to: "{{ inventory_hostname }}-cli"
      when: tpl_@@VM_ID@@_is_template.rc != 0

    - name: PROXMOX INIT - TEMPLATES - CREATE TEMPLATE - @@VM_NAME@@
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "vm_create"
        vm_id: @@VM_ID@@
        vm_name: "@@VM_NAME@@"
        vm_cpu: "host"
        vm_cores: @@VM_CORES@@
        vm_sockets: 1
        vm_memory: @@VM_MEMORY_MB@@
        vm_net_virtio_bridge: "@@VM_NET_BRIDGE@@"
      when:
        - tpl_@@VM_ID@@_is_template.rc != 0
        - tpl_@@VM_ID@@_exists.rc != 0

    - name: PROXMOX INIT - TEMPLATES - WAIT for vm_create to finish (lock-aware)
      ansible.builtin.shell: qm config @@VM_ID@@ | grep -q '^lock:'
      register: tpl_@@VM_ID@@_post_create_lock
      until: tpl_@@VM_ID@@_post_create_lock.rc != 0
      retries: 60
      delay: 5
      failed_when: false
      changed_when: false
      delegate_to: "{{ inventory_hostname }}-cli"
      when:
        - tpl_@@VM_ID@@_is_template.rc != 0
        - tpl_@@VM_ID@@_exists.rc != 0

- hosts: proxmox-cli
  gather_facts: false
  vars_files:
    - "../../../../secrets/default_vault.yml"

  tasks:
    - name: TEMPLATE @@VM_ID@@ - CHECK if already template (proxmox-cli play)
      ansible.builtin.shell: qm config @@VM_ID@@ 2>/dev/null | grep -q '^template:'
      register: tpl_@@VM_ID@@_is_template
      failed_when: false
      changed_when: false

    - name: PROXMOX INIT - TEMPLATES - IMPORT CLOUD INIT DISK - @@VM_NAME@@
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "template_cloudinit_import_disk"
        proxmox_node: "px-testing-cli"
        cloudinit_image_full_path: "@@CLOUDINIT_IMAGE_PATH@@"
        vm_id: @@VM_ID@@
        vm_disk_size: "@@VM_DISK_SIZE@@"
        proxmox_dest_vm_storage_name: "local-lvm"
      when: tpl_@@VM_ID@@_is_template.rc != 0

- hosts: proxmox
  gather_facts: false
  vars_files:
    - "../../../../secrets/default_vault.yml"

  tasks:
    - name: TEMPLATE @@VM_ID@@ - CHECK if already template (third play)
      ansible.builtin.shell: qm config @@VM_ID@@ 2>/dev/null | grep -q '^template:'
      register: tpl_@@VM_ID@@_is_template
      failed_when: false
      changed_when: false
      delegate_to: "{{ inventory_hostname }}-cli"

    - name: PROXMOX INIT - TEMPLATES - SET CLOUD DEFAULT INIT VARIABLE - @@VM_NAME@@
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "cloudinit_set_variables"
        vm_id: @@VM_ID@@
        vm_ci_user: "{{ default_admin_vm_ci_user | default('alice') }}"
        vm_ci_password: "{{ default_trainee_vm_ci_password | default('supersecret') }}"
        vm_ci_ssh_key: "{{ default_trainee_vm_ci_ssh_key }}"
        vm_ci_dns_ips: "1.1.1.1"
        vm_ci_ip: "@@VM_CI_IP@@"
        vm_ci_netmask: "24"
        vm_ci_ip_gw: "@@VM_CI_IP_GW@@"
      when: tpl_@@VM_ID@@_is_template.rc != 0

    - name: PROXMOX INIT - TEMPLATES - SET PROXMOX TAG
      include_role:
        name: range42-ansible_roles-proxmox_controller
      vars:
        proxmox_vm_action: "vm_set_tag"
        vm_id: @@VM_ID@@
        vm_tag_name: "template"
      when: tpl_@@VM_ID@@_is_template.rc != 0
"""

# Apt proxy cicustom play — rendered per image with its full vm_id list.
# @@VM_ID_LIST@@ — YAML sequence items, 6-space indent, e.g.:
#   "      - 9221  # template-vm-small-01-4g-32g\n      - 9222  # ..."
APPLY_APT_PROXY_YML = """\
##
## @@IMAGE_ID@@ - apt proxy via cloud-init cicustom (optional)
##
## Attaches /var/lib/vz/snippets/range42-apt-proxy.yaml as cloud-init vendor-data
## to every template VM. All VMs cloned from these templates inherit the apt
## proxy automatically via cloud-init at first boot.
## Skipped (no-op) if apt_proxy_url is empty/unset. Idempotent.
##

- hosts: proxmox-cli
  gather_facts: false
  vars_files:
    - "../../../../secrets/default_vault.yml"

  vars:
    bs2_template_vm_ids:
@@VM_ID_LIST@@
  tasks:
    - name: APT-PROXY - SKIP (apt_proxy_url is empty)
      ansible.builtin.debug:
        msg: "apt_proxy_url is empty - cloud-init cicustom not applied to templates"
      when: apt_proxy_url is not defined or (apt_proxy_url | length) == 0

    - name: APT-PROXY - ATTACH cicustom vendor TO TEMPLATES
      ansible.builtin.command:
        cmd: qm set {{ item }} --cicustom "vendor=local:snippets/range42-apt-proxy.yaml"
      loop: "{{ bs2_template_vm_ids }}"
      register: qm_result
      changed_when: qm_result.rc == 0
      failed_when:
        - qm_result.rc != 0
        - "'does not exist' not in qm_result.stderr"
      when: apt_proxy_url is defined and (apt_proxy_url | length) > 0

    - name: APT-PROXY - DETACH cicustom vendor FROM TEMPLATES (apt_proxy_url unset)
      ansible.builtin.command:
        cmd: qm set {{ item }} --delete cicustom
      loop: "{{ bs2_template_vm_ids }}"
      register: qm_unset
      changed_when: qm_unset.rc == 0
      failed_when:
        - qm_unset.rc != 0
        - "'does not exist' not in qm_unset.stderr"
      when: apt_proxy_url is not defined or (apt_proxy_url | length) == 0

    - name: APT-PROXY - DISPLAY STATUS
      ansible.builtin.debug:
        msg: |
          apt proxy: {{ apt_proxy_url if (apt_proxy_url is defined and (apt_proxy_url | length) > 0) else 'DISABLED' }}
          cicustom : {{ 'attached to ' + (bs2_template_vm_ids | length | string) + ' templates' if (apt_proxy_url is defined and (apt_proxy_url | length) > 0) else 'detached from templates' }}
"""

# Per-image stage_01 orchestrator — imports all template VM plays + proxy + update.
# @@IMAGE_ID@@        — image id
# @@TEMPLATE_IMPORTS@@ — "- import_playbook: ./template-vm-nano.yml\n..." lines
MAIN_IMAGE_YML = """\
##
## @@IMAGE_ID@@ — create + configure all Proxmox template VMs for this image
##

@@TEMPLATE_IMPORTS@@
# apt proxy cicustom (no-op if apt_proxy_url empty)
- import_playbook: ./_apply_apt_proxy.yml

# pre-update: start each VM, run apt update + dist-upgrade via cloud-init poweroff,
# then convert to template.
- import_playbook: ./_update_templates.yml
"""

# Reinstall helper for the 01_init_proxmox stage (re-run template creation).
INIT_REINSTALL_SH = """\
#!/bin/bash
##
## re-run 01_init_proxmox (download images + create templates)
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \\
    -l "proxmox" \\
    "./_main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
"""

# --- class-A: ansible-inventory.j2 (groups + member hosts, manifest-derived) ---
# @@GROUPS@@ is built per-composition; the proxmox/-cli groups stay verbatim
# (range42-context fills INFRASTRUCTURE_CODENAME / _PROXMOX_ADDRESS at deploy).

INVENTORY_J2 = """\
all:
  children:
    range42_infrastructure:
      children:
@@GROUPS@@
        proxmox:
          hosts:
            {{ INFRASTRUCTURE_CODENAME }}:
              ansible_host: {{ INFRASTRUCTURE_PROXMOX_ADDRESS | mandatory }}:8006
              ansible_connection: local
              ansible_python_interpreter: /usr/bin/python3

        proxmox-cli:
          hosts:
            {{ INFRASTRUCTURE_CODENAME }}-cli:
"""


# --- class-A: ssh-config.j2 (one Host block per VM, manifest-derived) -------
# @@VM_BLOCKS@@ is the per-VM Host/Hostname list; a single r42.* wildcard block
# carries the shared user / key / ProxyJump (all generated VMs are equivalent).

SSHCONFIG_J2 = """\
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####
#       infrastructure code name : {{ INFRASTRUCTURE_CODENAME }}
# infrastructure proxmox address : {{ INFRASTRUCTURE_PROXMOX_ADDRESS }}
#                       scenario : {{ INFRASTRUCTURE_SCENARIO }}
#### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

#### PROXMOX WEB UI (port forward) ####
Host px.{{ INFRASTRUCTURE_CODENAME }}.redirect_www.proxmox
    RequestTTY no
    RemoteCommand none
    localforward localhost:18042 {{ INFRASTRUCTURE_PROXMOX_ADDRESS | mandatory }}:8006

#### PX ROOT USER SSH ACCESS ####
Host px.{{ INFRASTRUCTURE_CODENAME }}-ssh_cli.root {{ INFRASTRUCTURE_CODENAME }}-cli
    Hostname {{ INFRASTRUCTURE_PROXMOX_ADDRESS | mandatory }}
    User root
    IdentityFile {{ DEPLOYER_CLI__DST_SSH_KEYS_JUMP_DEST_DIR }}/px.{{ INFRASTRUCTURE_CODENAME }}-{{ INFRASTRUCTURE_SCENARIO }}-ssh_cli.root
    Port 22

#### SSH JUMPER ####
Host px.{{ INFRASTRUCTURE_CODENAME }}.jumper
    Hostname {{ INFRASTRUCTURE_PROXMOX_ADDRESS | mandatory }}
    User jump_user
    IdentityFile {{ DEPLOYER_CLI__DST_SSH_KEYS_JUMP_DEST_DIR }}/px.{{ INFRASTRUCTURE_CODENAME }}-{{ INFRASTRUCTURE_SCENARIO }}-ssh_cli.jump_user
    Port 22

#### SCENARIO VMs ####
@@VM_BLOCKS@@

Host r42.*
    User alice
    IdentityFile {{ DEPLOYER_CLI__DST_SSH_KEYS_BACKEND_DEST_DIR }}/r42.{{ INFRASTRUCTURE_CODENAME }}-{{ INFRASTRUCTURE_SCENARIO }}-deployer-key_alice
    Port 22
    ProxyJump px.{{ INFRASTRUCTURE_CODENAME }}.jumper
"""


# --- class-A: section _main.yml (stage imports + per-VM global_* overrides) -

SECTION_MAIN_HEADER = """\
---
##
## @@SECTION@@ — generated by r42playbooks
## stage_00 clones VMs (per-VM global_* below); stage_01 installs software.
##
"""

# One stage_00 import with its global_* override block. Filled per box.
SECTION_MAIN_STAGE00 = """\
- import_playbook: ./stage_00/@@VM_NAME@@.yml
  vars:
    global_vm_name: "@@VM_NAME@@"
    global_vm_ssh_name: "r42.@@VM_NAME@@"
    global_vm_id: @@VM_ID@@
    global_vm_description: "@@DESCRIPTION@@"
    global_vm_tag_name: "@@TAG@@"
    global_vm_ci_ip: "@@IP@@"
    global_template_vm_id: @@TEMPLATE_VM_ID@@
    global_template_name: "@@TEMPLATE_NAME@@ - id @@TEMPLATE_VM_ID@@"
"""


README_MD = """\
# @@SCENARIO@@

Generated by **r42playbooks** (msfvenom-style scenario generator).

- subnet layout: `@@SUBNET_LAYOUT@@`

## Boxes

@@BOX_TABLE@@

## Deploy

```bash
range42-context use <codename> @@SCENARIO@@   # creates secrets/ symlink + vault
./@@SCENARIO@@.setup.sh                        # templates + VMs + software
```

The composition is reproduced in `scenario.r42.yml` — re-run
`r42playbooks new --spec scenario.r42.yml` to regenerate this tree.
"""
