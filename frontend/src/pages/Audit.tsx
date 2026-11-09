import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { fmtDate } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, ErrorBox, ExportButton, PageHeader } from "../components/ui";

export default function Audit() {
  const { t } = useTranslation();
  const [f, setF] = useState({ username: "", action: "", q: "", date_from: "", date_to: "" });
  const [text, setText] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => { const h = setTimeout(() => setF((s) => ({ ...s, q: text })), 350); return () => clearTimeout(h); }, [text]);
  useEffect(() => setPage(1), [f]);
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<any[]>("/users") });
  const params = { ...f, page, page_size: 50 };
  const q = useQuery({ queryKey: ["audit", params], queryFn: () => api.get("/audit", params), placeholderData: keepPreviousData });
  const kind = (a: string) => (a.includes("failed") || a.includes("delete") ? "inactive" : a.startsWith("export") || a.startsWith("view") ? undefined : a === "login" ? "active" : "attention");
  return (
    <>
      <PageHeader title={t("audit.title")} actions={<ExportButton path="/audit" params={f} />} />
      <div className="card p-4">
        <div className="flex flex-wrap gap-3 items-end mb-4">
          <div><span className="label">{t("audit.user")}</span>
            <select className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })}>
              <option value="">{t("app.all")}</option>{users.data?.map((u) => <option key={u.id}>{u.username}</option>)}
            </select></div>
          <div><span className="label">{t("audit.action")}</span>
            <select className="input" value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })}>
              <option value="">{t("app.all")}</option>{q.data?.actions?.map((a: string) => <option key={a}>{a}</option>)}
            </select></div>
          <div><span className="label">{t("filters.from")}</span><input type="date" className="input" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></div>
          <div><span className="label">{t("filters.to")}</span><input type="date" className="input" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></div>
          <div className="flex-1 min-w-48"><span className="label">{t("audit.details")}</span><input className="input" placeholder={t("app.search")} value={text} onChange={(e) => setText(e.target.value)} /></div>
        </div>
        {q.error ? <ErrorBox error={q.error} /> : (
          <DataTable rows={q.data?.rows ?? []} total={q.data?.total} page={page} pageSize={50} onPage={setPage} loading={q.isFetching} maxHeight={640} columns={[
            { key: "ts", label: t("audit.time"), render: (r) => fmtDate(r.ts, true) },
            { key: "username", label: t("audit.user"), render: (r) => <b>{r.username ?? "–"}</b> },
            { key: "action", label: t("audit.action"), render: (r) => <Badge kind={kind(r.action)}>{r.action}</Badge> },
            { key: "details", label: t("audit.details"), className: "whitespace-normal max-w-xl text-xs" },
            { key: "ip", label: t("audit.ip"), className: "font-mono text-xs text-muted" },
          ]} />
        )}
      </div>
    </>
  );
}
