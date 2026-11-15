import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { Link } from "react-router-dom";
import { Card, ErrorBox, ExportButton, Notice, PageHeader } from "../components/ui";
import { ScanSearch } from "lucide-react";
import { useAuth } from "../lib/auth";
import { RankBars } from "../components/charts";

export default function Products() {
  const { t } = useTranslation();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("sales");
  const [desc, setDesc] = useState(true);
  useEffect(() => { const h = setTimeout(() => setQ(text.trim()), 350); return () => clearTimeout(h); }, [text]);
  useEffect(() => setPage(1), [q, sort, desc, ...key]); // eslint-disable-line
  const [group, setGroup] = useState<"category" | "subcategory" | "brand" | "manufacturer">("category");
  const query = { ...params, q, sort, desc, page, page_size: 50, group };
  const res = useQuery({ queryKey: ["products", query], queryFn: () => api.get("/products", query), placeholderData: keepPreviousData });
  const [cats, setCats] = useState<any[]>([]);
  const [groups, setGroups] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (res.data?.by_category?.length) setCats(res.data.by_category);
    if (res.data?.groups) setGroups(res.data.groups);
  }, [res.data]);
  const { can } = useAuth();
  const [picked, setPicked] = useState<string[]>([]);
  const toggle = (k: string) => setPicked((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const [names, setNames] = useState<any>(null);
  useEffect(() => { if (res.data?.names) setNames(res.data.names); }, [res.data]);
  const c = (k: string, extra = {}) => ({ key: k, label: t(`col.${k}`), sortable: true, ...extra });
  return (
    <>
      <PageHeader title={t("prod.title")} subtitle={t("prod.subtitle")}
        actions={<>
          <button className="btn-primary" onClick={() => {
            if (picked.length) {
              const names = Object.fromEntries((res.data?.rows ?? []).map((r: any) => [r.key, [r.code, r.item].filter(Boolean).join(" · ")]));
              try { sessionStorage.setItem("cp_inspect_sel", JSON.stringify(Object.fromEntries(picked.map((k) => [k, names[k] ?? k.slice(2)])))); } catch { /* */ }
            }
            nav("/products/inspect");
          }}>
            <ScanSearch size={16} /> {picked.length ? t("insp.openN", { n: picked.length }) : t("insp.title")}
          </button>
          <ExportButton path="/products" params={{ ...params, q, sort, desc }} />
        </>} />
      <FilterBar />
      <div className="space-y-5">
        {names?.codes_without_name > 0 && (
          <Notice kind="warning">
            <div>{t("prod.namesMissing", { n: fmtInt(names.codes_without_name) })}</div>
            <div className="mt-1">{t("prod.namesFix")} {can("import") && <Link to="/import" className="underline font-semibold">{t("nav.import")}</Link>}</div>
          </Notice>
        )}
        {cats.length > 0 && (
          <Card title={t(`prod.byGroup.${group}`)} actions={
            <label className="flex items-center gap-2 text-sm"><span className="text-muted">{t("prod.groupBy")}</span>
              <select className="input py-1.5 w-auto" value={group} onChange={(e) => setGroup(e.target.value as typeof group)}>
                {(["category", "subcategory", "brand", "manufacturer"] as const).filter((g) => g === "category" || groups[g] || group === g).map((g) =>
                  <option key={g} value={g}>{g === "category" ? t("col.category") : t(`col.${g}`)}</option>)}
              </select>
            </label>}>
            <RankBars data={cats.slice(0, 15)} label="category" value="sales" name={t("col.sales")} />
          </Card>
        )}
        <Card help={`${t("prod.open")} ${t("prod.repeatHelp")}`}>
          <div className="relative mb-4">
            <Search size={16} className="absolute top-2.5 start-3 text-muted" />
            <input className="input ps-9" placeholder={t("prod.search")} value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          {res.error ? <ErrorBox error={res.error} /> : (
            <DataTable rows={res.data?.rows ?? []} total={res.data?.total} page={page} pageSize={50} onPage={setPage}
              sort={sort} desc={desc} onSort={(k, d) => { setSort(k); setDesc(d); }} loading={res.isFetching} maxHeight={640}
              onRowClick={(r) => nav(`/products/item?key=${encodeURIComponent(r.key)}`)}
              columns={[
                { key: "x", label: "", render: (r: any) => (
                  <input type="checkbox" className="accent-brand size-4 cursor-pointer" title={t("insp.tick")} checked={picked.includes(r.key)}
                    onClick={(e) => e.stopPropagation()} onChange={() => toggle(r.key)} />
                ) },
                c("code", { className: "font-mono text-xs whitespace-nowrap", render: (r: any) => r.code ?? "–" }),
                c("item", { className: "max-w-80 truncate font-medium", render: (r: any) => r.item ?? <span className="text-muted italic font-normal">{t("prod.noName")}</span> }),
                c("category", { render: (r: any) => r.category ?? r.material_group ?? "–" }),
                ...(groups.subcategory ? [c("subcategory", { render: (r: any) => r.subcategory ?? "–" })] : []),
                ...(groups.brand ? [c("brand", { render: (r: any) => r.brand ?? "–" })] : []),
                c("sales", { num: true, render: (r: any) => fmtMoney(r.sales) }),
                c("share", { num: true, render: (r: any) => fmtPct(r.share) }),
                c("quantity", { num: true, render: (r: any) => fmtNum(r.quantity) }),
                c("invoices", { num: true, render: (r: any) => fmtInt(r.invoices) }),
                c("customers", { num: true, render: (r: any) => fmtInt(r.customers) }),
                { key: "repeat_buyers", label: t("col.repeat_buyers"), num: true, render: (r: any) => fmtInt(r.repeat_buyers) },
                c("repeat_rate", { num: true, render: (r: any) => fmtPct(r.repeat_rate) }),
                { key: "times_per_buyer", label: t("col.times_per_buyer"), num: true, render: (r: any) => fmtNum(r.times_per_buyer) },
                c("avg_price", { num: true, render: (r: any) => fmtMoney(r.avg_price) }),
                c("avg_days_between", { num: true, render: (r: any) => (r.avg_days_between == null ? "–" : t("prod.days", { n: fmtInt(r.avg_days_between) })) }),
                { key: "top_branch", label: t("col.top_branch") },
                c("branches", { num: true, render: (r: any) => fmtInt(r.branches) }),
                c("last_sold", { render: (r: any) => fmtDate(r.last_sold) }),
              ]} />
          )}
        </Card>
      </div>
    </>
  );
}
