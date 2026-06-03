# bundles/core/linux/debian

Debian-targeted **example bundles** for composing scenarios — the siblings of
`../ubuntu/`.

The warmup/configure roles (`software.install.warmup.*`, `software.configure.*`,
`systems.configure.*`) dispatch per OS **at runtime** via
`ansible_facts.distribution` (ubuntu / debian / fedora — see the catalog's
`feat/local-apt-mirror`). Each bundle here therefore has the **same** `main.yml`
as `../ubuntu/` (it runs `hosts: all` + the OS-agnostic role); only the `test.sh`
target host differs (a Debian box, e.g. `r42.debian-jump-00`).

Pair with the catalog `debian-jump` box template (`image: debian_trixie`,
Debian 13) to deploy a Debian target these bundles can run against.

> If the roles stay fully OS-agnostic, a future cleanup may collapse
> `ubuntu/`+`debian/` into a single `linux/` set; kept split here to mirror the
> existing layout.
