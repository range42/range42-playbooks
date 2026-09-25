# systems.configure.terminfo (bundle)

Installs the alacritty terminfo entry on a target group and lets sshd accept the
client `TERM` value, so `TERM=alacritty` no longer breaks remote sessions on
Ubuntu minimal images.

Caller vars: `terminfo_hosts` (inventory group the play targets ; **required** —
scenario inventories carry `proxmox`/`proxmox_cli` groups, so an implicit `all`
would rewrite sshd config on the hypervisor and the deployer).

The terminfo binary is copied from the Ansible controller
(`/usr/share/terminfo/a/alacritty`). The play checks the controller first and
prints an explicit skip warning when the entry is missing (install `alacritty`
or `ncurses-term` on the controller), instead of failing silently. The sshd
edit is guarded by `validate: sshd -t`, so a config that would not parse is
never written.
