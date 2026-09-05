"""PostToolUse hook: append every order tool response to orders.jsonl and count live orders."""
from __future__ import annotations

import json
import sys
from datetime import datetime

from .. import paths, settings
from . import brokers
from . import state as sb_state


def _apply_home_arg() -> None:
    """Hooks are launched as `python -m focos.sandbox.<hook> --home <dir>`; honor it before touching paths."""
    if "--home" in sys.argv:
        i = sys.argv.index("--home")
        if i + 1 < len(sys.argv):
            paths.rebind(sys.argv[i + 1])
            settings.reset()


def orders_file():
    return paths.SANDBOX / "orders.jsonl"


def main() -> int:
    _apply_home_arg()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_name = payload.get("tool_name", "")
    adapter = brokers.current()
    if adapter.guarded_tools().get(tool_name) != "place":
        return 0
    order = dict(payload.get("tool_input") or {})
    order["account_last4"] = str(order.pop("account_number", ""))[-4:]
    resp = payload.get("tool_response")
    failed = adapter.response_failed(resp)
    orders = orders_file()
    orders.parent.mkdir(parents=True, exist_ok=True)
    with orders.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now(settings.tz()).isoformat(timespec="seconds"), "order": order,
                            "response": resp, "ok": not failed}, default=str) + "\n")
    if not failed:
        m = sb_state.load_mode()
        m["live_orders"] = int(m.get("live_orders", 0)) + 1
        sb_state.save_mode(m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
