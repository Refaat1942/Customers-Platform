import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { FileSpreadsheet, IdCard, Loader2, Search } from "lucide-react";
import { api, download } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum } from "../lib/format";
import FilterBar from "../components/FilterBar";
import FilterTotals from "../components/FilterTotals";
import DataTable, { type Column } from "../components/DataTable";
import { Badge, ErrorBox, ExportButton, MultiSelect, Notice, PageHeader, Spinner, Tabs } from "../components/ui";
import { useAuth } from "../lib/auth";

const CustomerBase = lazy(() => import("./CustomerBase"));

/** One Customers page with two tabs: people who bought (from sales) and everyone in the
 *  uploaded customer lists. Each tab follows its own permission. */
export default function Customers({ view }: { view: View }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [sp, setSp] = useSearchParams();
  if (view !== "customers") return <CustomerList view={view} />;
  const tabs = [
    ...(can("customers") ? [{ key: "bought" as const, label: t("cust.tabBought") }] : []),
    ...(can("customer_base") ? [{ key: "base" as const, label: t("cust.tabBase") }] : []),
  ];
  if (!tabs.length) return <Notice kind="warning">{t("app.noAccess")}</Notice>;
  const tab = tabs.find((x) => x.key === sp.get("tab"))?.key ?? tabs[0].key;
  const setTab = (k: string) => { const n = new URLSearchParams(); if (k !== "bought") n.set("tab", k); setSp(n, { replace: true }); };
  const header = (actions: ReactNode) => (
    <>
      <PageHeader title={t("nav.customers")} subtitle={t("cust.tabsHelp")} actions={actions} />
      {tabs.length > 1 && <Tabs value={tab} onChange={setTab} items={tabs} />}
    </>
  );
  return tab === "base"
    ? <Suspense fallback={<Spinner />}><CustomerBase header={header} /></Suspense>
    : <CustomerList view="customers" header={header} />;
}

type View = "customers" | "business" | "recommendations";
const FLAGS = ["", "high_value", "loyal", "due_soon", "overdue", "multi_branch", "invalid_phone"];
const SEGMENTS = ["champions", "loyal", "potential", "new", "promising", "cant_lose", "at_risk", "hibernating", "lost"];

