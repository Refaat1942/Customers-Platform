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
import { Card, ErrorBox, ExportButton, PageHeader } from "../components/ui";
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
  const query = { ...params, q, sort, desc, page, page_size: 50 };
  const res = useQuery({ queryKey: ["products", query], queryFn: () => api.get("/products", query), placeholderData: keepPreviousData });
  const [cats, setCats] = useState<any[]>([]);
  useEffect(() => { if (res.data?.by_category?.length) setCats(res.data.by_category); }, [res.data]);
  const c = (k: string, extra = {}) => ({ key: k, label: t(`col.${k}`), sortable: true, ...extra });
  return (
    <>
      <PageHeader title={t("prod.title")} subtitle={t("prod.subtitle")}
        actions={<ExportButton path="/products" params={{ ...params, q, sort, desc }} />} />
      <FilterBar />
      <div className="space-y-5">
        {cats.length > 0 && (
          <Card title={t("prod.byCategory")}>
            <RankBars data={cats.slice(0, 15)} label="category" value="sales" name={t("col.sales")} />
          </Card>
        )}
        <Card help={t("prod.repeatHelp")}>
          <div className="relative mb-4">
            <Search size={16} className="absolute top-2.5 start-3 text-muted" />
            <input className="input ps-9" placeholder={t("prod.search")} value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          {res.error ? <ErrorBox error={res.error} /> : (
            <DataTable rows={res.data?.rows ?? []} total={res.data?.total} page={page} pageSize={50} onPage={setPage}
              sort={sort} desc={desc} onSort={(k, d) => { setSort(k); setDesc(d); }} loading={res.isFetching} maxHeight={640}
              onRowClick={(r) => nav(`/transactions?q=${encodeURIComponent(r.item)}`)}
              columns={[
                c("item", { className: "max-w-72 truncate font-medium" }),
                { key: "category", label: t("col.category"), render: (r: any) => r.category ?? r.material_group ?? "–" },
                c("sales", { num: true, render: (r: any) => fmtMoney(r.sales) }),
                c("share", { num: true, render: (r: any) => fmtPct(r.share) }),
                c("quantity", { num: true, render: (r: any) => fmtNum(r.quantity) }),
                c("invoices", { num: true, render: (r: any) => fmtInt(r.invoices) }),
                c("customers", { num: true, render: (r: any) => fmtInt(r.customers) }),
                { key: "repeat_buyers", label: t("col.repeat_buyers"), num: true, render: (r: any) => fmtInt(r.repeat_buyers) },
                c("repeat_rate", { num: true, render: (r: any) => fmtPct(r.repeat_rate) }),
                { key: "times_per_buyer", label: t("col.times_per_buyer"), num: true, render: (r: any) => fmtNum(r.times_per_buyer) },
                c("avg_price", { num: true, render: (r: any) => fmtMoney(r.avg_price) }),
                { key: "top_branch", label: t("col.top_branch") },
                c("last_sold", { render: (r: any) => fmtDate(r.last_sold) }),
              ]} />
          )}
        </Card>
      </div>
    </>
  );
}
