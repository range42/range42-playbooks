"""Textual TUI view — thin shell over ScenarioComposerController.

Compose a lab: name it, pick a subnet layout + network policy, add boxes (with a
count), preview the allocation, and generate a deployable ``scenarios/<name>/``
tree. All logic is delegated to ScenarioComposerController (tested separately).
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from r42playbooks.core.errors import ScenarioExistsError, TopologyError
from r42playbooks.tui.controller import ScenarioComposerController

_DEFAULT_COUNT = "1"


class ScenarioComposerApp(App):
    """Interactive msfvenom-style scenario composer for r42playbooks."""

    CSS = """
    #form { height: auto; padding: 1; }
    #output { padding: 1; border: round $accent; height: 1fr; }
    Select, Input { width: 1fr; }
    """
    # Keyboard bindings so the TUI is fully operable without a mouse (terminals
    # over tmux/SSH often don't forward clicks). Function keys never collide with
    # typing in an Input or Select type-ahead. The buttons remain for mouse users.
    BINDINGS = [
        ("f1", "add", "Add box"),
        ("f2", "preview", "Preview"),
        ("f3", "generate", "Generate"),
        ("f4", "clear", "Clear boxes"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, controller: ScenarioComposerController, *, out_dir: Path | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.out_dir = out_dir or Path("scenarios")
        self._pending_overwrite = False  # set after an exists-warning; next Generate overwrites

    def _select(self, options: list[str], widget_id: str) -> Select:
        """A Select that defaults to its first option (no blank/prompt state).

        Without allow_blank=False a Select sits on Select.BLANK until the user
        opens it, which makes "Add" silently no-op on a freshly opened TUI.
        """
        opts = [(x, x) for x in options]
        if opts:
            return Select(opts, id=widget_id, allow_blank=False, value=opts[0][1])
        return Select(opts, id=widget_id)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Label("Scenario name")
            yield Input(placeholder="my_lab", id="scenario")
            yield Label("Subnet layout")
            yield self._select(self.controller.layouts(), "layout")
            yield Label("Network policy")
            yield self._select(self.controller.policies(), "policy")
            yield Label("Add box  (template, count)")
            with Horizontal():
                yield self._select(self.controller.box_templates(), "box")
                yield Input(value=_DEFAULT_COUNT, id="count")
                yield Button("Add", id="add", variant="primary")
            with Horizontal():
                yield Button("Preview", id="preview")
                yield Button("Generate", id="generate", variant="success")
                yield Button("Clear boxes", id="clear", variant="warning")
        yield Static(
            "Tab to move between fields. Mouse or keys: F1 Add · F2 Preview · "
            "F3 Generate · F4 Clear · q Quit.",
            id="output",
        )
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

    def _safe(self, handler) -> None:
        """Run an action handler, surfacing any error in-pane (never crash)."""
        try:
            handler()
        except Exception as exc:  # never let a handler silently kill the app
            self._set_output(f"✗ unexpected error: {exc!r}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "add": self._do_add,
            "preview": self._do_preview,
            "generate": self._do_generate,
            "clear": self._do_clear,
        }
        handler = handlers.get(event.button.id)
        if handler is not None:
            self._safe(handler)

    # keyboard bindings (work without a mouse) -> same handlers as the buttons
    def action_add(self) -> None:
        self._safe(self._do_add)

    def action_preview(self) -> None:
        self._safe(self._do_preview)

    def action_generate(self) -> None:
        self._safe(self._do_generate)

    def action_clear(self) -> None:
        self._safe(self._do_clear)

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
            root = self.controller.generate(self.out_dir, overwrite=self._pending_overwrite)
        except ScenarioExistsError as exc:
            self._pending_overwrite = True
            self._set_output(f"⚠ {exc}\n  press Generate again to overwrite it.")
            return
        except TopologyError as exc:
            self._set_output(f"✗ {exc}")
            return
        self._pending_overwrite = False
        self._set_output(f"✓ generated {root}")


def main() -> None:  # pragma: no cover - manual entry point
    import sys
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../range42-catalog")
    ScenarioComposerApp(ScenarioComposerController(catalog)).run()


if __name__ == "__main__":  # pragma: no cover
    main()
