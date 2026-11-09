import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { fmtInt } from "../lib/format";

export type Column<T> = {
  key: string; label: string; render?: (row: T) => ReactNode; sortable?: boolean; num?: boolean;
  className?: string;
};

type Props<T> = {
  columns: Column<T>[]; rows: T[]; total?: number; page?: number; pageSize?: number;
  onPage?: (p: number) => void; sort?: string; desc?: boolean; onSort?: (key: string, desc: boolean) => void;
  onRowClick?: (row: T) => void; loading?: boolean; empty?: string; maxHeight?: number;
};

export default function DataTable<T extends Record<string, any>>(p: Props<T>) {
  const { t, i18n } = useTranslation();
  const rtl = i18n.language === "ar";
  const pages = p.total != null && p.pageSize ? Math.max(1, Math.ceil(p.total / p.pageSize)) : 1;
  return (
    <div>
      <div className={clsx("overflow-auto border border-line rounded-lg", p.loading && "opacity-60")} style={{ maxHeight: p.maxHeight }}>
        <table className="w-full border-collapse">
          <thead className="bg-surface sticky top-0 z-10">
            <tr>
              {p.columns.map((c) => {
                const active = p.sort === c.key;
                return (
                  <th key={c.key} className={clsx("th", c.num && "text-end", c.sortable && p.onSort && "cursor-pointer hover:text-ink")}
                    onClick={() => c.sortable && p.onSort?.(c.key, active ? !p.desc : true)}>
                    <span className="inline-flex items-center gap-1">
                      {c.label}
                      {active && (p.desc ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {p.rows.map((r, i) => (
              <tr key={i} onClick={() => p.onRowClick?.(r)}
                className={clsx("border-t border-line", p.onRowClick && "cursor-pointer hover:bg-brand-soft")}>
                {p.columns.map((c) => (
                  <td key={c.key} className={clsx("td", c.num && "text-end num", c.className)}>
                    {c.render ? c.render(r) : (r[c.key] ?? "–")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {p.rows.length === 0 && !p.loading && <div className="text-center text-muted text-sm py-10">{p.empty ?? t("app.noData")}</div>}
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
