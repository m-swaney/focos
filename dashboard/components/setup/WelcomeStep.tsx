"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field, Msg, StepFrame, btnCls, inputCls } from "@/components/setup/StepFrame";

export function WelcomeStep() {
  const [status, setStatus] = useState<{ home?: string; home_label?: string; error?: string } | null>(null);
  const [label, setLabel] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    api("/setup/status").then((r) => {
      setStatus(r);
      setLabel(r?.home_label ?? "");
    });
  }, []);
  const save = async () => {
    const r = await api("/setup/label", { body: { home_label: label } });
    setMsg(r.error ? `Not saved: ${r.error}` : "Saved.");
    return !r.error;
  };
  return (
    <StepFrame href="/setup" title="Welcome to focos" onNext={save}
      intro="focos reads your bank, card, loan, and brokerage data on your own computer, runs the math locally, and asks an AI of your choice to write you a short brief on a schedule. Nothing is uploaded except the questions sent to the AI provider you pick.">
      {status?.error ? <Msg kind="bad">{status.error}</Msg> : null}
      <div className="space-y-4">
        <Field label="Your data folder" hint="Config, history, and briefs live here. Back it up like any other folder.">
          <code className="block rounded-[4px] bg-panel-2 px-2 py-1.5 text-[12px]">{status?.home ?? "…"}</code>
        </Field>
        <Field label="Household name" hint="Shown in the dashboard header; anything you like.">
          <input className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="The Example household" />
        </Field>
        <button type="button" className={btnCls} onClick={save}>Save</button>
        <Msg>{msg}</Msg>
        <div className="grid gap-3 text-[12px] text-secondary sm:grid-cols-3">
          <div className="rounded-[6px] border border-hairline p-3"><b className="text-ink">1. AI</b><br />Paste one API key (Anthropic, OpenAI, Gemini) or use a local model.</div>
          <div className="rounded-[6px] border border-hairline p-3"><b className="text-ink">2. Banks</b><br />A SimpleFIN setup token connects every account read-only.</div>
          <div className="rounded-[6px] border border-hairline p-3"><b className="text-ink">3. Profile</b><br />A five-minute interview fills in goals and context.</div>
        </div>
      </div>
    </StepFrame>
  );
}
