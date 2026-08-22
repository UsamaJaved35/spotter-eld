import { forwardRef, useMemo } from "react";
import type { DailyLog, DutyStatus, TripInputs } from "../lib/types";
import { formatSheetDate } from "../lib/format";

/* ---------------------------------------------------------------------------
   A faithful redraw of the FMCSA driver's daily log (49 CFR 395.8): the 24-hour
   graph grid with its four duty rows, the total-hours column, the Remarks band
   naming a city and state at every change of duty status, and the 70-hour/8-day
   recap. Rendered as SVG so it stays crisp and exports cleanly to PNG and PDF.
--------------------------------------------------------------------------- */

const W = 1000;
const H = 640;

// Graph grid geometry
const GRID_X = 176;
const GRID_W = 706;
const GRID_TOP = 258;
const ROW_H = 26;
const GRID_H = ROW_H * 4;
const TOTALS_X = GRID_X + GRID_W;
const TOTALS_W = W - TOTALS_X - 22;

const ROWS: { status: DutyStatus; label: string }[] = [
  { status: "OFF", label: "1. Off Duty" },
  { status: "SB", label: "2. Sleeper Berth" },
  { status: "D", label: "3. Driving" },
  { status: "ON", label: "4. On Duty (not driving)" },
];

const INK = "#14110c";
const RULE = "#6f6959";
const PEN = "#1b3a6b"; // ballpoint blue, as a driver would use

const x = (hour: number) => GRID_X + (hour / 24) * GRID_W;
const rowY = (status: DutyStatus) =>
  GRID_TOP + ROWS.findIndex((r) => r.status === status) * ROW_H + ROW_H / 2;

const HOUR_LABELS = [
  "Mid-\nnight", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11",
  "Noon", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "Mid-\nnight",
];

interface Props {
  log: DailyLog;
  inputs: TripInputs;
  /** Cycle hours used through the end of this day, for the recap block. */
  cycleUsedThroughToday: number;
  cycleLimit?: number;
  index: number;
  total: number;
}

