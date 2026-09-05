"""Markdown rendering of analytics results (used by the legacy analyze.py shim and the dashboard)."""
from __future__ import annotations


def money(x) -> str:
    return "n/a" if x is None else f"${x:,.0f}"


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def render(res: dict) -> str:
    out = [f"# Portfolio analysis (prices as of {res['meta']['asof']})\n", "## Accounts\n"]
    rows = [[a["account"], money(a["value"]), money(a["cost"]), money(a["gain"]), pct(a["gain_pct"]), pct(a["share_of_total"])]
            for a in res["accounts"]]
    out.append(table(["account", "value", "cost", "gain", "gain_pct", "share_of_total"], rows))

    out.append("\n## Positions\n")
    rows = [[p["symbol"], p["account"], f"{p['quantity']:.2f}", money(p["price"]), money(p["value"]),
             pct(p["weight_account"]), pct(p["weight_total"]), money(p["cost"]), money(p["gain"]), pct(p["gain_pct"])]
            for p in res["positions"]]
    out.append(table(["symbol", "account", "quantity", "price", "value", "weight_account", "weight_total", "cost", "gain", "gain_pct"], rows))

    c = res["concentration"]
    out.append("\n## Concentration (all accounts combined)\n")
    if c.get("top1"):
        out.append(f"- Top 1 holding: {c['top1']['symbol']} at {pct(c['top1']['weight'])}")
    out.append(f"- Top 3 holdings: {pct(c['top3_weight'])} ({', '.join(c['top3'])})")
    out.append(f"- Top 5 holdings: {pct(c['top5_weight'])}")
    if c.get("effective_positions"):
        out.append(f"- Herfindahl index: {c['hhi']:.3f} (effective number of positions: {c['effective_positions']:.1f})")

    out.append("\n## Look-through exposure (ETF top holdings unpacked)\n")
    rows = [[k, money(v["value"]), pct(v["weight"])] for k, v in list(res["look_through"].items())[:15]]
    out.append(table(["exposure", "value", "weight"], rows))

    out.append("\n## Sector exposure\n")
    rows = [[k, money(v["value"]), pct(v["weight"])] for k, v in res["sectors"].items()]
    out.append(table(["sector", "value", "weight"], rows))

    r = res.get("risk")
    if r:
        out.append(f"\n## Risk profile ({res['meta']['years']}y, current weights held constant)\n")
        rows = [["CAGR", pct(r["cagr"])], ["Benchmark CAGR", pct(r["benchmark_cagr"])], ["Volatility (ann.)", pct(r["volatility"])],
                ["Sharpe", f"{r['sharpe']:.2f}"], ["Sortino", f"{r['sortino']:.2f}"], ["Max drawdown", pct(r["max_drawdown"])],
                ["Benchmark max drawdown", pct(r["benchmark_max_drawdown"])], ["Beta vs SPY", f"{r['beta']:.2f}"],
                ["Worst day", pct(r["worst_day"])], ["Worst month", pct(r["worst_month"])]]
        out.append(table(["metric", "portfolio"], rows))
        if r.get("avg_pairwise_correlation") is not None:
            out.append(f"\nAverage pairwise correlation across holdings: {r['avg_pairwise_correlation']:.2f}")

    o = res.get("optimizer")
    if o:
        out.append(f"\n## Optimizer what-ifs (long-only, max {int(o['max_weight']*100)}% per name)\n")
        rows = [[k, pct(v["expected_return"]), pct(v["volatility"]), f"{v['sharpe']:.2f}",
                 ", ".join(f"{s} {w*100:.0f}%" for s, w in sorted(v["weights"].items(), key=lambda kv: -kv[1])[:8])]
                for k, v in o.items() if isinstance(v, dict)]
        out.append(table(["portfolio", "exp. return", "volatility", "sharpe", "top weights"], rows))

    t = res.get("tax_split")
    if t and t.get("available"):
        out.append("\n## Taxable account: short-term vs long-term unrealized gains" + (" (approximate)" if t.get("approximate") else "") + "\n")
        rows = [[b["symbol"], f"{b['st_shares']:.2f}", money(b["st_gain"]), f"{b['lt_shares']:.2f}", money(b["lt_gain"])]
                for b in t["by_symbol"]]
        tot = t["totals"]
        rows.append(["TOTAL", "", money(tot["st_gain"]), "", money(tot["lt_gain"])])
        out.append(table(["symbol", "st_shares", "st_gain", "lt_shares", "lt_gain"], rows))
        if tot.get("lt_share_of_gain") is not None:
            out.append(f"\nLong-term share of unrealized gain: {pct(tot['lt_share_of_gain'])}")
    return "\n".join(out) + "\n"
