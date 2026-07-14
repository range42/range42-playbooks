# software.install.warmup.dot_files (bundle)

Thin bundle: invokes the catalog role `software.install.warmup.dot_files` on a target group
for a given user (oh-my-zsh + zshrc + login shell = zsh). The role is reused as-is
(parameterized by `OPERATOR_USER`).

Caller vars: `TARGET_GROUP`, `TARGET_USER` (required) ; `WARMUP_INSTALL_ZSH_DOTFILES` (def YES),
`WARMUP_INSTALL_VIM_DOTFILES` (def NO), `WARMUP_APPLY_FOR_ROOT` (def NO). The optional knobs use a
distinct `WARMUP_` prefix (routed through `_warmup_*` internal vars) so they never self-reference
the role vars of the same name - which would trigger recursive templating.

> Distinct from the API-driven `bundles/core/linux/ubuntu/install/dot-files/` (which is
> `hosts: all`) : this one is group-targeted for scenario composition.
