"""Textual TUI for r42topo.

The interactive authoring frontend. All non-view logic lives in
``TuiController`` (pure, framework-light) so it can be unit-tested without the
event loop and shared with the range42 deployment TUI rewrite.
"""
