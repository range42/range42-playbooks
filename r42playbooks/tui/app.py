"""Textual TUI view — thin shell over ScenarioComposerController.

Compose a lab: name it, pick a subnet layout + network policy, add boxes (with a
count), preview the allocation, and generate a deployable ``scenarios/<name>/``
tree. All logic is delegated to ScenarioComposerController (tested separately).

Operated the standard way — **mouse or keyboard**: click a button, or Tab between
fields and press Enter/Space on the focused button; type in the inputs; use the
arrow keys to open and choose in the dropdowns. No custom key shortcuts.
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from r42playbooks.core.errors import ScenarioExistsError, TopologyError
from r42playbooks.tui.controller import ScenarioComposerController

_DEFAULT_COUNT = "1"


class ScenarioComposerApp(App):
    """Interactive scenario composer for r42playbooks."""

    CSS = """
    #body   { height: 1fr; }
    #form   { width: 60; height: 1fr; padding: 1; }
    #form Button { height: 1; min-height: 1; border: none; margin: 0; width: 100%; }
    #output { width: 1fr; height: 1fr; padding: 1; border: round $accent; }
    Select, Input { width: 1fr; }
    .row { height: auto; }
    #count  { width: 8; }
    #octet  { width: 10; }
    """

    def __init__(
        self, controller: ScenarioComposerController, *, out_dir: Path | None = None
    ) -> None:
        super().__init__()
        self.controller = controller
        self.out_dir = out_dir or Path("scenarios")
        self._pending_overwrite = (
            False  # set after an exists-warning; next Generate overwrites
        )

    def _select(self, options: list[str], widget_id: str) -> Select:
        """A Select that defaults to its first option (no blank/prompt state)."""
        opts = [(x, x) for x in options]
        if opts:
            return Select(opts, id=widget_id, allow_blank=False, value=opts[0][1])
        return Select(opts, id=widget_id)

    def _policy_select(self) -> Select:
        """Build the policy Select (optional — first option is blank/none)."""
        opts = [("(none — no isolation)", "")] + [
            (p, p) for p in self.controller.policies()
        ]
        return Select(opts, id="policy", allow_blank=False, value="")

    def _subnet_select(self) -> Select:
        """Build the subnet Select populated from the current layout selection."""
        layout = self._current_layout_id()
        subnets = self.controller.subnets_for_layout(layout) if layout else []
        opts = [(f"{name}  {cidr}", name) for name, cidr in subnets]
        if opts:
            return Select(opts, id="subnet", allow_blank=False, value=opts[0][1])
        return Select(opts, id="subnet", allow_blank=True)

    def _current_layout_id(self) -> str | None:
        try:
            value = self.query_one("#layout", Select).value
            return None if value is Select.BLANK else str(value)
        except Exception:
            return None

    def _refresh_subnet_options(self) -> None:
        """Repopulate #subnet when the chosen layout changes."""
        layout = self._current_layout_id()
        subnets = self.controller.subnets_for_layout(layout) if layout else []
        opts = [(f"{name}  {cidr}", name) for name, cidr in subnets]
        sel = self.query_one("#subnet", Select)
        sel.set_options(opts)
        if opts:
            sel.value = opts[0][1]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with VerticalScroll(id="form"):
                yield Label("Scenario name")
                yield Input(placeholder="my_lab", id="scenario")
                yield Label("Subnet layout")
                yield self._select(self.controller.layouts(), "layout")
                yield Label("Network policy (optional)")
                yield self._policy_select()
                yield Label("Box  (template · count · start octet · subnet)")
                with Horizontal(classes="row"):
                    yield self._select(self.controller.box_templates(), "box")
                    yield Input(value=_DEFAULT_COUNT, id="count")
                    yield Input(placeholder="octet", id="octet")
                yield self._subnet_select()
                yield Button("Add box", id="add", variant="primary")
                yield Button("Preview", id="preview")
                yield Button("Generate", id="generate", variant="success")
                yield Button("Clear boxes", id="clear", variant="warning")
                yield Button("Quit", id="quit", variant="error")
            yield Static(
                "Click a button, or Tab between fields and press Enter on a button.",
                id="output",
            )
        yield Footer()

    def on_mount(self) -> None:
        # Focus the name field so typing works immediately.
        self.query_one("#scenario", Input).focus()
        # Populate subnet options from the initial layout selection.
        self._refresh_subnet_options()

    # -- helpers --

    def _set_output(self, text: str) -> None:
        self.query_one("#output", Static).update(text)

    def _selected(self, widget_id: str) -> str | None:
        value = self.query_one(f"#{widget_id}", Select).value
        return None if value is Select.BLANK else str(value)

    def _count(self) -> int:
        try:
            return max(1, int(self.query_one("#count", Input).value or _DEFAULT_COUNT))
        except ValueError:
            return 1

    def _octet(self) -> int | None:
        raw = self.query_one("#octet", Input).value.strip()
        try:
            v = int(raw)
            return v if 1 <= v <= 254 else None
        except ValueError:
            return None

    def _sync_header_fields(self) -> None:
        """Push the name/layout/policy widgets into the controller."""
        self.controller.set_name(self.query_one("#scenario", Input).value)
        if (layout := self._selected("layout")) is not None:
            self.controller.set_subnet(layout)
        policy = self._selected("policy")
        self.controller.set_policy(policy or "")

    # -- events --

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "layout":
            self._refresh_subnet_options()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle every button — fired by a mouse click or Enter/Space when focused."""
        handlers = {
            "add": self._do_add,
            "preview": self._do_preview,
            "generate": self._do_generate,
            "clear": self._do_clear,
            "quit": self.exit,
        }
        handler = handlers.get(event.button.id)
        if handler is None:
            return
        try:
            handler()
        except Exception as exc:  # never let a handler silently kill the app
            self._set_output(f"✗ unexpected error: {exc!r}")

    def _do_add(self) -> None:
        template = self._selected("box")
        if template is None:
            self._set_output("⚠ pick a box template first")
            return
        subnet = self._selected("subnet")
        octet = self._octet()
        self.controller.add_box(template, self._count(), subnet, octet)
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
            root = self.controller.generate(
                self.out_dir, overwrite=self._pending_overwrite
            )
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
