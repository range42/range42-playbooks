#!/usr/bin/env python3
"""
bundles/_tools/generate-bundle-params.py

ANNOTATE-THEN-GENERATE. bundle_parameters.src.yml is the source of truth. This tool:
  (1) VALIDATE   each src against bundle_parameters.schema.json (reject malformed)
  (2) DEAD-PARAM each declared name must appear in the bundle CODE (main.yml, sub-playbooks)
                 OR a referenced catalog role -- NOT in its own annotation -> else WARN
  (3) RESOLVE    default_where=role-defaults params -> pull value from the role, mark default_review
  (4) TRANSCRIBE src -> bundle_parameters.json next to main.yml
Plus a COVERAGE gate in regenerate-all mode (every in-scope main.yml must have a src.yml).

Usage:
  generate-bundle-params.py                                  # all live bundles (+ coverage gate)
  generate-bundle-params.py generic/systems.configure.sudo [<tier>/<name> ...]
"""
import sys, os, re, json, glob
import yaml
import jsonschema

SELF_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLES_ROOT = os.path.dirname(SELF_DIR)
SCHEMA_PATH = os.path.join(SELF_DIR, "bundle_parameters.schema.json")
R = os.environ.get("RANGE42_GITDIR__ROOT_DIR", os.path.expanduser("~/range42")).rstrip("/")
CATALOG = os.environ.get("CATALOG", f"{R}/range42-catalog/02_ansible_layer")
GEN_MSG = "DO NOT EDIT - generated from bundle_parameters.src.yml by _tools/generate-bundle-params.py"
TIERS = ["admin", "proxmox", "generic", "ctf"]
ANNOTATION_FILES = {"bundle_parameters.src.yml", "bundle_parameters.json"}

with open(SCHEMA_PATH) as fh:
    SCHEMA = json.load(fh)


