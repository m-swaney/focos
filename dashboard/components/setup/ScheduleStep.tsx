"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field, Msg, StepFrame, btnCls, inputCls } from "@/components/setup/StepFrame";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export function ScheduleStep() {
  const [s, setS] = useState({ daily: { days: "weekdays", time: "16:35" }, weekly: { day: "sun", time: "18:00" }, monthly: { day: 1, time: "19:00" } });
  const [tz, setTz] = useState("");
  const [platform, setPlatform] = useState("");
  const [jobs, setJobs] = useState<{ name: string; installed: boolean; next_run?: string | null; detail?: { error?: string } }[]>([]);
  const [msg, setMsg] = useState<{ kind: "info" | "ok" | "warn" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/schedule/status").then((r) => {
      if (r.error) return;
      if (r.schedule) setS(r.schedule);
      setPlatform(r.platform ?? "");
      setJobs(r.jobs ?? []);
      setTz(r.timezone && r.timezone !== "America/New_York" ? r.timezone : Intl.DateTimeFormat().resolvedOptions().timeZone || r.timezone);
    });
  }, []);

  const install = async () => {
    setBusy(true);
    const r = await api("/schedule/install", { body: { schedule: s, timezone: tz, install: true } });
    setBusy(false);
    if (r.error) { setMsg({ kind: "bad", text: r.error }); return; }
    setJobs(r.jobs ?? []);
    const bad = (r.jobs ?? []).filter((j: { installed: boolean }) => !j.installed);
    setMsg(bad.length ? { kind: "warn", text: `Saved, but ${bad.length} job(s) did not install: ${bad.map((j: { detail?: { error?: string } }) => j.detail?.error).join("; ")}` }
                      : { kind: "ok", text: `Installed on ${r.platform}. The next daily run is ${r.jobs?.[0]?.next_run ?? "scheduled"}.` });
  };
  const installed = jobs.some((j) => j.installed);

  return (
    <StepFrame href="/setup/schedule" title="When should it run?" canNext={installed}
      intro={`focos runs on this computer while you are logged in (${platform === "windows" ? "Windows Task Scheduler" : platform === "macos" ? "launchd" : "your system scheduler"}); a sleeping laptop wakes for the daily run when the system allows it. Times are local.`}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Daily brief">
          <div className="flex gap-2">
            <select className={inputCls} value={s.daily.days} onChange={(e) => setS({ ...s, daily: { ...s.daily, days: e.target.value } })}><option value="weekdays">weekdays</option><option value="daily">every day</option></select>
            <input className={inputCls} type="time" value={s.daily.time} onChange={(e) => setS({ ...s, daily: { ...s.daily, time: e.target.value } })} />
          </div>
        </Field>
        <Field label="Weekly deep dive">
          <div className="flex gap-2">
            <select className={inputCls} value={s.weekly.day} onChange={(e) => setS({ ...s, weekly: { ...s.weekly, day: e.target.value } })}>{DAYS.map((d) => <option key={d} value={d}>{d}</option>)}</select>
            <input className={inputCls} type="time" value={s.weekly.time} onChange={(e) => setS({ ...s, weekly: { ...s.weekly, time: e.target.value } })} />
          </div>
        </Field>
        <Field label="Monthly review">
          <div className="flex gap-2">
            <select className={inputCls} value={s.monthly.day} onChange={(e) => setS({ ...s, monthly: { ...s.monthly, day: Number(e.target.value) } })}>{Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>day {d}</option>)}</select>
            <input className={inputCls} type="time" value={s.monthly.time} onChange={(e) => setS({ ...s, monthly: { ...s.monthly, time: e.target.value } })} />
          </div>
        </Field>
      </div>
      <div className="mt-4 max-w-[360px]">
        <Field label="Time zone" hint="Detected from this browser.">
          <input className={inputCls} value={tz} onChange={(e) => setTz(e.target.value)} />
        </Field>
      </div>
      <div className="mt-4"><button type="button" className={btnCls} disabled={busy} onClick={install}>Save and install schedule</button></div>
      {msg ? <Msg kind={msg.kind}>{msg.text}</Msg> : null}
      {jobs.length ? (
        <ul className="mt-3 text-[12px] text-secondary">
          {jobs.map((j) => <li key={j.name}>{j.installed ? "✓" : "–"} {j.name}{j.next_run ? ` · next ${j.next_run}` : ""}</li>)}
        </ul>
      ) : null}
    </StepFrame>
  );
}
