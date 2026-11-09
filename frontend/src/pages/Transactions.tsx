import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "../lib/api";
import { useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum } from "../lib/format";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { ErrorBox, ExportButton, PageHeader } from "../components/ui";

export default function Transactions() {
  const { t } = useTranslation();
  const { params, key } = useFilters();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [text, setText] = useState(sp.get("q") ?? "");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("invoice_date");
  const [desc, setDesc] = useState(true);
  useEffect(() => { const h = setTimeout(() => setQ(text.trim()), 350); return () => clearTimeout(h); }, [text]);
  useEffect(() => setPage(1), [q, sort, desc, ...key]); // eslint-disable-line
  const query = { ...params, q, sort, desc, page, page_size: 50 };
  const res = useQuery({ queryKey: ["sales", query], queryFn: () => api.get("/sales", query), placeholderData: keepPreviousData });
  const c = (k: string, extra = {}) => ({ key: k, label: t(`col.${k}`), sortable: true, ...extra });
  return (
    <>
      <PageHeader title={t("tx.title")} subtitle={t("tx.subtitle")}
        actions={<ExportButton path="/sales" params={{ ...params, q, sort, desc }} />} />
      <FilterBar />
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-4 mb-4">
          <div className="relative flex-1 min-w-56">
            <Search size={16} className="absolute top-2.5 start-3 text-muted" />
            <input className="input ps-9" placeholder={`${t("col.phone")} / ${t("col.name")} / ${t("col.item_name")} / ${t("col.invoice_no")}`} value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          {res.data && <div className="text-sm text-muted">{fmtInt(res.data.total)} {t("app.rows")} · <b className="text-ink num">{fmtMoney(res.data.sales)}</b></div>}
        </div>
        {res.error ? <ErrorBox error={res.error} /> : (
          <DataTable rows={res.data?.rows ?? []} total={res.data?.total} page={page} pageSize={50} onPage={setPage}
            sort={sort} desc={desc} onSort={(k, d) => { setSort(k); setDesc(d); }} loading={res.isFetching} maxHeight={640}
            onRowClick={(r) => r.cid && nav(`/customers/${r.cid}`)}
            columns={[
              c("invoice_date", { render: (r: any) => fmtDate(r.invoice_date, true) }),
              c("phone", { className: "font-mono text-xs" }), c("name"), c("branch"), c("district"),
              c("invoice_no", { sortable: false }), c("invoice_type"), c("item_name", { className: "max-w-64 truncate" }),
              c("item_category"), c("quantity", { num: true, render: (r: any) => fmtNum(r.quantity) }),
              c("item_price", { num: true, render: (r: any) => fmtMoney(r.item_price) }),
            ]} />
        )}
      </div>
    </>
  );
}
