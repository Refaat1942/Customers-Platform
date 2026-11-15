import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import clsx from "clsx";
import {
  ArrowLeft, BellRing, CalendarClock, Crown, Lightbulb, MapPin, Package, Phone, Repeat, ShoppingBag, Store, TrendingDown, TrendingUp, UserRound,
} from "lucide-react";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import { useBranchName, useFilters } from "../lib/filters";
import { fmtDate, fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";
import { SHIFT_COLORS, SHIFT_KEYS } from "../lib/shifts";
import { Badge, ErrorBox, PrintButton, Spinner } from "../components/ui";
import { Columns, ShareBar, TrendChart } from "../components/charts";
import { TrendBadge } from "./Customers";

/** Customer 360: everything about one customer on one clear page (prints on A4). */
export default function CustomerCard() {
  const { t } = useTranslation();
  const { cid } = useParams();
  const nav = useNavigate();
  const { params, key } = useFilters();
  const branchName = useBranchName();
  const prof = useQuery({ queryKey: ["customer", cid, ...key], queryFn: () => api.get(`/customers/${cid}`, params) });
  const card = useQuery({ queryKey: ["customer_card", cid, ...key], queryFn: () => api.get(`/customers/${cid}/card`, params) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get("/settings") });
  if (prof.isLoading || card.isLoading) return <Spinner />;
  if (prof.error || card.error) return <ErrorBox error={prof.error || card.error} />;
  const d = prof.data, c = card.data, s = d.summary, dir = d.directory ?? {}, si = d.sales_info ?? {}, h = d.habits ?? {};
  const days = t("days", { returnObjects: true }) as string[];
  const name = dir.name ?? s.name ?? s.phone;
  const initials = String(name).trim().split(/\s+/).slice(0, 2).map((w: string) => w[0]).join("").toUpperCase();
  const r = c.rhythm;
  const refills = (d.refills ?? []) as any[];
  const dueRefills = refills.filter((x) => x.refill_status === "overdue" || x.refill_status === "due_soon");
  const shiftVisits = SHIFT_KEYS.map((k) => ({ k, v: c.shifts.find((x: any) => x.shift === k)?.visits ?? 0 }));
  const shiftTotal = shiftVisits.reduce((a, x) => a + x.v, 0);
  const favShift = shiftTotal ? shiftVisits.reduce((a, x) => (x.v > a.v ? x : a)) : null;
  const typesTotal = c.types.reduce((a: number, x: any) => a + x.visits, 0);
  const age = dir.birth_date ? Math.floor((Date.now() - new Date(dir.birth_date).getTime()) / (365.25 * 864e5)) : null;
  const sm = settings.data?.shift_morning ?? "08:30", se = settings.data?.shift_evening ?? "16:30";

  // plain-language insights, most useful first
  const tips: { icon: ReactNode; text: string; kind?: "bad" | "good" }[] = [];
  if (s.overdue_days > 0) tips.push({ icon: <CalendarClock size={16} />, kind: "bad", text: t("c360.tipOverdue", { n: fmtInt(s.overdue_days), date: fmtDate(s.expected_next) }) });
  else if (s.expected_next) tips.push({ icon: <CalendarClock size={16} />, text: t("c360.tipNext", { date: fmtDate(s.expected_next) }) });
  if (r?.median) tips.push({ icon: <Repeat size={16} />, text: t("c360.tipRhythm", { n: fmtInt(r.median), reg: r.regularity ? t(`c360.reg.${r.regularity}`) : "" }) });
  if (dueRefills.length) tips.push({ icon: <BellRing size={16} />, kind: "bad", text: t("c360.tipRefills", { n: dueRefills.length, items: dueRefills.slice(0, 3).map((x) => x.item ?? x.code).join("، ") }) });
  if (c.rank?.top_pct != null && c.rank.top_pct <= 20) tips.push({ icon: <Crown size={16} />, kind: "good", text: t("c360.tipTop", { pct: fmtPct(c.rank.top_pct) }) });
  if (s.trend === "growing" || s.trend === "declining" || s.trend === "stopped")
    tips.push({ icon: s.trend === "growing" ? <TrendingUp size={16} /> : <TrendingDown size={16} />, kind: s.trend === "growing" ? "good" : "bad", text: t(`c360.tipTrend.${s.trend}`, { pct: s.trend_pct != null ? Math.abs(Math.round(s.trend_pct)) : "" }) });
  if (favShift && h.fav_dow) tips.push({ icon: <Store size={16} />, text: t("c360.tipWhen", { day: days[h.fav_dow - 1], shift: t(`shift.${favShift.k}`), branch: branchName(h.fav_branch ?? s.branch) ?? "–" }) });
  if (s.fav_item) tips.push({ icon: <Package size={16} />, text: t("c360.tipFav", { item: s.fav_item }) });
  if (h.delivery_pct >= 50) tips.push({ icon: <ShoppingBag size={16} />, text: t("c360.tipDelivery", { pct: h.delivery_pct }) });
  tips.push({ icon: <Lightbulb size={16} />, kind: "good", text: `${t("c360.tipAction")}: ${t(`action.${s.action}`)}` });

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-4 no-print">
        <button className="btn-ghost" onClick={() => nav(-1)}><ArrowLeft size={16} className="rtl:rotate-180" /> {t("cust.back")}</button>
        <div className="flex gap-2">
          <Link to={`/customers/${cid}`} className="btn-ghost">{t("c360.fullProfile")}</Link>
          <PrintButton />
        </div>
      </div>

      {/* ---------------------------------------------------------------- identity band */}
      <div className="card overflow-hidden">
        <div className="bg-brand text-white p-6 flex flex-wrap items-center gap-5">
          <div className="size-20 rounded-2xl bg-white/15 border border-white/30 grid place-items-center text-3xl font-bold">{initials || <UserRound size={36} />}</div>
          <div className="min-w-0 flex-1">
            <div className="text-xs uppercase tracking-widest opacity-80">{t("c360.title")}</div>
            <div className="text-3xl font-bold leading-tight truncate">{name}</div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mt-1.5 text-sm opacity-95">
              <span className="inline-flex items-center gap-1.5 font-mono text-base" dir="ltr"><Phone size={15} />{s.phone}</span>
              {(dir.district ?? s.district) && <span className="inline-flex items-center gap-1.5"><MapPin size={15} />{[dir.district ?? s.district, dir.city].filter(Boolean).join(" · ")}</span>}
              {si.first_purchase && <span>{t("c360.since", { date: fmtDate(si.first_purchase) })}</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2 bg-white rounded-xl p-2.5">
            <Badge kind={s.status}>{t(`status.${s.status}`)}</Badge>
            <Badge>{t(`seg.${s.segment}`)}</Badge>
            <Badge kind={s.churn_risk}>{t("col.churn_risk")}: {t(`risk.${s.churn_risk}`)}</Badge>
            <TrendBadge t={t} r={s} />
            {s.high_value && <Badge kind="active">{t("kpi.highValue")}</Badge>}
            {s.loyal && <Badge kind="active">{t("kpi.loyal")}</Badge>}
          </div>
        </div>

        {/* ---------------------------------------------------------------- big numbers */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-x divide-line rtl:divide-x-reverse border-b border-line">
          <Big label={t("c360.spend")} value={fmtMoney(s.total_spent)} sub={si.all_time_spend != null && si.all_time_spend !== s.total_spent ? `${t("c360.allTime")}: ${fmtMoney(si.all_time_spend)}` : undefined} />
          <Big label={t("c360.visits")} value={fmtInt(s.visits)} sub={si.all_time_visits && si.all_time_visits !== s.visits ? `${t("c360.allTime")}: ${fmtInt(si.all_time_visits)}` : undefined} />
          <Big label={t("c360.avgInvoice")} value={fmtMoney(s.avg_per_visit)} sub={`${t("c360.maxMin")}: ${fmtMoney(s.max_invoice)} / ${fmtMoney(s.min_invoice)}`} />
          <Big label={t("c360.lastVisit")} value={s.days_since != null ? t("c360.daysAgo", { n: fmtInt(s.days_since) }) : "–"} sub={fmtDate(s.last_visit)} />
          <Big label={t("c360.every")} value={r?.median != null ? t("prod.days", { n: fmtInt(r.median) }) : "–"} sub={r?.regularity ? t(`c360.reg.${r.regularity}`) : t("c360.oneVisit")} />
          <Big label={t("c360.rank")} value={c.rank ? `#${fmtInt(c.rank.rank)}` : "–"} sub={c.rank ? t("c360.rankOf", { n: fmtInt(c.rank.customers), pct: fmtPct(c.rank.top_pct) }) : undefined} />
        </div>

        {/* ---------------------------------------------------------------- insights */}
        <div className="p-6">
          <h3 className="font-semibold text-lg mb-3 flex items-center gap-2"><Lightbulb size={18} className="text-brand" />{t("c360.insights")}</h3>
          <ul className="grid md:grid-cols-2 gap-x-6 gap-y-2.5">
            {tips.map((x, i) => (
              <li key={i} className={clsx("flex gap-2.5 items-start text-[15px] leading-snug rounded-lg px-3 py-2",
                x.kind === "bad" ? "bg-red-50 text-red-900" : x.kind === "good" ? "bg-green-50 text-green-900" : "bg-surface")}>
                <span className="mt-0.5 shrink-0">{x.icon}</span><span>{x.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-5 mt-5">
        {/* ---------------------------------------------------------------- rhythm */}
        <Section title={t("c360.rhythm")} icon={<Repeat size={17} />}>
          {r ? (
            <>
              <div className="grid grid-cols-4 gap-3 mb-4 text-center">
                <Mini label={t("c360.usualGap")} value={t("prod.days", { n: fmtInt(r.median) })} strong />
                <Mini label={t("c360.lastGap")} value={t("prod.days", { n: fmtInt(r.last) })} />
                <Mini label={t("c360.shortest")} value={t("prod.days", { n: fmtInt(r.shortest) })} />
                <Mini label={t("c360.longest")} value={t("prod.days", { n: fmtInt(r.longest) })} />
              </div>
              <div className={clsx("rounded-lg px-4 py-3 mb-4 text-sm font-medium", s.overdue_days > 0 ? "bg-red-50 text-red-900" : "bg-green-50 text-green-900")}>
                {s.expected_next ? (s.overdue_days > 0 ? t("c360.lateBy", { n: fmtInt(s.overdue_days), date: fmtDate(s.expected_next) }) : t("c360.expected", { date: fmtDate(s.expected_next) })) : "–"}
              </div>
              <div className="text-xs text-muted mb-1">{t("c360.gapsChart")}</div>
              <Columns data={c.gaps.filter((g: any) => g.gap != null).map((g: any) => ({ day: fmtDate(g.day), gap: g.gap }))} x="day" y="gap" name={t("c360.daysBetween")} height={170} />
            </>
          ) : <div className="text-muted text-sm">{t("c360.oneVisit")}</div>}
        </Section>

        {/* ---------------------------------------------------------------- spend */}
        <Section title={t("c360.spendOverTime")} icon={<TrendingUp size={17} />}>
          {d.monthly.length > 1 ? <TrendChart data={d.monthly} x="month" y="sales" name={t("col.sales")} height={190} /> : <div className="text-muted text-sm">–</div>}
          <div className="grid grid-cols-3 gap-3 mt-3 text-center">
            <Mini label={t("c360.last90")} value={fmtMoney(s.spend_90)} strong />
            <Mini label={t("c360.prev90")} value={fmtMoney(s.spend_prev_90)} />
            <Mini label={t("trend.col")} value={s.trend_pct != null ? `${s.trend_pct >= 0 ? "+" : ""}${Math.round(s.trend_pct)}%` : t(`trend.${s.trend}`)} />
          </div>
          {c.yearly.length > 1 && (
            <div className="flex flex-wrap gap-2 mt-3 text-xs">
              {c.yearly.map((y: any) => <span key={y.year} className="rounded-md bg-surface px-2 py-1"><b>{y.year}</b>: <span className="num">{fmtMoney(y.sales)}</span> · {fmtInt(y.visits)} {t("c360.visitsShort")}</span>)}
            </div>
          )}
        </Section>

        {/* ---------------------------------------------------------------- products */}
        <Section title={t("c360.buys")} icon={<Package size={17} />}>
          <table className="w-full text-sm">
            <thead><tr className="text-muted text-xs text-start">
              <th className="text-start font-medium pb-2">{t("col.item")}</th><th className="text-end font-medium pb-2">{t("col.times")}</th><th className="text-end font-medium pb-2">{t("col.sales")}</th>
            </tr></thead>
            <tbody>
              {d.items.slice(0, 8).map((x: any) => (
                <tr key={x.key} className="border-t border-line">
                  <td className="py-1.5"><div className="font-medium truncate max-w-72">{x.item ?? <span className="italic text-muted">{t("prod.noName")}</span>}</div>{x.code && <div className="font-mono text-[11px] text-muted">{x.code}</div>}</td>
                  <td className="text-end num">{fmtInt(x.times)}</td>
                  <td className="text-end num font-medium">{fmtMoney(x.sales)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(h.categories ?? []).length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {h.categories.filter((x: any) => x.category && x.category !== "—" && x.category !== "-").map((x: any) => <span key={x.category} className="text-xs rounded-full bg-brand-soft text-brand px-2.5 py-1">{x.category} · <span className="num">{fmtMoney(x.sales)}</span></span>)}
            </div>
          )}
        </Section>

        {/* ---------------------------------------------------------------- refills */}
        <Section title={t("c360.refills")} icon={<BellRing size={17} />}>
          {refills.length ? (
            <table className="w-full text-sm">
              <thead><tr className="text-muted text-xs">
                <th className="text-start font-medium pb-2">{t("col.item")}</th><th className="text-end font-medium pb-2">{t("c360.cycle")}</th>
                <th className="text-end font-medium pb-2">{t("c360.due")}</th><th className="text-end font-medium pb-2"></th>
              </tr></thead>
              <tbody>
                {refills.slice(0, 8).map((x, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className="py-1.5 font-medium truncate max-w-56">{x.item ?? x.code}</td>
                    <td className="text-end num">{t("prod.days", { n: fmtInt(x.cycle_days) })}</td>
                    <td className="text-end">{fmtDate(x.due_date)}</td>
                    <td className="text-end"><Badge kind={x.refill_status === "overdue" || x.refill_status === "lapsed" ? "inactive" : x.refill_status === "due_soon" ? "attention" : "active"}>{t(`refill.status.${x.refill_status}`)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="text-muted text-sm">{t("c360.noRefills")}</div>}
        </Section>

        {/* ---------------------------------------------------------------- when & how */}
        <Section title={t("c360.when")} icon={<CalendarClock size={17} />}>
          <Columns data={[1, 2, 3, 4, 5, 6, 7].map((dow) => ({ day: days[dow - 1], visits: c.weekday.find((x: any) => x.dow === dow)?.visits ?? 0 }))} x="day" y="visits" name={t("c360.visits")} height={160} />
          {shiftTotal > 0 ? (
            <div className="mt-3"><ShareBar parts={shiftVisits.map((x) => ({ label: `${t(`shift.${x.k}`)} (\u2066${x.k === "night" ? `00:00–${sm}` : x.k === "morning" ? `${sm}–${se}` : `${se}–24:00`}\u2069)`, value: x.v, color: SHIFT_COLORS[x.k] }))} /></div>
          ) : <div className="text-xs text-muted mt-2">{t("pd.noTime")}</div>}
          <div className="grid grid-cols-3 gap-3 mt-4 text-center">
            <Mini label={t("habits.hour")} value={h.fav_hour != null ? `${String(h.fav_hour).padStart(2, "0")}:00` : "–"} />
            <Mini label={t("habits.itemsPerVisit")} value={fmtNum(h.items_per_visit)} />
            <Mini label={t("habits.returns")} value={fmtInt(h.returns)} />
          </div>
        </Section>

        {/* ---------------------------------------------------------------- where & how paid */}
        <Section title={t("c360.where")} icon={<Store size={17} />}>
          <div className="space-y-2">
            {d.branches.map((b: any) => {
              const pct = s.total_spent ? (100 * b.sales) / d.branches.reduce((a: number, x: any) => a + x.sales, 0) : 0;
              return (
                <div key={b.branch}>
                  <div className="flex justify-between text-sm"><span className="font-medium">{branchName(b.branch)}</span><span className="num text-muted">{fmtInt(b.visits)} {t("c360.visitsShort")} · {fmtMoney(b.sales)}</span></div>
                  <div className="h-2 rounded-full bg-surface mt-1"><div className="h-2 rounded-full bg-brand" style={{ width: `${Math.max(2, pct)}%` }} /></div>
                </div>
              );
            })}
          </div>
          {c.types.length > 0 && (
            <div className="mt-4">
              <div className="text-xs text-muted mb-1.5">{t("prof.salesTypes")}</div>
              <div className="flex flex-wrap gap-2">
                {c.types.map((x: any) => <span key={x.sales_type} className="text-sm rounded-lg border border-line px-2.5 py-1"><b>{x.sales_type}</b> <span className="text-muted num">{fmtPct((100 * x.visits) / (typesTotal || 1))}</span></span>)}
              </div>
            </div>
          )}
        </Section>
      </div>

      {/* ---------------------------------------------------------------- contact details */}
      <Section title={t("c360.details")} icon={<UserRound size={17} />} className="mt-5">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-4 text-sm">
          <Field label={t("dir.address")} value={dir.address ?? si.address} wide />
          <Field label={t("dir.region")} value={[dir.region, dir.city, dir.area].filter(Boolean).join(" · ")} />
          <Field label={t("dir.email")} value={dir.email} />
          <Field label={t("imp.fields.gender")} value={dir.gender} />
          <Field label={t("imp.fields.birth_date")} value={dir.birth_date ? `${fmtDate(dir.birth_date)}${age != null ? ` (${t("c360.age", { n: age })})` : ""}` : null} />
          <Field label={t("prof.registeredAt")} value={dir.registered_at ? fmtDate(dir.registered_at) : null} />
          <Field label={t("prof.registeredBranch")} value={dir.registered_branch ? branchName(dir.registered_branch) : null} />
          <Field label={t("prof.posId")} value={dir.pos_customer_id} />
          <Field label={t("prof.otherNames")} value={(si.names ?? []).filter((n: string) => n !== name).join(" · ")} />
        </div>
      </Section>
      <div className="text-xs text-muted mt-3">{d.reference_date && `${t("app.referenceDate")} ${fmtDate(d.reference_date)}`}</div>
    </div>
  );
}

function Big({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="p-5">
      <div className="text-xs text-muted font-medium">{label}</div>
      <div className="text-2xl font-bold num mt-1 leading-tight">{value}</div>
      {sub && <div className="text-xs text-muted mt-1 num">{sub}</div>}
    </div>
  );
}

function Mini({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-lg bg-surface px-2 py-2.5">
      <div className="text-[11px] text-muted">{label}</div>
      <div className={clsx("num mt-0.5", strong ? "text-lg font-bold text-brand" : "font-semibold")}>{value}</div>
    </div>
  );
}

function Section({ title, icon, children, className }: { title: string; icon: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("card p-5", className)}>
      <h3 className="font-semibold text-base mb-4 flex items-center gap-2"><span className="text-brand">{icon}</span>{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, value, wide }: { label: string; value: any; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <div className="text-xs text-muted">{label}</div>
      <div className="font-semibold break-words mt-0.5">{value === null || value === undefined || value === "" ? "–" : value}</div>
    </div>
  );
}
