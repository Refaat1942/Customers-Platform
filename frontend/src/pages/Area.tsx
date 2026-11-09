import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtInt, fmtMoney, fmtPct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Card, Empty, ErrorBox, ExportButton, PageHeader, PrintButton, Spinner } from "../components/ui";
import { RankBars } from "../components/charts";

export default function Area() {
  const { t } = useTranslation();
  const { params, key, set, f } = useFilters();
  const [minC, setMinC] = useState(5);
  const p = { ...params, min_customers: minC };
  const q = useQuery({ queryKey: ["area", minC, ...key], queryFn: () => api.get("/area", p) });
  const d = q.data;
  const cols = [
    { key: "district", label: t("col.district") },
    { key: "sales", label: t("col.sales"), num: true, render: (r: any) => fmtMoney(r.sales) },
    { key: "customers", label: t("col.customers"), num: true, render: (r: any) => fmtInt(r.customers) },
    { key: "invoices", label: t("col.invoices"), num: true, render: (r: any) => fmtInt(r.invoices) },
    { key: "spend_per_customer", label: t("col.spend_per_customer"), num: true, render: (r: any) => fmtMoney(r.spend_per_customer) },
    { key: "share", label: t("col.share"), num: true, render: (r: any) => fmtPct(r.share) },
  ];
  return (
    <>
      <PageHeader title={t("area.title")} actions={<><ExportButton path="/area" params={p} /><PrintButton /></>} />
      <FilterBar />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : !d?.districts.length ? <Empty /> : (
        <div className="space-y-5">
          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("area.districts")}>
              <RankBars data={d.districts.slice(0, 15)} label="district" value="sales" name={t("col.sales")}
                onClick={(r) => r?.district && set({ district: f.district.includes(r.district) ? [] : [r.district] })} />
            </Card>
            <Card title={t("area.weak")} actions={
              <label className="text-xs text-muted flex items-center gap-2">{t("area.minCustomers")}
                <input type="number" min={1} className="input w-20 py-1" value={minC} onChange={(e) => setMinC(Math.max(1, +e.target.value || 1))} />
              </label>}>
              <DataTable rows={d.weak} columns={cols.filter((c) => c.key !== "invoices")} />
            </Card>
          </div>
          <Card title={t("area.districts")}><DataTable rows={d.districts} columns={cols} maxHeight={480} /></Card>
          <Card title={t("area.branchDistrict")}>
            <DataTable rows={d.branch_district.filter((r: any) => r.rank <= 5)} maxHeight={520} columns={[
              { key: "branch", label: t("col.branch") },
              { key: "rank", label: t("col.rank"), num: true },
              { key: "district", label: t("col.district") },
              { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
              { key: "customers", label: t("col.customers"), num: true, render: (r) => fmtInt(r.customers) },
              { key: "spend_per_customer", label: t("col.spend_per_customer"), num: true, render: (r) => fmtMoney(r.spend_per_customer) },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
