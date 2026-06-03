"""Textual TUI view — thin shell over ScenarioComposerController.

Compose a lab: name it, pick a subnet layout + network policy, add boxes (with a
count), preview the allocation, and generate a deployable ``scenarios/<name>/``
tree. All logic is delegated to ScenarioComposerController (tested separately).

Designed to be **fully keyboard-operable**: many terminals (tmux/SSH, no mouse
reporting) don't forward clicks, and function keys are unreliable. Every action
is a Ctrl-binding chosen to NOT collide with Textual's ``Input`` key bindings, so
the shortcuts fire even while the name field is focused — no mouse or Tab needed.
The clickable buttons remain for mouse users.
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
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
    BINDINGS = [
        Binding("ctrl+n", "add", "Add box"),
        Binding("ctrl+b", "cycle_box", "Box"),
        Binding("ctrl+up", "count_up", "Count+", show=False),
        Binding("ctrl+down", "count_down", "Count-", show=False),
        Binding("ctrl+l", "cycle_layout", "Layout"),
        Binding("ctrl+o", "cycle_policy", "Policy"),
        Binding("ctrl+r", "preview", "Preview"),
        Binding("ctrl+g", "generate", "Generate"),
        Binding("ctrl+t", "clear", "Clear"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, controller: ScenarioComposerController, *, out_dir: Path | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.out_dir = out_dir or Path("scenarios")
        self._pending_overwrite = False  # set after an exists-warning; next Generate overwrites

    def _select(self, options: list[str], widget_id: str) -> Select:
        """A Select that defaults to its first option (no blank/prompt state)."""
        opts = [(x, x) for x in options]
        if opts:
            return Select(opts, id=widget_id, allow_blank=False, value=opts[0][1])
        return Select(opts, id=widget_id)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Label("Scenario name")
            yield Input(placeholder="my_lab", id="scenario")
            yield Label("Subnet layout  (Ctrl+L cycles)")
            yield self._select(self.controller.layouts(), "layout")
            yield Label("Network policy  (Ctrl+O cycles)")
            yield self._select(self.controller.policies(), "policy")
            yield Label("Box  (Ctrl+B cycles · Ctrl+↑/↓ count · Ctrl+N add)")
            with Horizontal():
                yield self._select(self.controller.box_templates(), "box")
                yield Input(value=_DEFAULT_COUNT, id="count")
                yield Button("Add", id="add", variant="primary")
            with Horizontal():
                yield Button("Preview", id="preview")
                yield Button("Generate", id="generate", variant="success")
                yield Button("Clear boxes", id="clear", variant="warning")
        yield Static(
            "Type a name, then (mouse or keyboard):\n"
            "  Ctrl+B pick box · Ctrl+↑/↓ count · Ctrl+N add · Ctrl+L layout · "
            "Ctrl+O policy · Ctrl+R preview · Ctrl+G generate · Ctrl+T clear · q quit",
            id="output",
        )
        yield Footer()

    def on_mount(self) -> None:
        # Auto-focus the name field so typing + Ctrl shortcuts work immediately.
        self.query_one("#scenario", Input).focus()

    # -- display helpers --

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

    def _sync_header_fields(self) -> None:
        """Push the name/layout/policy widgets into the controller."""
        self.controller.set_name(self.query_one("#scenario", Input).value)
        if (layout := self._selected("layout")) is not None:
            self.controller.set_subnet(layout)
        if (policy := self._selected("policy")) is not None:
            self.controller.set_policy(policy)

    def _render_status(self, note: str = "") -> None:
        """Show an optional note + the pending box/count + the live composition."""
        self._sync_header_fields()
        head = [note] if note else []
        head.append(f"next add → box={self._selected('box') or '(none)'}  count={self._count()}")
        self._set_output("\n".join(head) + "\n\n" + self.controller.preview())

    def _cycle(self, widget_id: str, options: list[str]) -> str | None:
        """Advance a Select to its next option (keyboard-only dropdown control)."""
        if not options:
            return None
        sel = self.query_one(f"#{widget_id}", Select)
        cur = None if sel.value is Select.BLANK else str(sel.value)
        idx = options.index(cur) if cur in options else -1
        nxt = options[(idx + 1) % len(options)]
        sel.value = nxt
        return nxt

    # -- dispatch (button + keyboard both route through _safe) --

    def _safe(self, handler) -> None:
        """Run a handler, surfacing any error in-pane (never crash the app)."""
        try:
            handler()
        except Exception as exc:
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

    def action_add(self) -> None:
        self._safe(self._do_add)

    def action_preview(self) -> None:
        self._safe(self._do_preview)

    def action_generate(self) -> None:
        self._safe(self._do_generate)

    def action_clear(self) -> None:
        self._safe(self._do_clear)

    def action_cycle_box(self) -> None:
        self._safe(lambda: self._render_status(f"box → {self._cycle('box', self.controller.box_templates())}"))

    def action_cycle_layout(self) -> None:
        self._safe(lambda: self._render_status(f"layout → {self._cycle('layout', self.controller.layouts())}"))

    def action_cycle_policy(self) -> None:
        self._safe(lambda: self._render_status(f"policy → {self._cycle('policy', self.controller.policies())}"))

    def action_count_up(self) -> None:
        self._safe(lambda: self._set_count(self._count() + 1))

    def action_count_down(self) -> None:
        self._safe(lambda: self._set_count(self._count() - 1))

    def _set_count(self, n: int) -> None:
        n = max(1, n)
        self.query_one("#count", Input).value = str(n)
        self._render_status(f"count → {n}")

    # -- handlers --

    def _do_add(self) -> None:
        template = self._selected("box")
        if template is None:
            self._set_output("⚠ pick a box template first (Ctrl+B)")
            return
        self.controller.add_box(template, self._count())
        self._render_status(f"✓ added {template} ×{self._count()}")

    def _do_clear(self) -> None:
        self.controller.clear_boxes()
        self._render_status("cleared boxes")

    def _do_preview(self) -> None:
        self._render_status()

    def _do_generate(self) -> None:
        self._sync_header_fields()
        try:
            root = self.controller.generate(self.out_dir, overwrite=self._pending_overwrite)
        except ScenarioExistsError as exc:
            self._pending_overwrite = True
            self._set_output(f"⚠ {exc}\n  press Generate (Ctrl+G) again to overwrite it.")
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
