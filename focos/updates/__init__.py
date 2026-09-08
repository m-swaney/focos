"""Structured updates: the one way the model, the dashboard, the CLI, and the pipeline change goals, the tax
agenda, profile notes, spending figures, and decision status. Every applied (or rejected) update is one line in
state/changes.jsonl, which the dashboard shows and the next brief reports under "What I updated".

Use `from focos.updates import apply as apply_mod` for the engine (apply_mod.apply / describe / recent_changes)."""
from __future__ import annotations

from . import apply  # noqa: F401  (the module; its `apply()` function is the entry point)
from .models import Update, UpdateError, validate_update  # noqa: F401
