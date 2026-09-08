"""Conversation engine for the setup interview (provider-agnostic, text-only history so it works everywhere)."""
from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any

import yaml
from pydantic import BaseModel

from .. import paths, settings
from ..llm import LLMError, Message, provider_for
from ..llm.base import LLMProvider
from . import schemas

MAX_TOKENS = 2048


class Proposal(BaseModel):
    section: str
    data: Any
    yaml: str
    confidence: str = "medium"
    assumptions: list[str] = []
    errors: list[str] = []


class Session(BaseModel):
    id: str
    created: str
    messages: list[Message] = []
    confirmed: list[str] = []
    skipped: list[str] = []
    pending: Proposal | None = None
    finished: bool = False
    cost_usd: float = 0.0
    turns: int = 0
    system: str = ""


class Turn(BaseModel):
    session_id: str
    assistant_text: str
    proposal: Proposal | None = None
    finished: bool = False
    confirmed: list[str] = []
    remaining: list[str] = []
    over_budget: bool = False


_SESSIONS: dict[str, Session] = {}


def _spill_path(sid: str):
    return paths.CACHE / f"interview-{sid}.json"


def _save(s: Session) -> None:
    _SESSIONS[s.id] = s
    try:
        paths.CACHE.mkdir(parents=True, exist_ok=True)
        _spill_path(s.id).write_text(s.model_dump_json(indent=1), encoding="utf-8")
    except OSError:
        pass


def get(sid: str) -> Session | None:
    s = _SESSIONS.get(sid)
    if s is None and _spill_path(sid).exists():
        s = Session.model_validate_json(_spill_path(sid).read_text(encoding="utf-8"))
        _SESSIONS[sid] = s
    return s


def _context_block() -> str:
    """What the interview already knows: discovered accounts (no ids), entities, holdings summary, current profile."""
    parts = []
    try:
        from ..ledger import providers
        p = providers.current()
        if p is not None and p.health().ok:
            rows = [{"name": a.name, "institution": a.institution_name, "type": a.account_type, "subtype": a.subtype,
                     "classification": a.classification, "balance": round(a.balance, 2)} for a in p.accounts()]
            parts.append("Ledger accounts:\n" + json.dumps(rows, indent=1))
    except Exception:  # noqa: BLE001
        pass
    ents = settings.entities_v2().get("entities") or {}
    parts.append("Entities: " + json.dumps({k: {"label": v.get("label"), "kind": v.get("kind")} for k, v in ents.items()}))
    br = settings.brokerage()
    if br:
        parts.append("Brokerage accounts: " + json.dumps([{"key": a["key"], "label": a.get("label"), "role": a.get("role")} for a in br]))
    prof = settings.profile_v2()
    filled = {k: v for k, v in prof.items() if k in schemas.PROFILE_SECTIONS and v not in (None, {}, [], {"sources": [], "notes": None})}
    if filled:
        parts.append("Already in profile.yml (confirm or refine, do not re-ask what is known):\n" + yaml.safe_dump(filled, sort_keys=False))
    return "\n\n".join(parts)


def system_prompt() -> str:
    from ..brief.prompts import render_placeholders

    base = (paths.AGENT / "prompts" / "interview.md").read_text(encoding="utf-8")
    hints = "\n".join(f"- {s}: {schemas.SECTION_HINTS[s]}" for s in schemas.SECTIONS)
    text = base.replace("{{SECTION_HINTS}}", hints).replace("{{SCHEMAS}}", json.dumps(schemas.all_schemas()))
    text = render_placeholders(text, date=datetime.now().date().isoformat())
    return text + "\n\n# What is already known\n\n" + _context_block()


def _budget() -> float:
    return float(((settings.focos().get("ai") or {}).get("budget_usd") or {}).get("interview") or 1.0)


def _provider(explicit: LLMProvider | None) -> LLMProvider:
    return explicit or provider_for(settings.focos().get("ai") or {})


