import type { Trip } from "../lib/types";
import { formatDayTime, hoursToHm, numberFmt } from "../lib/format";

const CYCLE_LIMIT = 70;

export function Summary({ trip }: { trip: Trip }) {
  const s = trip.summary;

  return (
    <div className="grid gap-px sm:grid-cols-2 lg:grid-cols-4" style={{ background: "var(--color-console-line)" }}>
      <Stat label="Total distance" value={numberFmt.format(s.total_miles)} unit="mi" />
      <Stat label="Driving time" value={hoursToHm(s.total_drive_hours)} />
      <Stat label="Trip duration" value={hoursToHm(s.total_duration_hours)} />
      <Stat label="Log sheets" value={String(s.log_sheet_count)} unit={s.log_sheet_count === 1 ? "day" : "days"} />
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="px-4 py-3" style={{ background: "var(--color-console-panel)" }}>
      <div className="stencil">{label}</div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span
          className="tnum font-mono text-2xl font-semibold"
          style={{ color: "var(--color-console-bright)" }}
        >
          {value}
        </span>
        {unit && (
          <span className="text-[11px]" style={{ color: "var(--color-console-dim)" }}>
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}

/** The 70-hour cycle as a fuel-gauge style meter. */
export function CycleGauge({ trip }: { trip: Trip }) {
  const s = trip.summary;
  const startPct = Math.min(100, (s.cycle_used_start / CYCLE_LIMIT) * 100);
  const tripPct = Math.min(100 - startPct, ((s.cycle_used_end - s.cycle_used_start) / CYCLE_LIMIT) * 100);
  const tight = s.cycle_remaining < 10;

  return (
    <div className="panel chamfer p-4">
      <div className="flex items-baseline justify-between">
        <span className="stencil">70-hour / 8-day cycle</span>
        <span
          className="tnum font-mono text-xs"
          style={{ color: tight ? "var(--color-warn)" : "var(--color-signal)" }}
        >
          {s.cycle_remaining.toFixed(1)} h available
        </span>
      </div>

      <div className="mt-3 flex h-2.5 w-full overflow-hidden" style={{ background: "var(--color-console-void)" }}>
        <div style={{ width: `${startPct}%`, background: "var(--color-console-edge)" }} title="Already used before this trip" />
        <div style={{ width: `${tripPct}%`, background: "var(--color-amber)" }} title="Used by this trip" />
      </div>

      <div className="mt-2 flex justify-between font-mono text-[10px]" style={{ color: "var(--color-console-dim)" }}>
        <span>{s.cycle_used_start.toFixed(1)} h before</span>
        <span style={{ color: "var(--color-amber)" }}>
          +{(s.cycle_used_end - s.cycle_used_start).toFixed(1)} h this trip
        </span>
        <span>{CYCLE_LIMIT} h limit</span>
      </div>

      <div className="mt-3 border-t pt-2 text-[11px]" style={{ borderColor: "var(--color-console-line)", color: "var(--color-console-dim)" }}>
        Departs {formatDayTime(s.start_at)} · arrives {formatDayTime(s.end_at)}
      </div>
    </div>
  );
}
