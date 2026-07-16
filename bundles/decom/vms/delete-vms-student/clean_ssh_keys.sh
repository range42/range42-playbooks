#!/bin/bash

STUDENT_BOX=(
    "192.168.143.160" # student-box-01
)

for ip in "${STUDENT_BOX[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done
