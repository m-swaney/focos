"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Msg, StepFrame, btnCls, btnQuietCls, inputCls } from "@/components/setup/StepFrame";

type Acct = { id: string; name: string; institution_name?: string; account_type: string; subtype?: string; classification: string; balance: number; entity?: string | null; brokerage?: { key: string; label?: string; role?: string } | null; is_manual?: boolean };
type Row = { id: string; entity: string; type: string; ignore: boolean; analyze: boolean; key: string; label: string; role: string };
const TYPES = ["depository", "credit_card", "loan", "investment", "property", "vehicle", "other"];
const ROLES = ["taxable", "roth_ira", "traditional_ira", "401k", "hsa", "529", "other"];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 30) || "acct";

export function AccountsStep() {
  const [accounts, setAccounts] = useState<Acct[]>([]);
  const [provider, setProvider] = useState<string | null>(null);
  const [rows, setRows] = useState<Record<string, Row>>({});
  const [entities, setEntities] = useState<{ key: string; label: string; kind: string }[]>([{ key: "personal", label: "Personal", kind: "household" }]);
  const [newEnt, setNewEnt] = useState("");
  const [manual, setManual] = useState({ name: "", type: "property", balance: "", liability: false });
  const [msg, setMsg] = useState<{ kind: "info" | "ok" | "warn" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = () => api("/ledger/accounts").then((r) => {
    if (r.error) { setMsg({ kind: "bad", text: r.error }); return; }
    setProvider(r.provider);
    const accts: Acct[] = r.accounts ?? [];
    setAccounts(accts);
    const ents = Object.entries(r.entities ?? {}).map(([key, v]) => ({ key, label: (v as { label?: string }).label ?? key, kind: (v as { kind?: string }).kind ?? "business" }));
    if (ents.length) setEntities(ents);
    const next: Record<string, Row> = {};
    for (const a of accts) {
      next[a.id] = { id: a.id, entity: a.entity ?? "personal", type: a.account_type, ignore: false, analyze: !!a.brokerage,
        key: a.brokerage?.key ?? slug(a.name), label: a.brokerage?.label ?? a.name, role: a.brokerage?.role ?? (a.subtype === "roth_ira" ? "roth_ira" : "taxable") };
    }
    setRows(next);
    setSaved(accts.some((a) => a.entity));
  });
  useEffect(() => { load(); }, []);

  const set = (id: string, patch: Partial<Row>) => setRows((r) => ({ ...r, [id]: { ...r[id], ...patch } }));

  const save = async () => {
    setBusy(true);
    const body = {
      entities: entities.filter((e) => e.key !== "personal"),
      accounts: Object.values(rows).map((r) => ({ id: r.id, entity: r.entity, type: r.type, ignore: r.ignore,
        brokerage_key: r.analyze ? r.key : null, brokerage_label: r.analyze ? r.label : null, brokerage_role: r.analyze ? r.role : null })),
    };
    const r = await api("/ledger/assign", { body });
    setBusy(false);
    if (r.error || !r.ok) { setMsg({ kind: "bad", text: r.error ?? r.issues?.map((i: { path: string; message: string }) => `${i.path}: ${i.message}`).join("; ") ?? "failed" }); return false; }
    setSaved(true);
    setMsg({ kind: "ok", text: `Saved.${r.seeded_rules ? ` Seeded ${r.seeded_rules} transfer rules from your institutions.` : ""}` });
    return true;
  };
  const addEntity = () => {
    const key = slug(newEnt);
    if (!key || entities.some((e) => e.key === key)) return;
    setEntities([...entities, { key, label: newEnt.trim(), kind: "business" }]);
    setNewEnt("");
  };
  const addManual = async () => {
    if (!manual.name) return;
    setBusy(true);
    const r = await api("/ledger/manual-accounts", { body: [{ key: slug(manual.name), name: manual.name, account_type: manual.type, balance: Number(manual.balance || 0), classification: manual.liability ? "liability" : "asset" }] });
    setBusy(false);
    if (r.error) { setMsg({ kind: "bad", text: r.error }); return; }
    setManual({ name: "", type: "property", balance: "", liability: false });
    await load();
  };

  return (
    <StepFrame href="/setup/accounts" title="Who owns what" canNext={saved || provider === "none" || provider === null} onNext={accounts.length ? save : undefined}
      intro="Assign each account to the household or to a business you run. Mark brokerage accounts you want analyzed. Types were guessed from the names; correct any that are wrong.">
      {provider === "none" || provider === null ? (
        <p className="text-[13px] text-secondary">No bank connection yet. You can still add manually valued accounts below (a house, a private loan) or continue.</p>
      ) : null}
      {accounts.length ? (
        <div className="overflow-x-auto">
          <table className="tbl text-[12px]">
            <thead><tr><th>Account</th><th>Balance</th><th>Entity</th><th>Type</th><th>Analyze holdings</th><th>Ignore</th></tr></thead>
            <tbody>
              {accounts.map((a) => {
                const r = rows[a.id];
                if (!r) return null;
                return (
                  <tr key={a.id} className={r.ignore ? "opacity-50" : ""}>
                    <td><div>{a.name}</div><div className="text-[11px] text-muted">{a.institution_name}{a.is_manual ? " · manual" : ""}</div></td>
                    <td className="num">{a.balance.toLocaleString(undefined, { style: "currency", currency: "USD" })}</td>
                    <td><select className={inputCls} value={r.entity} onChange={(e) => set(a.id, { entity: e.target.value })}>{entities.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}</select></td>
                    <td><select className={inputCls} value={r.type} onChange={(e) => set(a.id, { type: e.target.value })}>{TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select></td>
                    <td>
                      {r.type === "investment" ? (
                        <div className="flex flex-col gap-1">
                          <label className="flex items-center gap-1"><input type="checkbox" checked={r.analyze} onChange={(e) => set(a.id, { analyze: e.target.checked })} /> yes</label>
                          {r.analyze ? (
                            <select className={inputCls} value={r.role} onChange={(e) => set(a.id, { role: e.target.value })}>{ROLES.map((x) => <option key={x} value={x}>{x}</option>)}</select>
                          ) : null}
                        </div>
                      ) : <span className="text-muted">—</span>}
                    </td>
                    <td><input type="checkbox" checked={r.ignore} onChange={(e) => set(a.id, { ignore: e.target.checked })} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div className="rounded-[6px] border border-hairline p-3">
          <div className="label mb-2 text-ink">Add a business or other entity</div>
          <div className="flex gap-2">
            <input className={inputCls} value={newEnt} onChange={(e) => setNewEnt(e.target.value)} placeholder="e.g. Corner Shop LLC" />
            <button type="button" className={btnQuietCls} onClick={addEntity}>Add</button>
          </div>
          <div className="mt-2 text-[11px] text-muted">{entities.map((e) => e.label).join(" · ")}</div>
        </div>
        <div className="rounded-[6px] border border-hairline p-3">
          <div className="label mb-2 text-ink">Add a manually valued account</div>
          <div className="grid gap-2">
            <input className={inputCls} value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} placeholder="e.g. Primary residence" />
            <div className="flex gap-2">
              <select className={inputCls} value={manual.type} onChange={(e) => setManual({ ...manual, type: e.target.value })}>{TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select>
              <input className={inputCls} type="number" value={manual.balance} onChange={(e) => setManual({ ...manual, balance: e.target.value })} placeholder="value" />
            </div>
            <label className="flex items-center gap-1 text-[12px] text-secondary"><input type="checkbox" checked={manual.liability} onChange={(e) => setManual({ ...manual, liability: e.target.checked })} /> this is money owed</label>
            <button type="button" className={btnQuietCls} disabled={busy || !manual.name} onClick={addManual}>Add account</button>
          </div>
        </div>
      </div>
      <div className="mt-4 flex gap-2">
        <button type="button" className={btnCls} disabled={busy || !accounts.length} onClick={save}>Save assignments</button>
      </div>
      {msg ? <Msg kind={msg.kind}>{msg.text}</Msg> : null}
    </StepFrame>
  );
}
