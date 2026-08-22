import type { DutyStatus, StopKind } from "./types";

export const DUTY_LABEL: Record<DutyStatus, string> = {
  OFF: "Off Duty",
  SB: "Sleeper Berth",
  D: "Driving",
  ON: "On Duty (Not Driving)",
};

export const DUTY_SHORT: Record<DutyStatus, string> = {
  OFF: "OFF",
  SB: "SB",
  D: "DRV",
  ON: "ON",
};

export const DUTY_COLOR: Record<DutyStatus, string> = {
  OFF: "var(--color-duty-off)",
  SB: "var(--color-duty-sb)",
  D: "var(--color-duty-d)",
  ON: "var(--color-duty-on)",
};

export const STOP_GLYPH: Partial<Record<StopKind, string>> = {
  pickup: "▲",
  dropoff: "▼",
  fuel: "◆",
  break30: "●",
  rest10: "■",
  restart34: "★",
};

/** 7.25 -> "7h 15m" */
export function hoursToHm(hours: number): string {
  const total = Math.round(hours * 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

/** Hours from midnight -> "14:30" */
export function hourToClock(hour: number): string {
  const total = Math.round(hour * 60);
  const h = Math.floor(total / 60) % 24;
  const m = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function formatDayTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })} ${formatTime(iso)}`;
}

export function formatSheetDate(isoDate: string): { month: string; day: string; year: string } {
  const [year, month, day] = isoDate.split("-");
  return { month, day, year };
}

export function formatLongDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export const numberFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
