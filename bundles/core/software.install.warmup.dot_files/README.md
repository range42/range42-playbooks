# software.install.warmup.dot_files (bundle)

Thin bundle: invokes the catalog role `software.install.warmup.dot_files` on a target group
for a given user (oh-my-zsh + zshrc + login shell = zsh). The role is reused as-is
(parameterized by `OPERATOR_USER`).

Caller vars: `TARGET_GROUP`, `TARGET_USER` (required) ; `INSTALL_ZSH_DOTFILES` (def YES),
`INSTALL_VIM_DOTFILES` (def NO), `APPLY_FOR_ROOT` (def NO).

> Distinct from the API-driven `bundles/core/linux/ubuntu/install/dot-files/` (which is
> `hosts: all`) : this one is group-targeted for scenario composition.
