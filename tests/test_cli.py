"""S6 Typer CLI tests via CliRunner — the generator frontend.

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


def test_list_images_shows_base_images(fake_catalog):
    res = runner.invoke(app, ["list", "images", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "ubuntu_noble" in res.output and "debian_trixie" in res.output
    assert "template(s)" in res.output


def test_list_bad_catalog_exits_nonzero(tmp_path):
    res = runner.invoke(app, ["list", "boxes", "--catalog", str(tmp_path / "nope")])
    assert res.exit_code != 0


def test_list_scenarios_shows_generated(tmp_path, fake_catalog):
    out = tmp_path / "scenarios"
    gen = runner.invoke(
        app,
        [
            "new",
            "scen_a",
            "--subnet",
            "default-3zone",
            "--policy",
            "air-gap-ctf",
            "--box",
            "admin-wazuh:subnet=admin",
            "--catalog",
            str(fake_catalog),
            "-o",
            str(out),
        ],
    )
    assert gen.exit_code == 0, gen.output
    res = runner.invoke(app, ["list", "scenarios", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert "scen_a" in res.output
    assert "default-3zone" in res.output  # subnet layout shown in summary
    assert "admin-wazuh" in res.output  # box template shown in summary


# --- show ------------------------------------------------------------------


def test_show_box_template_details(fake_catalog):
    res = runner.invoke(app, ["show", "vuln-box", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "template-vm-ubuntu-noble-small-01-4g-32g" in res.output  # template_vm
    assert "ubuntu_noble" in res.output  # resolved image
    assert "9221" in res.output  # resolved vm_id
    assert "1cpu/4gb/32gb" in res.output  # resolved spec
    assert "CTF vulnerable target" in res.output  # description


def test_show_subnet_layout_details(fake_catalog):
    res = runner.invoke(app, ["show", "default-3zone", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "admin" in res.output and "192.168.142.0/24" in res.output  # lab zones
    assert "vmbr140" in res.output  # template_subnet bridge


def test_show_image_details(fake_catalog):
    res = runner.invoke(app, ["show", "ubuntu_noble", "--catalog", str(fake_catalog)])
    assert res.exit_code == 0, res.output
    assert "ubuntu/noble" in res.output
    assert "noble-minimal-cloudimg" in res.output  # cloud_image filename
    assert "9221" in res.output  # one of the template vm_ids
    assert "proxmox_templates" in res.output


def test_show_unknown_module_exits_nonzero(fake_catalog):
    res = runner.invoke(app, ["show", "does-not-exist", "--catalog", str(fake_catalog)])
    assert res.exit_code != 0


# --- new -------------------------------------------------------------------


def test_new_from_flags_writes_deployable_tree(tmp_path, fake_catalog):
    out = tmp_path / "scenarios"
    res = runner.invoke(
        app,
        [
            "new",
            "cli_lab",
            "--subnet",
            "default-3zone",
            "--policy",
            "air-gap-ctf",
            "--box",
            "admin-wazuh:subnet=admin",
            "--box",
            "vuln-box:subnet=ctf,count=3",
            "--catalog",
            str(fake_catalog),
            "-o",
            str(out),
        ],
    )
    assert res.exit_code == 0, res.output
    assert (
        "templates" in res.output and "boxes" in res.output
    )  # manifest summary printed
    root = out / "cli_lab"
    assert (root / "main.yml").is_file()
    assert (root / "manifest" / "scenario_vms.json").is_file()
    assert (root / "scenario.r42.yml").is_file()
    # count=3 expanded
    assert (root / "04_ctf_infrastructure" / "stage_00" / "ctf-vuln-box-02.yml").is_file()
    assert str(root) in res.output


def test_new_existing_dir_warns_then_force_overwrites(tmp_path, fake_catalog):
    out = tmp_path / "scenarios"
    args = [
        "new",
        "dup_lab",
        "--subnet",
        "default-3zone",
        "--policy",
        "air-gap-ctf",
        "--box",
        "admin-wazuh:subnet=admin",
        "--catalog",
        str(fake_catalog),
        "-o",
        str(out),
    ]
    assert runner.invoke(app, args).exit_code == 0
    again = runner.invoke(app, args)  # second run: refuse + hint
    assert again.exit_code != 0
    assert "already exists" in again.output and "--force" in again.output
    forced = runner.invoke(app, args + ["--force"])  # --force: overwrite
    assert forced.exit_code == 0, forced.output


def test_new_bad_box_ref_exits_nonzero(tmp_path, fake_catalog):
    out = tmp_path / "scenarios"
    res = runner.invoke(
        app,
        [
            "new",
            "bad_lab",
            "--subnet",
            "default-3zone",
            "--policy",
            "air-gap-ctf",
            "--box",
            "no-such-box:subnet=admin",
            "--catalog",
            str(fake_catalog),
            "-o",
            str(out),
        ],
    )
    assert res.exit_code != 0
    assert not (out / "bad_lab").exists()


def test_new_from_spec_file_roundtrips(tmp_path, fake_catalog, valid_spec_dict):
    import yaml

    spec_path = tmp_path / "compose.r42.yml"
    spec_path.write_text(yaml.safe_dump(valid_spec_dict), encoding="utf-8")
    out = tmp_path / "scenarios"
    res = runner.invoke(
        app,
        [
            "new",
            "from_spec",
            "--spec",
            str(spec_path),
            "--catalog",
            str(fake_catalog),
            "-o",
            str(out),
        ],
    )
    assert res.exit_code == 0, res.output
    # positional name overrides the spec's own name
    assert (out / "from_spec" / "main.yml").is_file()


def test_new_generated_tree_revalidates(tmp_path, fake_catalog):
    """A generated scenario.r42.yml re-loads + re-renders cleanly (no drift)."""
    out = tmp_path / "scenarios"
    res = runner.invoke(
        app,
        [
            "new",
            "round_lab",
            "--subnet",
            "default-3zone",
            "--policy",
            "air-gap-ctf",
            "--box",
            "admin-wazuh:subnet=admin",
            "--catalog",
            str(fake_catalog),
            "-o",
            str(out),
        ],
    )
    assert res.exit_code == 0, res.output
    regen = runner.invoke(
        app,
        [
            "new",
            "round_lab2",
            "--spec",
            str(out / "round_lab" / "scenario.r42.yml"),
            "--catalog",
            str(fake_catalog),
            "-o",
            str(out),
        ],
    )
    assert regen.exit_code == 0, regen.output


# --- validate ------------------------------------------------------------------


def test_validate_valid_spec_exits_zero(tmp_path, fake_catalog, valid_spec_dict):
    import yaml

    spec_path = tmp_path / "scenario.r42.yml"
    spec_path.write_text(yaml.safe_dump(valid_spec_dict), encoding="utf-8")
    res = runner.invoke(
        app, ["validate", str(spec_path), "--catalog", str(fake_catalog)]
    )
    assert res.exit_code == 0, res.output
    assert "valid" in res.output


def test_validate_generated_scenario_r42_yml(tmp_path, fake_catalog):
    """The scenario.r42.yml written by `new` should pass `validate` cleanly."""
    out = tmp_path / "scenarios"
    runner.invoke(
        app,
        [
            "new",
            "val_lab",
            "--subnet",
            "default-3zone",
            "--box",
            "admin-wazuh:subnet=admin",
            "--catalog",
            str(fake_catalog),
            "-o",
            str(out),
        ],
    )
    spec_path = out / "val_lab" / "scenario.r42.yml"
    res = runner.invoke(
        app, ["validate", str(spec_path), "--catalog", str(fake_catalog)]
    )
    assert res.exit_code == 0, res.output


def test_validate_bad_spec_exits_nonzero(tmp_path, fake_catalog):
    import yaml

    bad = {
        "schema_version": 1,
        "name": "bad",
        "subnet_layout": "no-such-layout",
        "boxes": [{"template": "vuln-box", "subnet": "ctf"}],
    }
    spec_path = tmp_path / "bad.r42.yml"
    spec_path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    res = runner.invoke(
        app, ["validate", str(spec_path), "--catalog", str(fake_catalog)]
    )
    assert res.exit_code != 0
    assert "no-such-layout" in res.output


def test_new_autodetects_reserved_json(tmp_path, fake_catalog):
    """When _reserved.json exists in the output dir, `new` uses it without --reserved."""
    import json

    out = tmp_path / "scenarios"
    out.mkdir()
    entry = {
        "vm_id": 1010, "ip": "192.168.144.10", "vm_name": "vuln-box-00",
        "subnet": "ctf", "bridge": "vmbr144", "scenario": "other_lab",
    }
    (out / "_reserved.json").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    res = runner.invoke(app, [
        "new", "my_lab", "--subnet", "default-3zone", "--box", "vuln-box:subnet=ctf",
        "--catalog", str(fake_catalog), "-o", str(out),
    ])
    assert res.exit_code == 0, res.output
    manifest = json.loads((out / "my_lab" / "manifest" / "scenario_vms.json").read_text())
    vm_ids = {v["vm_id"] for v in manifest["vms"]}
    assert 1010 not in vm_ids, "blocked vm_id 1010 was allocated despite _reserved.json"
    assert 1011 in vm_ids
