import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { Clock, Receipt, Store, TrendingDown, TrendingUp, UserPlus, Users, Wallet } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtInt, fmtMoney, fmtNum } from "../lib/format";
import { Card, Empty, ErrorBox, Notice, PageHeader, Spinner } from "../components/ui";
import { Sparkline, TodayVsYesterday } from "../components/charts";

const STATE = {
  online: { dot: "bg-good", text: "text-good", ring: "ring-green-200" },
  idle: { dot: "bg-warn", text: "text-warn", ring: "ring-amber-200" },
  offline: { dot: "bg-gray-400", text: "text-muted", ring: "ring-gray-200" },
} as const;

const time = (v: string | null, withDate = false) => {
  if (!v) return "–";
  const d = new Date(v);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: withDate ? undefined : "2-digit" }) +
    (withDate ? " · " + d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "");
};

function Delta({ cur, prev }: { cur: number; prev: number }) {
  const { t } = useTranslation();
  if (!prev) return null;
  const ch = (100 * (cur - prev)) / prev;
  return (
    <span className={clsx("inline-flex items-center gap-1 text-xs font-medium", ch >= 0 ? "text-good" : "text-bad")}>
      {ch >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}{ch >= 0 ? "+" : ""}{fmtNum(ch)}%
      <span className="text-muted font-normal">{t("live.vsYesterday")}</span>
    </span>
  );
}

