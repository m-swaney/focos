import { Icon } from "@/components/ui/Icon";
import { health } from "@/lib/data/status";
import { ago } from "@/lib/format";

/** Shown only when the last daily run failed or is stale. Quiet otherwise. */
export function FailureBanner() {
  const h = health();
  if (h.tone !== "bad") return null;
  return (
    <div className="border-b border-hairline bg-wash-critical text-critical">
      <div className="flex w-full max-w-[1900px] flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 text-xs md:px-6 lg:px-8">
        <Icon name="critical" size={14} />
        <span className="font-medium">{h.label}</span>
        <span className="text-secondary">
          {h.stale ? `Last finished ${ago(h.hoursSinceDaily)}.` : ""} {h.detail ?? ""} Run <code className="rounded bg-panel-2 px-1">focos run --mode daily</code> to refresh, or open <a href="/health" className="underline">Health</a>.
        </span>
      </div>
    </div>
  );
}
