# systems.configure.sudo (bundle)

Thin bundle: invokes the catalog role `systems.configure.sudo` on a target group.

Caller vars: `TARGET_GROUP`, `TARGET_USER` (required) ; `SUDO_STATE` (present/absent),
`SUDO_NOPASSWD` (bool) (optional).
