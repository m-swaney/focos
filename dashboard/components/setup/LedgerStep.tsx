"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field, Msg, StepFrame, btnCls, btnQuietCls, inputCls } from "@/components/setup/StepFrame";

type Acct = { id: string; name: string; institution_name?: string; account_type: string; balance: number; source?: string };

export function LedgerStep() {
  const [tab, setTab] = useState<"simplefin" | "skip">("simplefin");
  const [token, setToken] = useState("");
  const [mercury, setMercury] = useState("");
  const [showMercury, setShowMercury] = useState(false);
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
  const connectMercury = async () => {
    setBusy(true);
    setMsg({ kind: "info", text: "Checking the Mercury token and pulling recent transactions…" });
    const r = await api("/ledger/mercury/configure", { body: { token: mercury.trim() } });
    setBusy(false);
    if (r.error) { setMsg({ kind: "bad", text: r.error }); return; }
    setMercury("");
    setAccounts(r.accounts ?? []);
    setProvider(r.provider ?? "simplefin");
    const p = r.pull ?? {};
    setMsg({ kind: r.ok ? "ok" : "warn", text: `Mercury connected: ${r.mercury_accounts ?? p.accounts ?? 0} accounts, ${p.transactions_new ?? 0} transactions.` });
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
        {(["simplefin", "skip"] as const).map((t) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-[6px] px-3 py-1 text-xs font-medium ${tab === t ? "bg-panel text-ink shadow-[0_0_0_1px_var(--hairline)]" : "text-secondary hover:text-ink"}`}>
            {t === "simplefin" ? "SimpleFIN" : "Skip for now"}
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

          <div className="mt-4 border-t border-hairline pt-3">
            <button type="button" className="text-[13px] text-accent hover:underline" onClick={() => setShowMercury((v) => !v)}>
              {showMercury ? "Hide" : "Bank with Mercury?"} {showMercury ? "" : "Connect it directly"}
            </button>
            {showMercury ? (
              <div className="mt-2 space-y-2">
                <p className="text-[13px] text-secondary">
                  Mercury business accounts often do not sync through SimpleFIN. In Mercury open <b>Settings → API tokens</b>, create a <b>read-only</b> token, and paste it here. focos reads balances and transactions straight from Mercury and never stores account numbers.
                </p>
                <Field label="Mercury read-only API token">
                  <input className={`${inputCls} font-mono text-[12px]`} type="password" value={mercury} onChange={(e) => setMercury(e.target.value)} placeholder="secret-token:…" />
                </Field>
                <button type="button" className={btnCls} disabled={busy || mercury.trim().length < 10} onClick={connectMercury}>Connect Mercury</button>
              </div>
            ) : null}
          </div>
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
          <div className="label mb-1 text-ink">Discovered accounts</div>
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
