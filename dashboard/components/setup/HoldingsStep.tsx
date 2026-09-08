"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field, Msg, StepFrame, btnCls, btnQuietCls, inputCls } from "@/components/setup/StepFrame";

type Sources = { configured: string; sources: Record<string, { available: boolean; reason: string | null }>; latest: { date: string; source: string; accounts: number; total_value: number | null } | null };
type Row = { account_key: string; symbol: string; quantity: string; avg_cost: string; price: string };

export function HoldingsStep() {
  const [s, setS] = useState<Sources | null>(null);
  const [choice, setChoice] = useState<string>("none");
  const [rows, setRows] = useState<Row[]>([{ account_key: "brokerage", symbol: "", quantity: "", avg_cost: "", price: "" }]);
  const [csv, setCsv] = useState("");
  const [msg, setMsg] = useState<{ kind: "info" | "ok" | "warn" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api<Sources>("/holdings/sources").then((r) => { if (!r.error) { setS(r); setChoice(r.configured ?? "none"); } });
  useEffect(() => { load(); }, []);

  const setSource = async (source: string) => {
    setChoice(source);
    const r = await api("/holdings/source", { body: { source } });
    if (r.error || !r.ok) setMsg({ kind: "bad", text: r.error ?? "could not save" });
    await load();
  };
  const saveManual = async () => {
    setBusy(true);
    const clean = rows.filter((r) => r.symbol && Number(r.quantity) > 0).map((r) => ({ account_key: r.account_key || "brokerage", symbol: r.symbol, quantity: Number(r.quantity), avg_cost: r.avg_cost ? Number(r.avg_cost) : null, price: r.price ? Number(r.price) : null }));
    const keys = [...new Set(clean.map((r) => r.account_key))].map((key) => ({ key, label: key, role: key.includes("roth") ? "roth_ira" : "taxable" }));
    const r = await api("/holdings/manual", { body: { rows: clean, accounts: keys } });
    setBusy(false);
    setMsg(r.ok ? { kind: "ok", text: `Saved ${r.rows} holdings.` } : { kind: "bad", text: r.error ?? "failed" });
    await load();
  };
  const uploadCsv = async () => {
    setBusy(true);
    const r = await api("/holdings/csv", { body: { text: csv } });
    setBusy(false);
    setMsg(r.ok ? { kind: "ok", text: `Saved ${r.rows} rows.` } : { kind: "bad", text: r.error ?? "failed" });
    await load();
  };
  const capture = async () => {
    setBusy(true);
    const r = await api("/holdings/capture", { body: {} });
    setBusy(false);
    setMsg(r.ok ? { kind: "ok", text: `Captured ${r.accounts?.length ?? 0} account(s) worth ${r.total_value == null ? "n/a" : `$${Number(r.total_value).toLocaleString()}`}${r.notes ? ` (${r.notes})` : ""}.` }
                : { kind: "bad", text: r.error ?? "capture failed" });
    await load();
  };
  const sf = s?.sources?.simplefin_holdings;
  const rh = s?.sources?.robinhood_mcp;

  return (
    <StepFrame href="/setup/holdings" title="Investments to analyze"
      intro="Portfolio analytics (weights, risk, drift, tax lots) need ticker-level holdings. Pick where they come from, or skip if you only want cash, debt, and goal tracking.">
      <div className="grid gap-2 sm:grid-cols-2">
        {[
          { key: "simplefin_holdings", label: "From SimpleFIN", text: sf?.available ? "Your feed reports holdings." : (sf?.reason ?? "Needs the SimpleFIN connection."), ok: !!sf?.available },
          { key: "csv", label: "Enter or upload holdings", text: "A short table: account, ticker, shares, cost. Prices come from Yahoo Finance.", ok: true },
          { key: "robinhood_mcp", label: "Robinhood via Claude Code", text: rh?.available ? "Claude Code and Robinhood are connected." : (rh?.reason ?? "Needs agent mode."), ok: !!rh?.available },
          { key: "none", label: "Skip holdings", text: "Cash, debts, goals, and the plan still work.", ok: true },
        ].map((c) => (
          <label key={c.key} className={`flex cursor-pointer items-start gap-2 rounded-[6px] border p-3 text-[13px] ${choice === c.key ? "border-ink" : "border-hairline hover:bg-panel-2"} ${c.ok ? "" : "opacity-60"}`}>
            <input type="radio" name="holdings" checked={choice === c.key} disabled={!c.ok} onChange={() => setSource(c.key)} className="mt-1" />
            <span><b>{c.label}</b><br /><span className="text-[11px] text-muted">{c.text}</span></span>
          </label>
        ))}
      </div>
      {choice === "csv" ? (
        <div className="mt-4 space-y-3">
          <div className="overflow-x-auto">
            <table className="tbl text-[12px]">
              <thead><tr><th>Account</th><th>Ticker</th><th>Shares</th><th>Avg cost</th><th>Price (optional)</th><th /></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    {(["account_key", "symbol", "quantity", "avg_cost", "price"] as const).map((f) => (
                      <td key={f}><input className={inputCls} value={r[f]} onChange={(e) => setRows(rows.map((x, k) => (k === i ? { ...x, [f]: e.target.value } : x)))} placeholder={f === "account_key" ? "brokerage" : ""} /></td>
                    ))}
                    <td><button type="button" className="text-muted hover:text-critical" onClick={() => setRows(rows.filter((_, k) => k !== i))}>×</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnQuietCls} onClick={() => setRows([...rows, { account_key: rows[rows.length - 1]?.account_key ?? "brokerage", symbol: "", quantity: "", avg_cost: "", price: "" }])}>Add row</button>
            <button type="button" className={btnCls} disabled={busy} onClick={saveManual}>Save holdings</button>
          </div>
          <Field label="Or paste a CSV" hint="Columns: account_key, symbol, quantity, avg_cost, price (optional)">
            <textarea className={`${inputCls} min-h-[80px] font-mono text-[12px]`} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={"account_key,symbol,quantity,avg_cost\nbrokerage,VTI,10,200"} />
          </Field>
          <button type="button" className={btnQuietCls} disabled={busy || !csv.trim()} onClick={uploadCsv}>Upload CSV</button>
        </div>
      ) : null}
      {choice === "robinhood_mcp" && !rh?.available ? (
        <div className="mt-3 space-y-2">
          <Msg kind="warn">
            {rh?.reason ?? "Robinhood is not connected."} In a terminal run <code>focos auth robinhood</code>, finish the login in the browser, then check again.
            Agent mode must be on in the AI step. Once connected, a daily keep-alive job keeps the login fresh.
          </Msg>
          <button type="button" className={btnQuietCls} disabled={busy} onClick={load}>Check again</button>
        </div>
      ) : null}
      {choice !== "none" ? (
        <div className="mt-4 flex items-center gap-3">
          <button type="button" className={btnCls} disabled={busy} onClick={capture}>Capture holdings now</button>
          {s?.latest ? <span className="text-[12px] text-muted">Latest snapshot {s.latest.date} via {s.latest.source}: {s.latest.accounts} account(s)</span> : null}
        </div>
      ) : null}
      {msg ? <Msg kind={msg.kind}>{msg.text}</Msg> : null}
    </StepFrame>
  );
}
