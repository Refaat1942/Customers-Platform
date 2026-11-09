import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { Award, Calendar, MapPin, Package, ShoppingBag, Store, Tag } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtPct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import { Card, Empty, ErrorBox, ExportButton, Kpi, Notice, PageHeader, PrintButton, Spinner } from "../components/ui";
import { RankBars, ShareBar, TrendChart } from "../components/charts";
import DataTable from "../components/DataTable";

const change = (cur?: number, prev?: number) => (prev ? (100 * ((cur ?? 0) - prev)) / prev : null);

export default function Dashboard() {
  const { t } = useTranslation();
  const { params, key, meta } = useFilters();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["summary", ...key], queryFn: () => api.get("/summary", params) });
  const d = q.data;
  const prev = d?.previous;

  return (
    <>
      <PageHeader title={t("nav.dashboard")}
        subtitle={meta?.last_import ? `${fmtInt(meta.rows)} ${t("app.rows")} · ${meta.last_import.filename} · ${fmtDate(meta.last_import.finished_at, true)}` : undefined}
        actions={<><ExportButton path="/summary" params={params} /><PrintButton /></>} />
      {meta && meta.rows === 0 && meta.directory_customers > 0 && (
        <div className="mb-5"><Notice kind="info">
          <div className="font-semibold mb-1">{t("base.noSalesTitle")}</div>
          <div>{t("base.noSales", { n: fmtInt(meta.directory_customers) })}</div>
          <div className="flex gap-2 mt-3">
            <Link to="/customer-base" className="btn-primary">{t("base.openBase")}</Link>
            <Link to="/import" className="btn-ghost">{t("base.uploadSales")}</Link>
          </div>
        </Notice></div>
      )}
      <FilterBar />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : !d || d.kpis.lines === 0 ? <Empty /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
            <Kpi label={t("kpi.sales")} value={fmtInt(d.kpis.total_sales)} change={change(d.kpis.total_sales, prev?.total_sales)} />
            <Kpi label={t("kpi.customers")} value={fmtInt(d.kpis.customers)} change={change(d.kpis.customers, prev?.customers)} />
            <Kpi label={t("kpi.invoices")} value={fmtInt(d.kpis.invoices)} change={change(d.kpis.invoices, prev?.invoices)} />
            <Kpi label={t("kpi.avgCustomer")} value={fmtMoney(d.kpis.avg_per_customer)} change={change(d.kpis.avg_per_customer, prev?.avg_per_customer)} />
            <Kpi label={t("kpi.avgInvoice")} value={fmtMoney(d.kpis.avg_invoice)} change={change(d.kpis.avg_invoice, prev?.avg_invoice)} />
            <Kpi label={t("kpi.newCustomers")} value={d.new_customers == null ? "–" : fmtInt(d.new_customers)}
              sub={d.new_customers != null && d.kpis.customers ? fmtPct((100 * d.new_customers) / d.kpis.customers) : undefined} />
          </div>

          <Card title={t("dash.customerStatus")} help={d.reference_date ? `${t("app.referenceDate")} ${fmtDate(d.reference_date)}` : undefined}
            actions={<>
              <ExportButton path="/customers" params={{ ...params, flag: "high_value", view: "recommendations" }} label={t("dash.downloadHighValue")} />
              <ExportButton path="/customers" params={{ ...params, status: ["inactive"], view: "recommendations" }} label={t("dash.downloadAtRisk")} />
            </>}>
            <ShareBar parts={[
              { label: t("status.active"), value: d.segments.active, color: "#1a7f37" },
              { label: t("status.attention"), value: d.segments.attention, color: "#eda100" },
              { label: t("status.inactive"), value: d.segments.inactive, color: "#c62828" },
            ]} />
            <div className="flex flex-wrap gap-6 mt-4 text-sm">
              <button className="hover:underline cursor-pointer" onClick={() => nav("/customers?flag=high_value")}>{t("kpi.highValue")}: <b className="num">{fmtInt(d.segments.high_value)}</b></button>
              <button className="hover:underline cursor-pointer" onClick={() => nav("/customers?flag=loyal")}>{t("kpi.loyal")}: <b className="num">{fmtInt(d.segments.loyal)}</b></button>
              {d.segments.invalid_phone > 0 && <button className="hover:underline cursor-pointer text-warn" onClick={() => nav("/customers?flag=invalid_phone")}>{t("kpi.invalidPhone")}: <b className="num">{fmtInt(d.segments.invalid_phone)}</b></button>}
            </div>
          </Card>

          <div className="grid lg:grid-cols-3 gap-5">
            <Card title={t("dash.monthly")} className="lg:col-span-2">
              {d.monthly.length ? <TrendChart data={d.monthly} x="month" y="sales" name={t("col.sales")} /> : <Empty />}
            </Card>
            <Card title={t("dash.insights")}>
              <ul className="space-y-3 text-sm">
                {([
                  ["topBranch", d.insights.top_branch, Store],
                  ["topDistrict", d.insights.top_district, MapPin],
                  ["topItem", d.insights.top_item, Package],
                  ["topCategory", d.insights.top_category, Tag],
                  ["topMaterial", d.insights.top_material, ShoppingBag],
                  ["topSalesType", d.insights.top_sales_type, Award],
                  ["topSeason", d.insights.top_season ? t(`seasons.${d.insights.top_season}`) : null, Calendar],
                ] as const).map(([k, v, Icon]) => (
                  <li key={k} className="flex items-center gap-3">
                    <span className="size-8 rounded-lg bg-brand-soft text-brand grid place-items-center shrink-0"><Icon size={16} /></span>
                    <span className="text-muted flex-1">{t(`dash.${k}`)}</span>
                    <span className="font-semibold text-end truncate max-w-[50%]" title={v ?? ""}>{v ?? "–"}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("dash.byBranch")}>
              <RankBars data={d.by_branch.slice(0, 15)} label="branch" value="sales" name={t("col.sales")} />
              <div className="mt-4">
                <DataTable rows={d.by_branch} maxHeight={260} columns={[
                  { key: "branch", label: t("col.branch") },
                  { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
                  { key: "customers", label: t("col.customers"), num: true, render: (r) => fmtInt(r.customers) },
                  { key: "invoices", label: t("col.invoices"), num: true, render: (r) => fmtInt(r.invoices) },
                  { key: "avg_per_customer", label: t("col.spend_per_customer"), num: true, render: (r) => fmtMoney(r.avg_per_customer) },
                ]} />
              </div>
            </Card>
            <Card title={t("dash.topItems")}>
              <RankBars data={d.top_items} label="item" value="sales" name={t("col.sales")} />
            </Card>
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("dash.byType")}>
              {d.by_type.length ? <RankBars data={d.by_type} label="sales_type" value="sales" name={t("col.sales")} /> : <Empty />}
            </Card>
            <Card title={t("dash.bySeason")}>
              <RankBars data={d.by_season.map((s: any) => ({ ...s, label: t(`seasons.${s.season}`) }))} label="label" value="sales" name={t("col.sales")} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