def load_yaml(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def role_dirs(main_path):
    """Catalog role dirs referenced by the bundle (searched in both tiers)."""
    dirs = []
    if not os.path.isfile(main_path):
        return dirs
    try:
        doc = load_yaml(main_path)
    except Exception:
        return dirs
    if not isinstance(doc, list):
        return dirs
    for play in doc:
        if not isinstance(play, dict):
            continue
        for r in (play.get("roles") or []):
            role = r.get("role") if isinstance(r, dict) else r
            if not role:
                continue
            for tier in ("admin", "trainee"):
                d = f"{CATALOG}/{tier}/roles/{role}"
                if os.path.isdir(d):
                    dirs.append(d)
    return dirs


def _walk_role_names(node, acc):
    """Collect role names from include_role/import_role anywhere in a parsed doc."""
    if isinstance(node, dict):
        for key in ("include_role", "import_role"):
            v = node.get(key)
            if isinstance(v, dict) and v.get("name"):
                acc.add(str(v["name"]))
        for v in node.values():
            _walk_role_names(v, acc)
    elif isinstance(node, list):
        for it in node:
            _walk_role_names(it, acc)


def included_role_dirs(bundle_dir):
    """Catalog role dirs pulled dynamically via include_role/import_role in the
    bundle's playbooks (tasks) - invisible to role_dirs() which only reads `roles:`.
    Used to WIDEN the dead-param corpus only (never the default resolution)."""
    names = set()
    for yf in glob.glob(f"{bundle_dir}/**/*.yml", recursive=True):
        if os.path.basename(yf) in ANNOTATION_FILES:
            continue
        try:
            _walk_role_names(load_yaml(yf), names)
        except Exception:
            pass
    dirs = []
    for role in sorted(names):
        for tier in ("admin", "trainee"):
            d = f"{CATALOG}/{tier}/roles/{role}"
            if os.path.isdir(d):
                dirs.append(d)
    return dirs


def corpus_text(bundle_dir, rdirs):
    """All CODE under the bundle dir + referenced roles, EXCLUDING the annotation files."""
    buf = []
    for base in [bundle_dir] + rdirs:
        for root, _, files in os.walk(base):
            for fn in files:
                if fn in ANNOTATION_FILES:
                    continue
                try:
                    with open(os.path.join(root, fn), errors="ignore") as fh:
                        buf.append(fh.read())
                except Exception:
                    pass
    return "\n".join(buf)


def resolve_role_defaults(rdirs):
    merged = {}
    for d in rdirs:
        df = os.path.join(d, "defaults", "main.yml")
        if os.path.isfile(df):
            try:
                for k, v in (load_yaml(df) or {}).items():
                    merged.setdefault(k, v)
            except Exception:
                pass
    return merged


def process(bundle):
    bdir = os.path.join(BUNDLES_ROOT, bundle)
    src = os.path.join(bdir, "bundle_parameters.src.yml")
    if not os.path.isfile(src):
        print(f"MISS {bundle} (no src.yml)")
        return 1
    main = os.path.join(bdir, "main.yml")
    out = os.path.join(bdir, "bundle_parameters.json")
    tier = bundle.split("/")[0]

    try:
        doc = load_yaml(src) or {}
    except yaml.YAMLError as e:
        print(f"FAIL {bundle} -> yaml: {e}")
        return 1

    # (1) schema
    try:
        jsonschema.validate(doc, SCHEMA)
    except jsonschema.ValidationError as e:
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        print(f"FAIL {bundle} -> schema at {loc}: {e.message}")
        return 1

    rdirs = role_dirs(main)
    # dead-param corpus also spans dynamically-included roles (include_role in tasks);
    # role-defaults resolution below still uses rdirs only, so defaults are unchanged.
    dead_dirs = list(dict.fromkeys(rdirs + included_role_dirs(bdir)))
    corpus = corpus_text(bdir, dead_dirs)   # excludes the annotation files (real bugfix vs v2)

    # (2) dead-param: each declared name must appear in the CODE / role
    dead = [p["name"] for p in (doc.get("params") or [])
            if p.get("name") and not re.search(r"\b" + re.escape(p["name"]) + r"\b", corpus)]

    # (3) resolve role-defaults
    role_defaults = resolve_role_defaults(rdirs)
    for p in (doc.get("params") or []):
        if p.get("default_where") == "role-defaults" and "default" not in p:
            key = (p.get("renamed_to") or [p.get("name")])[0]
            if key in role_defaults:
                p["default"] = role_defaults[key]
                p["default_review"] = True

    # (4) transcribe
    result = {"_generated": GEN_MSG, "tier": tier}
    result.update(doc)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"GEN  {bundle}/bundle_parameters.json")

    if dead:
        print(f"     WARN declared param(s) not found in code/role (typo/stale?): {', '.join(dead)}")
        return 1
    print("     OK  all declared params resolve")
    return 0


def in_scope_bundles():
    out = []
    for tier in TIERS:
        for main in glob.glob(f"{BUNDLES_ROOT}/{tier}/**/main.yml", recursive=True):
            out.append(os.path.relpath(os.path.dirname(main), BUNDLES_ROOT))
    return sorted(out)


def main():
    args = sys.argv[1:]
    print(f"== bundles: {BUNDLES_ROOT} ==\n")
    rc = 0

    if not args:
        for b in in_scope_bundles():
            if not os.path.isfile(os.path.join(BUNDLES_ROOT, b, "bundle_parameters.src.yml")):
                print(f"UNCOVERED {b}")
                rc = 1
        targets = [b for b in in_scope_bundles()
                   if os.path.isfile(os.path.join(BUNDLES_ROOT, b, "bundle_parameters.src.yml"))]
    else:
        targets = args

    gen = 0
    for bundle in targets:
        r = process(bundle)
        rc |= r
        if r == 0:
            gen += 1
        print()

    print(f"== done: {gen} generated (exit {rc}) ==")
    sys.exit(rc)


if __name__ == "__main__":
    main()
