import { useTranslation } from "react-i18next";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtCompact, fmtMoney } from "../lib/format";

/* Validated categorical order (fixed, never cycled) and one-hue sequential ramp. */
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
export const SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const BRAND = "var(--brand, #1b5e20)";
const AXIS = { fontSize: 11, fill: "#5f665f" };
const GRID = "#eceee9";

function TooltipBox({ active, payload, label, money = true }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold mb-1">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="size-2 rounded-sm" style={{ background: p.color }} />
          <span className="text-muted">{p.name}</span>
          <span className="num font-semibold ms-auto">{money ? fmtMoney(p.value) : fmtCompact(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Single-series trend over time. */
export function TrendChart({ data, x, y, name, height = 260, money = true }: { data: any[]; x: string; y: string; name: string; height?: number; money?: boolean }) {
  const { i18n } = useTranslation();
  const rtl = i18n.language === "ar";
  return (
    <div dir="ltr"><ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={BRAND} stopOpacity={0.22} />
            <stop offset="100%" stopColor={BRAND} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} reversed={rtl} minTickGap={16} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmtCompact} width={48} orientation={rtl ? "right" : "left"} />
        <Tooltip content={<TooltipBox money={money} />} cursor={{ stroke: "#9aa19a", strokeDasharray: 3 }} />
        <Area type="monotone" dataKey={y} name={name} stroke={BRAND} strokeWidth={2} fill="url(#trendFill)" activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
      </AreaChart>
    </ResponsiveContainer></div>
  );
}

/** Horizontal bars for ranked categories (branches, products, districts). */
export function RankBars({ data, label, value, name, height, money = true, onClick }: {
  data: any[]; label: string; value: string; name: string; height?: number; money?: boolean; onClick?: (row: any) => void;
}) {
  const { i18n } = useTranslation();
  const rtl = i18n.language === "ar";
  const h = height ?? Math.max(120, data.length * 30 + 30);
  return (
    <div dir="ltr"><ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 12, left: 4, bottom: 0 }} barCategoryGap={6}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmtCompact} reversed={rtl} />
        <YAxis type="category" dataKey={label} tick={AXIS} tickLine={false} axisLine={false} width={130} orientation={rtl ? "right" : "left"}
          tickFormatter={(v: string) => (v && v.length > 20 ? v.slice(0, 19) + "…" : v)} />
        <Tooltip content={<TooltipBox money={money} />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
        <Bar dataKey={value} name={name} fill={BRAND} radius={rtl ? [4, 0, 0, 4] : [0, 4, 4, 0]} maxBarSize={18}
          onClick={onClick ? (d: any) => onClick(d.payload ?? d) : undefined} cursor={onClick ? "pointer" : undefined} />
      </BarChart>
    </ResponsiveContainer></div>
  );
}

/** Two or more series stacked per category (e.g. new vs returning per month). */
export function StackedBars({ data, x, series, height = 260 }: { data: any[]; x: string; series: { key: string; name: string }[]; height?: number }) {
  const { i18n } = useTranslation();
  const rtl = i18n.language === "ar";
  return (
    <div dir="ltr"><ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} reversed={rtl} minTickGap={12} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmtCompact} width={44} orientation={rtl ? "right" : "left"} />
        <Tooltip content={<TooltipBox money={false} />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
        <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} stackId="a" fill={SERIES[i]} stroke="#fff" strokeWidth={1}
            radius={i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} maxBarSize={36} />
        ))}
      </BarChart>
    </ResponsiveContainer></div>
  );
}

/** Share bar: one horizontal 100% bar split into labelled parts (status mix). */
export function ShareBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <div>
      <div className="flex h-3.5 rounded-full overflow-hidden gap-0.5 bg-surface">
        {parts.filter((p) => p.value > 0).map((p) => (
          <div key={p.label} title={`${p.label}: ${p.value}`} style={{ width: `${(100 * p.value) / total}%`, background: p.color }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-sm">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: p.color }} />
            <span className="text-muted">{p.label}</span>
            <span className="font-semibold num">{p.value.toLocaleString("en-US")}</span>
            <span className="text-muted num text-xs">({((100 * p.value) / total).toFixed(0)}%)</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Sequential colour for a 0..1 value (heatmaps, cohort tables). */
export function seqColor(v: number) {
  if (!isFinite(v) || v <= 0) return "#f4f6f3";
  const i = Math.min(SEQ.length - 1, Math.floor(v * SEQ.length));
  return SEQ[i];
}
export const seqText = (v: number) => (v > 0.55 ? "#fff" : "#1f2420");