export const LogSheet = forwardRef<SVGSVGElement, Props>(function LogSheet(
  { log, inputs, cycleUsedThroughToday, cycleLimit = 70, index, total },
  ref,
) {
  const { month, day, year } = formatSheetDate(log.date);

  /* The duty line is one continuous stroke: each entry contributes a horizontal
     run, and because entries are contiguous the joins become the vertical
     connectors at every change of duty status. */
  const penPath = useMemo(() => {
    const points: string[] = [];
    log.entries.forEach((entry) => {
      const y = rowY(entry.status);
      points.push(`${x(entry.start_hour).toFixed(2)},${y}`);
      points.push(`${x(entry.end_hour).toFixed(2)},${y}`);
    });
    return points.length ? `M ${points.join(" L ")}` : "";
  }, [log.entries]);

  const penLength = useMemo(() => {
    let length = 0;
    let previous: { x: number; y: number } | null = null;
    log.entries.forEach((entry) => {
      const y = rowY(entry.status);
      const a = { x: x(entry.start_hour), y };
      const b = { x: x(entry.end_hour), y };
      if (previous) length += Math.abs(a.y - previous.y);
      length += b.x - a.x;
      previous = b;
    });
    return Math.max(length, 1);
  }, [log.entries]);

  const from = log.remarks[0]?.location ?? "";
  const to = log.remarks[log.remarks.length - 1]?.location ?? from;
  const onDutyToday = (log.totals.D ?? 0) + (log.totals.ON ?? 0);
  const availableTomorrow = Math.max(0, cycleLimit - cycleUsedThroughToday);

  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      role="img"
      aria-label={`Driver's daily log for ${log.date}, sheet ${index + 1} of ${total}`}
      style={{ fontFamily: "'Archivo', sans-serif", display: "block" }}
    >
      <rect width={W} height={H} fill="var(--color-paper)" />

      {/* ---------- title block ---------- */}
      <text x={22} y={44} fontSize={27} fontWeight={800} fill={INK} letterSpacing="-0.4">
        Driver&apos;s Daily Log
      </text>
      <text x={22} y={62} fontSize={10.5} fill={INK}>
        (24 hours)
      </text>

      <Field x={252} y={44} w={54} value={month} label="(month)" />
      <text x={310} y={44} fontSize={15} fill={INK}>/</text>
      <Field x={322} y={44} w={44} value={day} label="(day)" />
      <text x={370} y={44} fontSize={15} fill={INK}>/</text>
      <Field x={382} y={44} w={62} value={year} label="(year)" />

      <text x={520} y={26} fontSize={9.5} fill={INK}>
        Original — File at home terminal.
      </text>
      <text x={520} y={40} fontSize={9.5} fill={INK}>
        Duplicate — Driver retains in his/her possession for 8 days.
      </text>
      <text x={520} y={58} fontSize={9.5} fill={RULE}>
        Sheet {index + 1} of {total}
      </text>

      {/* ---------- from / to ---------- */}
      <LabelledRule x={22} y={98} w={330} label="From:" value={from} />
      <LabelledRule x={392} y={98} w={330} label="To:" value={to} />

      {/* ---------- mileage + carrier ---------- */}
      <BoxField x={38} y={122} w={150} h={40} value={log.total_miles.toFixed(0)} caption="Total Miles Driving Today" />
      <BoxField x={202} y={122} w={150} h={40} value={log.total_miles.toFixed(0)} caption="Total Mileage Today" />
      <BoxField x={392} y={122} w={330} h={40} value={inputs.carrier_name} caption="Name of Carrier or Carriers" mono={false} />

      <BoxField x={38} y={182} w={314} h={40} value={inputs.truck_number} caption="Truck/Tractor and Trailer Numbers or License Plate(s)/State (show each unit)" mono={false} small />
      <BoxField x={392} y={182} w={330} h={40} value={inputs.main_office} caption="Main Office Address" mono={false} />
      <BoxField x={752} y={122} w={226} h={40} value={inputs.driver_name} caption="Driver's Signature in Full" mono={false} script />
      <BoxField x={752} y={182} w={226} h={40} value={inputs.main_office} caption="Home Terminal Address" mono={false} />

      {/* ---------- graph grid ---------- */}
      <HourScale y={GRID_TOP - 8} />

      {/* row bands: alternate faint shading so the four rows read apart */}
      {ROWS.map((row, i) => (
        <rect
          key={row.status}
          x={GRID_X}
          y={GRID_TOP + i * ROW_H}
          width={GRID_W}
          height={ROW_H}
          fill={i % 2 ? "var(--color-paper-shade)" : "transparent"}
          opacity={0.55}
        />
      ))}

      {/* quarter-hour ticks, as printed on the real form */}
      {Array.from({ length: 24 * 4 + 1 }, (_, i) => {
        const hour = i / 4;
        const isHour = i % 4 === 0;
        const isHalf = i % 4 === 2;
        return (
          <g key={i}>
            {ROWS.map((row, r) => {
              const top = GRID_TOP + r * ROW_H;
              const len = isHour ? ROW_H : isHalf ? ROW_H * 0.42 : ROW_H * 0.24;
              return (
                <line
                  key={row.status}
                  x1={x(hour)}
                  x2={x(hour)}
                  y1={top}
                  y2={top + len}
                  stroke={isHour ? RULE : "#a9a292"}
                  strokeWidth={isHour ? 0.8 : 0.5}
                />
              );
            })}
          </g>
        );
      })}

      {/* row separators + outer frame */}
      {Array.from({ length: 5 }, (_, i) => (
        <line
          key={i}
          x1={GRID_X}
          x2={GRID_X + GRID_W}
          y1={GRID_TOP + i * ROW_H}
          y2={GRID_TOP + i * ROW_H}
          stroke={INK}
          strokeWidth={i === 0 || i === 4 ? 1.4 : 0.9}
        />
      ))}
      <rect x={GRID_X} y={GRID_TOP} width={GRID_W} height={GRID_H} fill="none" stroke={INK} strokeWidth={1.4} />

      {/* row labels */}
      {ROWS.map((row, i) => (
        <text
          key={row.status}
          x={GRID_X - 10}
          y={GRID_TOP + i * ROW_H + ROW_H / 2 + 3.5}
          fontSize={10}
          fill={INK}
          textAnchor="end"
        >
          {row.label}
        </text>
      ))}

      {/* total-hours column */}
      <rect x={TOTALS_X} y={GRID_TOP} width={TOTALS_W} height={GRID_H} fill="none" stroke={INK} strokeWidth={1.4} />
      <text x={TOTALS_X + TOTALS_W / 2} y={GRID_TOP - 12} fontSize={9} fill={INK} textAnchor="middle">
        Total
      </text>
      <text x={TOTALS_X + TOTALS_W / 2} y={GRID_TOP - 3} fontSize={9} fill={INK} textAnchor="middle">
        Hours
      </text>
      {ROWS.map((row, i) => (
        <g key={row.status}>
          {i > 0 && (
            <line
              x1={TOTALS_X}
              x2={TOTALS_X + TOTALS_W}
              y1={GRID_TOP + i * ROW_H}
              y2={GRID_TOP + i * ROW_H}
              stroke={INK}
              strokeWidth={0.9}
            />
          )}
          <text
            x={TOTALS_X + TOTALS_W / 2}
            y={GRID_TOP + i * ROW_H + ROW_H / 2 + 4}
            fontSize={12}
            fontWeight={600}
            fill={PEN}
            textAnchor="middle"
            style={{ fontFamily: "'IBM Plex Mono', monospace" }}
          >
            {(log.totals[row.status] ?? 0).toFixed(2)}
          </text>
        </g>
      ))}
      <text
        x={TOTALS_X + TOTALS_W / 2}
        y={GRID_TOP + GRID_H + 16}
        fontSize={12}
        fontWeight={700}
        fill={PEN}
        textAnchor="middle"
        style={{ fontFamily: "'IBM Plex Mono', monospace" }}
      >
        = {log.total_hours.toFixed(2)}
      </text>

      <HourScale y={GRID_TOP + GRID_H + 12} compact />

      {/* ---------- the drawn duty line ---------- */}
      <path
        d={penPath}
        fill="none"
        stroke={PEN}
        strokeWidth={2.6}
        strokeLinejoin="round"
        strokeLinecap="round"
        strokeDasharray={penLength}
        strokeDashoffset={penLength}
        style={{ animation: `draw 1400ms cubic-bezier(0.4, 0, 0.2, 1) ${180 + index * 120}ms forwards` }}
      />

      {/* ---------- remarks ---------- */}
      <text x={22} y={GRID_TOP + GRID_H + 44} fontSize={12} fontWeight={700} fill={INK}>
        Remarks
      </text>
      <line
        x1={GRID_X}
        x2={GRID_X + GRID_W}
        y1={GRID_TOP + GRID_H + 30}
        y2={GRID_TOP + GRID_H + 30}
        stroke={RULE}
        strokeWidth={0.8}
      />
      {log.remarks.map((remark, i) => {
        const rx = x(remark.hour);
        const baseY = GRID_TOP + GRID_H + 30;
        return (
          <g key={`${remark.hour}-${i}`}>
            <line x1={rx} x2={rx} y1={baseY} y2={baseY + 10} stroke={PEN} strokeWidth={0.9} />
            <text
              x={rx - 2}
              y={baseY + 13}
              fontSize={9}
              fill={PEN}
              textAnchor="end"
              transform={`rotate(-60 ${rx - 2} ${baseY + 13})`}
              style={{ fontFamily: "'IBM Plex Mono', monospace" }}
            >
              {remark.location}
            </text>
          </g>
        );
      })}

      {/* ---------- shipping documents ---------- */}
      <g transform={`translate(0, ${H - 130})`}>
        <line x1={22} x2={W - 22} y1={0} y2={0} stroke={RULE} strokeWidth={0.8} />
        <text x={22} y={18} fontSize={9.5} fill={INK}>Shipping Documents:</text>
        <text x={22} y={36} fontSize={9} fill={RULE}>DVL or Manifest No.</text>
        <text
          x={140}
          y={36}
          fontSize={11}
          fill={PEN}
          style={{ fontFamily: "'IBM Plex Mono', monospace" }}
        >
          {inputs.shipping_doc}
        </text>
        <text x={22} y={54} fontSize={9} fill={RULE}>Shipper &amp; Commodity</text>
        <text
          x={140}
          y={54}
          fontSize={11}
          fill={PEN}
          style={{ fontFamily: "'IBM Plex Mono', monospace" }}
        >
          {inputs.pickup_location}
        </text>

        {/* recap: 70 hour / 8 day */}
        <rect x={430} y={-4} width={W - 452} height={106} fill="none" stroke={RULE} strokeWidth={0.8} />
        <text x={444} y={14} fontSize={9.5} fontWeight={700} fill={INK}>
          Recap — 70 Hour / 8 Day Drivers
        </text>
        <RecapCell
          x={444}
          label="A. Total hours on duty today (lines 3 &amp; 4)"
          value={onDutyToday.toFixed(2)}
        />
        <RecapCell
          x={630}
          label="B. Total hours on duty last 8 days including today"
          value={cycleUsedThroughToday.toFixed(2)}
        />
        <RecapCell
          x={816}
          label="C. Total hours available tomorrow (70 hr. minus B)"
          value={availableTomorrow.toFixed(2)}
        />
      </g>
    </svg>
  );
});

