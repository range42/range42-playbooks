# systems.configure.add_user (bundle)

Thin, group-targeted bundle: invokes the catalog role `systems.configure.add_user` on
`TARGET_GROUP` to create a user (home + shell + password, no chpasswd).

Caller vars: `TARGET_GROUP`, `TARGET_USER`, `TARGET_PASSWORD` (required) ;
`TARGET_SHELL_PATH`, `TARGET_UPDATE_PASSWORD` (`always`/`on_create`), `CHANGE_PWD_AT_LOGON` (optional).

> Group-targeted for scenario composition. The old `hosts: all` API-driven duplicate over the
> same underlying role was decommissioned.
