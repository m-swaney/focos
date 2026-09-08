"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { CATEGORIES, CATEGORY_LABEL } from "@/lib/categories";
import { btnQuietCls, inputCls } from "@/components/setup/StepFrame";

/** Pick a category for a merchant: writes a user rule (beats seeds and the model) and relabels its transactions. */
export function CategoryPicker({ merchantKey, current }: { merchantKey: string; current?: string | null }) {
  const [value, setValue] = useState(current ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const router = useRouter();

  const save = async (category: string) => {
    if (!category) return;
    setBusy(true);
    setMsg("");
    const r = await api("/ledger/categories/rule", { body: { merchant_key: merchantKey, category } });
    setBusy(false);
    if (r.error || !r.ok) {
      setMsg(r.error ?? "not saved");
      return;
    }
    setMsg(`Saved, ${r.change?.after?.transactions ?? 0} charge(s) relabeled.`);
    router.refresh();
  };

  return (
    <span className="inline-flex items-center gap-2">
      <select
        className={`${inputCls} w-auto py-1 text-[12px]`}
        value={value}
        disabled={busy}
        onChange={(e) => {
          setValue(e.target.value);
          void save(e.target.value);
        }}
        aria-label={`Category for ${merchantKey}`}
      >
        <option value="">Pick a category</option>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {CATEGORY_LABEL[c]}
          </option>
        ))}
      </select>
      {current ? (
        <button type="button" className={`${btnQuietCls} px-2 py-0.5 text-[11px]`} disabled={busy} onClick={() => save(current)}>
          Keep
        </button>
      ) : null}
      {msg ? <span className="text-[11px] text-secondary">{msg}</span> : null}
    </span>
  );
}
