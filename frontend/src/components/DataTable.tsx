import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Download, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtInt } from "../lib/format";
import { useBranchName } from "../lib/filters";

const BRANCH_COLS = new Set(["branch", "top_branch", "fav_branch", "registered_branch"]);

export type Column<T> = {
  key: string; label: string; render?: (row: T) => ReactNode; sortable?: boolean; num?: boolean;
  className?: string;
  /** value used for sorting / Excel when the cell is rendered from several fields */
  value?: (row: T) => unknown;
};

type Props<T> = {
  columns: Column<T>[]; rows: T[]; total?: number; page?: number; pageSize?: number;
  onPage?: (p: number) => void; sort?: string; desc?: boolean; onSort?: (key: string, desc: boolean) => void;
  onRowClick?: (row: T) => void; loading?: boolean; empty?: string; maxHeight?: number;
  /** name of the Excel file / sheet for the table's own Excel button */
  title?: string;
  /** hide the table's own Excel button (pages that export the full filtered list themselves) */
  noExport?: boolean;
};

const raw = <T,>(c: Column<T>, r: T) => (c.value ? c.value(r) : (r as any)[c.key]);

function compare(a: unknown, b: unknown) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;   // empty values always last
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  const na = Number(a), nb = Number(b);
  if (a !== "" && b !== "" && !isNaN(na) && !isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

export default function DataTable<T extends Record<string, any>>(p: Props<T>) {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const branchName = useBranchName();
  const rtl = i18n.language === "ar";
  const server = !!p.onSort;               // sorted by the server (paged lists)
  const [lsort, setLsort] = useState<string | null>(null);
  const [ldesc, setLdesc] = useState(true);
  const [busy, setBusy] = useState(false);

  const sortable = (c: Column<T>) => (server ? !!c.sortable : c.key !== "x" && c.key !== "check" &&
    p.rows.some((r) => raw(c, r) !== undefined));
  const sortKey = server ? p.sort : lsort;
  const sortDesc = server ? p.desc : ldesc;

  const rows = useMemo(() => {
    if (server || !lsort) return p.rows;
    const col = p.columns.find((c) => c.key === lsort);
    if (!col) return p.rows;
    const out = [...p.rows].sort((a, b) => compare(raw(col, a), raw(col, b)));
    return ldesc ? out.reverse().sort((a, b) => (raw(col, a) == null ? 1 : 0) - (raw(col, b) == null ? 1 : 0)) : out;
  }, [p.rows, p.columns, lsort, ldesc, server]);

  const clickHeader = (c: Column<T>) => {
    if (!sortable(c)) return;
    const next = sortKey === c.key ? !sortDesc : true;   // first click: highest / newest / Z first
    if (server) p.onSort!(c.key, next);
    else { setLsort(c.key); setLdesc(next); }
  };

  const exportXlsx = async () => {
    const cols = p.columns.filter((c) => c.key !== "x" && rows.some((r) => raw(c, r) !== undefined));
    setBusy(true);
    try {
      const res = await api.raw("POST", "/export/table", {
        title: p.title || document.title, lang: i18n.language,
        columns: cols.map((c) => c.label || c.key),
        rows: rows.map((r) => cols.map((c) => {
          const v = raw(c, r);
          return v === null || v === undefined ? null : typeof v === "object" ? (Array.isArray(v) ? v.join(", ") : JSON.stringify(v)) : v;
        })),
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${(p.title || "table").replace(/[\\/:*?"<>|]/g, "")}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  };

  const pages = p.total != null && p.pageSize ? Math.max(1, Math.ceil(p.total / p.pageSize)) : 1;
  const showExport = !p.noExport && !p.onPage && can("export") && rows.length > 0;
  return (
    <div>
      {showExport && (
        <div className="flex justify-end -mt-1 mb-2 no-print">
          <button className="text-xs text-muted hover:text-brand inline-flex items-center gap-1 cursor-pointer" onClick={exportXlsx} disabled={busy}
            title={t("table.excelHint")}>
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} {t("table.excel")}
          </button>
        </div>
      )}
      <div className={clsx("overflow-auto border border-line rounded-lg", p.loading && "opacity-60")} style={{ maxHeight: p.maxHeight }}>
        <table className="w-full border-collapse">
          <thead className="bg-surface sticky top-0 z-10">
            <tr>
              {p.columns.map((c) => {
                const active = sortKey === c.key;
                const can = sortable(c);
                return (
                  <th key={c.key} className={clsx("th", c.num && "text-end", can && "cursor-pointer hover:text-ink group")}
                    onClick={() => clickHeader(c)} title={can ? t("table.sortHint") : undefined}>
                    <span className={clsx("inline-flex items-center gap-1", c.num && "flex-row-reverse")}>
                      {c.label}
                      {active ? (sortDesc ? <ArrowDown size={12} className="text-brand" /> : <ArrowUp size={12} className="text-brand" />)
                        : can && <ArrowUpDown size={11} className="opacity-0 group-hover:opacity-60" />}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} onClick={() => p.onRowClick?.(r)}
                className={clsx("border-t border-line", p.onRowClick && "cursor-pointer hover:bg-brand-soft")}>
                {p.columns.map((c) => (
                  <td key={c.key} className={clsx("td", c.num && "text-end num", c.className)}>
                    {c.render ? c.render(r) : BRANCH_COLS.has(c.key) && r[c.key] ? branchName(r[c.key]) : (r[c.key] ?? "–")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && !p.loading && <div className="text-center text-muted text-sm py-10">{p.empty ?? t("app.noData")}</div>}
      </div>
      {p.onPage && p.total != null && p.total > (p.pageSize ?? 0) && (
        <div className="flex items-center justify-between mt-3 text-sm text-muted no-print">
          <span className="num">{fmtInt(((p.page ?? 1) - 1) * (p.pageSize ?? 0) + 1)}–{fmtInt(Math.min((p.page ?? 1) * (p.pageSize ?? 0), p.total))} {t("app.of")} {fmtInt(p.total)}</span>
          <div className="flex items-center gap-2">
            <button className="btn-ghost px-2" disabled={(p.page ?? 1) <= 1} onClick={() => p.onPage!((p.page ?? 1) - 1)}>
              {rtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
            <span className="num">{t("app.page")} {p.page} / {fmtInt(pages)}</span>
            <button className="btn-ghost px-2" disabled={(p.page ?? 1) >= pages} onClick={() => p.onPage!((p.page ?? 1) + 1)}>
              {rtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
