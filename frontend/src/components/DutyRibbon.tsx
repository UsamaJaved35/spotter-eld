import type { DailyLog, DutyStatus } from "../lib/types";
import { DUTY_COLOR, DUTY_LABEL, hourToClock, hoursToHm } from "../lib/format";

/**
 * The console counterpart to the paper grid: one day of duty status compressed
 * into a single colour-coded band. Gives the whole trip's shape at a glance,
 * where the paper sheet gives the regulatory detail.
 */
export function DutyRibbon({ log, compact = false }: { log: DailyLog; compact?: boolean }) {
  return (
    <div className="w-full">
      <div
        className={`relative flex w-full overflow-hidden ${compact ? "h-3" : "h-7"}`}
        style={{ background: "var(--color-console-void)" }}
        role="img"
        aria-label={`Duty status for ${log.date}`}
      >
        {log.entries.map((entry, i) => {
          const width = ((entry.end_hour - entry.start_hour) / 24) * 100;
          if (width <= 0) return null;
          return (
            <div
              key={i}
              className="group relative h-full"
              style={{ width: `${width}%`, background: DUTY_COLOR[entry.status] }}
              title={`${hourToClock(entry.start_hour)}–${hourToClock(entry.end_hour)} · ${DUTY_LABEL[entry.status]}${entry.location ? ` · ${entry.location}` : ""}`}
            >
              {!compact && entry.end_hour - entry.start_hour > 1.6 && (
                <span
                  className="absolute inset-0 flex items-center justify-center font-mono text-[9px] font-semibold tracking-widest"
                  style={{ color: "var(--color-console-void)" }}
                >
                  {entry.status}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {!compact && (
        <div className="mt-1 flex justify-between font-mono text-[9px]" style={{ color: "var(--color-console-dim)" }}>
          {["00", "06", "12", "18", "24"].map((tick) => (
            <span key={tick}>{tick}:00</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function DutyLegend() {
  const statuses: DutyStatus[] = ["OFF", "SB", "D", "ON"];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {statuses.map((status) => (
        <span key={status} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5" style={{ background: DUTY_COLOR[status] }} />
          <span className="text-[11px]" style={{ color: "var(--color-console-text)" }}>
            {DUTY_LABEL[status]}
          </span>
        </span>
      ))}
    </div>
  );
}

export function DayTotals({ log }: { log: DailyLog }) {
  const statuses: DutyStatus[] = ["OFF", "SB", "D", "ON"];
  return (
    <div className="grid grid-cols-4 gap-px" style={{ background: "var(--color-console-line)" }}>
      {statuses.map((status) => (
        <div key={status} className="px-2 py-1.5" style={{ background: "var(--color-console-panel)" }}>
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5" style={{ background: DUTY_COLOR[status] }} />
            <span className="stencil !text-[9px] !tracking-[0.14em]">{status}</span>
          </div>
          <div className="tnum mt-0.5 font-mono text-sm" style={{ color: "var(--color-console-bright)" }}>
            {hoursToHm(log.totals[status] ?? 0)}
          </div>
        </div>
      ))}
    </div>
  );
}
