import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";
import { useFilters, type Preset } from "../lib/filters";
import { MultiSelect } from "./ui";

const PRESETS: Preset[] = ["all", "7d", "30d", "90d", "month", "lastMonth", "year", "lastYear", "custom"];

export default function FilterBar() {
  const { t } = useTranslation();
  const { f, set, reset, meta } = useFilters();
  const active = f.preset !== "all" || f.branch.length || f.type.length || f.district.length || f.season.length;
  return (
    <div className="card px-4 py-3 mb-5 flex flex-wrap items-end gap-3 no-print">
      <div>
        <span className="label">{t("filters.dateRange")}</span>
        <select className="input min-w-36" value={f.preset} onChange={(e) => set({ preset: e.target.value as Preset })}>
          {PRESETS.map((p) => <option key={p} value={p}>{t(`filters.presets.${p}`)}</option>)}
        </select>
      </div>
      <div>
        <span className="label">{t("filters.from")}</span>
        <input type="date" className="input" value={f.date_from} min={meta?.date_min ?? undefined} max={meta?.date_max ?? undefined}
          onChange={(e) => set({ preset: "custom", date_from: e.target.value })} />
      </div>
      <div>
        <span className="label">{t("filters.to")}</span>
        <input type="date" className="input" value={f.date_to} min={meta?.date_min ?? undefined} max={meta?.date_max ?? undefined}
          onChange={(e) => set({ preset: "custom", date_to: e.target.value })} />
      </div>
      {meta && meta.branches.length > 1 && (
        <MultiSelect label={t("filters.branch")} options={meta.branches} value={f.branch} onChange={(v) => set({ branch: v })} />
      )}
      {meta && meta.types.length > 0 && (
        <MultiSelect label={t("filters.type")} options={meta.types} value={f.type} onChange={(v) => set({ type: v })} />
      )}
      {meta && meta.districts.length > 1 && (
        <MultiSelect label={t("filters.district")} options={meta.districts} value={f.district} onChange={(v) => set({ district: v })} />
      )}
      <MultiSelect label={t("filters.season")} options={meta?.seasons ?? []} value={f.season} onChange={(v) => set({ season: v })}
        render={(s) => t(`seasons.${s}`)} />
      {active ? <button className="btn-ghost" onClick={reset}><RotateCcw size={14} /> {t("filters.reset")}</button> : null}
    </div>
  );
}
