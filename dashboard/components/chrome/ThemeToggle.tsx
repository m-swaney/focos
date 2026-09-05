"use client";

import { useEffect } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { THEME_KEY, applyTheme } from "@/lib/theme";
import { useLocalStorage } from "@/lib/useLocalStorage";

type Choice = "system" | "light" | "dark";

const OPTIONS: { value: Choice; icon: IconName; label: string }[] = [
  { value: "system", icon: "monitor", label: "System" },
  { value: "light", icon: "sun", label: "Light" },
  { value: "dark", icon: "moon", label: "Dark" },
];

function apply(choice: Choice) {
  const root = document.documentElement;
  const resolved = choice === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : choice;
  root.classList.add("theme-transition");
  applyTheme(resolved);
  window.setTimeout(() => root.classList.remove("theme-transition"), 200);
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [stored, setStored] = useLocalStorage(THEME_KEY);
  const choice: Choice | null = stored == null ? null : stored === "light" || stored === "dark" ? stored : "system";

  useEffect(() => {
    if (choice !== "system") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [choice]);

  const select = (c: Choice) => {
    setStored(c === "system" ? null : c);
    apply(c);
  };

  return (
    <div role="radiogroup" aria-label="Theme" className={`grid grid-cols-3 rounded-[4px] border border-hairline p-0.5 ${className}`}>
      {OPTIONS.map((o) => {
        const active = choice === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={o.label}
            title={o.label}
            onClick={() => select(o.value)}
            className={`flex items-center justify-center gap-1 rounded-[3px] py-1 text-[11px] ${active ? "bg-panel-2 text-ink" : "text-muted hover:text-ink"}`}
          >
            <Icon name={o.icon} size={12} />
          </button>
        );
      })}
    </div>
  );
}
