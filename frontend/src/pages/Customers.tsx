import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable, { type Column } from "../components/DataTable";
import { Badge, ErrorBox, ExportButton, MultiSelect, PageHeader } from "../components/ui";

type View = "customers" | "business" | "recommendations";
const FLAGS = ["", "high_value", "loyal", "due_soon", "overdue", "multi_branch", "invalid_phone"];
const SEGMENTS = ["champions", "loyal", "potential", "new", "promising", "cant_lose", "at_risk", "hibernating", "lost"];

export default function Customers({ view }: { view: View }) {
  const { t } = useTranslation();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [qText, setQText] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState(view === "recommendations" ? "priority" : "total_spent");
  const [desc, setDesc] = useState(true);

  const flag = sp.get("flag") ?? "";
  const status = sp.getAll("status");
  const segment = sp.getAll("segment");
  const churn = sp.getAll("churn");
  const setList = (name: string, v: string[]) => {
    const n = new URLSearchParams(sp); n.delete(name); v.forEach((x) => n.append(name, x)); setSp(n, { replace: true });
  };

  useEffect(() => { const h = setTimeout(() => setQ(qText.trim()), 350); return () => clearTimeout(h); }, [qText]);
  useEffect(() => setPage(1), [q, flag, status.join(), segment.join(), churn.join(), sort, desc, ...key]); // eslint-disable-line

  const query = { ...params, q, flag: flag || undefined, status, segment, churn, sort, desc, page, page_size: 50, view };
  const res = useQuery({ queryKey: ["customers", query], queryFn: () => api.get("/customers", query), placeholderData: keepPreviousData });

  const c = (k: string, extra: Partial<Column<any>> = {}): Column<any> => ({ key: k, label: t(`col.${k}`), sortable: true, ...extra });
  const nameCol: Column<any>[] = [
    c("phone", { className: "font-mono text-xs" }),
    c("name", { className: "max-w-56 truncate" }),
    c("branch"),
  ];
  const cols: Record<View, Column<any>[]> = {
    customers: [
      ...nameCol, c("district", { sortable: false }),
      c("total_spent", { num: true, render: (r) => fmtMoney(r.total_spent) }),
      c("visits", { num: true, render: (r) => fmtInt(r.visits) }),
      c("last_visit", { render: (r) => fmtDate(r.last_visit) }),
      c("days_since", { num: true, render: (r) => fmtInt(r.days_since) }),
      c("avg_per_visit", { num: true, render: (r) => fmtMoney(r.avg_per_visit) }),
      c("avg_days_between", { num: true, render: (r) => fmtNum(r.avg_days_between) }),
      c("segment", { render: (r) => <Badge>{t(`seg.${r.segment}`)}</Badge> }),
      c("status", { sortable: false, render: (r) => <Badge kind={r.status}>{t(`status.${r.status}`)}</Badge> }),
    ],
    business: [
      ...nameCol,
      c("total_spent", { num: true, render: (r) => fmtMoney(r.total_spent) }),
      c("visits", { num: true, render: (r) => fmtInt(r.visits) }),
      c("top_material", { sortable: false }), c("top_category", { sortable: false }),
      c("top_sales_type", { sortable: false }),
      c("top_season", { sortable: false, render: (r) => (r.top_season ? t(`seasons.${r.top_season}`) : "–") }),
      c("loyal", { sortable: false, render: (r) => (r.loyal ? <Badge kind="active">{t("app.yes")}</Badge> : <span className="text-muted">{t("app.no")}</span>) }),
    ],
    recommendations: [
      ...nameCol,
      c("total_spent", { num: true, render: (r) => fmtMoney(r.total_spent) }),
      c("visits", { num: true, render: (r) => fmtInt(r.visits) }),
      c("last_visit", { render: (r) => fmtDate(r.last_visit) }),
      c("days_since", { num: true, render: (r) => fmtInt(r.days_since) }),
      c("expected_next", { render: (r) => fmtDate(r.expected_next) }),
      c("overdue_days", { num: true, render: (r) => (r.overdue_days > 0 ? <span className="text-bad font-semibold">{fmtInt(r.overdue_days)}</span> : fmtInt(r.overdue_days)) }),
      c("churn_risk", { sortable: false, render: (r) => <Badge kind={r.churn_risk}>{t(`risk.${r.churn_risk}`)}</Badge> }),
      c("status", { sortable: false, render: (r) => <Badge kind={r.status}>{t(`status.${r.status}`)}</Badge> }),
      c("action", { sortable: false, render: (r) => <span className="font-medium">{t(`action.${r.action}`)}</span> }),
    ],
  };
  const titles = { customers: [t("cust.title"), t("cust.subtitle")], business: [t("biz.title"), t("biz.subtitle")], recommendations: [t("rec.title"), t("rec.subtitle")] };

  return (
    <>
      <PageHeader title={titles[view][0]} subtitle={titles[view][1]}
        actions={<ExportButton path="/customers" params={{ ...query, page: undefined, page_size: undefined }} />} />
      <FilterBar />
      <div className="card p-4">
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <div className="relative flex-1 min-w-56">
            <Search size={16} className="absolute top-2.5 start-3 text-muted" />
            <input className="input ps-9" placeholder={`${t("col.phone")} / ${t("col.name")}…`} value={qText} onChange={(e) => setQText(e.target.value)} />
          </div>
          <div>
            <span className="label">&nbsp;</span>
            <select className="input" value={flag} onChange={(e) => { const n = new URLSearchParams(sp); e.target.value ? n.set("flag", e.target.value) : n.delete("flag"); setSp(n, { replace: true }); }}>
              {FLAGS.map((f) => <option key={f} value={f}>{t(`cust.flags.${f}`)}</option>)}
            </select>
          </div>
          <MultiSelect label={t("col.status")} options={["active", "attention", "inactive"]} value={status} onChange={(v) => setList("status", v)} render={(s) => t(`status.${s}`)} />
          <MultiSelect label={t("col.segment")} options={SEGMENTS} value={segment} onChange={(v) => setList("segment", v)} render={(s) => t(`seg.${s}`)} />
          <MultiSelect label={t("col.churn_risk")} options={["high", "medium", "low"]} value={churn} onChange={(v) => setList("churn", v)} render={(s) => t(`risk.${s}`)} />
        </div>
        {res.error ? <ErrorBox error={res.error} onRetry={() => res.refetch()} /> : (
          <>
            {res.data?.reference_date && <div className="text-xs text-muted mb-2">{t("app.referenceDate")} {fmtDate(res.data.reference_date)}</div>}
            <DataTable columns={cols[view]} rows={res.data?.rows ?? []} total={res.data?.total} page={page} pageSize={50} onPage={setPage}
              sort={sort} desc={desc} onSort={(k, d) => { setSort(k); setDesc(d); }} loading={res.isFetching}
              onRowClick={(r) => nav(`/customers/${r.cid}`)} maxHeight={640} />
          </>
        )}
      </div>
    </>
  );
}
