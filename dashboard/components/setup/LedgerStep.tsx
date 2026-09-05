"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field, Msg, StepFrame, btnCls, btnQuietCls, inputCls } from "@/components/setup/StepFrame";

type Acct = { id: string; name: string; institution_name?: string; account_type: string; balance: number };

export function LedgerStep() {
  const [tab, setTab] = useState<"simplefin" | "sure" | "skip">("simplefin");
  const [token, setToken] = useState("");
  const [sure, setSure] = useState({ api_url: "http://127.0.0.1:3000", api_key_rw: "", api_key_ro: "" });
  const [accounts, setAccounts] = useState<Acct[] | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "info" | "ok" | "warn" | "bad"; text: string } | null>(null);

  const load = () => api("/ledger/accounts").then((r) => { if (!r.error) { setAccounts(r.accounts ?? []); setProvider(r.provider); } });
  useEffect(() => { load(); }, []);

  const claim = async () => {
    setBusy(true);
    setMsg({ kind: "info", text: "Connecting to SimpleFIN and pulling the first window of transactions… this can take a minute." });
    const r = await api("/ledger/simplefin/claim", { body: { setup_token: token.trim() } });
    setBusy(false);
    if (r.error) { setMsg({ kind: "bad", text: r.error }); return; }
    setToken("");
    setAccounts(r.accounts ?? []);
    setProvider("simplefin");
    const p = r.pull ?? {};
    setMsg({ kind: r.ok ? "ok" : "warn", text: `Connected. ${p.accounts ?? 0} accounts, ${p.transactions_new ?? 0} transactions${(p.errors?.length ? `; notes: ${p.errors.join("; ")}` : "")}.` });
  };
  const configureSure = async () => {
    setBusy(true);
    const r = await api("/ledger/sure/configure", { body: sure });
    setBusy(false);
    if (r.error) { setMsg({ kind: "bad", text: r.error }); return; }
    setAccounts(r.accounts ?? []); setProvider("sure");
    setMsg({ kind: r.health?.ok ? "ok" : "warn", text: r.health?.ok ? `Sure reachable, ${r.accounts?.length ?? 0} accounts.` : (r.health?.reason ?? "saved") });
  };
  const skip = async () => {
    const r = await api("/ledger/provider", { body: { provider: "none" } });
    setMsg(r.ok ? { kind: "info", text: "Skipped. You can connect banks later from this page." } : { kind: "bad", text: r.error ?? "failed" });
    setProvider("none");
  };
  const connected = (accounts?.length ?? 0) > 0 || provider === "none";

  return (
    <StepFrame href="/setup/ledger" title="Connect your banks, cards, and loans" canNext={connected}
      intro="SimpleFIN is a small read-only service (about $1.50/month) that securely relays balances and transactions from your institutions. focos pulls once a day into a private database in your data folder.">
      <div role="tablist" className="mb-4 inline-flex rounded-[7px] bg-panel-2 p-0.5">
        {(["simplefin", "sure", "skip"] as const).map((t) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-[6px] px-3 py-1 text-xs font-medium ${tab === t ? "bg-panel text-ink shadow-[0_0_0_1px_var(--hairline)]" : "text-secondary hover:text-ink"}`}>
            {t === "simplefin" ? "SimpleFIN" : t === "sure" ? "I run Sure" : "Skip for now"}
          </button>
        ))}
      </div>
      {tab === "simplefin" ? (
        <div className="space-y-3">
          <ol className="list-decimal space-y-1 pl-5 text-[13px] text-secondary">
            <li>Go to <a className="underline" href="https://bridge.simplefin.org" target="_blank" rel="noreferrer">bridge.simplefin.org</a>, create an account, and connect each bank, card, and loan.</li>
            <li>Open <b>Apps</b> → <b>New app</b> and copy the <b>setup token</b> (a long code that works once).</li>
            <li>Paste it below. focos exchanges it for a private access link and stores that link in your data folder.</li>
          </ol>
          <Field label="SimpleFIN setup token">
            <textarea className={`${inputCls} min-h-[72px] font-mono text-[12px]`} value={token} onChange={(e) => setToken(e.target.value)} placeholder="paste the setup token" />
          </Field>
          <button type="button" className={btnCls} disabled={busy || token.trim().length < 20} onClick={claim}>Connect</button>
        </div>
      ) : tab === "sure" ? (
        <div className="space-y-3">
          <p className="text-[13px] text-secondary">Advanced: keep using a self-hosted Sure ledger. focos reads it over its API.</p>
          <Field label="Sure URL"><input className={inputCls} value={sure.api_url} onChange={(e) => setSure({ ...sure, api_url: e.target.value })} /></Field>
          <Field label="Read-write API key"><input className={inputCls} type="password" value={sure.api_key_rw} onChange={(e) => setSure({ ...sure, api_key_rw: e.target.value })} /></Field>
          <Field label="Read-only API key (optional)"><input className={inputCls} type="password" value={sure.api_key_ro} onChange={(e) => setSure({ ...sure, api_key_ro: e.target.value })} /></Field>
          <button type="button" className={btnCls} disabled={busy} onClick={configureSure}>Save and check</button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-[13px] text-secondary">Without a bank connection focos still analyzes holdings you enter and tracks goals, but cash, debt, and cash-flow sections stay empty.</p>
          <button type="button" className={btnQuietCls} onClick={skip}>Skip banks for now</button>
        </div>
      )}
      {msg ? <Msg kind={msg.kind}>{msg.text}</Msg> : null}
      {accounts && accounts.length ? (
        <div className="mt-4">
          <div className="label mb-1 text-ink">Discovered accounts ({provider})</div>
          <table className="tbl text-[12px]">
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}><td>{a.name}</td><td className="text-muted">{a.institution_name}</td><td className="text-muted">{a.account_type}</td>
                  <td className="num">{a.balance.toLocaleString(undefined, { style: "currency", currency: "USD" })}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </StepFrame>
  );
}
