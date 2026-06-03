"""Canonical Typer CLI (r42topo.cli) — thin frontend over the engine."""
import json
from pathlib import Path

from typer.testing import CliRunner

from r42topo.cli import app

runner = CliRunner()
VECTORS = Path(__file__).parent / "vectors" / "test-vectors" / "topology"


def _write_topo(tmp_path: Path, name: str) -> Path:
    doc = json.loads((VECTORS / f"{name}.json").read_text(encoding="utf-8"))
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_validate_ok(tmp_path):
    res = runner.invoke(app, ["validate", str(_write_topo(tmp_path, "01-minimal"))])
    assert res.exit_code == 0, res.output
    assert "valid" in res.output


def test_validate_rejects_bad_doc(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"kind": "nope", "name": 1}), encoding="utf-8")
    res = runner.invoke(app, ["validate", str(bad)])
    assert res.exit_code == 1


def test_compose_prints_hash(tmp_path):
    base = _write_topo(tmp_path, "01-minimal")
    res = runner.invoke(app, ["compose", str(base)])
    assert res.exit_code == 0, res.output
    assert "effective_doc_hash: sha256:" in res.output


def test_expand_writes_output(tmp_path):
    src = _write_topo(tmp_path, "02-multi-team")
    out = tmp_path / "expanded.json"
    res = runner.invoke(app, ["expand", str(src), "--teams", "3", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert out.exists()
    json.loads(out.read_text())  # valid JSON


def test_inventory_writes_hosts(tmp_path):
    src = _write_topo(tmp_path, "02-multi-team")
    out = tmp_path / "hosts.yml"
    res = runner.invoke(app, [
        "inventory", str(src), "--teams", "2",
        "--codename", "MT", "--proxmox", "10.0.0.1",
        "--ssh-keys", str(tmp_path / "keys"), "-o", str(out),
    ])
    assert res.exit_code == 0, res.output
    assert out.exists()


def test_preflight_pass(tmp_path):
    # safe-range template_vmid (see test_api note on the template_vmid base quirk)
    safe = tmp_path / "safe.json"
    safe.write_text(json.dumps({
        "schema_version": "1.0", "kind": "gamenet", "name": "x", "naming_prefix": "x",
        "nodes": [
            {"id": "adm", "kind": "vm", "role": "admin",
             "replication": {"scope": "shared"}, "template_vmid": 5000},
        ],
    }), encoding="utf-8")
    res = runner.invoke(app, ["preflight", str(safe), "--teams", "2"])
    assert res.exit_code == 0, res.output
    assert "result: pass" in res.output


def test_preflight_block_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "schema_version": "1.0", "kind": "gamenet", "name": "x", "naming_prefix": "x",
        "nodes": [{"id": "n", "kind": "vm", "replication": {"scope": "shared"}}],  # no role
    }), encoding="utf-8")
    res = runner.invoke(app, ["preflight", str(bad), "--teams", "1"])
    assert res.exit_code == 1


def test_scaffold_emits_valid_document(tmp_path):
    out = tmp_path / "scaffold.json"
    res = runner.invoke(app, ["scaffold", "--name", "My Lab", "-o", str(out)])
    assert res.exit_code == 0, res.output
    # the emitted doc must itself validate
    val = runner.invoke(app, ["validate", str(out)])
    assert val.exit_code == 0, val.output


def test_scaffold_output_passes_the_full_flow(tmp_path):
    """The scaffold skeleton must be green end-to-end: validate, expand
    (multiplies the per-team node), and preflight all pass out of the box."""
    out = tmp_path / "scaffold.json"
    runner.invoke(app, ["scaffold", "--name", "My Lab", "-o", str(out)])

    # expand must actually produce per-team copies (regression: a shared-only
    # skeleton made expand look like a no-op)
    expanded = tmp_path / "expanded.json"
    runner.invoke(app, ["expand", str(out), "--teams", "3", "-o", str(expanded)])
    ids = [n["id"] for n in json.loads(expanded.read_text())["nodes"]]
    assert "trainee__team_1" in ids and "trainee__team_3" in ids

    # preflight must pass (template_vmid kept out of the protected 9000-9999 band)
    pf = runner.invoke(app, ["preflight", str(out), "--teams", "3"])
    assert pf.exit_code == 0, pf.output
    assert "result: pass" in pf.output


def test_show_lists_nodes(tmp_path):
    src = _write_topo(tmp_path, "02-multi-team")
    res = runner.invoke(app, ["show", str(src)])
    assert res.exit_code == 0, res.output
    assert "nodes: 3" in res.output
