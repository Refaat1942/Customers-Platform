import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Loader2, Plus, Search, X } from "lucide-react";
import { api } from "../lib/api";
import { useBranchName, useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Card, Empty, ErrorBox, ExportButton, Notice, PageHeader, Spinner } from "../components/ui";
import { MultiLines, SERIES, StackedBars } from "../components/charts";

type Hit = { key: string; code: string | null; item: string | null; brand?: string | null };

/** Pick one or many products and see them side by side, within the filters above
 *  (dates, branches, sales types, districts). */
export default function ProductInspector() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const branchName = useBranchName();
  const { params, key, f } = useFilters();
  const [sp, setSp] = useSearchParams();
  const keys = sp.getAll("k");
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [interval, setInterval_] = useState<"day" | "week" | "month">("month");
  const [measure, setMeasure] = useState<"units" | "sales">("units");

  const setKeys = (k: string[]) => { const n = new URLSearchParams(); k.forEach((x) => n.append("k", x)); setSp(n, { replace: true }); };
  const add = (h: Hit) => { if (!keys.includes(h.key)) setKeys([...keys, h.key]); setLabels((l) => ({ ...l, [h.key]: label(h) })); };
  const remove = (k: string) => setKeys(keys.filter((x) => x !== k));

  const q = useQuery({
    queryKey: ["inspect", keys, interval, ...key], enabled: keys.length > 0, placeholderData: keepPreviousData,
    queryFn: () => api.get("/products/inspect", { ...params, keys, interval }),
  });
  const d = q.data;
  useEffect(() => {
    if (d?.products) setLabels((l) => ({ ...l, ...Object.fromEntries(d.products.map((p: any) => [p.key, label(p)])) }));
  }, [d]);

  const name = (k: string) => labels[k] ?? k.slice(2);
  const color = (k: string) => SERIES[Math.max(0, keys.indexOf(k)) % SERIES.length];
  const series = keys.map((k) => ({ key: k, name: name(k) }));
  const pivot = (rows: any[], dim: string, render?: (v: string) => string) => {
    const m = new Map<string, any>();
    for (const r of rows ?? []) {
      const o = m.get(r[dim]) ?? { [dim]: render ? render(r[dim]) : r[dim], _total: 0 };
      o[r.key] = (o[r.key] ?? 0) + (r[measure] ?? 0); o._total += r[measure] ?? 0;
      m.set(r[dim], o);
    }
    return [...m.values()];
  };
  // every period between the first and last sale, with 0 where a product sold nothing
  const timeline = useMemo(() => {
    const rows = pivot(d?.timeline, "period");
    if (!rows.length) return rows;
    const byP = new Map(rows.map((r) => [r.period, r]));
    const ps = [...byP.keys()].sort();
    const out: any[] = [];
    const step = (x: string) => {
      if (interval === "month") { const [y, m] = x.split("-").map(Number); return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`; }
      const dt = new Date(x + "T00:00:00Z"); dt.setUTCDate(dt.getUTCDate() + (interval === "week" ? 7 : 1));
      return dt.toISOString().slice(0, 10);
    };
    for (let p = ps[0], n = 0; p <= ps[ps.length - 1] && n < 1500; p = step(p), n++) {
      const r = { ...(byP.get(p) ?? { period: p }) };
      for (const k of keys) r[k] = r[k] ?? 0;
      out.push(r);
    }
    return out;
  }, [d, measure, interval]); // eslint-disable-line
  const byType = useMemo(() => pivot(d?.by_type, "sales_type").sort((a, b) => b._total - a._total), [d, measure]); // eslint-disable-line
  const byBranch = useMemo(() => pivot(d?.by_branch, "branch", (v) => branchName(v)).sort((a, b) => b._total - a._total).slice(0, 20), [d, measure]); // eslint-disable-line
  const byShift = useMemo(() => pivot(d?.by_shift, "shift", (v) => t(`shift.${v}`)), [d, measure]); // eslint-disable-line
  const money = measure === "sales";

  return (
    <>
      <Link to="/products" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink mb-2"><ArrowLeft size={15} className="rtl:rotate-180" /> {t("pd.back")}</Link>
      <PageHeader title={t("insp.title")} subtitle={t("insp.subtitle")}
        actions={keys.length > 0 && <ExportButton path="/products/inspect" params={{ ...params, keys, interval }} />} />
      <FilterBar />
      {f?.type?.length > 0 && <div className="text-sm mb-3 -mt-2"><Notice kind="info">{t("insp.typeOn", { types: f.type.join("، ") })}</Notice></div>}

      <Card title={t("insp.pick")} help={t("insp.pickHelp")} className="mb-5">
        <Picker onPick={add} chosen={keys} />
        {keys.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {keys.map((k) => (
              <span key={k} className="inline-flex items-center gap-2 rounded-full border border-line bg-white ps-3 pe-1 py-1 text-sm">
                <span className="size-2.5 rounded-full" style={{ background: color(k) }} />
                <span className="max-w-72 truncate">{name(k)}</span>
                <button className="rounded-full p-1 hover:bg-red-50 text-muted hover:text-bad cursor-pointer" onClick={() => remove(k)} title={t("app.delete")}><X size={13} /></button>
              </span>
            ))}
            <button className="text-sm text-bad hover:underline cursor-pointer ms-1" onClick={() => setKeys([])}>{t("insp.clear")}</button>
          </div>
        )}
      </Card>

      {keys.length === 0 ? <Notice kind="info">{t("insp.empty")}</Notice> : q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : !d?.products?.length ? <Empty /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <Toggle value={measure} onChange={setMeasure} items={[["units", t("col.units")], ["sales", t("col.sales")]]} label={t("insp.show")} />
            <Toggle value={interval} onChange={setInterval_} items={[["day", t("insp.day")], ["week", t("insp.week")], ["month", t("insp.month")]]} label={t("insp.every")} />
            {q.isFetching && <Loader2 size={16} className="animate-spin text-muted" />}
          </div>

          <Card title={t("insp.summary")}>
            <DataTable rows={d.products} onRowClick={(r: any) => nav(`/products/item?key=${encodeURIComponent(r.key)}`)} columns={[
              { key: "x", label: "", render: (r: any) => <span className="inline-block size-3 rounded-full" style={{ background: color(r.key) }} /> },
              { key: "code", label: t("col.code"), className: "font-mono text-xs", render: (r: any) => r.code ?? "–" },
              { key: "item", label: t("col.item"), className: "max-w-72 truncate font-medium", render: (r: any) => r.item ?? <span className="italic text-muted">{t("prod.noName")}</span> },
              { key: "units", label: t("col.units"), num: true, render: (r: any) => fmtNum(r.units) },
              { key: "sales", label: t("col.sales"), num: true, render: (r: any) => fmtMoney(r.sales) },
              { key: "share", label: "%", num: true, render: (r: any) => fmtPct(r.share) },
              { key: "invoices", label: t("col.invoices"), num: true, render: (r: any) => fmtInt(r.invoices) },
              { key: "customers", label: t("col.customers"), num: true, render: (r: any) => fmtInt(r.customers) },
              { key: "avg_price", label: t("col.avg_price"), num: true, render: (r: any) => fmtMoney(r.avg_price) },
              { key: "first_sold", label: t("insp.first"), render: (r: any) => fmtDate(r.first_sold) },
              { key: "last_sold", label: t("col.last_sold"), render: (r: any) => fmtDate(r.last_sold) },
            ]} />
            {d.missing?.length > 0 && <div className="text-xs text-muted mt-2">{t("insp.noSales", { items: d.missing.map(name).join("، ") })}</div>}
          </Card>

          <Card title={t(`insp.over.${measure}`)}>
            {timeline.length ? <MultiLines data={timeline} x="period" series={series} money={money} /> : <Empty />}
          </Card>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("insp.byType")}>
              {byType.length ? <StackedBars grouped money={money} data={byType} x="sales_type" series={series} colors={keys.map(color)} /> : <Empty />}
            </Card>
            <Card title={t("insp.byShift")}>
              {byShift.length ? <StackedBars grouped money={money} data={byShift} x="shift" series={series} colors={keys.map(color)} /> : <Empty />}
            </Card>
          </div>
          <Card title={t("insp.byBranch")}>
            {byBranch.length ? <StackedBars grouped money={money} data={byBranch} x="branch" series={series} colors={keys.map(color)} height={320} /> : <Empty />}
          </Card>

          <Card title={t("insp.buyers")}>
            <DataTable rows={d.buyers} maxHeight={480} onRowClick={(r: any) => nav(`/customers/${r.cid}`)} columns={[
              { key: "phone", label: t("col.phone"), className: "font-mono text-xs" },
              { key: "name", label: t("col.name"), className: "max-w-56 truncate" },
              { key: "branch", label: t("col.branch") },
              { key: "purchases", label: t("col.purchases"), num: true, render: (r: any) => fmtInt(r.purchases) },
              { key: "units", label: t("col.units"), num: true, render: (r: any) => fmtNum(r.units) },
              { key: "sales", label: t("col.sales"), num: true, render: (r: any) => fmtMoney(r.sales) },
              { key: "last_bought", label: t("col.last_bought"), render: (r: any) => fmtDate(r.last_bought) },
              { key: "products", label: t("insp.which"), className: "max-w-72 truncate text-xs text-muted" },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}

const label = (h: { code?: string | null; item?: string | null }) => [h.code, h.item].filter(Boolean).join(" · ") || "–";

function Picker({ onPick, chosen }: { onPick: (h: Hit) => void; chosen: string[] }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { const h = setTimeout(() => setQ(text.trim()), 250); return () => clearTimeout(h); }, [text]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);
  const res = useQuery({ queryKey: ["psearch", q], enabled: q.length >= 2, queryFn: () => api.get<Hit[]>("/products/search", { q }) });
  return (
    <div ref={ref} className="relative max-w-2xl">
      <Search size={16} className="absolute top-2.5 start-3 text-muted" />
      <input className="input ps-9" placeholder={t("insp.search")} value={text} onFocus={() => setOpen(true)}
        onChange={(e) => { setText(e.target.value); setOpen(true); }} />
      {open && q.length >= 2 && (
        <div className="absolute z-30 mt-1 w-full card shadow-xl max-h-80 overflow-auto p-1">
          {res.isLoading ? <div className="p-3 text-sm text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin" />{t("app.loading")}</div>
            : !res.data?.length ? <div className="p-3 text-sm text-muted">{t("app.noData")}</div>
            : res.data.map((h) => {
              const on = chosen.includes(h.key);
              return (
                <button key={h.key} disabled={on} onClick={() => { onPick(h); setText(""); setOpen(false); }}
                  className="w-full flex items-center gap-3 text-start rounded-lg px-3 py-2 text-sm hover:bg-brand-soft cursor-pointer disabled:opacity-40 disabled:cursor-default">
                  <Plus size={14} className="text-brand shrink-0" />
                  <span className="font-mono text-xs text-muted w-20 shrink-0">{h.code ?? "–"}</span>
                  <span className="flex-1 truncate">{h.item ?? <i className="text-muted">{t("prod.noName")}</i>}</span>
                  {h.brand && <span className="text-xs text-muted">{h.brand}</span>}
                </button>
              );
            })}
        </div>
      )}
    </div>
  );
}

function Toggle<T extends string>({ value, onChange, items, label }: { value: T; onChange: (v: T) => void; items: [T, string][]; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-muted">{label}</span>
      <span className="inline-flex rounded-lg border border-line overflow-hidden">
        {items.map(([k, l]) => (
          <button key={k} onClick={() => onChange(k)} className={`px-3 py-1.5 cursor-pointer ${value === k ? "bg-brand text-white" : "bg-white hover:bg-brand-soft"}`}>{l}</button>
        ))}
      </span>
    </span>
  );
}
