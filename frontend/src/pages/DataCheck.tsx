import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtInt, fmtMoney } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, ErrorBox, Kpi, Notice, PageHeader, Spinner } from "../components/ui";

export default function DataCheck() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["data-check"], queryFn: () => api.get("/maintenance/data-check"), staleTime: 0 });
  const [done, setDone] = useState(false);
  const refresh = async () => {
    await api.post("/maintenance/refresh");
    await qc.invalidateQueries();
    setDone(true);
  };
  const d = q.data;
  const range = (r: any) => (r.date_from ? `${fmtDate(r.date_from)} → ${fmtDate(r.date_to)}` : "–");
  return (
    <>
      <PageHeader title={t("dc.title")} subtitle={t("dc.subtitle")}
        actions={<button className="btn-primary" onClick={refresh}><RefreshCw size={16} /> {t("dc.refresh")}</button>} />
      {done && <div className="mb-5"><Notice kind="success">{t("dc.refreshed")}</Notice></div>}
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : d && (
        <div className="space-y-5">
          <div className="text-xs text-muted">{t("dc.checked")}: {fmtDate(d.checked_at, true)}</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Kpi label={t("dc.lines")} value={fmtInt(d.totals.lines)} />
            <Kpi label={t("dc.customers")} value={fmtInt(d.totals.customers)} />
            <Kpi label={t("dc.invoices")} value={fmtInt(d.totals.invoices)} />
            <Kpi label={t("dc.sales")} value={fmtInt(d.totals.sales)} />
            <Kpi label={t("dc.range")} value={d.totals.date_from ? fmtDate(d.totals.date_from) : "–"} sub={d.totals.date_to ? `→ ${fmtDate(d.totals.date_to)}` : undefined} />
            <Kpi label={t("dc.noPhone")} value={fmtInt(d.totals.lines_without_phone)} />
            <Kpi label={t("dc.pos")} value={fmtInt(d.totals.pos_lines)} />
            <Kpi label={t("dc.listed")} value={fmtInt(d.directory.customers)} />
          </div>
          <Card title={t("dc.imports")}>
            <DataTable rows={d.imports} maxHeight={480} columns={[
              { key: "id", label: "#", num: true },
              { key: "filename", label: "File", className: "max-w-72 truncate" },
              { key: "kind", label: t("imp.kind"), render: (r) => <Badge>{t(`imp.kinds.${r.kind ?? "sales"}`)}</Badge> },
              { key: "rows_imported", label: t("dc.rowsAdded"), num: true, render: (r) => fmtInt(r.rows_imported) },
              { key: "rows_now", label: t("dc.rowsNow"), num: true, render: (r) => <b>{fmtInt(r.rows_now)}</b> },
              { key: "check", label: "", render: (r) => r.status === "running" ? <Badge kind="attention">…</Badge>
                  : r.rows_now >= r.rows_imported ? <Badge kind="active">{t("dc.ok")}</Badge>
                  : <span title={t("dc.removed")}><Badge kind="attention">−{fmtInt(r.rows_imported - r.rows_now)}</Badge></span> },
              { key: "sales", label: t("dc.sales"), num: true, render: (r) => (r.sales == null ? "–" : fmtMoney(r.sales)) },
              { key: "range", label: t("dc.range"), render: range },
              { key: "finished_at", label: t("audit.time"), render: (r) => fmtDate(r.finished_at, true) },
            ]} />
          </Card>
          <div className="grid xl:grid-cols-2 gap-5">
            <Card title={t("dc.byType")}>
              <DataTable rows={d.by_type} columns={[
                { key: "sales_type", label: t("col.invoice_type") },
                { key: "lines", label: t("dc.lines"), num: true, render: (r) => fmtInt(r.lines) },
                { key: "customers", label: t("col.customers"), num: true, render: (r) => fmtInt(r.customers) },
                { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
              ]} />
            </Card>
            <Card title={t("dc.byBranch")}>
              <DataTable rows={d.by_branch} maxHeight={400} columns={[
                { key: "branch", label: t("col.branch") },
                { key: "lines", label: t("dc.lines"), num: true, render: (r) => fmtInt(r.lines) },
                { key: "customers", label: t("col.customers"), num: true, render: (r) => fmtInt(r.customers) },
                { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
                { key: "range", label: t("dc.range"), render: range },
              ]} />
            </Card>
          </div>
          <Card title={t("dc.byMonth")}>
            <DataTable rows={d.by_month} maxHeight={480} columns={[
              { key: "month", label: t("col.month") },
              { key: "lines", label: t("dc.lines"), num: true, render: (r) => fmtInt(r.lines) },
              { key: "customers", label: t("col.customers"), num: true, render: (r) => fmtInt(r.customers) },
              { key: "invoices", label: t("col.invoices"), num: true, render: (r) => fmtInt(r.invoices) },
              { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
