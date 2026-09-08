"""Build the inline context bundle for API-mode briefs from state/derived/latest and the data dir, ranked by
priority so it can be trimmed to a token budget."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .. import paths, settings
from ..llm.cost import estimate_tokens
from . import outputs

TOP_POSITIONS = 40
TOP_LOOK_THROUGH = 15
PREVIOUS_BRIEF_WORDS = 1500
DECISIONS = 20


@dataclass
class Section:
    name: str
    priority: int                 # higher survives trimming longer
    data: Any                     # dict/list (rendered as JSON) or str (rendered as text)
    note: str = ""

    def render(self) -> str:
        body = self.data if isinstance(self.data, str) else json.dumps(self.data, indent=1, default=str, sort_keys=True)
        fence = "text" if isinstance(self.data, str) else "json"
        head = f"### {self.name}" + (f" ({self.note})" if self.note else "")
        return f"{head}\n```{fence}\n{body}\n```"

    def tokens(self) -> int:
        return estimate_tokens(self.render())


@dataclass
class Bundle:
    sections: list[Section] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

    def render(self) -> str:
        return "\n\n".join(s.render() for s in self.sections)

    def tokens(self) -> int:
        return sum(s.tokens() for s in self.sections)


def _latest(name: str) -> dict | None:
    return settings.read_json(paths.LATEST / name, None)


def _trim_portfolio(p: dict | None) -> dict | None:
    if not p or not p.get("available", True):
        return p
    out = {k: v for k, v in p.items() if k not in ("positions", "look_through", "class_weights")}
    out["positions"] = sorted(p.get("positions") or [], key=lambda r: -(r.get("value") or 0))[:TOP_POSITIONS]
    lt = p.get("look_through") or {}
    out["look_through"] = dict(sorted(lt.items(), key=lambda kv: -(kv[1].get("weight") or 0))[:TOP_LOOK_THROUGH])
    out["class_weights"] = p.get("class_weights")
    return out


def _trim_catalysts(c: dict | None) -> dict | None:
    if not c:
        return c
    news = [{k: n.get(k) for k in ("symbol", "title", "published_at", "source") if k in n} for n in (c.get("news") or [])][:40]
    return {"date": c.get("date"), "earnings": (c.get("earnings") or [])[:40], "news": news}


def _trim_sandbox(s: dict | None) -> dict | None:
    if not s:
        return s
    out = dict(s)
    acct = dict(s.get("account") or {})
    acct.pop("recent_orders", None)
    out["account"] = acct
    out["proposals"] = (s.get("proposals") or [])[-10:]
    sc = s.get("scorecard") or {}
    out["scorecard"] = {k: v for k, v in sc.items() if k != "positions"} | {"open_positions": [p for p in (sc.get("positions") or []) if p.get("status") == "open"][:10]}
    return out


def _profile_subset() -> dict:
    p = settings.profile_v2()
    keep = ("owner", "household", "spouse", "income", "spending", "cash_policy", "debt_terms", "retirement", "family", "protection",
            "tax_agenda", "risk", "targets")
    return {k: p.get(k) for k in keep if p.get(k) not in (None, {}, [])}


def _previous_brief(mode: str, date: str) -> tuple[str, str] | None:
    rel = outputs.previous_brief_path(mode, date)
    if not rel:
        return None
    text = (paths.HOME / rel).read_text(encoding="utf-8", errors="replace")
    words = text.split()
    if len(words) > PREVIOUS_BRIEF_WORDS:
        text = " ".join(words[:PREVIOUS_BRIEF_WORDS]) + "\n[truncated]"
    return rel, text


def build(mode: str, date: str) -> Bundle:
    heavy = mode != "daily"
    b = Bundle()
    add = b.sections.append
    add(Section("profile", 100, _profile_subset(), "config/profile.yml"))
    add(Section("goals", 95, settings.goals_v2().get("goals") or [], "config/goals.yml"))
    add(Section("inbox", 94, _latest("inbox.json") or {"notes": [], "recent_changes": []},
                "notes from the owner, recent changes, open tax items, active goals"))
    add(Section("alerts", 92, _latest("alerts.json") or {"alerts": []}))
    add(Section("portfolio", 90, _trim_portfolio(_latest("portfolio.json")) or {"available": False}))
    add(Section("diff", 88, _latest("diff.json") or {"available": False}, "since the previous snapshot"))
    add(Section("consolidated", 85, _latest("consolidated.json") or {"available": False}, "ledger: net worth, cash flow"))
    add(Section("plan", 84 if heavy else 60, _latest("plan.json") or {"available": False}))
    add(Section("sandbox", 75, _trim_sandbox(_latest("sandbox.json")) or {"mode": "paper"}))
    add(Section("sandbox_rules", 50, settings.sandbox_rules() or {}))
    add(Section("catalysts", 65, _trim_catalysts(_latest("catalysts.json")) or {"earnings": [], "news": []}))
    if heavy:
        add(Section("risk", 80, _latest("risk.json") or {"available": False}))
        add(Section("tax_lots", 72, _latest("tax_lots.json") or {"available": False}))
        add(Section("drift", 70, _latest("drift.json") or {}))
        add(Section("optimizer", 45, _latest("optimizer.json") or {"available": False}))
        add(Section("entities", 68, _latest("entities.json") or {"available": False}))
    prev = _previous_brief(mode, date)
    if prev:
        add(Section("previous_brief", 58, prev[1], prev[0]))
    add(Section("decisions", 62, outputs.recent_decisions(DECISIONS), "last entries of state/decisions.jsonl"))
    return b


def fit(bundle: Bundle, max_input_tokens: int) -> Bundle:
    """Drop the lowest-priority sections until the bundle fits; never drops profile/alerts/portfolio."""
    protected = {"profile", "alerts", "portfolio", "inbox"}
    while bundle.tokens() > max_input_tokens:
        candidates = [s for s in bundle.sections if s.name not in protected]
        if not candidates:
            break
        victim = min(candidates, key=lambda s: s.priority)
        bundle.sections.remove(victim)
        bundle.dropped.append(victim.name)
    return bundle
