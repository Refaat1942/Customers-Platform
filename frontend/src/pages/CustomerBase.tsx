import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtInt, fmtMoney, fmtPct } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, Empty, ErrorBox, ExportButton, Kpi, MultiSelect, PageHeader, Spinner } from "../components/ui";
import { RankBars, ShareBar } from "../components/charts";

export default function CustomerBase() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const sum = useQuery({ queryKey: ["dir_summary"], queryFn: () => api.get("/directory/summary") });
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("name");
  const [desc, setDesc] = useState(false);
  const [bought, setBought] = useState<"" | "true" | "false">("");
  const [region, setRegion] = useState<string[]>([]);
  const [city, setCity] = useState<string[]>([]);
  const [district, setDistrict] = useState<string[]>([]);
  const [filters, setFilters] = useState<Record<string, string[]> | null>(null);
  useEffect(() => { const h = setTimeout(() => setQ(text.trim()), 350); return () => clearTimeout(h); }, [text]);
  useEffect(() => setPage(1), [q, sort, desc, bought, region, city, district]);
  const query = { q, sort, desc, page, page_size: 50, bought: bought || undefined, region, city, district };
  const list = useQuery({ queryKey: ["directory", query], queryFn: () => api.get("/directory", query), placeholderData: keepPreviousData });
  useEffect(() => { if (list.data?.filters) setFilters(list.data.filters); }, [list.data]);

  const k = sum.data?.kpis;
  const pct = (n: number) => (k?.total ? fmtPct((100 * n) / k.total) : undefined);
  const bars = (rows: any[]) => rows.filter((r) => r.label !== "—").slice(0, 15);

  return (
    <>
      <PageHeader title={t("base.title")} subtitle={t("base.subtitle")}
        actions={<ExportButton path="/directory" params={{ ...query, page: undefined, page_size: undefined }} />} />
      {sum.isLoading ? <Spinner /> : sum.error ? <ErrorBox error={sum.error} /> : !k?.total ? <Empty /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
            <Kpi label={t("base.total")} value={fmtInt(k.total)} />
            <Kpi label={t("base.valid")} value={fmtInt(k.valid_phones)} sub={pct(k.valid_phones)} />
            <Kpi label={t("base.withAddress")} value={fmtInt(k.with_address)} sub={pct(k.with_address)} />
            <Kpi label={t("base.withDistrict")} value={fmtInt(k.with_district)} sub={pct(k.with_district)} />
            <Kpi label={t("base.bought")} value={fmtInt(k.bought)} sub={pct(k.bought)} />
            <Kpi label={t("base.never")} value={fmtInt(k.never_bought)} sub={pct(k.never_bought)} />
          </div>
          <Card title={t("base.quality")}>
            <ShareBar parts={[
              { label: t("base.valid"), value: k.valid_phones, color: "#1a7f37" },
              { label: t("base.invalid"), value: k.invalid_phones, color: "#c62828" },
            ]} />
          </Card>
          <div className="grid lg:grid-cols-2 gap-5">
            {([["byRegion", "by_region", region, setRegion], ["byCity", "by_city", city, setCity], ["byDistrict", "by_district", district, setDistrict], ["byArea", "by_area", null, null]] as const).map(([title, key, sel, setSel]) =>
              bars(sum.data[key]).length > 0 && (
                <Card key={key} title={t(`base.${title}`)}>
                  <RankBars data={bars(sum.data[key])} label="label" value="customers" name={t("col.customers")} money={false}
                    onClick={setSel ? (r) => r?.label && (setSel as (v: string[]) => void)((sel as string[]).includes(r.label) ? [] : [r.label]) : undefined} />
                </Card>
              ))}
          </div>
          <Card>
            <div className="flex flex-wrap items-end gap-3 mb-4">
              <div className="relative flex-1 min-w-56">
                <Search size={16} className="absolute top-2.5 start-3 text-muted" />
                <input className="input ps-9" placeholder={t("base.search")} value={text} onChange={(e) => setText(e.target.value)} />
              </div>
              <div>
                <span className="label">&nbsp;</span>
                <select className="input" value={bought} onChange={(e) => setBought(e.target.value as "" | "true" | "false")}>
                  <option value="">{t("base.all")}</option><option value="true">{t("base.yes")}</option><option value="false">{t("base.no")}</option>
                </select>
              </div>
              {filters?.region?.length ? <MultiSelect label={t("dir.region")} options={filters.region} value={region} onChange={setRegion} /> : null}
              {filters?.city?.length ? <MultiSelect label={t("dir.city")} options={filters.city} value={city} onChange={setCity} /> : null}
              {filters?.district?.length ? <MultiSelect label={t("col.district")} options={filters.district} value={district} onChange={setDistrict} /> : null}
            </div>
            {list.error ? <ErrorBox error={list.error} /> : (
              <DataTable rows={list.data?.rows ?? []} total={list.data?.total} page={page} pageSize={50} onPage={setPage}
                sort={sort} desc={desc} onSort={(k2, d) => { setSort(k2); setDesc(d); }} loading={list.isFetching} maxHeight={640}
                onRowClick={(r) => r.cid && nav(`/customers/${r.cid}`)}
                columns={[
                  { key: "phone", label: t("col.phone"), sortable: true, className: "font-mono text-xs", render: (r) => <span className={r.phone_valid ? "" : "text-bad"}>{r.phone}</span> },
                  { key: "name", label: t("col.name"), sortable: true, className: "max-w-56 truncate" },
                  { key: "region", label: t("dir.region"), sortable: true },
                  { key: "city", label: t("dir.city"), sortable: true },
                  { key: "district", label: t("col.district"), sortable: true },
                  { key: "area", label: t("dir.area"), sortable: true, className: "max-w-48 truncate" },
                  { key: "address", label: t("dir.address"), className: "max-w-72 truncate" },
                  { key: "bought", label: t("base.bought"), render: (r) => r.bought ? <Badge kind="active">{t("app.yes")}</Badge> : <span className="text-muted">{t("app.no")}</span> },
                  { key: "total_spent", label: t("col.total_spent"), sortable: true, num: true, render: (r) => (r.total_spent == null ? "–" : fmtMoney(r.total_spent)) },
                  { key: "visits", label: t("col.visits"), sortable: true, num: true, render: (r) => (r.visits == null ? "–" : fmtInt(r.visits)) },
                  { key: "last_visit", label: t("col.last_visit"), sortable: true, render: (r) => fmtDate(r.last_visit) },
                ]} />
            )}
          </Card>
        </div>
      )}
    </>
  );
}
