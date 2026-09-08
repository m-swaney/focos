"""Parse `claude -p --output-format json` output and extract JSON payloads from the result text."""
from __future__ import annotations

import json
import re
from pathlib import Path

FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def read_result(path: Path) -> dict:
    """Return the final result object. Handles both single-object and stream (list/ndjson) files."""
    text = _read_any_encoding(path).strip()
    if not text:
        raise ValueError(f"{path} is empty")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        objs = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    objs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        obj = objs
    if isinstance(obj, list):
        results = [o for o in obj if isinstance(o, dict) and o.get("type") == "result"]
        if not results:
            raise ValueError("no result object in stream output")
        obj = results[-1]
    if not isinstance(obj, dict):
        raise ValueError("unexpected claude output shape")
    return obj


def _read_any_encoding(path: Path) -> str:
    """PowerShell redirection writes UTF-16 with BOM; Out-File -Encoding utf8 writes UTF-8 with BOM."""
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    if len(data) > 1 and data[1:2] == b"\x00":  # UTF-16 LE without BOM
        return data.decode("utf-16-le", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def extract_json(text: str) -> dict:
    """Pull a JSON object out of model text: prefer a fenced block, else the outermost braces."""
    if not text:
        raise ValueError("empty result text")
    m = FENCE.findall(text)
    if m:
        return json.loads(m[-1])
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in result text")
    return json.loads(text[start:end + 1])


def summarize(result: dict) -> dict:
    return {
        "is_error": bool(result.get("is_error")),
        "duration_ms": result.get("duration_ms"),
        "num_turns": result.get("num_turns"),
        "session_id": result.get("session_id"),
        "mcp_servers": result.get("mcp_servers"),
        "subtype": result.get("subtype"),
    }
