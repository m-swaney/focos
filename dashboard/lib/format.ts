const usd = (digits: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits, minimumFractionDigits: digits });

const isNum = (v: unknown): v is number => typeof v === "number" && !Number.isNaN(v);

export const money = (v: number | null | undefined, digits = 0) => (isNum(v) ? usd(digits).format(v) : "n/a");

/** $78.5k, $1.2M. Used on axes and in tight spaces. */
export const moneyCompact = (v: number | null | undefined) => {
  if (!isNum(v)) return "n/a";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  const trim = (x: string) => x.replace(/\.0$/, "");
  if (a >= 1e6) return `${sign}$${trim((a / 1e6).toFixed(a >= 1e7 ? 0 : 1))}M`;
  if (a >= 1e3) return `${sign}$${trim((a / 1e3).toFixed(a >= 1e5 ? 0 : 1))}k`;
  return `${sign}$${a.toFixed(0)}`;
};

export const pct = (v: number | null | undefined, digits = 1) => (isNum(v) ? `${(v * 100).toFixed(digits)}%` : "n/a");

export const signed = (v: number | null | undefined, fmt: (x: number) => string) => (isNum(v) ? `${v > 0 ? "+" : ""}${fmt(v)}` : "n/a");

export const tone = (v: number | null | undefined) => (!isNum(v) || v === 0 ? "" : v > 0 ? "text-gain" : "text-loss");

export const num = (v: number | null | undefined, digits = 2) =>
  isNum(v) ? v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }) : "n/a";

export const ago = (hours: number | null) =>
  hours == null
    ? "never"
    : hours < 1
      ? `${Math.max(1, Math.round(hours * 60))} min ago`
      : hours < 48
        ? `${hours.toFixed(hours < 10 ? 1 : 0)} h ago`
        : `${Math.round(hours / 24)} d ago`;

export const relTime = (iso: string | null | undefined, now = Date.now()) => {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = t - now;
  const h = Math.abs(diff) / 36e5;
  const past = diff < 0;
  const label = h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} d`;
  return past ? `${label} ago` : `in ${label}`;
};

const parseDate = (iso: string) => (/^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00`) : new Date(iso));

export const dateLong = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
};

export const dateShort = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export const dateMDY = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

export const dateMonthYear = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
};

export const timeShort = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
};

export const dateTime = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};

/** snake_case keys from the pipeline into plain words. */
export const humanize = (s: string | null | undefined) => {
  if (!s) return "";
  const known: Record<string, string> = {
    individual_stocks: "Individual stocks",
    us_broad_index: "US broad index",
    us_large_growth_index: "US large growth",
    international: "International",
    factor_tilts: "Factor tilts",
    small_cap: "Small cap",
    term_life: "Term life insurance",
    will_or_trust: "Will or trust",
    umbrella_liability: "Umbrella liability",
    disability: "Disability insurance",
    owner_pay: "Owner pay",
    guaranteed_payment: "Guaranteed payment",
    other_income: "Other income",
    rent: "Rent",
  };
  if (known[s]) return known[s];
  const words = s.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** Repairs UTF-8 text that was decoded as Windows code page 437 upstream. */
const MOJIBAKE: [string, string][] = [
  ["ΓÇö", "—"],
  ["ΓÇô", "–"],
  ["ΓÇÖ", "’"],
  ["ΓÇò", "‘"],
  ["ΓÇ£", "“"],
  ["ΓÇ¥", "”"],
  ["ΓÇª", "…"],
  ["Ã©", "é"],
];
export const clean = (s: string | null | undefined) => {
  if (!s) return "";
  let out = s;
  for (const [bad, good] of MOJIBAKE) out = out.split(bad).join(good);
  return out;
};
