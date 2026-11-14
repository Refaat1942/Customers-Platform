/** Shift colours and labels, shared by the Shifts page, product page and customer profile. */
export const SHIFT_KEYS = ["night", "morning", "evening"] as const;
export const SHIFT_COLORS: Record<string, string> = { night: "#6250d6", morning: "#eda100", evening: "#2a78d6", unknown: "#b8bdb6" };
export const shiftRange = (k: string, s?: { morning: string; evening: string }) => {
  const m = s?.morning ?? "08:30", e = s?.evening ?? "16:30";
  return k === "night" ? `00:00 – ${m}` : k === "morning" ? `${m} – ${e}` : k === "evening" ? `${e} – 24:00` : "";
};
