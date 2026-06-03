"""S6 Typer CLI tests via CliRunner — the msfvenom-style generator frontend.

The CLI is a thin shell over the frozen ``r42playbooks.api``: ``list`` enumerates
pickable catalog modules, ``show`` describes one, and ``new`` composes a
``ScenarioSpec`` (from flags or ``--spec``) and renders a deployable
``scenarios/<name>/`` tree. All business logic lives in the core; the CLI only
parses args, prints, and maps errors to exit codes.
"""

from typer.testing import CliRunner

from r42playbooks.cli import app

runner = CliRunner()


# --- list ------------------------------------------------------------------

def test_list_boxes_shows_catalog_box_templates(fake_catalog):
    res = runner.invoke(app, ["list", "boxes", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "admin-wazuh" in res.output
    assert "vuln-box" in res.output


def test_list_roles_shows_named_roles(fake_catalog):
    res = runner.invoke(app, ["list", "roles", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "software.install.wazuh-agent" in res.output


def test_list_containers_shows_ctf_stacks(fake_catalog):
    res = runner.invoke(app, ["list", "containers", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "cve/web/dvwa" in res.output


def test_list_subnets_and_policies(fake_catalog):
    res = runner.invoke(app, ["list", "subnets", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0 and "default-3zone" in res.output
    res = runner.invoke(app, ["list", "policies", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0 and "air-gap-ctf" in res.output


def test_list_bad_catalog_exits_nonzero(tmp_path):
    res = runner.invoke(app, ["list", "boxes", "--catalog", str(tmp_path / "nope")])
    assert res.exit_code != 0


def test_list_scenarios_shows_generated(tmp_path, fake_catalog):
    out = tmp_path / "scenarios"
    gen = runner.invoke(app, [
        "new", "scen_a", "--subnet", "default-3zone", "--policy", "air-gap-ctf",
        "--box", "admin-wazuh", "--catalog", str(fake_catalog), "-o", str(out),
    ])
    assert gen.exit_code == 0, gen.output
    res = runner.invoke(app, ["list", "scenarios", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert "scen_a" in res.output


# --- show ------------------------------------------------------------------

def test_show_box_template_details(fake_catalog):
    res = runner.invoke(app, ["show", "vuln-box", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "ctf" in res.output            # role
    assert "1cpu/4gb/32gb" in res.output  # spec


def test_show_unknown_module_exits_nonzero(fake_catalog):
    res = runner.invoke(app, ["show", "does-not-exist", "--catalog", str(fake_catalog)])
    assert res.exit_code != 0


# --- new -------------------------------------------------------------------

def test_new_from_flags_writes_deployable_tree(tmp_path, fake_catalog):
    out = tmp_path / "scenarios"
    res = runner.invoke(app, [
        "new", "cli_lab",
        "--subnet", "default-3zone", "--policy", "air-gap-ctf",
        "--box", "admin-wazuh", "--box", "vuln-box:count=3",
        "--catalog", str(fake_catalog), "-o", str(out),
    ])
    assert res.exit_code == 0, res.output
    root = out / "cli_lab"
    assert (root / "main.yml").is_file()
    assert (root / "manifest" / "scenario_vms.json").is_file()
    assert (root / "scenario.r42.yml").is_file()
    # count=3 expanded
    assert (root / "04_ctf_infrastructure" / "stage_00" / "vuln-box-02.yml").is_file()
    assert str(root) in res.output


def test_new_bad_box_ref_exits_nonzero(tmp_path, fake_catalog):
    out = tmp_path / "scenarios"
    res = runner.invoke(app, [
        "new", "bad_lab",
        "--subnet", "default-3zone", "--policy", "air-gap-ctf",
        "--box", "no-such-box",
        "--catalog", str(fake_catalog), "-o", str(out),
    ])
    assert res.exit_code != 0
    assert not (out / "bad_lab").exists()


def test_new_from_spec_file_roundtrips(tmp_path, fake_catalog, valid_spec_dict):
    import yaml
    spec_path = tmp_path / "compose.r42.yml"
    spec_path.write_text(yaml.safe_dump(valid_spec_dict), encoding="utf-8")
    out = tmp_path / "scenarios"
    res = runner.invoke(app, [
        "new", "from_spec",
        "--spec", str(spec_path),
        "--catalog", str(fake_catalog), "-o", str(out),
    ])
    assert res.exit_code == 0, res.output
    # positional name overrides the spec's own name
    assert (out / "from_spec" / "main.yml").is_file()


def test_new_generated_tree_revalidates(tmp_path, fake_catalog):
    """A generated scenario.r42.yml re-loads + re-renders cleanly (no drift)."""
    out = tmp_path / "scenarios"
    res = runner.invoke(app, [
        "new", "round_lab",
        "--subnet", "default-3zone", "--policy", "air-gap-ctf",
        "--box", "admin-wazuh",
        "--catalog", str(fake_catalog), "-o", str(out),
    ])
    assert res.exit_code == 0, res.output
    regen = runner.invoke(app, [
        "new", "round_lab2",
        "--spec", str(out / "round_lab" / "scenario.r42.yml"),
        "--catalog", str(fake_catalog), "-o", str(out),
    ])
    assert regen.exit_code == 0, regen.output
