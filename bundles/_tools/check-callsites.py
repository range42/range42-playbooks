#!/usr/bin/env python3
"""
bundles/_tools/check-callsites.py

Cross-check each bundle_parameters.src.yml against how the bundle is ACTUALLY called - in scenarios
AND in other bundles (bundle-to-bundle imports). The call-site `vars:` block is the ground-truth
caller contract. Catches:
  - MISSING  : a var passed at a call-site but NOT declared (annotation gap)
  - PHANTOM  : a declared param default_where=none, never passed, not the target (suspicious)
  - REQUIRED?: declared required:false but passed by 100% of call-sites (always provided)
Bundles with 0 call-sites anywhere are true orphans.

Read-only. Usage: check-callsites.py [--all] [<tier>/<name> ...]
"""
import glob, re, os, sys, collections
import yaml

SELF = os.path.dirname(os.path.abspath(__file__))
BROOT = os.path.dirname(SELF)
R = os.environ.get("RANGE42_GITDIR__ROOT_DIR", os.path.expanduser("~/range42")).rstrip("/")
SCEN = f"{R}/range42-playbooks/scenarios"

sites = collections.defaultdict(lambda: {"scen": 0, "bundle": 0, "keys": collections.Counter(), "flags": collections.Counter()})


def scan(root, kind):
    for f in glob.glob(f"{root}/**/*.yml", recursive=True):
        if f"{BROOT}/_tools/" in f:
            continue
        try:
            doc = yaml.safe_load(open(f))
        except Exception:
            continue
        if not isinstance(doc, list):
            continue
        for item in doc:
            if not (isinstance(item, dict) and "import_playbook" in item):
                continue
            m = re.search(r"\}\}/(.+?)/main\.yml", str(item["import_playbook"]))
            if not m:
                continue
            s = sites[m.group(1)]
            s[kind] += 1
            for k in (item.get("vars") or {}):
                s["keys"][k] += 1
            w = str(item.get("when", ""))
            s["flags"][w.split("|")[0].strip() if w else "(always)"] += 1


scan(SCEN, "scen")
scan(BROOT, "bundle")

argv = [a for a in sys.argv[1:] if a != "--all"]
show_all = "--all" in sys.argv
srcs = ([f"{BROOT}/{b}/bundle_parameters.src.yml" for b in argv] if argv
        else sorted(glob.glob(f"{BROOT}/**/bundle_parameters.src.yml", recursive=True)))

issues = 0
orphans = []
for src in srcs:
    if not os.path.isfile(src):
        print(f"MISS {src}"); continue
    bundle = os.path.relpath(os.path.dirname(src), BROOT)
    if bundle.split("/")[0] in ("_tools", "decom"):
        continue
    doc = yaml.safe_load(open(src)) or {}
    params = {p["name"]: p for p in (doc.get("params") or [])}
    cs = sites.get(bundle, {"scen": 0, "bundle": 0, "keys": collections.Counter(), "flags": collections.Counter()})
    n = cs["scen"] + cs["bundle"]
    if n == 0:
        orphans.append((bundle, len(params)))
        continue
    inst_flag = doc.get("install_flag")   # the bundle's toggle is passed at the call-site but captured at bundle-level, not a param
    missing = [k for k in cs["keys"] if k not in params and k != inst_flag]
    phantom = [nm for nm, p in params.items()
               if nm not in cs["keys"] and not p.get("target")
               and p.get("default_where") == "none" and not p.get("from_vault")]
    always = [nm for nm, p in params.items() if cs["keys"].get(nm, 0) == n and p.get("required") is False]
    src_lbl = f"{cs['scen']} scen + {cs['bundle']} bundle"
    flags = ", ".join(f"{k}={v}" for k, v in cs["flags"].most_common())
    if show_all or missing or phantom or always:
        if missing or phantom or always:
            issues += 1
        print(f"[{bundle}]  {src_lbl} | when: {flags}")
        if missing:
            print(f"   MISSING (passed but not declared): {', '.join(sorted(missing))}")
        if phantom:
            print(f"   PHANTOM? (required-ish, never passed): {', '.join(sorted(phantom))}")
        if always:
            print(f"   REQUIRED? (required:false but passed {n}/{n}): {', '.join(sorted(always))}")

if orphans:
    print(f"\n-- TRUE orphans (0 call-sites anywhere): {len(orphans)} --")
    for b, np in orphans:
        print(f"   {b} ({np} declared)")

print(f"\n== bundles with call-site discrepancies: {issues} ==")
