"""P5 TUI tests — pure controller (sync) + a Textual mount smoke test."""

import asyncio

from r42playbooks.core.io import load_topology
from r42playbooks.tui.controller import TuiController


def test_controller_lists_catalog_choices(fake_catalog):
    ctl = TuiController(fake_catalog)
    assert "default-3zone" in ctl.layouts()
    assert "air-gap-ctf" in ctl.policies()


def test_controller_scaffold_and_validate(fake_catalog):
    ctl = TuiController(fake_catalog)
    ctl.scaffold(scenario="tui_lab", layout_id="default-3zone", policy_id="air-gap-ctf")
    assert ctl.topology is not None
    assert ctl.validate() == []
    assert "tui_lab" in ctl.summary()
    assert "DROP" in ctl.rules_text()


def test_controller_save_roundtrip(fake_catalog, tmp_path):
    ctl = TuiController(fake_catalog)
    ctl.scaffold(scenario="tui_lab", layout_id="default-3zone", policy_id="air-gap-ctf")
    out = ctl.save(tmp_path / "topology.json")
    assert load_topology(out) == ctl.topology


def test_app_mounts(fake_catalog):
    """The Textual app composes and mounts headlessly without error."""
    from r42playbooks.tui.app import TopologyAuthorApp

    async def _go():
        app = TopologyAuthorApp(TuiController(fake_catalog))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#scenario") is not None
            assert app.query_one("#output") is not None

    asyncio.run(_go())