def _handle(s: Session, comp, provider_name: str) -> Turn:
    s.turns += 1
    s.cost_usd += comp.cost_usd or 0.0
    text = comp.text.strip()
    proposal = None
    for call in comp.tool_calls:
        if call.get("name") == "finish":
            s.finished = True
            text = text or str((call.get("input") or {}).get("summary") or "That covers everything.")
        elif call.get("name") == "propose_section":
            inp = call.get("input") or {}
            section = str(inp.get("section") or "")
            data = inp.get("data")
            if section == "goals" and isinstance(data, dict) and "goals" in data:
                data = data["goals"]
            if section not in schemas.SECTIONS:
                continue
            norm, errors = schemas.validate_section(section, data)
            proposal = Proposal(section=section, data=norm, yaml=yaml.safe_dump({section: norm} if section != "goals" else {"goals": norm}, sort_keys=False, allow_unicode=True),
                                confidence=str(inp.get("confidence") or "medium"), assumptions=list(inp.get("assumptions") or []), errors=errors)
            s.pending = proposal
            # keep a text-only trace so any provider can continue the conversation
            text = (text + "\n\n" if text else "") + f"[proposed section '{section}'; awaiting your confirmation]"
    s.messages.append(Message(role="assistant", content=text or "(no response)"))
    _save(s)
    return Turn(session_id=s.id, assistant_text=text, proposal=proposal, finished=s.finished, confirmed=list(s.confirmed),
                remaining=[x for x in schemas.SECTIONS if x not in s.confirmed and x not in s.skipped],
                over_budget=s.cost_usd > _budget())


def _complete(s: Session, provider: LLMProvider):
    return provider.complete(s.system, s.messages, max_tokens=MAX_TOKENS, tools=schemas.tools(), tool_choice=None)


def start(provider: LLMProvider | None = None, sections: list[str] | None = None) -> Turn:
    prov = _provider(provider)
    s = Session(id=secrets.token_hex(6), created=datetime.now().astimezone().isoformat(timespec="seconds"), system=system_prompt())
    if sections:
        s.skipped = [x for x in schemas.SECTIONS if x not in sections]
    s.messages.append(Message(role="user", content="Let's begin. Ask your first question."))
    try:
        comp = _complete(s, prov)
    except LLMError as e:
        raise
    return _handle(s, comp, prov.name)


def reply(sid: str, text: str, provider: LLMProvider | None = None) -> Turn:
    s = get(sid)
    if s is None:
        raise KeyError(sid)
    if s.cost_usd > _budget():
        raise LLMError("the interview reached its usage limit (ai.budget_usd.interview); finish the remaining sections with the forms")
    prov = _provider(provider)
    s.messages.append(Message(role="user", content=text))
    comp = _complete(s, prov)
    return _handle(s, comp, prov.name)


def confirm(sid: str | None, section: str, data: Any) -> tuple[list[str], Any]:
    """Validate and write one section. Returns (errors, normalized data). Works without a session (plain forms)."""
    from ..config import writer

    if section == "goals" and isinstance(data, dict) and "goals" in data:
        data = data["goals"]
    norm, errors = schemas.validate_section(section, data)
    if errors:
        return errors, norm
    if section == "goals":
        issues = writer.write_section("goals.yml", "goals", norm)
    else:
        issues = writer.write_section("profile.yml", section, norm)
    if issues:
        return [f"{i.path}: {i.message}" for i in issues], norm
    if sid:
        s = get(sid)
        if s is not None:
            if section not in s.confirmed:
                s.confirmed.append(section)
            s.pending = None
            s.messages.append(Message(role="user", content=f"[confirmed section '{section}'] Continue with the next topic."))
            _save(s)
    return [], norm


def skip(sid: str, section: str) -> Session:
    s = get(sid)
    if s is None:
        raise KeyError(sid)
    if section not in s.skipped:
        s.skipped.append(section)
    s.pending = None
    s.messages.append(Message(role="user", content=f"[skipped section '{section}'] Move on to the next topic."))
    _save(s)
    return s
