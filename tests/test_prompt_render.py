import re
from pathlib import Path

import yaml

from focos import paths, settings
from focos.cli import render_placeholders


def test_owner_and_account_names_substituted(initialized_home: Path):
    (initialized_home / "config" / "profile.yml").write_text(yaml.safe_dump({"version": 2, "owner": {"name": "Ann"}}), encoding="utf-8")
    (initialized_home / "config" / "accounts.yml").write_text(yaml.safe_dump({"version": 2, "brokerage": [
        {"key": "brk", "label": "Brokerage", "role": "taxable"}]}), encoding="utf-8")
    settings.reset()
    out = render_placeholders("## Actions for {{OWNER}}\nnames: {{ACCOUNT_NAMES}}\n{{DATE}} {{MONTH}}", date="2026-03-04")
    assert out == "## Actions for Ann\nnames: brk (Brokerage, taxable)\n2026-03-04 2026-03"


def test_shipped_prompts_are_templated_not_personal(initialized_home: Path):
    """Every 'Actions/Questions/Decisions for <name>' heading in the shipped prompts must use the placeholder."""
    for p in (paths.AGENT / "prompts").rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"(Actions|Questions|Decisions) for (\S+)", text):
            assert m.group(2).startswith("{{OWNER}}"), f"{p.name}: hard-coded name in {m.group(0)!r}"
    rendered = render_placeholders((paths.AGENT / "prompts" / "system.md").read_text(encoding="utf-8"), date="2026-01-01")
    assert "{{" not in rendered
    assert "## Actions for you" in rendered  # no owner configured -> generic
    assert "## What I updated" in rendered and '"target":"goal"' in rendered


def test_task_prompts_point_at_the_inbox(initialized_home: Path):
    from focos.brief import prompts

    daily = prompts.render("daily", "2026-03-04", "daily-2026-03-04-1")
    assert "state/derived/latest/inbox.json" in daily and "state/updates/daily-2026-03-04-1.json" in daily
    assert '"updates_file"' in daily
    api_daily = prompts.render("daily", "2026-03-04", "r", variant="api")
    assert "inbox" in api_daily and '"note_replies"' in api_daily
    for mode in ("weekly", "monthly"):
        assert "state/updates/r.json" in prompts.render(mode, "2026-03-04", "r")
    assert "state/updates/**" in prompts.addendum("agent")
