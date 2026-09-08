"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field, Msg, StepFrame, btnCls, btnQuietCls, inputCls } from "@/components/setup/StepFrame";

const PROVIDERS = [
  { key: "anthropic", label: "Anthropic (Claude)", key_hint: "ANTHROPIC_API_KEY from console.anthropic.com" },
  { key: "openai", label: "OpenAI", key_hint: "OPENAI_API_KEY from platform.openai.com" },
  { key: "gemini", label: "Google Gemini", key_hint: "GEMINI_API_KEY from aistudio.google.com" },
  { key: "ollama", label: "Ollama (local, free)", key_hint: "No key. Ollama must be running on this computer." },
];

type Models = { defaults: Record<string, string>; keys: Record<string, [boolean, string]> };

export function AiStep() {
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [agent, setAgent] = useState(false);
  const [agentAvailable, setAgentAvailable] = useState(false);
  const [models, setModels] = useState<Models | null>(null);
  const [msg, setMsg] = useState<{ kind: "info" | "ok" | "warn" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api("/setup/status").then((r) => {
      if (r?.ai) {
        setProvider(r.ai.provider ?? "anthropic");
        setModel(r.ai.model ?? "");
        setBaseUrl(r.ai.base_url ?? "");
        setAgent(r.ai.mode === "agent");
        setSaved(r.steps?.ai === "done");
      }
      setAgentAvailable(!!r?.agent_available);
    });
    api<Models>("/ai/models").then((r) => !r.error && setModels(r));
  }, []);

  const keyState = models?.keys?.[provider];

  const save = async () => {
    setBusy(true);
    const r = await api("/ai/configure", { body: { provider, model: model || null, api_key: apiKey || null, base_url: baseUrl || null, mode: agent ? "agent" : "api" } });
    setBusy(false);
    if (r.error) { setMsg({ kind: "bad", text: r.error }); return false; }
    setApiKey("");
    setSaved(r.key_ok);
    setMsg({ kind: r.key_ok ? "ok" : "warn", text: r.key_ok ? `Saved. ${r.key}.` : `Saved, but ${r.key}.` });
    const m = await api<Models>("/ai/models");
    if (!m.error) setModels(m);
    return true;
  };
  const test = async () => {
    setBusy(true);
    const r = await api("/ai/test", { body: {} });
    setBusy(false);
    setMsg(r.ok ? { kind: "ok", text: `Works: ${r.model} answered in ${r.latency_ms} ms.` }
                : { kind: "bad", text: r.error ?? "test failed" });
  };

  return (
    <StepFrame href="/setup/ai" title="Choose your AI" canNext={saved} onNext={apiKey ? save : undefined}
      intro="The AI only ever sees the summary numbers focos computes and the profile you confirm, never account numbers or raw transactions.">
      <div className="space-y-4">
        <div className="grid gap-2 sm:grid-cols-2">
          {PROVIDERS.map((p) => (
            <label key={p.key} className={`flex cursor-pointer items-start gap-2 rounded-[6px] border p-3 text-[13px] ${provider === p.key ? "border-ink" : "border-hairline hover:bg-panel-2"}`}>
              <input type="radio" name="provider" checked={provider === p.key} onChange={() => { setProvider(p.key); setModel(""); }} className="mt-1" />
              <span><b>{p.label}</b><br /><span className="text-[11px] text-muted">{p.key_hint}</span></span>
            </label>
          ))}
        </div>
        {provider !== "ollama" ? (
          <Field label="API key" hint={keyState?.[0] ? `A key is already saved (${keyState[1]}). Paste a new one to replace it.` : "Stored in your data folder's .env file, never committed."}>
            <input className={inputCls} type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={keyState?.[0] ? "••••••••" : "paste key"} />
          </Field>
        ) : (
          <Field label="Ollama URL" hint="Default http://localhost:11434/v1">
            <input className={inputCls} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:11434/v1" />
          </Field>
        )}
        <Field label="Model" hint={`Leave empty for the default (${models?.defaults?.[provider] ?? "…"}).`}>
          <input className={inputCls} value={model} onChange={(e) => setModel(e.target.value)} placeholder={models?.defaults?.[provider] ?? ""} />
        </Field>
        {agentAvailable ? (
          <label className="flex items-start gap-2 text-[12px] text-secondary">
            <input type="checkbox" checked={agent} onChange={(e) => setAgent(e.target.checked)} className="mt-0.5" />
            <span><b className="text-ink">Advanced: agent mode.</b> Claude Code was found on this computer. In agent mode it reads the data files itself and can connect Robinhood and the trading sandbox. Leave off unless you know you want this.</span>
          </label>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btnCls} disabled={busy} onClick={save}>Save</button>
          <button type="button" className={btnQuietCls} disabled={busy || !saved} onClick={test}>Test the connection</button>
        </div>
        {msg ? <Msg kind={msg.kind}>{msg.text}</Msg> : null}
      </div>
    </StepFrame>
  );
}
