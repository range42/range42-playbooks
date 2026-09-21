#!/usr/bin/env python3
"""
Regenerate the README.md index of the bundles tree from every bundle_parameters.json.

Writes bundles/README.md (the tiers and the conventions) and one README.md per tier
(admin, ctf, firewall, generic, proxmox) : one table row per bundle, its first sentence,
its parameter count, and the links to the bundle, its README when it has one, and its
two parameter files. Run it after adding, renaming or re-describing a bundle :

    "$RANGE42_BUNDLE_DIR"/_tools/generate-bundle-index.py

The descriptions come from bundle_parameters.json, itself generated from the hand-written
bundle_parameters.src.yml by generate-bundle-params.py : fix the wording there, then run both.
"""

import json
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIERS = ["admin", "proxmox", "firewall", "generic", "ctf"]

TIER_TITLE = {
    "admin": "admin bundles : the application stacks of the admin tier",
    "proxmox": "proxmox bundles : images, templates, VMs and SDN networks on the hypervisor",
    "firewall": "firewall bundles : the Proxmox firewall and the firewall inside the VM",
    "generic": "generic bundles : group-targeted system, network and repository primitives",
    "ctf": "ctf bundles : vulnerable containers for training",
}

TIER_INTRO = {
    "admin": [
        "Each bundle installs one application stack (docker-compose, from the matching element of range42-catalog) on the dedicated admin VM the scenario manifest reserves for it, on the admin network `net142`.",
        "Every admin bundle is **optional** : the scenario imports it behind its feature flag (`INSTALL_<NAME>=YES` on `range42-context deploy -e ...`, or the checkbox of the `range42-context --tui` deploy panel), and the flags of a scenario are listed in its `manifest/feature_flags.yml`.",
        "The hypervisor firewall profile of each stack (its open ports on the guest's Proxmox chain) lives in [firewall/in_proxmox](../firewall/README.md) under the `firewall.baseline.*` of the same service ; the firewall inside the VM comes from `firewall/in_vm` and `generic/network.baseline.*`.",
    ],
    "proxmox": [
        "Everything that talks to the Proxmox API through the `range42-ansible_roles-proxmox_controller` role : the cloud images, the VM templates, the per-VM bootstrap and its network cards, the SDN networks and the migration from the legacy bridges.",
        "The SDN family has two layers. `sdn_network.bootstrap` is the composite a scenario imports from its `00_sdn_bootstrap/_main.yml` : it reads the live state, creates what is missing, updates what drifted, applies once and reconciles the live SNAT rules. The single actions (`sdn_network.{create,update,delete}.*`, `list.*`, `apply`) are raw API calls, one bundle one call, meant for the backend API and the UI : a create or a delete stays pending until `sdn_network.apply` runs, and an apply replays the `post-up` of every active subnet, which is why `reconcile.snat_rules` exists.",
        "`template_net_bridge` is the parameter that puts a template build on the SDN templating network (`net140`) ; the manifest of the scenario (`manifest/scenario_vms.json`) drives which templates and which VMs exist.",
    ],
    "firewall": [
        "Two different firewalls, two sub-directories.",
        "`in_proxmox/` is the **Proxmox firewall**, on the hypervisor : the `baseline.*` bundles declare rules (anti-lockout accepts on the datacenter and the node, an ssh accept on every VM, the open ports of each admin profile) without switching anything on ; the `enable.*` and `disable.*` bundles arm and disarm the datacenter, the node, one guest or every guest of the active scenario, always with the ssh accept posted first ; `report.status` reads the three levels. Arming is opt-in at deploy (`-e FIREWALL_ARM_VMS=YES`) or later through `range42-context networks-firewall-on`.",
        "`in_vm/` is the firewall **inside the VM** (ufw), applied on an inventory group : the same five profiles also exist as `generic/network.baseline.*`, their former home, and both are imported by the scenarios today.",
    ],
    "generic": [
        "Reusable primitives applied on an inventory group of the scenario (`target_group`), from the roles of range42-catalog : system baselines and their variants, user and access configuration, network policies inside the VM, repository clones and the Kunai workshop toolchain.",
        "`network.baseline.*` and [firewall/in_vm/os_firewall.baseline.*](../firewall/README.md) are the same five ufw profiles under two names ; the firewall tier is the newer home, both are imported by the scenarios today.",
    ],
    "ctf": [
        "One vulnerable container per bundle, deployed with docker-compose from the matching element of range42-catalog (`03_container_layer/docker/_ctf/`, mirrored exactly) on one target VM of the scenario. The five parameters are the same for every bundle : the target VM (`global_vm_ssh_name`), the operator user, the remote compose directory, its cleanup once the stack is up, and whether the proof-of-concept files ship along.",
        "The taxonomy follows the catalog : `cve/<domain>/<product>/<CVE-id>` and `misconfiguration/<domain>/<service>`. The tier is open-ended, the path of a bundle may be deeper than in the other tiers.",
    ],
}

