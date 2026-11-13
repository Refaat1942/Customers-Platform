import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { Search } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Badge, Card, ErrorBox, ExportButton, Kpi, PageHeader } from "../components/ui";

const STATUSES = ["due_soon", "overdue", "lapsed", "ok"] as const;
const KIND: Record<string, string> = { due_soon: "attention", overdue: "inactive", lapsed: "unknown", ok: "active" };

export default function Refills() {
  const { t } = useTranslation();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const [status, setStatus] = useState<string[]>(["due_soon", "overdue"]);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("due_date");
  const [desc, setDesc] = useState(false);
  useEffect(() => { const h = setTimeout(() => setQ(text.trim()), 350); return () => clearTimeout(h); }, [text]);
  useEffect(() => setPage(1), [q, status.join(), sort, desc, ...key]); // eslint-disable-line
  const query = { ...params, q, status, sort, desc, page, page_size: 50 };
  const res = useQuery({ queryKey: ["refills", query], queryFn: () => api.get("/refills", query), placeholderData: keepPreviousData });
  const d = res.data;
  const sm = d?.summary;
  const toggle = (s: string) => setStatus((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  return (
    <>
      <PageHeader title={t("refill.title")} subtitle={t("refill.subtitle")}
        actions={<ExportButton path="/refills" params={{ ...query, page: undefined, page_size: undefined }} />} />
      <FilterBar />
      {res.error ? <ErrorBox error={res.error} onRetry={() => res.refetch()} /> : (
        <div className="space-y-5">
          {sm && (
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
              <Kpi label={t("refill.dueSoon")} value={fmtInt(sm.due_soon)} />
              <Kpi label={t("refill.overdue")} value={fmtInt(sm.overdue)} />
              <Kpi label={t("refill.lapsed")} value={fmtInt(sm.lapsed)} />
              <Kpi label={t("refill.customers")} value={fmtInt(sm.customers_to_contact)} />
              <Kpi label={t("refill.expected")} value={fmtMoney(sm.expected_value)} />
              <Kpi label={t("refill.refillCustomers")} value={fmtInt(sm.refill_customers)} />
            </div>
          )}
          <Card help={t("refill.help")}>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {STATUSES.map((s) => (
                <button key={s} onClick={() => toggle(s)}
                  className={clsx("px-3 py-1.5 rounded-full text-sm border cursor-pointer", status.includes(s) ? "bg-brand text-white border-brand" : "bg-white border-line hover:border-brand")}>
                  {t(`refill.status.${s}`)}
                </button>
              ))}
              <div className="relative flex-1 min-w-56 ms-auto">
                <Search size={16} className="absolute top-2.5 start-3 text-muted" />
                <input className="input ps-9" placeholder={t("refill.search")} value={text} onChange={(e) => setText(e.target.value)} />
              </div>
            </div>
            {d?.reference_date && <div className="text-xs text-muted mb-2">{t("app.referenceDate")} {fmtDate(d.reference_date)}</div>}
            <DataTable rows={d?.rows ?? []} total={d?.total} page={page} pageSize={50} onPage={setPage}
              sort={sort} desc={desc} onSort={(k, dd) => { setSort(k); setDesc(dd); }} loading={res.isFetching} maxHeight={640}
              onRowClick={(r) => nav(`/customers/${r.cid}`)}
              columns={[
                { key: "phone", label: t("col.phone"), className: "font-mono text-xs" },
                { key: "name", label: t("col.name"), sortable: true, className: "max-w-44 truncate" },
                { key: "item", label: t("refill.col.item"), sortable: true, className: "max-w-64 truncate font-medium" },
                { key: "branch", label: t("col.branch"), sortable: true },
                { key: "cycle_days", label: t("refill.col.cycle_days"), sortable: true, num: true },
                { key: "last_bought", label: t("refill.col.last_bought"), render: (r) => fmtDate(r.last_bought) },
                { key: "due_date", label: t("refill.col.due_date"), sortable: true, render: (r) => <b>{fmtDate(r.due_date)}</b> },
                { key: "days_late", label: t("refill.col.days_late"), sortable: true, num: true,
                  render: (r) => (r.days_late > 0 ? <span className="text-bad font-semibold">{fmtInt(r.days_late)}</span> : <span className="text-muted">{fmtInt(r.days_late)}</span>) },
                { key: "refill_status", label: t("refill.col.refill_status"), render: (r) => <Badge kind={KIND[r.refill_status]}>{t(`refill.status.${r.refill_status}`)}</Badge> },
                { key: "purchases", label: t("refill.col.purchases"), sortable: true, num: true },
                { key: "avg_qty", label: t("refill.col.avg_qty"), num: true, render: (r) => fmtNum(r.avg_qty) },
                { key: "avg_amount", label: t("refill.col.avg_amount"), sortable: true, num: true, render: (r) => fmtMoney(r.avg_amount) },
              ]} />
          </Card>
          {d?.top_items?.length > 0 && (
            <Card title={t("refill.topItems")}>
              <DataTable rows={d.top_items} maxHeight={420} columns={[
                { key: "item", label: t("refill.col.item"), className: "font-medium" },
                { key: "customers", label: t("col.customers"), num: true, render: (r) => fmtInt(r.customers) },
                { key: "due_now", label: t("refill.dueNow"), num: true, render: (r) => fmtInt(r.due_now) },
                { key: "cycle_days", label: t("refill.col.cycle_days"), num: true },
              ]} />
            </Card>
          )}
        </div>
      )}
    </>
  );
}
