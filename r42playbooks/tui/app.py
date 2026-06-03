"""Textual TUI view — thin shell over ScenarioComposerController.

Compose a lab: name it, pick a subnet layout + network policy, add boxes (with a
count), preview the allocation, and generate a deployable ``scenarios/<name>/``
tree. All logic is delegated to ScenarioComposerController (tested separately).
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from r42playbooks.core.errors import TopologyError
from r42playbooks.tui.controller import ScenarioComposerController

_DEFAULT_COUNT = "1"


class ScenarioComposerApp(App):
    """Interactive msfvenom-style scenario composer for r42playbooks."""

    CSS = """
    #form { height: auto; padding: 1; }
    #output { padding: 1; border: round $accent; height: 1fr; }
    Select, Input { width: 1fr; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, controller: ScenarioComposerController, *, out_dir: Path | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.out_dir = out_dir or Path("scenarios")

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Label("Scenario name")
            yield Input(placeholder="my_lab", id="scenario")
            yield Label("Subnet layout")
            yield Select([(x, x) for x in self.controller.layouts()], id="layout")
            yield Label("Network policy")
            yield Select([(x, x) for x in self.controller.policies()], id="policy")
            yield Label("Add box")
            with Horizontal():
                yield Select([(x, x) for x in self.controller.box_templates()], id="box")
                yield Input(value=_DEFAULT_COUNT, id="count")
                yield Button("Add", id="add", variant="primary")
            with Horizontal():
                yield Button("Preview", id="preview")
                yield Button("Generate", id="generate", variant="success")
                yield Button("Clear boxes", id="clear", variant="warning")
        yield Static("(compose a scenario to begin)", id="output")
        yield Footer()

    # -- helpers --

    def _set_output(self, text: str) -> None:
        self.query_one("#output", Static).update(text)

    def _selected(self, widget_id: str) -> str | None:
        value = self.query_one(f"#{widget_id}", Select).value
        return None if value is Select.BLANK else str(value)

    def _sync_header_fields(self) -> None:
        """Push the name/layout/policy widgets into the controller."""
        self.controller.set_name(self.query_one("#scenario", Input).value)
        if (layout := self._selected("layout")) is not None:
            self.controller.set_subnet(layout)
        if (policy := self._selected("policy")) is not None:
            self.controller.set_policy(policy)

    # -- events --

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "add": self._do_add,
            "preview": self._do_preview,
            "generate": self._do_generate,
            "clear": self._do_clear,
        }
        handler = handlers.get(event.button.id)
        if handler:
            handler()

    def _do_add(self) -> None:
        template = self._selected("box")
        if template is None:
            self._set_output("⚠ pick a box template first")
            return
        try:
            count = int(self.query_one("#count", Input).value or _DEFAULT_COUNT)
        except ValueError:
            self._set_output("⚠ count must be an integer")
            return
        self.controller.add_box(template, count)
        self._do_preview()

    def _do_clear(self) -> None:
        self.controller.clear_boxes()
        self._do_preview()

    def _do_preview(self) -> None:
        self._sync_header_fields()
        self._set_output(self.controller.preview())

    def _do_generate(self) -> None:
        self._sync_header_fields()
        try:
            root = self.controller.generate(self.out_dir)
        except TopologyError as exc:
            self._set_output(f"✗ {exc}")
            return
        self._set_output(f"✓ generated {root}")


def main() -> None:  # pragma: no cover - manual entry point
    import sys
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../range42-catalog")
    ScenarioComposerApp(ScenarioComposerController(catalog)).run()


if __name__ == "__main__":  # pragma: no cover
    main()
