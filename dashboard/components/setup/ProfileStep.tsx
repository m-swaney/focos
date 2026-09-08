"use client";

import { useEffect, useRef, useState } from "react";
import { parse as parseYaml } from "yaml";
import { api } from "@/lib/api";
import { SchemaForm } from "@/components/setup/SchemaForm";
import { Msg, StepFrame, btnCls, btnQuietCls, inputCls } from "@/components/setup/StepFrame";

type Proposal = { section: string; data: unknown; yaml: string; confidence: string; assumptions: string[]; errors: string[] };
type Turn = { session_id: string; assistant_text: string; proposal: Proposal | null; finished: boolean; confirmed: string[]; remaining: string[]; over_budget: boolean };
type Chat = { role: "user" | "assistant"; text: string };

export function ProfileStep() {
  const [mode, setMode] = useState<"interview" | "forms">("interview");
  const [aiReady, setAiReady] = useState<boolean | null>(null);
  const [chat, setChat] = useState<Chat[]>([]);
  const [sid, setSid] = useState<string | null>(null);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [input, setInput] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "info" | "ok" | "warn" | "bad"; text: string } | null>(null);
  const [schemas, setSchemas] = useState<{ sections: string[]; hints: Record<string, string>; schemas: Record<string, unknown> } | null>(null);
  const [current, setCurrent] = useState<{ profile: Record<string, unknown>; goals: unknown[] } | null>(null);
  const [section, setSection] = useState("owner");
  const [formValue, setFormValue] = useState<unknown>({});
  const endRef = useRef<HTMLDivElement>(null);

  const valueFor = (s: string, c: { profile: Record<string, unknown>; goals: unknown[] } | null): unknown =>
    s === "goals" ? { goals: c?.goals ?? [] } : (c?.profile?.[s] ?? {});
  const chooseSection = (s: string) => {
    setSection(s);
    setFormValue(valueFor(s, current));
  };
  const refreshCurrent = () =>
    api("/interview/current").then((r) => {
      if (r.error) return;
      setCurrent(r);
      setFormValue(valueFor(section, r));
    });
  useEffect(() => {
    api("/setup/status").then((r) => setAiReady(r?.steps?.ai === "done"));
    api("/interview/schema").then((r) => !r.error && setSchemas(r));
    refreshCurrent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [chat]);

  const apply = (t: Turn) => {
    setTurn(t);
    setSid(t.session_id);
    setChat((c) => [...c, { role: "assistant", text: t.assistant_text }]);
    setYamlText(t.proposal?.yaml ?? "");
    if (t.over_budget) setMsg({ kind: "warn", text: "The interview reached its usage limit; you can finish with the forms." });
  };
  const start = async () => {
    setBusy(true); setChat([]);
    const t = await api<Turn>("/interview/start", { body: {} });
    setBusy(false);
    if (t.error) { setMsg({ kind: "bad", text: t.error }); return; }
    apply(t);
  };
  const send = async () => {
    if (!sid || !input.trim()) return;
    const text = input.trim();
    setInput(""); setBusy(true);
    setChat((c) => [...c, { role: "user", text }]);
    const t = await api<Turn>("/interview/reply", { body: { session_id: sid, text } });
    setBusy(false);
    if (t.error) { setMsg({ kind: "bad", text: t.error }); return; }
    apply(t);
  };
  const confirm = async () => {
    if (!turn?.proposal) return;
    let data: unknown;
    try {
      const doc = parseYaml(yamlText) ?? {};
      data = turn.proposal.section === "goals" ? (doc.goals ?? doc) : (doc[turn.proposal.section] ?? doc);
    } catch (e) { setMsg({ kind: "bad", text: `YAML does not parse: ${String(e)}` }); return; }
    const r = await api("/interview/confirm", { body: { session_id: sid, section: turn.proposal.section, data } });
    if (!r.ok) { setMsg({ kind: "bad", text: (r.errors ?? [r.error]).join("; ") }); return; }
    setMsg({ kind: "ok", text: `Saved ${turn.proposal.section}.` });
    setTurn({ ...turn, proposal: null, confirmed: [...turn.confirmed, turn.proposal.section] });
    refreshCurrent();
  };
  const skip = async () => {
    if (!turn?.proposal || !sid) return;
    await api("/interview/skip", { body: { session_id: sid, section: turn.proposal.section } });
    setTurn({ ...turn, proposal: null });
  };
  const saveForm = async () => {
    const data = section === "goals" ? (formValue as { goals?: unknown }).goals ?? formValue : formValue;
    const r = await api("/interview/confirm", { body: { section, data } });
    setMsg(r.ok ? { kind: "ok", text: `Saved ${section}.` } : { kind: "bad", text: (r.errors ?? [r.error]).join("; ") });
    if (r.ok) refreshCurrent();
  };
  const done = (turn?.confirmed?.length ?? 0) > 0 || !!current?.profile?.owner;

  return (
    <StepFrame href="/setup/profile" title="Tell focos about your household" canNext={done}
      intro="A short conversation fills in your profile and goals. Every answer becomes a proposal you review before it is saved; nothing here is sent anywhere except to the AI provider you chose.">
      <div role="tablist" className="mb-4 inline-flex rounded-[7px] bg-panel-2 p-0.5">
        {(["interview", "forms"] as const).map((t) => (
          <button key={t} role="tab" type="button" aria-selected={mode === t} onClick={() => setMode(t)}
            className={`rounded-[6px] px-3 py-1 text-xs font-medium ${mode === t ? "bg-panel text-ink shadow-[0_0_0_1px_var(--hairline)]" : "text-secondary hover:text-ink"}`}>
            {t === "interview" ? "Interview" : "Fill in forms"}
          </button>
        ))}
      </div>
      {mode === "interview" ? (
        aiReady === false ? (
          <Msg kind="warn">Set up an AI provider first, or use the forms.</Msg>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="flex min-h-[360px] flex-col rounded-[6px] border border-hairline">
              <div className="flex-1 space-y-3 overflow-y-auto p-3 text-[13px]">
                {chat.length === 0 ? (
                  <div className="text-secondary">
                    <p>Ready when you are. About five minutes.</p>
                    <button type="button" className={`${btnCls} mt-3`} disabled={busy} onClick={start}>Start the interview</button>
                  </div>
                ) : chat.map((m, i) => (
                  <div key={i} className={`max-w-[85%] whitespace-pre-wrap rounded-[8px] px-3 py-2 ${m.role === "user" ? "ml-auto bg-panel-2 text-ink" : "bg-page text-ink border border-hairline"}`}>{m.text}</div>
                ))}
                {busy ? <div className="text-[12px] text-muted">thinking…</div> : null}
                <div ref={endRef} />
              </div>
              {sid && !turn?.finished ? (
                <form className="flex gap-2 border-t border-hairline p-2" onSubmit={(e) => { e.preventDefault(); send(); }}>
                  <input className={inputCls} autoFocus value={input} onChange={(e) => setInput(e.target.value)} placeholder="type your answer" disabled={busy} />
                  <button type="submit" className={btnCls} disabled={busy || !input.trim()}>Send</button>
                </form>
              ) : null}
              {turn?.finished ? <div className="border-t border-hairline p-2 text-[12px] text-gain">Interview finished. Confirmed: {turn.confirmed.join(", ") || "nothing yet"}.</div> : null}
            </div>
            <div className="space-y-3">
              <div className="rounded-[6px] border border-hairline p-3">
                <div className="label mb-1 text-ink">Proposal</div>
                {turn?.proposal ? (
                  <>
                    <div className="mb-1 text-[11px] text-muted">{turn.proposal.section} · confidence {turn.proposal.confidence}</div>
                    {turn.proposal.assumptions?.length ? <ul className="mb-1 list-disc pl-4 text-[11px] text-warn">{turn.proposal.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul> : null}
                    {turn.proposal.errors?.length ? <div className="mb-1 text-[11px] text-critical">{turn.proposal.errors.join("; ")}</div> : null}
                    <textarea className={`${inputCls} min-h-[180px] font-mono text-[11px]`} value={yamlText} onChange={(e) => setYamlText(e.target.value)} />
                    <div className="mt-2 flex gap-2">
                      <button type="button" className={btnCls} onClick={confirm}>Looks right</button>
                      <button type="button" className={btnQuietCls} onClick={skip}>Skip</button>
                    </div>
                  </>
                ) : <div className="text-[12px] text-muted">Proposals appear here as the interview learns enough about a topic. Edit the text before saving if anything is off.</div>}
              </div>
              {turn ? (
                <div className="rounded-[6px] border border-hairline p-3 text-[11px] text-muted">
                  <div>Confirmed: {turn.confirmed.join(", ") || "—"}</div>
                  <div>Remaining: {turn.remaining.join(", ") || "—"}</div>
                </div>
              ) : null}
            </div>
          </div>
        )
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <select className={`${inputCls} w-auto`} value={section} onChange={(e) => chooseSection(e.target.value)}>
              {(schemas?.sections ?? []).map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </select>
            <span className="text-[11px] text-muted">{schemas?.hints?.[section]}</span>
          </div>
          {schemas?.schemas?.[section] ? (
            (schemas.schemas[section] as { type?: string }).type === "array" ? (
              <textarea className={`${inputCls} min-h-[200px] font-mono text-[12px]`}
                defaultValue={JSON.stringify(section === "goals" ? ((formValue as { goals?: unknown }).goals ?? []) : formValue, null, 1)}
                onBlur={(e) => { try { const v = JSON.parse(e.target.value || "[]"); setFormValue(section === "goals" ? { goals: v } : v); } catch { setMsg({ kind: "bad", text: "not valid JSON" }); } }} />
            ) : (
              <SchemaForm schema={schemas.schemas[section]} value={formValue} onChange={setFormValue} />
            )
          ) : null}
          <button type="button" className={btnCls} onClick={saveForm}>Save {section.replace(/_/g, " ")}</button>
        </div>
      )}
      {msg ? <Msg kind={msg.kind}>{msg.text}</Msg> : null}
    </StepFrame>
  );
}
