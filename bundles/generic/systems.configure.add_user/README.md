# systems.configure.add_user (bundle)

Thin, group-targeted bundle: invokes the catalog role `systems.configure.add_user` on
`TARGET_GROUP` to create a user (home + shell + password, no chpasswd).

Caller vars: `TARGET_GROUP`, `TARGET_USER`, `TARGET_PASSWORD` (required) ;
`TARGET_SHELL_PATH`, `TARGET_UPDATE_PASSWORD` (`always`/`on_create`), `CHANGE_PWD_AT_LOGON` (optional).

> Distinct from the API-driven `bundles/core/linux/ubuntu/configure/add-user/` (`hosts: all`) :
> this one is group-targeted for scenario composition. Same underlying role.