/* ---------------------------------------------------------------- helpers */

function HourScale({ y, compact = false }: { y: number; compact?: boolean }) {
  return (
    <g>
      {HOUR_LABELS.map((label, i) => {
        const lines = label.split("\n");
        return (
          <text
            key={i}
            x={x(i)}
            y={y}
            fontSize={compact ? 7.5 : 8}
            fill={INK}
            textAnchor="middle"
            style={{ fontFamily: "'IBM Plex Mono', monospace" }}
          >
            {lines.map((line, li) => (
              <tspan key={li} x={x(i)} dy={li === 0 ? 0 : 8}>
                {line}
              </tspan>
            ))}
          </text>
        );
      })}
    </g>
  );
}

function Field({ x: fx, y, w, value, label }: { x: number; y: number; w: number; value: string; label: string }) {
  return (
    <g>
      <text
        x={fx + w / 2}
        y={y - 4}
        fontSize={14}
        fill={PEN}
        textAnchor="middle"
        style={{ fontFamily: "'IBM Plex Mono', monospace" }}
      >
        {value}
      </text>
      <line x1={fx} x2={fx + w} y1={y} y2={y} stroke={INK} strokeWidth={0.9} />
      <text x={fx + w / 2} y={y + 11} fontSize={8} fill={RULE} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}

function LabelledRule({
  x: lx, y, w, label, value,
}: { x: number; y: number; w: number; label: string; value: string }) {
  return (
    <g>
      <text x={lx} y={y - 3} fontSize={11} fontWeight={600} fill={INK}>
        {label}
      </text>
      <text
        x={lx + 46}
        y={y - 3}
        fontSize={12}
        fill={PEN}
        style={{ fontFamily: "'IBM Plex Mono', monospace" }}
      >
        {value}
      </text>
      <line x1={lx + 42} x2={lx + w} y1={y} y2={y} stroke={INK} strokeWidth={0.9} />
    </g>
  );
}

function BoxField({
  x: bx, y, w, h, value, caption, mono = true, small = false, script = false,
}: {
  x: number; y: number; w: number; h: number; value: string;
  caption: string; mono?: boolean; small?: boolean; script?: boolean;
}) {
  return (
    <g>
      <rect x={bx} y={y} width={w} height={h} fill="none" stroke={INK} strokeWidth={0.9} />
      <text
        x={bx + w / 2}
        y={y + h / 2 + 5}
        fontSize={script ? 15 : 13}
        fill={PEN}
        textAnchor="middle"
        style={{
          fontFamily: mono ? "'IBM Plex Mono', monospace" : "'Archivo', sans-serif",
          fontStyle: script ? "italic" : "normal",
        }}
      >
        {truncate(value, Math.floor(w / (script ? 8 : 7.2)))}
      </text>
      <text x={bx + w / 2} y={y + h + 11} fontSize={small ? 6.8 : 7.6} fill={RULE} textAnchor="middle">
        {caption}
      </text>
    </g>
  );
}

function RecapCell({ x: rx, label, value }: { x: number; label: string; value: string }) {
  const words = label.split(" ");
  const lines: string[] = [];
  let current = "";
  words.forEach((word) => {
    if ((current + " " + word).trim().length > 24) {
      lines.push(current.trim());
      current = word;
    } else {
      current = `${current} ${word}`;
    }
  });
  if (current.trim()) lines.push(current.trim());

  return (
    <g>
      <text
        x={rx}
        y={44}
        fontSize={19}
        fontWeight={700}
        fill={PEN}
        style={{ fontFamily: "'IBM Plex Mono', monospace" }}
      >
        {value}
      </text>
      <text x={rx} y={62} fontSize={7.4} fill={RULE}>
        {lines.map((line, i) => (
          <tspan key={i} x={rx} dy={i === 0 ? 0 : 8.6}>
            {line}
          </tspan>
        ))}
      </text>
    </g>
  );
}

function truncate(value: string, max: number): string {
  if (!value) return "";
  return value.length > max ? `${value.slice(0, Math.max(1, max - 1))}…` : value;
}
