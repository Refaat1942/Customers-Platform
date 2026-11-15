import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Clock, Repeat, Store } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import { SHIFT_COLORS, SHIFT_KEYS, shiftRange } from "../lib/shifts";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Badge, Card, Empty, ErrorBox, ExportButton, Kpi, Notice, PageHeader, Spinner } from "../components/ui";
import { Columns, RankBars, ShareBar, StackedBars } from "../components/charts";

/** One product: where it sells, when (month, weekday, hour, shift), how often customers come
 *  back for it, who buys it, and what is bought with it. */
export default function ProductDetail() {
  const { t } = useTranslation();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const key = sp.get("key") ?? "";
  const { params, key: fkey } = useFilters();
  const q = useQuery({ queryKey: ["product", key, ...fkey], queryFn: () => api.get("/products/detail", { ...params, key }), enabled: !!key, retry: false });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get("/settings") });
  const sh = { morning: settings.data?.shift_morning ?? "08:30", evening: settings.data?.shift_evening ?? "16:30" };
  const d = q.data;
  const p = d?.product;
  const days = t("days", { returnObjects: true }) as string[];
  const shiftName = (k: string) => t(`shift.${k}`);
  const hasTime = (d?.shifts ?? []).some((s: any) => s.shift !== "unknown");

  return (
    <>
      <Link to="/products" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink mb-2"><ArrowLeft size={15} className="rtl:rotate-180" /> {t("pd.back")}</Link>
      <PageHeader
        title={<span className="flex flex-wrap items-baseline gap-x-3">
          <span>{p?.item ?? (p ? <span className="italic text-muted">{t("prod.noName")}</span> : "…")}</span>
          {p?.code && <span className="font-mono text-base text-muted">#{p.code}</span>}
        </span>}
        subtitle={p ? [p.category, p.subcategory, p.brand, p.manufacturer, p.material_group, p.unit, p.list_price != null ? `${t("col.list_price")}: ${fmtMoney(p.list_price)}` : null].filter(Boolean).join(" · ") || undefined : undefined}
        actions={<><Link to={`/products/inspect?k=${encodeURIComponent(key)}`} className="btn-ghost">{t("insp.compare")}</Link><ExportButton path="/products/detail" params={{ ...params, key }} /></>} />
      <FilterBar />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : !d ? <Empty /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Kpi label={t("pd.units")} value={fmtNum(p.units)} />
            <Kpi label={t("pd.sales")} value={fmtMoney(p.sales)} />
            <Kpi label={t("pd.invoices")} value={fmtInt(p.invoices)} />
            <Kpi label={t("pd.customers")} value={fmtInt(p.customers)} />
            <Kpi label={t("pd.avgPrice")} value={fmtMoney(p.avg_price)} />
            <Kpi label={t("pd.perInvoice")} value={fmtNum(p.units_per_invoice)} />
            <Kpi label={t("pd.interval")} value={p.median_days == null ? "–" : t("prod.days", { n: fmtInt(p.median_days) })} sub={t("pd.intervalSub")} icon={<Repeat size={16} />} />
            <Kpi label={t("pd.repeat")} value={fmtInt(p.repeat_customers ?? 0)} sub={p.customers ? fmtPct((100 * (p.repeat_customers ?? 0)) / p.customers) : undefined} />
          </div>
          <div className="text-xs text-muted flex flex-wrap gap-x-5 gap-y-1">
            <span>{t("pd.firstLast")}: <b>{fmtDate(p.first_sold)} – {fmtDate(p.last_sold)}</b></span>
            {d.by_branch[0] && <span className="inline-flex items-center gap-1"><Store size={13} /> {t("pd.topBranch")}: <b>{d.by_branch[0].branch}</b> ({fmtPct(d.by_branch[0].share)})</span>}
            {p.catalogue && <span>{t(`pd.catalogue.${p.catalogue}`)}</span>}
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("pd.byBranch")}>
              <RankBars data={d.by_branch.slice(0, 15)} label="branch" value="units" name={t("col.units")} money={false} />
              <div className="mt-4">
                <DataTable rows={d.by_branch} maxHeight={300} columns={[
                  { key: "branch", label: t("col.branch") },
                  { key: "units", label: t("col.units"), num: true, render: (r: any) => fmtNum(r.units) },
                  { key: "share", label: "%", num: true, render: (r: any) => fmtPct(r.share) },
                  { key: "sales", label: t("col.sales"), num: true, render: (r: any) => fmtMoney(r.sales) },
                  { key: "invoices", label: t("col.invoices"), num: true, render: (r: any) => fmtInt(r.invoices) },
                  { key: "customers", label: t("col.customers"), num: true, render: (r: any) => fmtInt(r.customers) },
                  { key: "units_per_day", label: t("col.units_per_day"), num: true, render: (r: any) => fmtNum(r.units_per_day) },
                  { key: "last_sold", label: t("col.last_sold"), render: (r: any) => fmtDate(r.last_sold) },
                ]} />
              </div>
            </Card>
            <div className="space-y-5">
              <Card title={t("pd.byShift")}>
                {hasTime ? (
                  <>
                    <ShareBar parts={SHIFT_KEYS.map((k) => ({ label: `${shiftName(k)} (\u2066${shiftRange(k, sh)}\u2069)`, value: Math.round(d.shifts.find((s: any) => s.shift === k)?.units ?? 0), color: SHIFT_COLORS[k] }))} />
                    {d.shifts.some((s: any) => s.shift === "unknown") && <div className="text-xs text-muted mt-2">{t("shift.unknown")}: {fmtNum(d.shifts.find((s: any) => s.shift === "unknown").units)} {t("shift.units")}</div>}
                  </>
                ) : <Notice kind="info">{t("pd.noTime")}</Notice>}
              </Card>
              <Card title={t("pd.byMonth")}>
                {d.monthly.length ? <Columns data={d.monthly} x="month" y="units" name={t("col.units")} height={220} /> : <Empty />}
              </Card>
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("pd.byWeekday")}>
              <Columns data={d.weekday.map((r: any) => ({ ...r, day: days[r.dow - 1] }))} x="day" y="units" name={t("col.units")} height={220} />
            </Card>
            <Card title={t("pd.byHour")}>
              {d.hourly.length ? <Columns data={d.hourly.map((r: any) => ({ ...r, h: `${String(r.hour).padStart(2, "0")}:00` }))} x="h" y="units" name={t("col.units")} height={220} />
                : <Notice kind="info">{t("pd.noTime")}</Notice>}
            </Card>
          </div>

          {hasTime && d.branch_shift.length > 0 && (
            <Card title={t("pd.branchShift")}>
              <StackedBars data={d.branch_shift.slice(0, 20)} x="branch" colors={SHIFT_KEYS.map((k) => SHIFT_COLORS[k])}
                series={SHIFT_KEYS.map((k) => ({ key: k, name: shiftName(k) }))} />
            </Card>
          )}

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("pd.intervals")} help={t("pd.intervalSub")}>
              {d.intervals.length ? (
                <Columns data={d.intervals.map((r: any) => ({ ...r, label: (t("pd.buckets", { returnObjects: true }) as string[])[r.bucket - 1] }))} x="label" y="n" name={t("col.customers")} height={220} color="#1baf7a" />
              ) : <Empty />}
            </Card>
            <Card title={t("pd.together")}>
              {d.together.length ? (
                <DataTable rows={d.together} maxHeight={300} onRowClick={(r: any) => nav(`/products/item?key=${encodeURIComponent(r.key)}`)} columns={[
                  { key: "code", label: t("col.code"), className: "font-mono text-xs", render: (r: any) => r.code ?? "–" },
                  { key: "item", label: t("col.item"), className: "max-w-64 truncate", render: (r: any) => r.item ?? <span className="text-muted italic">{t("prod.noName")}</span> },
                  { key: "invoices", label: t("col.invoices"), num: true, render: (r: any) => fmtInt(r.invoices) },
                  { key: "pct", label: t("col.pct"), num: true, render: (r: any) => fmtPct(r.pct) },
                ]} />
              ) : <Empty />}
            </Card>
          </div>

          <Card title={t("pd.topCustomers")}>
            <DataTable rows={d.top_customers} maxHeight={420} onRowClick={(r: any) => nav(`/customers/${r.cid}`)} columns={[
              { key: "phone", label: t("col.phone"), className: "font-mono text-xs" },
              { key: "name", label: t("col.name"), className: "max-w-56 truncate" },
              { key: "branch", label: t("col.branch") },
              { key: "purchases", label: t("col.purchases"), num: true, render: (r: any) => fmtInt(r.purchases) },
              { key: "units", label: t("col.units"), num: true, render: (r: any) => fmtNum(r.units) },
              { key: "sales", label: t("col.sales"), num: true, render: (r: any) => fmtMoney(r.sales) },
              { key: "last_bought", label: t("col.last_bought"), render: (r: any) => fmtDate(r.last_bought) },
            ]} />
          </Card>

          {p.file_data?.length > 0 && (
            <Card title={t("pd.fileData")} help={t("pd.fileDataHelp")}>
              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3 text-sm">
                {p.file_data.map((x: any) => (
                  <div key={x.column} className="border-b border-line/60 pb-2">
                    <div className="text-xs text-muted">{x.column}</div>
                    <div className="font-semibold break-words num">{typeof x.value === "number" ? (Number.isInteger(x.value) ? String(x.value) : fmtNum(x.value)) : /^\d{4}-\d{2}-\d{2}T/.test(String(x.value)) ? fmtDate(x.value) : String(x.value)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {d.names.length > 1 && (
            <Card title={t("pd.otherNames")}>
              <div className="flex flex-wrap gap-2">
                {d.names.map((n: any) => <Badge key={n.name}>{n.name} <span className="text-muted num">· {fmtInt(n.lines)}</span></Badge>)}
              </div>
            </Card>
          )}
          <div className="text-xs text-muted inline-flex items-center gap-1"><Clock size={12} /> {SHIFT_KEYS.map((k) => `${shiftName(k)} ${shiftRange(k, sh)}`).join(" · ")}</div>
        </div>
      )}
    </>
  );
}
