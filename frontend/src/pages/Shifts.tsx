import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Moon, Sun, Sunset } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import { SHIFT_COLORS, SHIFT_KEYS, shiftRange } from "../lib/shifts";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Card, Empty, ErrorBox, ExportButton, Notice, PageHeader, PrintButton, Spinner } from "../components/ui";
import { Columns, StackedBars } from "../components/charts";

const ICONS = { night: Moon, morning: Sun, evening: Sunset } as const;

/** When do customers buy: night / morning / evening shifts, per branch and hour,
 *  live POS vs uploaded files. */
export default function Shifts() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { params, key } = useFilters();
  const q = useQuery({ queryKey: ["shifts", ...key], queryFn: () => api.get("/shifts", params) });
  const d = q.data;
  const days = t("days", { returnObjects: true }) as string[];
  const name = (k: string) => t(`shift.${k}`);
  const known = (d?.totals ?? []).filter((x: any) => x.shift !== "unknown");
  const hasData = known.some((x: any) => x.invoices > 0);

  return (
    <>
      <PageHeader title={t("shift.title")} subtitle={t("shift.subtitle")} actions={<><ExportButton path="/shifts" params={params} /><PrintButton /></>} />
      <FilterBar />
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : !d || (!hasData && !d.unknown_time) ? <Empty /> : (
        <div className="space-y-5">
          {d.unknown_time > 0 && <Notice kind="info">{t("shift.unknownNote", { n: fmtInt(d.unknown_time) })}</Notice>}

          <div className="grid md:grid-cols-3 gap-4">
            {SHIFT_KEYS.map((k) => {
              const r = d.totals.find((x: any) => x.shift === k) ?? {};
              const Icon = ICONS[k];
              return (
                <div key={k} className="card p-5 border-t-4" style={{ borderTopColor: SHIFT_COLORS[k] }}>
                  <div className="flex items-center gap-3">
                    <span className="size-10 rounded-xl grid place-items-center text-white" style={{ background: SHIFT_COLORS[k] }}><Icon size={20} /></span>
                    <div>
                      <div className="font-semibold">{name(k)}</div>
                      <div className="text-xs text-muted num" dir="ltr">{shiftRange(k, d.settings)}</div>
                    </div>
                    <div className="ms-auto text-end">
                      <div className="text-2xl font-bold num">{fmtPct(r.share ?? 0)}</div>
                      <div className="text-xs text-muted">{t("shift.share")}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
                    <div><div className="text-muted text-xs">{t("col.sales")}</div><div className="font-semibold num">{fmtMoney(r.sales ?? 0)}</div></div>
                    <div><div className="text-muted text-xs">{t("col.invoices")}</div><div className="font-semibold num">{fmtInt(r.invoices ?? 0)}</div></div>
                    <div><div className="text-muted text-xs">{t("col.customers")}</div><div className="font-semibold num">{fmtInt(r.customers ?? 0)}</div></div>
                    <div><div className="text-muted text-xs">{t("shift.avgInvoice")}</div><div className="font-semibold num">{fmtMoney(r.avg_invoice)}</div></div>
                    <div><div className="text-muted text-xs">{t("col.units")}</div><div className="font-semibold num">{fmtNum(r.units ?? 0)}</div></div>
                    <div><div className="text-muted text-xs">{t("shift.prefer")}</div><div className="font-semibold num">{fmtInt(d.customers?.[k] ?? 0)}</div></div>
                  </div>
                </div>
              );
            })}
          </div>

          <Card title={t("shift.byBranch")}>
            <StackedBars data={d.by_branch.slice(0, 25).map((b: any) => ({ branch: b.branch, night: b.night_sales ?? 0, morning: b.morning_sales ?? 0, evening: b.evening_sales ?? 0 }))}
              x="branch" colors={SHIFT_KEYS.map((k) => SHIFT_COLORS[k])} series={SHIFT_KEYS.map((k) => ({ key: k, name: name(k) }))} height={300} />
            <div className="mt-4">
              <DataTable rows={d.by_branch} maxHeight={420} columns={[
                { key: "branch", label: t("col.branch") },
                { key: "sales", label: t("col.sales"), num: true, render: (r: any) => fmtMoney(r.sales) },
                { key: "top_shift", label: t("shift.busiest"), render: (r: any) => r.top_shift ? <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: SHIFT_COLORS[r.top_shift] }} />{name(r.top_shift)}</span> : "–" },
                ...SHIFT_KEYS.flatMap((k) => [
                  { key: `${k}_sales`, label: `${name(k)} – ${t("col.sales")}`, num: true, render: (r: any) => fmtMoney(r[`${k}_sales`] ?? 0) },
                  { key: `${k}_share`, label: `${name(k)} %`, num: true, render: (r: any) => (r[`${k}_share`] == null ? "–" : fmtPct(r[`${k}_share`])) },
                ]),
              ]} />
            </div>
          </Card>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("shift.hourly")}>
              {d.hourly.length ? <Columns data={d.hourly.map((r: any) => ({ ...r, h: `${String(r.hour).padStart(2, "0")}:00` }))} x="h" y="invoices" name={t("col.invoices")} height={240} /> : <Empty />}
            </Card>
            <Card title={t("shift.weekday")}>
              {d.weekday.length ? <StackedBars data={d.weekday.map((r: any) => ({ ...r, day: days[r.dow - 1] }))} x="day" colors={SHIFT_KEYS.map((k) => SHIFT_COLORS[k])}
                series={SHIFT_KEYS.map((k) => ({ key: k, name: name(k) }))} height={240} /> : <Empty />}
            </Card>
          </div>

          <Card title={t("shift.source")}>
            <DataTable rows={d.by_source.filter((r: any) => r.shift !== "unknown" || r.file_invoices || r.live_invoices)} columns={[
              { key: "shift", label: t("col.shift"), render: (r: any) => <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: SHIFT_COLORS[r.shift] }} />{name(r.shift)}</span> },
              { key: "live_sales", label: `${t("shift.live")} – ${t("col.sales")}`, num: true, render: (r: any) => fmtMoney(r.live_sales ?? 0) },
              { key: "live_invoices", label: `${t("shift.live")} – ${t("col.invoices")}`, num: true, render: (r: any) => fmtInt(r.live_invoices ?? 0) },
              { key: "live_customers", label: `${t("shift.live")} – ${t("col.customers")}`, num: true, render: (r: any) => fmtInt(r.live_customers ?? 0) },
              { key: "file_sales", label: `${t("shift.file")} – ${t("col.sales")}`, num: true, render: (r: any) => fmtMoney(r.file_sales ?? 0) },
              { key: "file_invoices", label: `${t("shift.file")} – ${t("col.invoices")}`, num: true, render: (r: any) => fmtInt(r.file_invoices ?? 0) },
              { key: "file_customers", label: `${t("shift.file")} – ${t("col.customers")}`, num: true, render: (r: any) => fmtInt(r.file_customers ?? 0) },
            ]} />
          </Card>

          <Card title={t("shift.topItems")}>
            <div className="grid lg:grid-cols-3 gap-5">
              {SHIFT_KEYS.map((k) => (
                <div key={k}>
                  <div className="font-semibold text-sm mb-2 flex items-center gap-2"><span className="size-2.5 rounded-sm" style={{ background: SHIFT_COLORS[k] }} />{name(k)}</div>
                  <DataTable rows={d.top_items?.[k] ?? []} onRowClick={(r: any) => r.code && nav(`/products/item?key=${encodeURIComponent("c:" + r.code)}`)} columns={[
                    { key: "code", label: t("col.code"), className: "font-mono text-xs", render: (r: any) => r.code ?? "–" },
                    { key: "item", label: t("col.item"), className: "max-w-48 truncate", render: (r: any) => r.item ?? <span className="text-muted italic">{t("prod.noName")}</span> },
                    { key: "units", label: t("col.units"), num: true, render: (r: any) => fmtNum(r.units) },
                  ]} />
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
