# systems.configure.terminfo (bundle)

Installs the alacritty terminfo entry on a target group and lets sshd accept the
client `TERM` value, so `TERM=alacritty` no longer breaks remote sessions on
Ubuntu minimal images.

Caller vars: `terminfo_hosts` (inventory group the play targets ; falls back to
`all`).

The terminfo binary is copied from the Ansible controller
(`/usr/share/terminfo/a/alacritty`) ; the copy is best-effort, so the play is a
no-op when the controller has no alacritty entry.
