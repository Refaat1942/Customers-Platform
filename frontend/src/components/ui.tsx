import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { AlertTriangle, Check, ChevronDown, Download, Info, Loader2, Printer, TrendingDown, TrendingUp, X } from "lucide-react";
import { download, type Params } from "../lib/api";
import { useAuth } from "../lib/auth";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2 no-print">{actions}</div>}
    </div>
  );
}

export function Card({ title, help, actions, children, className, pad = true }: {
  title?: ReactNode; help?: string; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={clsx("card", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-2">
          <div>
            {title && <h2 className="font-semibold">{title}</h2>}
            {help && <p className="text-xs text-muted mt-0.5 max-w-2xl">{help}</p>}
          </div>
          {actions && <div className="flex gap-2 shrink-0 no-print">{actions}</div>}
        </div>
      )}
      <div className={clsx(pad && "px-5 pb-5 pt-2")}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, change, icon }: { label: string; value: string; sub?: string; change?: number | null; icon?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between text-muted text-xs font-semibold">
        <span>{label}</span>{icon}
      </div>
      <div className="text-2xl font-bold mt-1.5 num truncate" title={value}>{value}</div>
      {change != null && isFinite(change) && (
        <div className={clsx("text-xs mt-1 flex items-center gap-1 font-medium", change >= 0 ? "text-good" : "text-bad")}>
          {change >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          <span className="num">{change >= 0 ? "+" : ""}{change.toFixed(1)}%</span>
          <span className="text-muted font-normal">{t("kpi.vsPrev")}</span>
        </div>
      )}
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-muted text-sm">
      <Loader2 className="animate-spin" size={18} /> {label ?? t("app.loading")}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="card p-5 border-red-200 bg-red-50/40 text-sm flex items-center gap-3">
      <AlertTriangle className="text-bad shrink-0" size={18} />
      <span className="flex-1">{(error as Error)?.message || t("app.error")}</span>
      {onRetry && <button className="btn-ghost" onClick={onRetry}>{t("app.retry")}</button>}
    </div>
  );
}

export function Empty({ text }: { text?: string }) {
  const { t } = useTranslation();
  return <div className="text-center text-muted text-sm py-10">{text ?? t("app.noData")}</div>;
}

const STATUS_STYLE: Record<string, string> = {
  active: "bg-green-50 text-good border-green-200",
  attention: "bg-amber-50 text-warn border-amber-200",
  inactive: "bg-red-50 text-bad border-red-200",
  unknown: "bg-gray-50 text-muted border-gray-200",
  high: "bg-red-50 text-bad border-red-200",
  medium: "bg-amber-50 text-warn border-amber-200",
  low: "bg-green-50 text-good border-green-200",
};

export function Badge({ kind, children, className }: { kind?: string; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
      (kind && STATUS_STYLE[kind]) || "bg-surface text-ink border-line", className)}>
      {kind && STATUS_STYLE[kind] && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function ExportButton({ path, params, label }: { path: string; params: Params; label?: string }) {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!can("export")) return null;
  return (
    <span className="inline-flex flex-col">
      <button className="btn-ghost" disabled={busy} onClick={async () => {
        setBusy(true); setErr(null);
        try { await download(path, { ...params, lang: i18n.language }); } catch (e) { setErr((e as Error).message); }
        setBusy(false);
      }}>
        {busy ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />} {label ?? t("app.export")}
      </button>
      {err && <span className="text-xs text-bad mt-1">{err}</span>}
    </span>
  );
}

export function PrintButton() {
  const { t } = useTranslation();
  return <button className="btn-ghost" onClick={() => window.print()}><Printer size={16} /> {t("app.print")}</button>;
}

export function MultiSelect({ label, options, value, onChange, render }: {
  label: string; options: string[]; value: string[]; onChange: (v: string[]) => void; render?: (v: string) => string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const shown = options.filter((o) => (render ? render(o) : o).toLowerCase().includes(q.toLowerCase()));
  const toggle = (o: string) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  const text = value.length === 0 ? t("app.all") : value.length === 1 ? (render ? render(value[0]) : value[0]) : `${value.length} ${t("filters.selected")}`;
  return (
    <div className="relative" ref={ref}>
      <span className="label">{label}</span>
      <button type="button" className={clsx("input flex items-center justify-between gap-2 min-w-36 text-start", value.length && "border-brand")} onClick={() => setOpen(!open)}>
        <span className="truncate max-w-40">{text}</span>
        <ChevronDown size={14} className="text-muted shrink-0" />
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-64 card p-2 shadow-lg">
          {options.length > 8 && <input autoFocus className="input mb-2" placeholder={t("app.search")} value={q} onChange={(e) => setQ(e.target.value)} />}
          <div className="max-h-64 overflow-auto">
            {shown.map((o) => (
              <label key={o} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-surface cursor-pointer text-sm">
                <input type="checkbox" className="accent-brand" checked={value.includes(o)} onChange={() => toggle(o)} />
                <span className="truncate">{render ? render(o) : o}</span>
              </label>
            ))}
            {shown.length === 0 && <div className="text-xs text-muted p-2">—</div>}
          </div>
          {value.length > 0 && <button className="btn-ghost w-full mt-2 justify-center" onClick={() => onChange([])}><X size={14} /> {t("filters.reset")}</button>}
        </div>
      )}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex items-start justify-center p-4 overflow-auto" onMouseDown={onClose}>
      <div className={clsx("card w-full mt-10 shadow-xl", wide ? "max-w-3xl" : "max-w-lg")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <h3 className="font-semibold">{title}</h3>
          <button className="text-muted hover:text-ink cursor-pointer" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "warning" | "danger" | "success"; children: ReactNode }) {
  const style = {
    info: "bg-blue-50 border-blue-200 text-blue-900",
    warning: "bg-amber-50 border-amber-200 text-amber-900",
    danger: "bg-red-50 border-red-200 text-red-900",
    success: "bg-green-50 border-green-200 text-green-900",
  }[kind];
  const Icon = kind === "success" ? Check : kind === "info" ? Info : AlertTriangle;
  return (
    <div className={clsx("rounded-lg border px-3.5 py-2.5 text-sm flex gap-2.5 items-start", style)}>
      <Icon size={16} className="mt-0.5 shrink-0" /><div className="flex-1">{children}</div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { key: T; label: string }[] }) {
  return (
    <div className="flex gap-1 border-b border-line mb-5 overflow-x-auto">
      {items.map((it) => (
        <button key={it.key} onClick={() => onChange(it.key)}
          className={clsx("px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap cursor-pointer",
            value === it.key ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink")}>
          {it.label}
        </button>
      ))}
    </div>
  );
}
