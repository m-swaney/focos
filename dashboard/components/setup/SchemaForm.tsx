"use client";

import { inputCls } from "@/components/setup/StepFrame";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Schema = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Value = any;

function unwrap(s: Schema): { schema: Schema; nullable: boolean } {
  if (s?.anyOf) {
    const non = s.anyOf.filter((x: Schema) => x.type !== "null");
    return { schema: non[0] ?? {}, nullable: non.length < s.anyOf.length };
  }
  return { schema: s ?? {}, nullable: false };
}

function humanize(k: string): string {
  return k.replace(/_/g, " ").replace(/\bpct\b/, "%").replace(/^./, (c) => c.toUpperCase());
}

/** Renders inputs for a JSON-schema object one level deep; nested objects recurse, lists of objects become JSON. */
export function SchemaForm({ schema, value, onChange, depth = 0 }: { schema: Schema; value: Value; onChange: (v: Value) => void; depth?: number }) {
  const props: Record<string, Schema> = schema?.properties ?? {};
  const v = value ?? {};
  const set = (k: string, x: Value) => onChange({ ...v, [k]: x });
  return (
    <div className={`grid gap-3 ${depth === 0 ? "sm:grid-cols-2" : ""}`}>
      {Object.entries(props).map(([k, raw]) => {
        const { schema: s, nullable } = unwrap(raw);
        const label = humanize(k);
        const desc = raw?.description ?? s?.description;
        const cur = v[k];
        let field: React.ReactNode;
        if (s.enum) {
          field = (
            <select className={inputCls} value={cur ?? ""} onChange={(e) => set(k, e.target.value === "" ? null : e.target.value)}>
              {nullable || cur == null ? <option value="">—</option> : null}
              {s.enum.map((o: string) => <option key={o} value={o}>{o}</option>)}
            </select>
          );
        } else if (s.type === "boolean") {
          field = (
            <select className={inputCls} value={cur == null ? "" : String(cur)} onChange={(e) => set(k, e.target.value === "" ? null : e.target.value === "true")}>
              <option value="">unknown</option><option value="true">yes</option><option value="false">no</option>
            </select>
          );
        } else if (s.type === "number" || s.type === "integer") {
          field = <input className={inputCls} type="number" step={s.type === "integer" ? 1 : "any"} value={cur ?? ""} onChange={(e) => set(k, e.target.value === "" ? null : Number(e.target.value))} />;
        } else if (s.type === "array" && (s.items?.type === "string" || !s.items?.type)) {
          if (s.items?.type === "string" || !s.items) {
            field = <textarea className={`${inputCls} min-h-[60px]`} value={(cur ?? []).join("\n")} onChange={(e) => set(k, e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} placeholder="one per line" />;
          }
        }
        if (!field && (s.type === "array" || s.type === "object") && !s.properties) {
          field = (
            <textarea className={`${inputCls} min-h-[80px] font-mono text-[12px]`} defaultValue={JSON.stringify(cur ?? (s.type === "array" ? [] : {}), null, 1)}
              onBlur={(e) => { try { set(k, JSON.parse(e.target.value || (s.type === "array" ? "[]" : "{}"))); } catch { /* keep typing */ } }} />
          );
        }
        if (!field && s.type === "object" && s.properties) {
          field = <div className="rounded-[6px] border border-hairline p-3"><SchemaForm schema={s} value={cur ?? {}} onChange={(x) => set(k, x)} depth={depth + 1} /></div>;
        }
        if (!field) {
          field = <input className={inputCls} value={cur ?? ""} onChange={(e) => set(k, e.target.value === "" ? null : e.target.value)} />;
        }
        const wide = s.type === "array" || s.type === "object";
        return (
          <label key={k} className={`block ${wide ? "sm:col-span-2" : ""}`}>
            <span className="label block text-ink">{label}</span>
            {desc ? <span className="mb-1 block text-[11px] text-muted">{desc}</span> : null}
            {field}
          </label>
        );
      })}
    </div>
  );
}
