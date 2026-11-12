import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtPct } from "../lib/format";

/** "How many customers / invoices / how much sales match my filters" + split by sales type. */
export default function FilterTotals() {
  const { t } = useTranslation();
  const { params, key } = useFilters();
  const q = useQuery({ queryKey: ["customer-totals", ...key], queryFn: () => api.get("/customer-totals", params) });
  const d = q.data;
  if (!d) return <div className="card p-4 mb-5 h-24 animate-pulse" />;
  const tt = d.totals;
  return (
    <div className="card p-4 mb-5">
      <div className="text-xs font-semibold text-muted mb-3">{t("tot.title")}</div>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-3">
          {[[t("tot.customers"), fmtInt(tt.customers)], [t("tot.invoices"), fmtInt(tt.invoices)], [t("tot.sales"), fmtMoney(tt.sales)],
            [t("tot.period"), tt.date_from ? `${fmtDate(tt.date_from)} – ${fmtDate(tt.date_to)}` : "–"]].map(([l, v]) => (
            <div key={l}><div className="text-xs text-muted">{l}</div><div className="text-xl font-bold num whitespace-nowrap">{v}</div></div>
          ))}
        </div>
        {d.by_type.length > 0 && (
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead><tr>
                <th className="th">{t("tot.byType")}</th><th className="th text-end">{t("tot.customers")}</th>
                <th className="th text-end">{t("tot.invoices")}</th><th className="th text-end">{t("tot.sales")}</th><th className="th text-end">{t("tot.share")}</th>
              </tr></thead>
              <tbody>
                {d.by_type.map((r: any) => (
                  <tr key={r.sales_type} className="border-t border-line">
                    <td className="td font-medium">{r.sales_type}</td>
                    <td className="td text-end num">{fmtInt(r.customers)}</td>
                    <td className="td text-end num">{fmtInt(r.invoices)}</td>
                    <td className="td text-end num">{fmtMoney(r.sales)}</td>
                    <td className="td text-end num text-muted">{fmtPct(r.share)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