export default function Live() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const nav = useNavigate();
  const [branch, setBranch] = useState<string>("");
  const q = useQuery({ queryKey: ["live", branch], queryFn: () => api.get("/live", { branch: branch || undefined }), refetchInterval: 10_000, refetchIntervalInBackground: false });
  const d = q.data;

  // highlight invoices that arrived since the previous refresh
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!d) return;
    const keys = new Set<string>(d.feed.map((f: any) => f.ext_key));
    if (seen.current) setFresh(new Set([...keys].filter((k) => !seen.current!.has(k))));
    seen.current = keys;
  }, [d]);
  useEffect(() => { seen.current = null; }, [branch]);

  const [, tick] = useState(0);
  useEffect(() => { const h = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(h); }, []);
  const ago = q.dataUpdatedAt ? Math.round((Date.now() - q.dataUpdatedAt) / 1000) : null;

  const k = d?.kpis, y = d?.same_time_yesterday;
  const online = d?.branches.filter((b: any) => b.state === "online").length ?? 0;

  return (
    <>
      <PageHeader title={t("live.title")} subtitle={t("live.subtitle")}
        actions={
          <div className="flex items-center gap-3 card px-3 py-2">
            <span className="relative flex size-2.5">
              <span className={clsx("absolute inline-flex h-full w-full rounded-full opacity-75", q.isError ? "bg-bad" : "bg-good animate-ping")} />
              <span className={clsx("relative inline-flex size-2.5 rounded-full", q.isError ? "bg-bad" : "bg-good")} />
            </span>
            <span className="text-sm font-semibold tracking-wide">{t("live.live")}</span>
            <span className="text-xs text-muted num">{ago == null ? "" : t("live.updated", { s: ago })}</span>
          </div>} />

      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : d && !d.has_pos ? (
        <Card><div className="text-center py-10 max-w-xl mx-auto">
          <Store size={40} className="mx-auto text-brand" />
          <div className="font-semibold text-lg mt-3">{t("live.noPosTitle")}</div>
          <p className="text-sm text-muted mt-2">{t("live.noPos")}</p>
          {can("settings") && <Link to="/settings" className="btn-primary mt-4">{t("live.setup")}</Link>}
        </div></Card>
      ) : d && (
        <div className="space-y-5">
          {/* branch chips */}
          {d.branches.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {[{ branch: "" }, ...d.branches].map((b: any) => (
                <button key={b.branch || "all"} onClick={() => setBranch(b.branch)}
                  className={clsx("px-3.5 py-1.5 rounded-full text-sm border transition cursor-pointer inline-flex items-center gap-2",
                    branch === b.branch ? "bg-brand text-white border-brand" : "bg-white border-line hover:border-brand")}>
                  {b.branch && <span className={clsx("size-2 rounded-full", STATE[b.state as keyof typeof STATE].dot)} />}
                  {b.branch || t("app.all")}
                </button>
              ))}
            </div>
          )}

          {/* today KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
            {[
              { icon: Wallet, label: t("live.salesToday"), value: fmtMoney(k.sales), delta: <Delta cur={k.sales} prev={y.sales} />, big: true },
              { icon: Receipt, label: t("live.invoicesToday"), value: fmtInt(k.invoices), delta: <Delta cur={k.invoices} prev={y.invoices} /> },
              { icon: Users, label: t("live.customersToday"), value: fmtInt(k.customers), delta: <Delta cur={k.customers} prev={y.customers} /> },
              { icon: Receipt, label: t("live.avgInvoice"), value: fmtMoney(k.avg_invoice) },
              { icon: UserPlus, label: t("live.newCustomers"), value: fmtInt(k.new_customers) },
              { icon: Store, label: t("live.branchesOnline"), value: `${online} / ${d.branches.length}`, sub: k.last_invoice ? `${t("live.lastInvoice")} ${time(k.last_invoice)}` : undefined },
            ].map((x, i) => (
              <div key={i} className={clsx("card p-4", x.big && "bg-brand text-white border-brand")}>
                <div className={clsx("flex items-center justify-between text-xs font-semibold", x.big ? "text-white/80" : "text-muted")}>
                  <span>{x.label}</span><x.icon size={16} />
                </div>
                <div className="text-2xl font-bold mt-1.5 num truncate">{x.value}</div>
                <div className={clsx("mt-1 min-h-4", x.big && "[&_*]:!text-white/90")}>{x.delta}{x.sub && <span className="text-xs text-muted">{x.sub}</span>}</div>
              </div>
            ))}
          </div>

          <div className="grid xl:grid-cols-3 gap-5">
            <Card title={t("live.hourly")} className="xl:col-span-2">
              <TodayVsYesterday data={d.hourly} todayLabel={t("live.today")} yesterdayLabel={t("live.yesterday")} />
            </Card>
            <Card title={t("live.topItems")}>
              {d.top_items.length ? (
                <ol className="space-y-2.5">
                  {d.top_items.map((it: any, i: number) => (
                    <li key={it.item} className="flex items-center gap-3 text-sm">
                      <span className="size-6 rounded-full bg-brand-soft text-brand text-xs font-bold grid place-items-center shrink-0">{i + 1}</span>
                      <span className="flex-1 truncate" title={it.item}>{it.item}</span>
                      <span className="text-muted num text-xs">×{fmtNum(it.quantity)}</span>
                      <span className="font-semibold num">{fmtMoney(it.sales)}</span>
                    </li>
                  ))}
                </ol>
              ) : <Empty />}
            </Card>
          </div>

          {/* branches */}
          <Card title={t("live.branches")}>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
              {d.branches.map((b: any) => {
                const st = STATE[b.state as keyof typeof STATE];
                return (
                  <button key={b.branch} onClick={() => setBranch(branch === b.branch ? "" : b.branch)}
                    className={clsx("text-start rounded-xl border border-line p-4 hover:shadow-md transition cursor-pointer ring-2 ring-transparent", branch === b.branch && st.ring)}>
                    <div className="flex items-center gap-2">
                      <span className={clsx("size-2.5 rounded-full", st.dot, b.state === "online" && "animate-pulse")} />
                      <span className="font-semibold truncate flex-1">{b.branch}</span>
                      <span className={clsx("text-xs font-medium", st.text)}>{t(`live.state.${b.state}`)}</span>
                    </div>
                    <div className="flex items-end justify-between mt-3 gap-3">
                      <div>
                        <div className="text-xl font-bold num">{fmtMoney(b.sales)}</div>
                        <div className="text-xs text-muted num">{fmtInt(b.invoices)} {t("live.invoices")} · {fmtInt(b.customers)} {t("live.customers")}</div>
                      </div>
                      <Sparkline values={b.hourly} width={96} />
                    </div>
                    <div className="flex items-center justify-between mt-3 text-xs text-muted">
                      <span className="inline-flex items-center gap-1"><Clock size={12} />
                        {b.minutes_since == null ? t("live.never") : b.minutes_since < 1 ? t("live.justNow") : t("live.minAgo", { n: fmtInt(b.minutes_since) })}</span>
                      <Delta cur={b.sales} prev={b.yesterday_sales} />
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>

          <div className="grid xl:grid-cols-4 gap-5">
            <Card title={t("live.feed")} className="xl:col-span-3" pad={false}>
              <div className="max-h-[1000px] overflow-auto">
                <table className="w-full text-sm">
                  <thead className="bg-surface sticky top-0 z-10">
                    <tr>
                      {["time", "branch", "invoice", "customer", "items", "type", "total"].map((c) => (
                        <th key={c} className={clsx("th", c === "total" && "text-end")}>{t(`live.col.${c}`)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {d.feed.map((f: any) => (
                      <tr key={f.ext_key} onClick={() => f.cid && nav(`/customers/${f.cid}`)}
                        className={clsx("border-t border-line transition-colors duration-1000", f.cid && "cursor-pointer hover:bg-brand-soft", fresh.has(f.ext_key) && "bg-green-50")}>
                        <td className="td num text-muted">{time(f.time, new Date(f.time).toDateString() !== new Date().toDateString())}</td>
                        <td className="td font-medium">{f.branch}</td>
                        <td className="td"><div className="font-mono text-xs">{f.invoice_no}</div>{f.cashier && <div className="text-xs text-muted">{t("live.col.cashier")}: {f.cashier}</div>}</td>
                        <td className="td"><div className="max-w-36 truncate">{f.name || "–"}</div><div className="text-xs text-muted font-mono">{f.phone || ""}</div></td>
                        <td className="td"><div className="max-w-44 truncate text-xs" title={f.items}>{f.items}</div><div className="text-xs text-muted">{fmtInt(f.lines)} {t("live.lines")}</div></td>
                        <td className="td text-xs">{f.sales_type === "Return" ? <span className="text-bad font-semibold">{t("live.return")}</span> : (f.sales_type || "–")}{f.payment && <div className="text-muted">{f.payment}</div>}</td>
                        <td className={clsx("td text-end num font-semibold", f.total < 0 && "text-bad")}>{fmtMoney(f.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {d.feed.length === 0 && <Empty />}
              </div>
            </Card>
            <Card title={t("live.newRegistrations")}>
              {d.new_customers.length ? (
                <ul className="divide-y divide-line">
                  {d.new_customers.map((c: any) => (
                    <li key={c.phone} className="py-2.5 flex items-center gap-3">
                      <span className="size-8 rounded-full bg-brand-soft text-brand grid place-items-center shrink-0"><UserPlus size={15} /></span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{c.name || c.phone}</div>
                        <div className="text-xs text-muted truncate">{[c.branch, c.district || c.city].filter(Boolean).join(" · ")}</div>
                      </div>
                      <span className="text-xs text-muted num whitespace-nowrap">{time(c.time, true)}</span>
                    </li>
                  ))}
                </ul>
              ) : <Empty />}
            </Card>
          </div>
          {d.branches.some((b: any) => b.state === "offline") && (
            <Notice kind="warning">{t("live.offlineHint")}</Notice>
          )}
        </div>
      )}
    </>
  );
}
