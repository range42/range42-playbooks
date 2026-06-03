"""S7 TUI tests — the pure ScenarioComposerController (compose + generate).

The view (Textual) stays a thin shell; all logic lives in the controller, so it
is unit-tested headless. A single mount smoke test confirms the app composes.
"""

import asyncio

import pytest

from r42playbooks.core.errors import TopologyError
from r42playbooks.tui.controller import ScenarioComposerController


def _composed(fake_catalog) -> ScenarioComposerController:
    ctl = ScenarioComposerController(fake_catalog)
    ctl.set_name("tui_lab")
    ctl.set_subnet("default-3zone")
    ctl.set_policy("air-gap-ctf")
    ctl.add_box("admin-wazuh")
    ctl.add_box("vuln-box", count=3)
    return ctl


def test_controller_lists_catalog_choices(fake_catalog):
    ctl = ScenarioComposerController(fake_catalog)
    assert "default-3zone" in ctl.layouts()
    assert "air-gap-ctf" in ctl.policies()
    assert "admin-wazuh" in ctl.box_templates()
    assert "vuln-box" in ctl.box_templates()


def test_controller_compose_builds_spec(fake_catalog):
    ctl = _composed(fake_catalog)
    assert ctl.validate() == []
    spec = ctl.build_spec()
    assert spec.name == "tui_lab"
    assert [b.template for b in spec.boxes] == ["admin-wazuh", "vuln-box"]
    assert spec.boxes[1].count == 3


def test_controller_remove_and_clear_boxes(fake_catalog):
    ctl = _composed(fake_catalog)
    ctl.remove_box(0)
    assert [t for t, _c in ctl.boxes] == ["vuln-box"]
    ctl.clear_boxes()
    assert ctl.boxes == []


def test_controller_validate_reports_incomplete_then_bad_ref(fake_catalog):
    ctl = ScenarioComposerController(fake_catalog)
    assert ctl.validate()  # nothing composed -> non-empty problem list
    ctl.set_name("x")
    ctl.set_subnet("default-3zone")
    ctl.set_policy("air-gap-ctf")
    ctl.add_box("no-such-box")
    problems = ctl.validate()
    assert any("no-such-box" in p for p in problems)


def test_controller_preview_shows_allocation(fake_catalog):
    ctl = _composed(fake_catalog)
    preview = ctl.preview()
    assert "admin-wazuh" in preview
    assert "vuln-box-00" in preview
    assert "vuln-box-02" in preview  # count=3 expanded


def test_controller_generate_writes_deployable_tree(fake_catalog, tmp_path):
    ctl = _composed(fake_catalog)
    root = ctl.generate(tmp_path / "scenarios")
    assert root.name == "tui_lab"
    assert (root / "main.yml").is_file()
    assert (root / "manifest" / "scenario_vms.json").is_file()
    assert (root / "scenario.r42.yml").is_file()


def test_controller_generate_without_compose_raises(fake_catalog, tmp_path):
    ctl = ScenarioComposerController(fake_catalog)
    with pytest.raises(TopologyError):
        ctl.generate(tmp_path / "scenarios")


def test_controller_preview_surfaces_allocation_error_without_raising(fake_catalog, monkeypatch):
    """preview() must never crash the TUI on an allocation error — return text."""
    import r42playbooks.tui.controller as ctlmod
    from r42playbooks.core.errors import CompileError

    def _boom(*_a, **_k):
        raise CompileError("subnet exhausted")

    ctl = _composed(fake_catalog)
    monkeypatch.setattr(ctlmod, "allocate", _boom)
    out = ctl.preview()
    assert out.startswith("✗ cannot allocate")
    assert "subnet exhausted" in out


def test_app_mounts(fake_catalog):
    """The Textual app composes and mounts headlessly without error."""
    from r42playbooks.tui.app import ScenarioComposerApp

    async def _go():
        app = ScenarioComposerApp(ScenarioComposerController(fake_catalog))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#scenario") is not None
            assert app.query_one("#output") is not None

    asyncio.run(_go())
