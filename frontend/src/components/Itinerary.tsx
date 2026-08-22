import type { Segment, Trip } from "../lib/types";
import { DUTY_COLOR, DUTY_LABEL, STOP_GLYPH, formatDayTime, formatTime, hoursToHm } from "../lib/format";

/**
 * Every duty segment in order, each stating *why* it exists. The reason text is
 * the point: it turns the plan from an opaque schedule into something a
 * dispatcher can check against the regulation.
 */
export function Itinerary({ trip }: { trip: Trip }) {
  return (
    <ol className="relative">
      {/* continuous rail behind the markers */}
      <span
        aria-hidden
        className="absolute top-2 bottom-2 left-[7px] w-px"
        style={{ background: "var(--color-console-line)" }}
      />

      {trip.segments.map((segment, i) => (
        <Row key={i} segment={segment} index={i} />
      ))}
    </ol>
  );
}

function Row({ segment, index }: { segment: Segment; index: number }) {
  const isDriving = segment.status === "D";
  const glyph = STOP_GLYPH[segment.kind];

  return (
    <li
      className="rise relative flex gap-3 py-2 pl-6"
      style={{ animationDelay: `${Math.min(index * 34, 700)}ms` }}
    >
      <span
        aria-hidden
        className="absolute top-3.5 left-0 grid h-[15px] w-[15px] place-items-center text-[8px]"
        style={{
          background: "var(--color-console-deep)",
          border: `1.5px solid ${DUTY_COLOR[segment.status]}`,
          color: DUTY_COLOR[segment.status],
        }}
      >
        {glyph ?? ""}
      </span>

      <div className="tnum w-[74px] shrink-0 pt-0.5 font-mono text-[11px]" style={{ color: "var(--color-console-dim)" }}>
        {formatTime(segment.start)}
        <span className="opacity-45"> → </span>
        {formatTime(segment.end)}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span
            className="font-mono text-[10px] font-semibold tracking-[0.14em]"
            style={{ color: DUTY_COLOR[segment.status] }}
          >
            {DUTY_LABEL[segment.status].toUpperCase()}
          </span>
          <span className="tnum font-mono text-[11px]" style={{ color: "var(--color-console-bright)" }}>
            {hoursToHm(segment.hours)}
          </span>
          {isDriving && segment.miles > 0 && (
            <span className="tnum font-mono text-[11px]" style={{ color: "var(--color-console-dim)" }}>
              {segment.miles.toFixed(0)} mi
            </span>
          )}
        </div>

        <div className="mt-0.5 truncate text-[12px]" style={{ color: "var(--color-console-text)" }}>
          {segment.note}
        </div>

        {segment.location && (
          <div className="truncate font-mono text-[10px]" style={{ color: "var(--color-console-dim)" }}>
            {segment.location}
          </div>
        )}
      </div>
    </li>
  );
}

export function StopList({ trip }: { trip: Trip }) {
  if (!trip.stops.length) return null;

  return (
    <ul className="grid gap-px" style={{ background: "var(--color-console-line)" }}>
      {trip.stops.map((stop, i) => (
        <li
          key={i}
          className="flex items-center gap-3 px-3 py-2"
          style={{ background: "var(--color-console-panel)" }}
        >
          <span className="w-4 text-center text-[11px]" style={{ color: "var(--color-amber)" }}>
            {STOP_GLYPH[stop.kind] ?? "•"}
          </span>
          <span className="w-[104px] shrink-0 text-[12px]" style={{ color: "var(--color-console-bright)" }}>
            {stop.label}
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-[11px]" style={{ color: "var(--color-console-text)" }}>
            {stop.location}
          </span>
          <span className="tnum shrink-0 font-mono text-[11px]" style={{ color: "var(--color-console-dim)" }}>
            {formatDayTime(stop.arrive)}
          </span>
          <span className="tnum w-[52px] shrink-0 text-right font-mono text-[11px]" style={{ color: "var(--color-amber)" }}>
            {hoursToHm(stop.hours)}
          </span>
        </li>
      ))}
    </ul>
  );
}
