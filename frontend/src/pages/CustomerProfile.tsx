import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import clsx from "clsx";
import { ArrowLeft, ArrowRight, ChevronDown, Loader2, Phone, Search } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, Empty, ErrorBox, ExportButton, Kpi, PageHeader, PrintButton, Spinner, Tabs } from "../components/ui";
import { RankBars, TrendChart } from "../components/charts";

type Tab = "purchases" | "data";

export default function CustomerProfile() {
  const { t, i18n } = useTranslation();
  const { cid } = useParams();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>("purchases");
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

          <Tabs value={tab} onChange={setTab} items={[
            { key: "purchases", label: t("prof.purchases") },
            { key: "data", label: t("prof.data") },
          ]} />

          {tab === "purchases" ? <Purchases d={d} cid={cid!} params={params} /> : <CustomerData d={d} />}
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ purchases */
function Purchases({ d, cid, params }: { d: any; cid: string; params: any }) {
  const { t, i18n } = useTranslation();
  const s = d.summary;
  const [open, setOpen] = useState<string | null>(null);
  const [itemQ, setItemQ] = useState("");
  const items = d.items.filter((x: any) => !itemQ || `${x.item} ${x.code ?? ""} ${x.category ?? ""}`.toLowerCase().includes(itemQ.toLowerCase()));
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
        <Kpi label={t("col.total_spent")} value={fmtMoney(s.total_spent)} />
        <Kpi label={t("col.visits")} value={fmtInt(s.visits)} sub={`${fmtInt(s.items_count)} ${t("prof.differentProducts")}`} />
        <Kpi label={t("col.avg_per_visit")} value={fmtMoney(s.avg_per_visit)}
          sub={`${t("col.max_invoice")}: ${fmtMoney(s.max_invoice)} · ${t("col.min_invoice")}: ${fmtMoney(s.min_invoice)}`} />
        <Kpi label={t("col.last_visit")} value={fmtDate(s.last_visit)} sub={`${fmtInt(s.days_since)} ${i18n.language === "ar" ? "يوم" : "days ago"}`} />
        <Kpi label={t("col.avg_days_between")} value={fmtNum(s.avg_days_between)} sub={`${t("col.first_visit")}: ${fmtDate(s.first_visit)}`} />
        <Kpi label={t("col.expected_next")} value={fmtDate(s.expected_next)}
          sub={s.overdue_days > 0 ? `${fmtInt(s.overdue_days)} ${t("col.overdue_days")}` : undefined} />
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <Card title={t("cust.monthlySpend")}><TrendChart data={d.monthly} x="month" y="sales" name={t("col.sales")} height={220} /></Card>
        <Card title={t("cust.favourite")}>{d.top_items.length ? <RankBars data={d.top_items.slice(0, 10)} label="item" value="sales" name={t("col.sales")} /> : <Empty />}</Card>
      </div>

      <Card title={t("cust.visitsHistory")} help={t("prof.visitsHelp")} pad={false}>
        <div className="max-h-[640px] overflow-auto">
          <table className="w-full border-collapse">
            <thead className="bg-surface sticky top-0 z-10">
              <tr>
                <th className="th w-8" />
                {["date", "branch", "invoice_no", "invoice_type", "lines", "total", "items"].map((c) => (
                  <th key={c} className={clsx("th", (c === "lines" || c === "total") && "text-end")}>{t(`col.${c}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.visits.map((v: any) => (
                <Fragment key={v.visit_key}>
                  <tr onClick={() => setOpen(open === v.visit_key ? null : v.visit_key)}
                    className={clsx("border-t border-line cursor-pointer hover:bg-brand-soft", open === v.visit_key && "bg-brand-soft")}>
                    <td className="td"><ChevronDown size={15} className={clsx("transition text-muted", open === v.visit_key ? "rotate-0" : "-rotate-90 rtl:rotate-90")} /></td>
                    <td className="td num">{fmtDate(v.date, true)}</td>
                    <td className="td">{v.branch ?? "–"}</td>
                    <td className="td font-mono text-xs">{v.invoice_no ?? "–"}</td>
                    <td className="td">{v.sales_type ?? "–"}</td>
                    <td className="td text-end num">{fmtInt(v.lines)}</td>
                    <td className={clsx("td text-end num font-semibold", v.total < 0 && "text-bad")}>{fmtMoney(v.total)}</td>
                    <td className="td"><div className="max-w-md truncate text-xs text-muted">{v.items}</div></td>
                  </tr>
                  {open === v.visit_key && (
                    <tr className="bg-surface/60"><td colSpan={8} className="px-4 py-3"><VisitLines cid={cid} visitKey={v.visit_key} params={params} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {d.visits.length === 0 && <Empty />}
        </div>
      </Card>

      <Card title={t("prof.allItems")} help={t("prof.allItemsHelp")}>
        <div className="relative mb-3 max-w-sm">
          <Search size={16} className="absolute top-2.5 start-3 text-muted" />
          <input className="input ps-9" placeholder={t("prof.searchItems")} value={itemQ} onChange={(e) => setItemQ(e.target.value)} />
        </div>
        <DataTable rows={items} maxHeight={520} columns={[
          { key: "item", label: t("col.item"), className: "max-w-72 truncate font-medium" },
          { key: "code", label: t("col.code"), className: "font-mono text-xs" },
          { key: "category", label: t("col.category") },
          { key: "quantity", label: t("col.quantity"), num: true, render: (r) => fmtNum(r.quantity) },
          { key: "times", label: t("col.times"), num: true, render: (r) => fmtInt(r.times) },
          { key: "avg_price", label: t("col.avg_price"), num: true, render: (r) => fmtMoney(r.avg_price) },
          { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
          { key: "first_bought", label: t("prof.firstBought"), render: (r) => fmtDate(r.first_bought) },
          { key: "last_bought", label: t("prof.lastBought"), render: (r) => fmtDate(r.last_bought) },
        ]} />
      </Card>
    </div>
  );
}

function VisitLines({ cid, visitKey, params }: { cid: string; visitKey: string; params: any }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["visit", cid, visitKey], queryFn: () => api.get(`/customers/${cid}/visit`, { ...params, key: visitKey }) });
  if (q.isLoading) return <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> {t("app.loading")}</div>;
  if (q.error) return <ErrorBox error={q.error} />;
  const lines = q.data.lines as any[];
  const total = lines.reduce((a, x) => a + (x.item_price ?? 0), 0);
  const first = lines[0] ?? {};
  return (
    <div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted mb-2">
        {first.cashier && <span>{t("live.col.cashier")}: <b className="text-ink">{first.cashier}</b></span>}
        {first.payment && <span>{t("prof.payment")}: <b className="text-ink">{first.payment}</b></span>}
      </div>
      <table className="w-full text-sm bg-white border border-line rounded-lg overflow-hidden">
        <thead className="bg-surface">
          <tr>{["item_code", "item_name", "item_category", "quantity", "item_unit", "unit_price", "item_price"].map((c) => (
            <th key={c} className={clsx("th", ["quantity", "unit_price", "item_price"].includes(c) && "text-end")}>{t(`prof.line.${c}`)}</th>
          ))}</tr>
        </thead>
        <tbody>
          {lines.map((x, i) => (
            <tr key={i} className="border-t border-line">
              <td className="td font-mono text-xs">{x.item_code ?? "–"}</td>
              <td className="td">{x.item_name ?? "–"}</td>
              <td className="td text-xs">{x.item_category ?? x.material_group ?? "–"}</td>
              <td className="td text-end num">{fmtNum(x.quantity)}</td>
              <td className="td text-xs">{x.item_unit ?? "–"}</td>
              <td className="td text-end num">{fmtMoney(x.unit_price)}</td>
              <td className={clsx("td text-end num font-medium", x.item_price < 0 && "text-bad")}>{fmtMoney(x.item_price)}</td>
            </tr>
          ))}
          <tr className="border-t-2 border-line bg-surface font-semibold">
            <td className="td" colSpan={6}>{t("col.total")}</td>
            <td className="td text-end num">{fmtMoney(total)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ customer data */
function CustomerData({ d }: { d: any }) {
  const { t } = useTranslation();
  const s = d.summary, dir = d.directory, si = d.sales_info ?? {};
  const field = (label: string, value: any, wide = false) => (
    <div className={wide ? "sm:col-span-2" : ""}>
      <div className="text-muted text-xs">{label}</div>
      <div className="font-semibold break-words">{value === null || value === undefined || value === "" ? "–" : value}</div>
    </div>
  );
  const list = (v: string[] | null) => (v && v.length ? v.join(" · ") : "–");
  return (
    <div className="space-y-5">
      <Card title={t("prof.identity")}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 text-sm">
          {field(t("col.phone"), s.phone)}
          {field(t("col.name"), dir?.name ?? s.name)}
          {field(t("imp.fields.first_name"), dir?.first_name)}
          {field(t("imp.fields.last_name"), dir?.last_name)}
          {field(t("prof.otherNames"), list((si.names ?? []).filter((n: string) => n !== (dir?.name ?? s.name))))}
          {field(t("dir.email"), dir?.email)}
          {field(t("imp.fields.gender"), dir?.gender)}
          {field(t("imp.fields.birth_date"), dir?.birth_date ? fmtDate(dir.birth_date) : null)}
          {field(t("prof.phoneValid"), s.phone_valid ? t("app.yes") : t("app.no"))}
          {field(t("prof.posId"), dir?.pos_customer_id)}
        </div>
      </Card>
      <Card title={t("prof.address")}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 text-sm">
          {field(t("dir.address"), dir?.address ?? si.address, true)}
          {field(t("dir.region"), dir?.region)}
          {field(t("dir.city"), dir?.city)}
          {field(t("col.district"), dir?.district ?? s.district)}
          {field(t("dir.area"), dir?.area)}
        </div>
      </Card>
      <Card title={t("prof.relationship")}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 text-sm">
          {field(t("prof.registeredAt"), dir?.registered_at ? fmtDate(dir.registered_at, true) : null)}
          {field(t("prof.registeredBranch"), dir?.registered_branch)}
          {field(t("prof.firstPurchase"), si.first_purchase ? fmtDate(si.first_purchase, true) : null)}
          {field(t("prof.lastPurchase"), si.last_purchase ? fmtDate(si.last_purchase, true) : null)}
          {field(t("prof.branchesUsed"), list(si.branches))}
          {field(t("prof.salesTypes"), list(si.sales_types))}
          {field(t("prof.allTimeVisits"), fmtInt(si.all_time_visits))}
          {field(t("prof.allTimeSpend"), fmtMoney(si.all_time_spend))}
          {field(t("col.segment"), t(`seg.${s.segment}`))}
          {field(t("col.status"), t(`status.${s.status}`))}
          {field(t("col.top_season"), s.top_season ? t(`seasons.${s.top_season}`) : null)}
          {field(t("prof.source"), dir?.source === "pos" ? "POS" : dir ? t("prof.fromList") : t("prof.fromSales"))}
        </div>
      </Card>
      {dir?.extra && Object.keys(dir.extra).length > 0 && (
        <Card title={t("prof.extra")}>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 text-sm">
            {Object.entries(dir.extra).map(([k, v]) => field(k, typeof v === "object" ? JSON.stringify(v) : String(v)))}
          </div>
        </Card>
      )}
    </div>
  );
}
