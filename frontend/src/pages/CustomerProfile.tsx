import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Phone } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, ErrorBox, ExportButton, Kpi, PageHeader, PrintButton, Spinner } from "../components/ui";
import { RankBars, TrendChart } from "../components/charts";

export default function CustomerProfile() {
  const { t, i18n } = useTranslation();
  const { cid } = useParams();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["customer", cid, ...key], queryFn: () => api.get(`/customers/${cid}`, params) });
  const d = q.data;
  const s = d?.summary;
  const Back = i18n.language === "ar" ? ArrowRight : ArrowLeft;

  return (
    <>
      <button className="btn-ghost mb-4 no-print" onClick={() => nav(-1)}><Back size={16} /> {t("cust.back")}</button>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : s && (
        <div className="space-y-5">
          <PageHeader title={s.name || s.phone} subtitle={t("cust.profile")}
            actions={<><ExportButton path={`/customers/${cid}`} params={params} /><PrintButton /></>} />
          <div className="card p-5 flex flex-wrap items-center gap-x-8 gap-y-3">
            <div className="flex items-center gap-2 font-mono text-lg"><Phone size={18} className="text-brand" />
              {s.phone && !s.phone.includes("*") ? <a href={`tel:${s.phone}`} className="hover:underline">{s.phone}</a> : s.phone}
            </div>
            <Badge kind={s.status}>{t(`status.${s.status}`)}</Badge>
            <Badge>{t(`seg.${s.segment}`)}</Badge>
            <span className="text-sm">{t("col.churn_risk")}: <Badge kind={s.churn_risk}>{t(`risk.${s.churn_risk}`)}</Badge></span>
            {s.high_value && <Badge kind="active">{t("kpi.highValue")}</Badge>}
            {s.loyal && <Badge kind="active">{t("kpi.loyal")}</Badge>}
            <span className="text-sm ms-auto font-semibold text-brand">→ {t(`action.${s.action}`)}</span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
            <Kpi label={t("col.total_spent")} value={fmtMoney(s.total_spent)} />
            <Kpi label={t("col.visits")} value={fmtInt(s.visits)} />
            <Kpi label={t("col.avg_per_visit")} value={fmtMoney(s.avg_per_visit)} />
            <Kpi label={t("col.last_visit")} value={fmtDate(s.last_visit)} sub={`${fmtInt(s.days_since)} ${i18n.language === "ar" ? "يوم" : "days ago"}`} />
            <Kpi label={t("col.avg_days_between")} value={fmtNum(s.avg_days_between)} sub={`${t("col.first_visit")}: ${fmtDate(s.first_visit)}`} />
            <Kpi label={t("col.expected_next")} value={fmtDate(s.expected_next)}
              sub={s.overdue_days > 0 ? `${fmtInt(s.overdue_days)} ${t("col.overdue_days")}` : undefined} />
          </div>

          <div className="card p-5 grid sm:grid-cols-2 lg:grid-cols-5 gap-4 text-sm">
            {(["branch", "district", "top_category", "top_material", "top_sales_type"] as const).map((k) => (
              <div key={k}><div className="text-muted text-xs">{t(`col.${k}`)}</div><div className="font-semibold">{s[k] ?? "–"}</div></div>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("cust.monthlySpend")}><TrendChart data={d.monthly} x="month" y="sales" name={t("col.sales")} height={220} /></Card>
            <Card title={t("cust.favourite")}><RankBars data={d.top_items.slice(0, 10)} label="item" value="sales" name={t("col.sales")} /></Card>
          </div>

          <Card title={t("cust.visitsHistory")}>
            <DataTable rows={d.visits} maxHeight={480} columns={[
              { key: "date", label: t("col.date"), render: (r) => fmtDate(r.date, true) },
              { key: "branch", label: t("col.branch") },
              { key: "sales_type", label: t("col.invoice_type") },
              { key: "lines", label: t("col.lines"), num: true },
              { key: "total", label: t("col.total"), num: true, render: (r) => fmtMoney(r.total) },
              { key: "items", label: t("col.items"), className: "max-w-md truncate whitespace-normal" },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
