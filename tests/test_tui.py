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


def test_controller_preview_lists_added_boxes_when_incomplete(fake_catalog):
    """Every add_box gives visible feedback even before name/subnet/policy are set."""
    ctl = ScenarioComposerController(fake_catalog)
    ctl.add_box("vuln-box", count=2)             # nothing else picked yet
    preview = ctl.preview()
    assert "vuln-box ×2" in preview              # the pick is shown
    assert "not ready" in preview                # and the readiness gap


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


def test_controller_generate_refuses_existing_then_overwrites(fake_catalog, tmp_path):
    from r42playbooks.core.errors import ScenarioExistsError
    ctl = _composed(fake_catalog)
    out = tmp_path / "scenarios"
    ctl.generate(out)
    with pytest.raises(ScenarioExistsError):
        ctl.generate(out)                       # default refuses
    root = ctl.generate(out, overwrite=True)    # explicit overwrite
    assert (root / "main.yml").is_file()


def test_app_generate_warns_on_existing_then_overwrites(fake_catalog, tmp_path):
    """Two-press overwrite: first Generate warns, second overwrites (no crash)."""
    import asyncio
    from textual.widgets import Input, Select
    from r42playbooks.tui.app import ScenarioComposerApp

    out = tmp_path / "scenarios"
    (out / "dup").mkdir(parents=True)            # pre-existing scenario dir

    async def _go():
        app = ScenarioComposerApp(ScenarioComposerController(fake_catalog), out_dir=out)
        shown: list[str] = []
        app._set_output = lambda t: shown.append(t)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#scenario", Input).value = "dup"
            app.query_one("#layout", Select).value = "default-3zone"
            app.query_one("#policy", Select).value = "air-gap-ctf"
            app.query_one("#box", Select).value = "admin-wazuh"
            await pilot.pause()
            app._do_add()
            app._do_generate()      # first: warns, arms overwrite
            assert app._pending_overwrite is True
            app._do_generate()      # second: overwrites
            assert app._pending_overwrite is False
        assert any("press Generate again to overwrite" in s for s in shown)
        assert any(s.startswith("✓ generated") for s in shown)

    asyncio.run(_go())


def test_app_handler_catch_all_shows_error_not_crash(fake_catalog, monkeypatch):
    """Any handler exception is shown in-pane, never silently killing the app."""
    import asyncio
    from r42playbooks.tui.app import ScenarioComposerApp
    from textual.widgets import Button

    async def _go():
        app = ScenarioComposerApp(ScenarioComposerController(fake_catalog))
        shown: list[str] = []
        app._set_output = lambda t: shown.append(t)
        async with app.run_test():
            def _boom():
                raise RuntimeError("kaboom")
            monkeypatch.setattr(app, "_do_preview", _boom)
            app.on_button_pressed(Button.Pressed(app.query_one("#preview", Button)))
        assert any("unexpected error" in s and "kaboom" in s for s in shown)

    asyncio.run(_go())


def test_controller_preview_surfaces_allocation_error_without_raising(fake_catalog, monkeypatch):
    """preview() must never crash the TUI on an allocation error — return text."""
    import r42playbooks.tui.controller as ctlmod
    from r42playbooks.core.errors import CompileError

    def _boom(*_a, **_k):
        raise CompileError("subnet exhausted")

    ctl = _composed(fake_catalog)
    monkeypatch.setattr(ctlmod, "allocate", _boom)
    out = ctl.preview()
    assert "✗ cannot allocate" in out
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
