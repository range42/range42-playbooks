"""P4 Typer CLI tests via CliRunner — thin frontend over api.py."""

import json

from typer.testing import CliRunner

from r42topo.cli import app

runner = CliRunner()


def _write_topology(path, valid_topology_dict):
    path.write_text(json.dumps(valid_topology_dict), encoding="utf-8")
    return path


def test_validate_ok(tmp_path, valid_topology_dict, fake_catalog):
    top = _write_topology(tmp_path / "t.json", valid_topology_dict)
    res = runner.invoke(app, ["validate", str(top), "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "valid" in res.output.lower()


def test_validate_reports_problem(tmp_path, valid_topology_dict, fake_catalog):
    bad = dict(valid_topology_dict)
    bad["boxes"] = [dict(b) for b in bad["boxes"]]
    bad["boxes"][0]["ip"] = "10.9.9.9"
    top = _write_topology(tmp_path / "bad.json", bad)
    res = runner.invoke(app, ["validate", str(top), "--catalog", str(fake_catalog)])
    assert res.exit_code == 1
    assert "10.9.9.9" in res.output


def test_compile_writes_artifacts(tmp_path, valid_topology_dict, fake_catalog):
    top = _write_topology(tmp_path / "t.json", valid_topology_dict)
    ws = tmp_path / "ws"
    res = runner.invoke(app, ["compile", str(top), "--workspace", str(ws),
                              "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert (ws / "project" / "topology.json").exists()
    assert (ws / "inventory" / "hosts.yml").exists()


def test_author_scaffolds_valid_topology(tmp_path, fake_catalog):
    out = tmp_path / "scaffold.json"
    res = runner.invoke(app, ["author", "--scenario", "lab1", "--layout", "default-3zone",
                              "--policy", "air-gap-ctf", "--catalog", str(fake_catalog),
                              "-o", str(out)])
    assert res.exit_code == 0, res.output
    # the scaffold must itself validate
    res2 = runner.invoke(app, ["validate", str(out), "--catalog", str(fake_catalog)])
    assert res2.exit_code == 0, res2.output


def test_show_summary_and_rules(tmp_path, valid_topology_dict, fake_catalog):
    top = _write_topology(tmp_path / "t.json", valid_topology_dict)
    res = runner.invoke(app, ["show", str(top), "--catalog", str(fake_catalog), "--rules"])
    assert res.exit_code == 0, res.output
    assert "demo_lab_network" in res.output
    assert "DROP" in res.output  # compiled FORWARD rules shown