function CustomerList({ view, header }: { view: View; header?: (actions: ReactNode) => ReactNode }) {
  const { t } = useTranslation();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [qText, setQText] = useState(() => new URLSearchParams(window.location.search).get("q") ?? "");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState(view === "recommendations" ? "priority" : "total_spent");
  const [desc, setDesc] = useState(true);

  const flag = sp.get("flag") ?? "";
  const status = sp.getAll("status");
  const segment = sp.getAll("segment");
  const churn = sp.getAll("churn");
  const trend = sp.getAll("trend");
  const setList = (name: string, v: string[]) => {
    const n = new URLSearchParams(sp); n.delete(name); v.forEach((x) => n.append(name, x)); setSp(n, { replace: true });
  };

  useEffect(() => { const h = setTimeout(() => setQ(qText.trim()), 350); return () => clearTimeout(h); }, [qText]);
  useEffect(() => { const v = sp.get("q"); if (v !== null && v !== qText) setQText(v); }, [sp.get("q")]); // eslint-disable-line
  useEffect(() => setPage(1), [q, flag, status.join(), segment.join(), churn.join(), trend.join(), sort, desc, ...key]); // eslint-disable-line

  const query = { ...params, q, flag: flag || undefined, status, segment, churn, trend, sort, desc, page, page_size: 50, view };
  const res = useQuery({ queryKey: ["customers", query], queryFn: () => api.get("/customers", query), placeholderData: keepPreviousData });

  const c = (k: string, extra: Partial<Column<any>> = {}): Column<any> => ({ key: k, label: t(`col.${k}`), sortable: true, ...extra });
  const nameCol: Column<any>[] = [
    { key: "x", label: "360°", render: (r: any) => (
      <button title={t("c360.open")} className="text-brand hover:bg-brand-soft rounded p-1 cursor-pointer" onClick={(e) => { e.stopPropagation(); nav(`/customers/${r.cid}/card`); }}><IdCard size={17} /></button>
    ) },
    c("phone", { className: "font-mono text-xs" }),
    c("name", { className: "max-w-56 truncate" }),
    c("branch"),
  ];
  const cols: Record<View, Column<any>[]> = {
    customers: [
      ...nameCol, c("district", { sortable: false }),
      c("total_spent", { num: true, render: (r) => fmtMoney(r.total_spent) }),
      c("visits", { num: true, render: (r) => fmtInt(r.visits) }),
      { key: "trend", label: t("trend.col"), sortable: false, render: (r: any) => <TrendBadge t={t} r={r} /> },
      c("last_visit", { render: (r) => fmtDate(r.last_visit) }),
      c("days_since", { num: true, render: (r) => fmtInt(r.days_since) }),
      c("avg_per_visit", { num: true, render: (r) => fmtMoney(r.avg_per_visit) }),
      c("max_invoice", { num: true, render: (r) => fmtMoney(r.max_invoice) }),
      c("min_invoice", { num: true, render: (r) => fmtMoney(r.min_invoice) }),
      c("items_count", { num: true, render: (r) => fmtInt(r.items_count) }),
      c("fav_item", { sortable: false, className: "max-w-48 truncate" }),
      c("avg_days_between", { num: true, render: (r) => fmtNum(r.avg_days_between) }),
      c("segment", { render: (r) => <Badge>{t(`seg.${r.segment}`)}</Badge> }),
      c("status", { sortable: false, render: (r) => <Badge kind={r.status}>{t(`status.${r.status}`)}</Badge> }),
    ],
    business: [
      ...nameCol,
      c("total_spent", { num: true, render: (r) => fmtMoney(r.total_spent) }),
      c("visits", { num: true, render: (r) => fmtInt(r.visits) }),
      c("max_invoice", { num: true, render: (r) => fmtMoney(r.max_invoice) }),
      c("items_count", { num: true, render: (r) => fmtInt(r.items_count) }),
      c("fav_item", { sortable: false, className: "max-w-48 truncate" }),
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
      {(() => {
        const actions = <>{view === "customers" && <ClassifiedButton params={params} />}<ExportButton path="/customers" params={{ ...query, page: undefined, page_size: undefined }} /></>;
        return header ? header(actions) : <PageHeader title={titles[view][0]} subtitle={titles[view][1]} actions={actions} />;
      })()}
      <FilterBar />
      <FilterTotals />
      <div className="card p-4">
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <div className="relative flex-1 min-w-56">
            <Search size={16} className="absolute top-2.5 start-3 text-muted" />
            <input className="input ps-9" placeholder={t("cust.searchHint")} value={qText} onChange={(e) => setQText(e.target.value)} />
          </div>
          <div>
            <span className="label">&nbsp;</span>
            <select className="input" value={flag} onChange={(e) => { const n = new URLSearchParams(sp); e.target.value ? n.set("flag", e.target.value) : n.delete("flag"); setSp(n, { replace: true }); }}>
              {FLAGS.map((f) => <option key={f} value={f}>{t(`cust.flags.${f}`)}</option>)}
            </select>
          </div>
          <MultiSelect label={t("col.status")} options={["active", "attention", "inactive"]} value={status} onChange={(v) => setList("status", v)} render={(s) => t(`status.${s}`)} />
          <MultiSelect label={t("col.segment")} options={SEGMENTS} value={segment} onChange={(v) => setList("segment", v)} render={(s) => t(`seg.${s}`)} />
          <MultiSelect label={t("trend.col")} options={["growing", "stable", "declining", "stopped", "new", "back"]} value={trend} onChange={(v) => setList("trend", v)} render={(s) => t(`trend.${s}`)} />
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

export function TrendBadge({ r, t }: { r: any; t: (k: string) => string }) {
  const kind: Record<string, string> = { growing: "active", stable: "", declining: "attention", stopped: "inactive", new: "active", back: "active", none: "unknown" };
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge kind={kind[r.trend] || undefined}>{t(`trend.${r.trend}`)}</Badge>
      {r.trend_pct != null && <span className={r.trend_pct >= 0 ? "text-good text-xs num" : "text-bad text-xs num"}>{r.trend_pct >= 0 ? "+" : ""}{Math.round(r.trend_pct)}%</span>}
    </span>
  );
}

const CLASSES = ["segment", "status", "churn", "trend", "value", "visits", "branch", "district"] as const;

/** Excel with a summary + one sheet per class (segment, status, branch, spend band...). */
function ClassifiedButton({ params }: { params: Record<string, any> }) {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!can("export")) return null;
  const go = async (by: string) => {
    setBusy(by); setErr(null);
    try { await download("/customers/classified", { ...params, by, lang: i18n.language }); setOpen(false); }
    catch (e) { setErr((e as Error).message); }
    setBusy(null);
  };
  return (
    <span className="relative inline-flex flex-col">
      <button className="btn-primary" onClick={() => setOpen(!open)}><FileSpreadsheet size={16} /> {t("cls.button")}</button>
      {open && (
        <div className="absolute start-0 top-full mt-2 z-30 w-80 max-w-[90vw] card p-3 shadow-xl">
          <div className="text-sm font-semibold mb-1">{t("cls.title")}</div>
          <div className="text-xs text-muted mb-3">{t("cls.help")}</div>
          <div className="grid gap-1">
            {CLASSES.map((c) => (
              <button key={c} disabled={!!busy} onClick={() => go(c)}
                className="flex items-center gap-2 text-start rounded-lg px-3 py-2 text-sm hover:bg-brand-soft cursor-pointer">
                {busy === c ? <Loader2 size={15} className="animate-spin" /> : <FileSpreadsheet size={15} className="text-brand" />}
                <span className="flex-1">{t(`cls.by.${c}`)}</span>
              </button>
            ))}
          </div>
          {err && <div className="text-xs text-bad mt-2">{err}</div>}
        </div>
      )}
    </span>
  );
}
