import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Info, OctagonAlert } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Badge, Card, Empty, ErrorBox, ExportButton, Kpi, PageHeader, PrintButton, Spinner } from "../components/ui";
import { seqColor, seqText, StackedBars } from "../components/charts";

const ALERT_ICON = { danger: OctagonAlert, warning: AlertTriangle, info: Info, success: CheckCircle2 } as const;
const ALERT_STYLE = { danger: "border-red-200 bg-red-50/60", warning: "border-amber-200 bg-amber-50/60", info: "border-blue-200 bg-blue-50/50", success: "border-green-200 bg-green-50/60" } as const;

export default function Insights() {
  const { t, i18n } = useTranslation();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["insights", ...key], queryFn: () => api.get("/insights", params) });
  const d = q.data;
  const lang = i18n.language as "en" | "ar";

  const churnOf = (k: string) => d?.churn.find((c: any) => c.churn_risk === k);
  const totalCustomers = d?.due?.customers ?? 0;

  // heatmap matrix
  const heat = (() => {
    if (!d) return null;
    const byKey = new Map<string, number>();
    let max = 0;
    for (const h of d.heatmap) { byKey.set(`${h.dow}-${h.hour}`, h.visits); max = Math.max(max, h.visits); }
    const hours = d.has_time ? Array.from(new Set<number>(d.heatmap.map((h: any) => h.hour))).sort((a, b) => a - b) : [];
    const perDay = [1, 2, 3, 4, 5, 6, 7].map((dow) => d.heatmap.filter((h: any) => h.dow === dow).reduce((s: number, h: any) => s + h.visits, 0));
    return { byKey, max, hours, perDay };
  })();

  return (
    <>
      <PageHeader title={t("nav.insights")} actions={<><ExportButton path="/insights" params={params} /><PrintButton /></>} />
      <FilterBar />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : !d || !totalCustomers ? <Empty /> : (
        <div className="space-y-5">
          {d.alerts.length > 0 && (
            <Card title={t("ins.alerts")}>
              <div className="grid md:grid-cols-2 gap-3">
                {d.alerts.map((a: any, i: number) => {
                  const Icon = ALERT_ICON[a.level as keyof typeof ALERT_ICON] ?? Info;
                  return (
                    <div key={i} className={clsx("rounded-lg border px-3.5 py-3 text-sm flex gap-3", ALERT_STYLE[a.level as keyof typeof ALERT_STYLE])}>
                      <Icon size={17} className="shrink-0 mt-0.5" /> <span>{a[lang]}</span>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <Kpi label={t("ins.dueSoon")} value={fmtInt(d.due.due_soon)} />
            <Kpi label={t("ins.overdue")} value={fmtInt(d.due.overdue)} sub={fmtPct((100 * d.due.overdue) / totalCustomers)} />
            <Kpi label={`${t("ins.churn")}: ${t("risk.high")}`} value={fmtInt(churnOf("high")?.customers ?? 0)} sub={fmtMoney(churnOf("high")?.sales ?? 0)} />
            <Kpi label={t("ins.multiBranch")} value={fmtInt(d.due.multi_branch)} />
            <Kpi label={t("ins.pareto")} value={fmtPct(d.pareto?.top20_share)} sub={t("ins.paretoOf")} />
          </div>
          {d.directory?.listed > 0 && (
            <div className="grid grid-cols-2 gap-4">
              <Kpi label={t("dir.listed")} value={fmtInt(d.directory.listed)} />
              <Kpi label={t("dir.neverBought")} value={fmtInt(d.directory.never_bought)} sub={fmtPct((100 * d.directory.never_bought) / d.directory.listed)} />
            </div>
          )}

          {d.trend?.length > 0 && (
            <Card title={t("trend.title")}>
              <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
                {["growing", "stable", "declining", "stopped", "new", "back", "none"].map((k) => {
                  const r = d.trend.find((x: any) => x.trend === k);
                  return (
                    <button key={k} onClick={() => nav(`/customers?trend=${k}`)} className="text-start rounded-lg border border-line p-3 hover:border-brand hover:bg-brand-soft cursor-pointer">
                      <div className="text-xs text-muted">{t(`trend.${k}`)}</div>
                      <div className="text-xl font-bold num">{fmtInt(r?.customers ?? 0)}</div>
                      {r && (k === "declining" || k === "stopped") && <div className="text-xs text-bad num">{fmtMoney((r.spend_prev_90 ?? 0) - (r.spend_90 ?? 0))} ↓</div>}
                    </button>
                  );
                })}
              </div>
            </Card>
          )}

          <Card title={t("ins.rfm")} help={t("ins.rfmHelp")}>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
              {d.rfm.map((s: any) => (
                <button key={s.segment} onClick={() => nav(`/customers?segment=${s.segment}`)}
                  className="text-start rounded-lg border border-line p-3.5 hover:border-brand hover:bg-brand-soft transition cursor-pointer">
                  <div className="font-semibold">{t(`seg.${s.segment}`)}</div>
                  <div className="text-xs text-muted mb-2 min-h-8">{t(`segHelp.${s.segment}`)}</div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-xl font-bold num">{fmtInt(s.customers)}</span>
                    <span className="text-xs text-muted num">{fmtPct(s.share)} {t("ins.share")}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-surface mt-2 overflow-hidden">
                    <div className="h-full bg-brand" style={{ width: `${Math.min(100, s.share ?? 0)}%` }} />
                  </div>
                  <div className="text-xs text-muted mt-2 num">{t("ins.avgSpend")}: {fmtMoney(s.avg_spend)} · {t("ins.avgVisits")}: {fmtNum(s.avg_visits)}</div>
                </button>
              ))}
            </div>
          </Card>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("ins.churn")} help={t("ins.churnHelp")}>
              <div className="space-y-3">
                {["high", "medium", "low"].map((k) => {
                  const c = churnOf(k);
                  const n = c?.customers ?? 0;
                  return (
                    <button key={k} onClick={() => nav(`/recommendations?churn=${k}`)} className="w-full flex items-center gap-3 cursor-pointer group">
                      <Badge kind={k} className="w-20 justify-center">{t(`risk.${k}`)}</Badge>
                      <div className="flex-1 h-2.5 rounded-full bg-surface overflow-hidden">
                        <div className="h-full" style={{ width: `${(100 * n) / totalCustomers}%`, background: k === "high" ? "#c62828" : k === "medium" ? "#eda100" : "#1a7f37" }} />
                      </div>
                      <span className="num font-semibold w-16 text-end group-hover:underline">{fmtInt(n)}</span>
                    </button>
                  );
                })}
              </div>
            </Card>
            <Card title={t("ins.newReturning")}>
              {d.new_vs_returning.length ? (
                <StackedBars data={d.new_vs_returning} x="month" height={220}
                  series={[{ key: "returning", name: lang === "ar" ? "عائدون" : "Returning" }, { key: "new", name: lang === "ar" ? "جدد" : "New" }]} />
              ) : <Empty />}
            </Card>
          </div>

          <Card title={t("ins.growth")}
            help={d.periods?.current?.[0] ? `${fmtDate(d.periods.current[0])} – ${fmtDate(d.periods.current[1])}  vs  ${fmtDate(d.periods.previous[0])} – ${fmtDate(d.periods.previous[1])}` : undefined}>
            <DataTable rows={d.branch_growth} columns={[
              { key: "branch", label: t("col.branch") },
              { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
              { key: "prev_sales", label: t("col.prev_sales"), num: true, render: (r) => fmtMoney(r.prev_sales) },
              { key: "sales_change", label: t("col.sales_change"), num: true, render: (r) => <Change v={r.sales_change} /> },
              { key: "customers", label: t("col.customers"), num: true, render: (r) => fmtInt(r.customers) },
              { key: "customers_change", label: t("col.customers_change"), num: true, render: (r) => <Change v={r.customers_change} /> },
            ]} />
          </Card>

          <Card title={t("ins.basket")} help={t("ins.basketHelp")}>
            <DataTable rows={d.basket} maxHeight={420} columns={[
              { key: "item_a", label: t("ins.itemA") },
              { key: "item_b", label: t("ins.itemB") },
              { key: "together", label: t("ins.together"), num: true, render: (r) => fmtInt(r.together) },
              { key: "confidence_a_b", label: t("ins.conf"), num: true, render: (r) => fmtPct(r.confidence_a_b) },
              { key: "lift", label: t("ins.lift"), num: true, render: (r) => <b>{fmtNum(r.lift)}</b> },
            ]} />
          </Card>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("ins.cohorts")} help={t("ins.cohortHelp")}>
              {d.cohorts.length ? (
                <div className="overflow-auto">
                  <table className="text-xs border-separate border-spacing-0.5">
                    <thead><tr>
                      <th className="th">{t("ins.cohort")}</th><th className="th text-end">{t("ins.size")}</th>
                      {Array.from({ length: 12 }, (_, k) => <th key={k} className="th text-center">M{k}</th>)}
                    </tr></thead>
                    <tbody>
                      {d.cohorts.map((c: any) => (
                        <tr key={c.cohort}>
                          <td className="px-2 font-medium whitespace-nowrap">{c.cohort}</td>
                          <td className="px-2 text-end num">{fmtInt(c.size)}</td>
                          {Array.from({ length: 12 }, (_, k) => {
                            const r = c.retention.find((x: any) => x.k === k);
                            const v = r ? r.pct / 100 : 0;
                            return <td key={k} title={r ? `${r.pct}%` : ""} className="w-10 h-7 text-center num rounded"
                              style={{ background: r ? seqColor(k === 0 ? 1 : Math.min(1, v * 2)) : "transparent", color: r ? seqText(k === 0 ? 1 : v * 2) : undefined }}>
                              {r ? Math.round(r.pct) : ""}
                            </td>;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <Empty />}
            </Card>

            <Card title={d.has_time ? t("ins.heatmap") : t("ins.heatmapDays")}>
              {heat && (d.has_time ? (
                <div className="overflow-auto">
                  <table className="text-[11px] border-separate border-spacing-0.5">
                    <thead><tr><th />{heat.hours.map((h) => <th key={h} className="font-normal text-muted px-0.5">{h}</th>)}</tr></thead>
                    <tbody>
                      {[1, 2, 3, 4, 5, 6, 7].map((dow) => (
                        <tr key={dow}>
                          <td className="pe-2 text-muted whitespace-nowrap">{(t("days", { returnObjects: true }) as string[])[dow - 1]}</td>
                          {heat.hours.map((h) => {
                            const v = heat.byKey.get(`${dow}-${h}`) ?? 0;
                            return <td key={h} title={`${v}`} className="w-6 h-6 rounded-sm" style={{ background: seqColor(v / (heat.max || 1)) }} />;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="space-y-2">
                  {heat.perDay.map((v, i) => (
                    <div key={i} className="flex items-center gap-3 text-sm">
                      <span className="w-20 text-muted">{(t("days", { returnObjects: true }) as string[])[i]}</span>
                      <div className="flex-1 h-5 bg-surface rounded overflow-hidden">
                        <div className="h-full bg-brand rounded" style={{ width: `${(100 * v) / Math.max(...heat.perDay, 1)}%` }} />
                      </div>
                      <span className="num w-16 text-end">{fmtInt(v)}</span>
                    </div>
                  ))}
                </div>
              ))}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function Change({ v }: { v: number | null }) {
  if (v == null) return <span className="text-muted">–</span>;
  return <span className={v >= 0 ? "text-good font-semibold" : "text-bad font-semibold"}>{v >= 0 ? "+" : ""}{fmtNum(v)}%</span>;
}
