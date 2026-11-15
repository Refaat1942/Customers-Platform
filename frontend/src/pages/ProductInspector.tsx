import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Loader2, Plus, Search, X } from "lucide-react";
import { api, qs } from "../lib/api";
import { useBranchName, useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Card, Empty, ErrorBox, Modal, Notice, PageHeader, Spinner } from "../components/ui";
import { ListChecks, Download } from "lucide-react";

const SEL_KEY = "cp_inspect_sel";
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
  // selection lives in the browser session (hundreds of products do not fit in a link);
  // ?k=... links (from a product page) are added to it
  const [sel, setSel] = useState<Record<string, string>>(() => {
    try { return JSON.parse(sessionStorage.getItem(SEL_KEY) || "{}"); } catch { return {}; }
  });
  useEffect(() => { try { sessionStorage.setItem(SEL_KEY, JSON.stringify(sel)); } catch { /* */ } }, [sel]);
  useEffect(() => {
    const k = sp.getAll("k");
    if (k.length) { setSel((s0) => ({ ...s0, ...Object.fromEntries(k.filter((x) => !s0[x]).map((x) => [x, x.slice(2)])) })); setSp(new URLSearchParams(), { replace: true }); }
  }, []); // eslint-disable-line
  const keys = Object.keys(sel);
  const labels = sel;
  const [chooser, setChooser] = useState(false);
  const [interval, setInterval_] = useState<"day" | "week" | "month">("month");
  const [measure, setMeasure] = useState<"units" | "sales">("units");

  const setKeys = (k: string[]) => setSel((s0) => Object.fromEntries(k.map((x) => [x, s0[x] ?? x.slice(2)])));
  const add = (h: Hit) => setSel((s0) => ({ ...s0, [h.key]: label(h) }));
  const addMany = (hs: Hit[]) => setSel((s0) => ({ ...s0, ...Object.fromEntries(hs.map((h) => [h.key, label(h)])) }));
  const remove = (k: string) => setSel((s0) => { const n = { ...s0 }; delete n[k]; return n; });

  const keySig = keys.slice().sort().join("|");
  const q = useQuery({
    queryKey: ["inspect", keySig, interval, ...key], enabled: keys.length > 0, placeholderData: keepPreviousData,
    queryFn: () => api.post(`/products/inspect${qs(params)}`, { keys, interval }),
  });
  const d = q.data;
  useEffect(() => {
    if (d?.products) setSel((l) => {
      let changed = false; const n = { ...l };
      for (const p of d.products) if (n[p.key] !== undefined && n[p.key] !== label(p)) { n[p.key] = label(p); changed = true; }
      return changed ? n : l;
    });
  }, [d]);

  const name = (k: string) => (k === "_all" ? t("insp.allSel", { n: fmtInt(keys.length) }) : labels[k] ?? k.slice(2));
  const shown: string[] = d?.series ?? keys.slice(0, 10);
  const color = (k: string) => (k === "_all" ? "#3b3f3b" : SERIES[Math.max(0, shown.filter((x) => x !== "_all").indexOf(k)) % SERIES.length]);
  const series = shown.map((k) => ({ key: k, name: name(k) }));
  // bars: one bar per product for small selections, only the total for big ones
  const barSeries = shown.includes("_all") ? series.filter((x) => x.key === "_all") : series;
  const barColors = barSeries.map((x) => color(x.key));
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
      for (const k of shown) r[k] = r[k] ?? 0;
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
        actions={keys.length > 0 && <InspectExport params={params} keys={keys} interval={interval} />} />
      <FilterBar />
      {f?.type?.length > 0 && <div className="text-sm mb-3 -mt-2"><Notice kind="info">{t("insp.typeOn", { types: f.type.join("، ") })}</Notice></div>}

      <Card title={t("insp.pick")} help={t("insp.pickHelp")} className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn-primary" onClick={() => setChooser(true)}><ListChecks size={16} /> {t("insp.choose")}</button>
          <span className="text-sm text-muted">{t("insp.orSearch")}</span>
          <div className="flex-1 min-w-64"><Picker onPick={add} chosen={keys} /></div>
        </div>
        {keys.length > 0 && (
          <div className="mt-3">
            <div className="text-sm font-semibold mb-2">{t("insp.selected", { n: fmtInt(keys.length) })}
              <button className="text-sm text-bad hover:underline cursor-pointer ms-3 font-normal" onClick={() => setKeys([])}>{t("insp.clear")}</button></div>
            <div className="flex flex-wrap gap-2 max-h-36 overflow-auto">
              {keys.slice(0, 200).map((k) => (
                <span key={k} className="inline-flex items-center gap-2 rounded-full border border-line bg-white ps-3 pe-1 py-1 text-sm">
                  {shown.includes(k) && <span className="size-2.5 rounded-full" style={{ background: color(k) }} />}
                  <span className="max-w-72 truncate">{name(k)}</span>
                  <button className="rounded-full p-1 hover:bg-red-50 text-muted hover:text-bad cursor-pointer" onClick={() => remove(k)} title={t("app.delete")}><X size={13} /></button>
                </span>
              ))}
              {keys.length > 200 && <span className="text-sm text-muted self-center">+{fmtInt(keys.length - 200)}</span>}
            </div>
          </div>
        )}
        {chooser && <Chooser params={params} chosen={sel} onClose={() => setChooser(false)}
          onApply={(hs) => { setSel(Object.fromEntries(hs.map((h) => [h.key, label(h)]))); setChooser(false); }} onAdd={addMany} />}
      </Card>

      {keys.length === 0 ? <Notice kind="info">{t("insp.empty")}</Notice> : q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : !d?.products?.length ? <Empty /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <Toggle value={measure} onChange={setMeasure} items={[["units", t("col.units")], ["sales", t("col.sales")]]} label={t("insp.show")} />
            <Toggle value={interval} onChange={setInterval_} items={[["day", t("insp.day")], ["week", t("insp.week")], ["month", t("insp.month")]]} label={t("insp.every")} />
            {q.isFetching && <Loader2 size={16} className="animate-spin text-muted" />}
          </div>

          <Card title={t("insp.summary")}>
            {keys.length > 10 && <div className="text-xs text-muted mb-2">{t("insp.manyNote")}</div>}
            <DataTable rows={d.products} maxHeight={480} onRowClick={(r: any) => nav(`/products/item?key=${encodeURIComponent(r.key)}`)} columns={[
              { key: "x", label: "", render: (r: any) => shown.includes(r.key) ? <span className="inline-block size-3 rounded-full" style={{ background: color(r.key) }} /> : null },
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
            {timeline.length ? <MultiLines data={timeline} x="period" series={series} money={money} colors={shown.map(color)} /> : <Empty />}
          </Card>

          <div className="grid lg:grid-cols-2 gap-5">
            <Card title={t("insp.byType")}>
              {byType.length ? <StackedBars grouped money={money} data={byType} x="sales_type" series={barSeries} colors={barColors} /> : <Empty />}
            </Card>
            <Card title={t("insp.byShift")}>
              {byShift.length ? <StackedBars grouped money={money} data={byShift} x="shift" series={barSeries} colors={barColors} /> : <Empty />}
            </Card>
          </div>
          <Card title={t("insp.byBranch")}>
            {byBranch.length ? <StackedBars grouped money={money} data={byBranch} x="branch" series={barSeries} colors={barColors} height={320} /> : <Empty />}
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

function InspectExport({ params, keys, interval }: { params: Record<string, any>; keys: string[]; interval: string }) {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      const res = await api.raw("POST", `/products/inspect${qs(params)}`, { keys, interval, export: true, lang: i18n.language });
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a"); a.href = url; a.download = "products_inspect.xlsx";
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  };
  return <button className="btn-ghost" disabled={busy} onClick={go}>{busy ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />} {t("app.export")}</button>;
}

/** Every product with checkboxes: search, filter by category / sub-category / brand,
 *  tick rows or "Select all" that match. */
function Chooser({ params, chosen, onClose, onApply }: {
  params: Record<string, any>; chosen: Record<string, string>; onClose: () => void; onApply: (h: Hit[]) => void; onAdd: (h: Hit[]) => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [only, setOnly] = useState<{ only_category?: string; only_subcategory?: string; only_brand?: string }>({});
  const [picked, setPicked] = useState<Record<string, Hit>>(() => Object.fromEntries(Object.entries(chosen).map(([k, v]) => [k, { key: k, code: null, item: v }])));
  const [busy, setBusy] = useState(false);
  useEffect(() => { const h = setTimeout(() => setQ(text.trim()), 300); return () => clearTimeout(h); }, [text]);
  useEffect(() => setPage(1), [q, only]);
  const query = { ...params, q, page, page_size: 100, sort: "sales", desc: true, ...only };
  const res = useQuery({ queryKey: ["chooser", query], queryFn: () => api.get("/products", query), placeholderData: keepPreviousData });
  const [opts, setOpts] = useState<any>(null);
  useEffect(() => { if (res.data?.options) setOpts(res.data.options); }, [res.data]);
  const rows: any[] = res.data?.rows ?? [];
  const total = res.data?.total ?? 0;
  const n = Object.keys(picked).length;
  const toggle = (r: any) => setPicked((p) => { const c = { ...p }; if (c[r.key]) delete c[r.key]; else c[r.key] = { key: r.key, code: r.code, item: r.item }; return c; });
  const pageAll = rows.length > 0 && rows.every((r) => picked[r.key]);
  const togglePage = () => setPicked((p) => {
    const c = { ...p };
    if (pageAll) rows.forEach((r) => delete c[r.key]); else rows.forEach((r) => { c[r.key] = { key: r.key, code: r.code, item: r.item }; });
    return c;
  });
  const selectAll = async () => {
    setBusy(true);
    try {
      const all = await api.get("/products/keys", { ...params, q, ...only });
      setPicked((p) => ({ ...p, ...Object.fromEntries(all.rows.map((r: any) => [r.key, { key: r.key, code: r.code, item: r.item }])) }));
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  };
  const sel = (name: "only_category" | "only_subcategory" | "only_brand", label: string, list?: string[]) => list?.length ? (
    <label className="text-sm"><span className="label">{label}</span>
      <select className="input py-1.5" value={only[name] ?? ""} onChange={(e) => setOnly((o) => ({ ...o, [name]: e.target.value || undefined }))}>
        <option value="">{t("app.all")}</option>
        {list.map((v) => <option key={v} value={v}>{v}</option>)}
      </select></label>
  ) : null;
  return (
    <Modal title={t("insp.choose")} onClose={onClose} wide>
      <div className="flex flex-wrap items-end gap-3 mb-3">
        <div className="relative flex-1 min-w-56">
          <Search size={16} className="absolute top-2.5 start-3 text-muted" />
          <input className="input ps-9" placeholder={t("prod.search")} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
        </div>
        {sel("only_category", t("col.category"), opts?.category)}
        {sel("only_subcategory", t("col.subcategory"), opts?.subcategory)}
        {sel("only_brand", t("col.brand"), opts?.brand)}
      </div>
      <div className="flex flex-wrap items-center gap-3 mb-3 text-sm">
        <button className="btn-primary" disabled={busy || !total} onClick={selectAll}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <ListChecks size={15} />} {t("insp.selectAll", { n: fmtInt(Math.min(total, 5000)) })}
        </button>
        <button className="btn-ghost" onClick={() => setPicked({})}>{t("insp.clear")}</button>
        <span className="ms-auto font-semibold">{t("insp.selected", { n: fmtInt(n) })}</span>
      </div>
      <div className="border border-line rounded-lg overflow-auto max-h-[55vh]">
        <table className="w-full text-sm">
          <thead className="bg-surface sticky top-0">
            <tr>
              <th className="th w-10"><input type="checkbox" className="accent-brand size-4 cursor-pointer" checked={pageAll} onChange={togglePage} title={t("insp.page")} /></th>
              <th className="th">{t("col.code")}</th><th className="th">{t("col.item")}</th><th className="th">{t("col.category")}</th>
              <th className="th">{t("col.brand")}</th><th className="th text-end">{t("col.units")}</th><th className="th text-end">{t("col.sales")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} onClick={() => toggle(r)} className={`border-t border-line cursor-pointer ${picked[r.key] ? "bg-brand-soft" : "hover:bg-surface"}`}>
                <td className="td"><input type="checkbox" className="accent-brand size-4 pointer-events-none" readOnly checked={!!picked[r.key]} /></td>
                <td className="td font-mono text-xs">{r.code ?? "–"}</td>
                <td className="td max-w-80 truncate">{r.item ?? <i className="text-muted">{t("prod.noName")}</i>}</td>
                <td className="td text-xs">{r.category ?? "–"}{r.subcategory ? ` · ${r.subcategory}` : ""}</td>
                <td className="td text-xs">{r.brand ?? "–"}</td>
                <td className="td text-end num">{fmtNum(r.quantity)}</td>
                <td className="td text-end num">{fmtMoney(r.sales)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {res.isFetching && !rows.length && <Spinner />}
        {!res.isFetching && !rows.length && <div className="p-6 text-center text-muted text-sm">{t("app.noData")}</div>}
      </div>
      <div className="flex items-center justify-between mt-3 text-sm">
        <span className="text-muted">{fmtInt(total)} {t("insp.products")}</span>
        <div className="flex items-center gap-2">
          <button className="btn-ghost py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
          <span className="num">{page} / {Math.max(1, Math.ceil(total / 100))}</span>
          <button className="btn-ghost py-1" disabled={page * 100 >= total} onClick={() => setPage(page + 1)}>›</button>
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-4 border-t border-line pt-4">
        <button className="btn-ghost" onClick={onClose}>{t("app.cancel")}</button>
        <button className="btn-primary" disabled={!n} onClick={() => onApply(Object.values(picked))}>{t("insp.apply", { n: fmtInt(n) })}</button>
      </div>
    </Modal>
  );
}