TIER_ONE_LINE = {
    "admin": "application stacks on the dedicated admin VMs, each behind an `INSTALL_<NAME>` feature flag",
    "proxmox": "cloud images, VM templates, VM bootstrap and network cards, SDN networks, legacy bridge migration",
    "firewall": "the Proxmox firewall (`in_proxmox`) and the firewall inside the VM (`in_vm`)",
    "generic": "group-targeted primitives : system baselines, users and access, network policies, repositories, Kunai workshop",
    "ctf": "vulnerable containers for training, one CVE or misconfiguration each",
}

GROUP_TITLE = {
    "proxmox": OrderedDict([
        ("cloud_init_image", "Cloud images"),
        ("template", "VM templates"),
        ("vm", "VMs and their network cards"),
        ("sdn_network", "SDN networks"),
        ("legacy_bridge", "Legacy bridges (migration)"),
    ]),
    "generic": OrderedDict([
        ("systems", "Systems"),
        ("network", "Network policies inside the VM"),
        ("repo", "Repositories"),
        ("software", "Software"),
    ]),
    "firewall": OrderedDict([
        ("in_proxmox", "in_proxmox : the Proxmox firewall"),
        ("in_vm", "in_vm : the firewall inside the VM (ufw)"),
    ]),
}


def first_sentence(text):
    """The first sentence, plus the second one while the result stays under 60 characters :
    the raw single-action bundles open with a five-word sentence and say what matters next."""
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z`])", text)
    out = parts[0].strip()
    for extra in parts[1:]:
        if len(out) >= 60:
            break
        out = (out + " " + extra).strip()
    return out


def cell(text):
    return text.replace("|", "\\|")


def load_bundles():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("_"))
        if "bundle_parameters.json" not in filenames or "main.yml" not in filenames:
            continue
        with open(os.path.join(dirpath, "bundle_parameters.json")) as fh:
            data = json.load(fh)
        rel = os.path.relpath(dirpath, ROOT)
        tier = rel.split(os.sep)[0]
        out.append({
            "rel": rel,
            "tier": tier,
            "name": rel[len(tier) + 1:],
            "desc": first_sentence(data.get("description", "")),
            "optional": bool(data.get("optional")),
            "flag": data.get("install_flag") or "",
            "nparams": len(data.get("params", [])),
            "readme": os.path.exists(os.path.join(dirpath, "README.md")),
        })
    out.sort(key=lambda b: b["rel"])
    return out


def link_to_bundle(b, base):
    target = b["name"] + ("/README.md" if b["readme"] else "/")
    return "[`%s`](%s)" % (b["name"], target)


def params_cell(b):
    return "%d, [json](%s/bundle_parameters.json), [src](%s/bundle_parameters.src.yml)" % (b["nparams"], b["name"], b["name"])


def table(rows, with_flag=False):
    lines = []
    if with_flag:
        lines.append("| Bundle | Feature flag | What it does | Parameters |")
        lines.append("|---|---|---|---|")
        for b in rows:
            lines.append("| %s | `%s` | %s | %s |" % (link_to_bundle(b, None), b["flag"], cell(b["desc"]), params_cell(b)))
    else:
        lines.append("| Bundle | What it does | Parameters |")
        lines.append("|---|---|---|")
        for b in rows:
            lines.append("| %s | %s | %s |" % (link_to_bundle(b, None), cell(b["desc"]), params_cell(b)))
    return lines


def group_key(b):
    tier = b["tier"]
    if tier == "firewall":
        return b["name"].split("/")[0]
    if tier in ("proxmox", "generic"):
        return b["name"].split(".")[0]
    if tier == "ctf":
        parts = b["name"].split("/")
        return "/".join(parts[:2])
    return ""


def tier_readme(tier, bundles):
    rows = [b for b in bundles if b["tier"] == tier]
    lines = ["# %s" % TIER_TITLE[tier], ""]
    for paragraph in TIER_INTRO[tier]:
        lines += [paragraph, ""]
    lines.append("%d bundles. Every bundle is a playbook, `main.yml`, imported at parse time through `RANGE42_BUNDLE_DIR` ; its caller-facing parameters are declared in `bundle_parameters.src.yml` and published as `bundle_parameters.json` (see [../README.md](../README.md))." % len(rows))
    lines.append("")
    if tier == "admin":
        lines += table(rows, with_flag=True)
    elif tier in GROUP_TITLE:
        for key, title in GROUP_TITLE[tier].items():
            sub = [b for b in rows if group_key(b) == key]
            if not sub:
                continue
            lines.append("## %s" % title)
            lines.append("")
            lines += table(sub)
            lines.append("")
        leftovers = [b for b in rows if group_key(b) not in GROUP_TITLE[tier]]
        if leftovers:
            lines.append("## Other")
            lines.append("")
            lines += table(leftovers)
            lines.append("")
    else:
        groups = OrderedDict()
        for b in rows:
            groups.setdefault(group_key(b), []).append(b)
        for key, sub in groups.items():
            lines.append("## %s" % key)
            lines.append("")
            lines += table(sub)
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")
    lines.append("Regenerate this index with `_tools/generate-bundle-index.py` after adding or re-describing a bundle.")
    return "\n".join(lines) + "\n"


def root_readme(bundles):
    counts = OrderedDict((t, len([b for b in bundles if b["tier"] == t])) for t in TIERS)
    lines = [
        "# bundles",
        "",
        "A **bundle** is a reusable Ansible playbook with a declared interface : one action on the Proxmox host, one stack on a VM, one policy on a group of VMs. The scenarios of `scenarios/` are compositions of bundles, and the same bundles are the interface meant for the backend API and the deployer UI : one bundle, one call, one result.",
        "",
        "## Layout and grammar",
        "",
        "Paths follow `<tier>/<subject>.<verb>.<object>/` (the `ctf` tier is deeper, `ctf/cve/<domain>/<product>/<CVE-id>/`). A scenario imports a bundle at parse time through the `RANGE42_BUNDLE_DIR` environment variable, exported by `range42-context` :",
        "",
        "```yaml",
        "- import_playbook: \"{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/generic/network.baseline.ssh/main.yml\"",
        "  vars:",
        "    target_group: \"r42_admin\"",
        "```",
        "",
        "Each bundle directory holds :",
        "",
        "- `main.yml`, the playbook, its header saying what it does, its required variables and an example call site",
        "- `bundle_parameters.src.yml`, the hand-written contract : the caller-facing parameters, their type, whether they come from the vault, their default and where it lives",
        "- `bundle_parameters.json`, generated from the source by [`_tools/generate-bundle-params.py`](_tools/README.md), never edited by hand, consumed by the backend API and the UI",
        "- a `README.md` for the bundles that need more than their header",
        "",
        "## Tiers",
        "",
        "| Tier | Bundles | What lives there | Index |",
        "|---|---|---|---|",
    ]
    for t in TIERS:
        lines.append("| `%s/` | %d | %s | [%s/README.md](%s/README.md) |" % (t, counts[t], TIER_ONE_LINE[t], t, t))
    lines += [
        "| `_tools/` | | the parameter contract tooling : schema, generator, call-site check, reference annotations, and this index generator | [_tools/README.md](_tools/README.md) |",
        "",
        "%d bundles in total." % len(bundles),
        "",
        "## Where a scenario imports them",
        "",
        "- `00_sdn_bootstrap/_main.yml` imports `proxmox/sdn_network.bootstrap` with the networks the scenario declares, then `proxmox/legacy_bridge.workaround.shadowed_subnet` for a host that still carries the old bridges",
        "- `01_templates-bootstrap/_main.yml` imports `proxmox/cloud_init_image.download.all` and the `proxmox/template.build.*` bundles, driven by the scenario manifest and `template_net_bridge`",
        "- every `stage_00` of a tier imports `proxmox/vm.bootstrap` once per VM : clone, cloud-init, start, wait for ssh",
        "- `_firewall/` imports the `firewall/in_proxmox/*` anchors : status, management access, the ssh baseline of every VM, and the opt-in arming",
        "- every `stage_01` imports `generic/*` primitives on its groups and, on the admin tier, one `admin/software.install.*` stack per feature flag, with its `firewall/in_proxmox/firewall.baseline.<name>` profile and its `firewall/in_vm` or `generic/network.baseline.*` policy",
        "",
        "## Parameter contracts",
        "",
        "`bundle_parameters.src.yml` is the source of truth of a bundle's interface. `_tools/generate-bundle-params.py` validates every source against `_tools/bundle_parameters.schema.json`, emits the `bundle_parameters.json` next to each `main.yml`, and `_tools/check-callsites.py` compares the declared parameters with what the scenarios really pass. Details and rules in [_tools/README.md](_tools/README.md).",
        "",
        "Regenerate the six index files (this one and one per tier) with `_tools/generate-bundle-index.py` after adding, renaming or re-describing a bundle.",
    ]
    return "\n".join(lines) + "\n"


def main():
    bundles = load_bundles()
    if not bundles:
        print("no bundle found under %s" % ROOT, file=sys.stderr)
        return 1
    unknown = sorted({b["tier"] for b in bundles} - set(TIERS))
    if unknown:
        print("unknown tier(s) %s : add them to TIERS and their texts" % ", ".join(unknown), file=sys.stderr)
        return 1
    written = []
    with open(os.path.join(ROOT, "README.md"), "w") as fh:
        fh.write(root_readme(bundles))
    written.append("README.md")
    for t in TIERS:
        with open(os.path.join(ROOT, t, "README.md"), "w") as fh:
            fh.write(tier_readme(t, bundles))
        written.append("%s/README.md" % t)
    print("%d bundles, wrote : %s" % (len(bundles), ", ".join(written)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
