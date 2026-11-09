import i18n from "../i18n";

const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

export const fmtInt = (v: number | null | undefined) => (v == null ? "–" : nf0.format(v));
export const fmtMoney = (v: number | null | undefined) => (v == null ? "–" : nf2.format(v));
export const fmtNum = (v: number | null | undefined) => (v == null ? "–" : nf1.format(v));
export const fmtPct = (v: number | null | undefined) => (v == null ? "–" : `${nf1.format(v)}%`);

export function fmtCompact(v: number | null | undefined) {
  if (v == null) return "–";
  const a = Math.abs(v);
  if (a >= 1e6) return `${nf1.format(v / 1e6)}M`;
  if (a >= 1e3) return `${nf1.format(v / 1e3)}K`;
  return nf0.format(v);
}

export function fmtDate(v: string | null | undefined, withTime = false) {
  if (!v) return "–";
  const d = new Date(v);
  if (isNaN(d.getTime())) return v;
  const loc = i18n.language === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
  return d.toLocaleDateString(loc, { year: "numeric", month: "short", day: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) });
}

export function fmtBytes(n: number) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}

export function isoDate(d: Date) {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
