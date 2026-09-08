"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { btnCls, btnQuietCls, inputCls } from "@/components/setup/StepFrame";

type About = { type: string; id?: string };

/**
 * A place to tell your chief of staff something. The note is saved to state/inbox.jsonl and read on the next run.
 * `compact` renders a "Reply" button that reveals a one-line input (used next to questions on the home page).
 */
export function NoteBox({ about, compact = false, placeholder }: { about?: About; compact?: boolean; placeholder?: string }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(!compact);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const router = useRouter();

  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    const r = await api("/inbox", { body: { text: text.trim(), about } });
    setBusy(false);
    if (r.error || !r.ok) {
      setMsg({ ok: false, text: r.error ?? "could not save the note" });
      return;
    }
    setText("");
    setMsg({ ok: true, text: "Saved. Your chief of staff reads it on the next run." });
    if (compact) setOpen(false);
    router.refresh();
  };

  if (compact && !open)
    return (
      <span className="inline-flex items-center gap-2">
        <button type="button" className={btnQuietCls} onClick={() => setOpen(true)}>
          Reply
        </button>
        {msg ? <span className={`text-[11px] ${msg.ok ? "text-secondary" : "text-critical"}`}>{msg.text}</span> : null}
      </span>
    );

  return (
    <div className={compact ? "flex w-full flex-wrap items-center gap-2" : "space-y-2"}>
      {compact ? (
        <input
          className={`${inputCls} min-w-[220px] flex-1`}
          value={text}
          autoFocus
          placeholder={placeholder ?? "Your answer"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
            if (e.key === "Escape") setOpen(false);
          }}
        />
      ) : (
        <textarea
          className={`${inputCls} min-h-[72px]`}
          value={text}
          placeholder={placeholder ?? "Anything that changed, a correction, or a question. Example: the payroll withholding is fixed as of this month."}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={btnCls} disabled={busy || !text.trim()} onClick={send}>
          {compact ? "Send" : "Tell your chief of staff"}
        </button>
        {compact ? (
          <button type="button" className={btnQuietCls} onClick={() => setOpen(false)}>
            Cancel
          </button>
        ) : null}
        {msg ? <span className={`text-[11px] ${msg.ok ? "text-secondary" : "text-critical"}`}>{msg.text}</span> : null}
      </div>
    </div>
  );
}
