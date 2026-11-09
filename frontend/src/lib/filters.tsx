import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Params } from "./api";
import { isoDate } from "./format";

export type Preset = "all" | "7d" | "30d" | "90d" | "month" | "lastMonth" | "year" | "lastYear" | "custom";

export type FilterState = {
  preset: Preset; date_from: string; date_to: string;
  branch: string[]; type: string[]; district: string[]; season: string[];
};

export type Meta = {
  branches: string[]; types: string[]; districts: string[]; seasons: string[];
  date_min: string | null; date_max: string | null; rows: number;
  last_import: { id: number; filename: string; finished_at: string } | null;
  segments: string[]; ai_enabled: boolean;
  settings: Record<string, any>;
};

const EMPTY: FilterState = { preset: "all", date_from: "", date_to: "", branch: [], type: [], district: [], season: [] };

/** Presets are relative to the latest date in the data (not today), so old imports still show. */
export function presetRange(p: Preset, anchor: string | null): [string, string] {
  if (p === "all" || p === "custom" || !anchor) return ["", ""];
  const end = new Date(anchor + "T00:00:00");
  const d = (y: number, m: number, day: number) => isoDate(new Date(y, m, day));
  const y = end.getFullYear(), m = end.getMonth();
  switch (p) {
    case "7d": return [isoDate(new Date(end.getTime() - 6 * 864e5)), isoDate(end)];
    case "30d": return [isoDate(new Date(end.getTime() - 29 * 864e5)), isoDate(end)];
    case "90d": return [isoDate(new Date(end.getTime() - 89 * 864e5)), isoDate(end)];
    case "month": return [d(y, m, 1), isoDate(end)];
    case "lastMonth": return [d(y, m - 1, 1), d(y, m, 0)];
    case "year": return [d(y, 0, 1), isoDate(end)];
    case "lastYear": return [d(y - 1, 0, 1), d(y - 1, 11, 31)];
  }
  return ["", ""];
}

type Ctx = {
  f: FilterState; set: (patch: Partial<FilterState>) => void; reset: () => void;
  params: Params; meta: Meta | undefined; key: unknown[];
};
const FiltersCtx = createContext<Ctx>(null!);

function load(): FilterState {
  try { return { ...EMPTY, ...JSON.parse(localStorage.getItem("cp_filters") || "{}") }; } catch { return EMPTY; }
}

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [f, setF] = useState<FilterState>(load);
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: () => api.get<Meta>("/meta"), staleTime: 60_000 });

  // keep relative presets fresh when new data is imported
  useEffect(() => {
    if (!meta || f.preset === "custom" || f.preset === "all") return;
    const [a, b] = presetRange(f.preset, meta.date_max);
    if (a !== f.date_from || b !== f.date_to) setF((s) => ({ ...s, date_from: a, date_to: b }));
  }, [meta?.date_max, f.preset]); // eslint-disable-line

  useEffect(() => { try { localStorage.setItem("cp_filters", JSON.stringify(f)); } catch { /* */ } }, [f]);

  const value = useMemo<Ctx>(() => {
    const params: Params = {
      date_from: f.date_from || undefined, date_to: f.date_to || undefined,
      branch: f.branch, type: f.type, district: f.district, season: f.season,
    };
    return {
      f, meta, params, key: [f.date_from, f.date_to, f.branch, f.type, f.district, f.season],
      set: (patch) => setF((s) => {
        const n = { ...s, ...patch };
        if (patch.preset && patch.preset !== "custom") [n.date_from, n.date_to] = presetRange(patch.preset, meta?.date_max ?? null);
        return n;
      }),
      reset: () => setF(EMPTY),
    };
  }, [f, meta]);

  return <FiltersCtx.Provider value={value}>{children}</FiltersCtx.Provider>;
}

export const useFilters = () => useContext(FiltersCtx);
