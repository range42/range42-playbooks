"""Textual TUI view — thin shell over TuiController.

Pick a scenario name, subnet layout, and network policy; scaffold a starter
topology; see its summary, validation result, and compiled FORWARD rules; save
it to disk. All logic is delegated to TuiController (tested separately).
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from r42topo.tui.controller import TuiController


class TopologyAuthorApp(App):
    """Interactive authoring app for r42topo topologies."""

    CSS = """
    #form { height: auto; padding: 1; }
    #output { padding: 1; border: round $accent; height: 1fr; }
    Select, Input { width: 1fr; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, controller: TuiController, *, out_path: Path | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.out_path = out_path or Path("topology.json")

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Label("Scenario name")
            yield Input(placeholder="my_lab", id="scenario")
            yield Label("Subnet layout")
            yield Select([(x, x) for x in self.controller.layouts()], id="layout")
            yield Label("Network policy")
            yield Select([(x, x) for x in self.controller.policies()], id="policy")
            with Horizontal():
                yield Button("Scaffold", id="scaffold", variant="primary")
                yield Button("Save", id="save", variant="success")
        yield Static("(author a topology to begin)", id="output")
        yield Footer()

    def _set_output(self, text: str) -> None:
        self.query_one("#output", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scaffold":
            self._do_scaffold()
        elif event.button.id == "save":
            self._do_save()

    def _selected(self, widget_id: str) -> str | None:
        value = self.query_one(f"#{widget_id}", Select).value
        return None if value is Select.BLANK else str(value)

    def _do_scaffold(self) -> None:
        scenario = self.query_one("#scenario", Input).value.strip()
        layout = self._selected("layout")
        policy = self._selected("policy")
        if not (scenario and layout and policy):
            self._set_output("⚠ fill scenario, layout, and policy first")
            return
        try:
            self.controller.scaffold(scenario=scenario, layout_id=layout, policy_id=policy)
        except Exception as exc:  # surface authoring errors in the view
            self._set_output(f"✗ {exc}")
            return
        problems = self.controller.validate()
        verdict = "✓ valid" if not problems else "✗ " + "; ".join(problems)
        self._set_output(
            f"{self.controller.summary()}\n\n{verdict}\n\n{self.controller.rules_text()}"
        )

    def _do_save(self) -> None:
        try:
            path = self.controller.save(self.out_path)
        except Exception as exc:
            self._set_output(f"✗ {exc}")
            return
        self._set_output(f"✓ saved {path}")


def main() -> None:  # pragma: no cover - manual entry point
    import sys
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../range42-catalog")
    TopologyAuthorApp(TuiController(catalog)).run()


if __name__ == "__main__":  # pragma: no cover
    main()
