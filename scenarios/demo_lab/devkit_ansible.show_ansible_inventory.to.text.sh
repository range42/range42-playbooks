#!/bin/bash

# ansible-inventory -i "./inventory/inventory_default.yml" --graph
ansible-inventory -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" --graph
