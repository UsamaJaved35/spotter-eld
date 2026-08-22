import { useState } from "react";
import { LocationField } from "./LocationField";
import type { TripFormValues } from "../lib/types";

const PRESETS: { name: string; hint: string; values: Partial<TripFormValues> }[] = [
  {
    name: "Short haul",
    hint: "One sheet, no rest required",
    values: {
      current_location: "Fort Worth, Texas",
      pickup_location: "Dallas, Texas",
      dropoff_location: "Waco, Texas",
      cycle_used_hours: "8",
    },
  },
  {
    name: "Two-day run",
    hint: "Fuel stop and a 10-hour rest",
    values: {
      current_location: "Dallas, Texas",
      pickup_location: "Oklahoma City, Oklahoma",
      dropoff_location: "Chicago, Illinois",
      cycle_used_hours: "20",
    },
  },
  {
    name: "Cycle nearly spent",
    hint: "Forces a 34-hour restart",
    values: {
      current_location: "Denver, Colorado",
      pickup_location: "Salt Lake City, Utah",
      dropoff_location: "Portland, Oregon",
      cycle_used_hours: "68",
    },
  },
];

export function defaultValues(): TripFormValues {
  const now = new Date();
  now.setMinutes(Math.floor(now.getMinutes() / 15) * 15, 0, 0);
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);

  return {
    current_location: "",
    pickup_location: "",
    dropoff_location: "",
    cycle_used_hours: "0",
    start_at: local.toISOString().slice(0, 16),
    driver_name: "",
    carrier_name: "",
    main_office: "",
    truck_number: "",
    shipping_doc: "",
  };
}

interface Props {
  values: TripFormValues;
  onChange: (values: TripFormValues) => void;
  onSubmit: () => void;
  loading: boolean;
  fieldErrors: Record<string, string[]>;
}

export function TripForm({ values, onChange, onSubmit, loading, fieldErrors }: Props) {
  const [showDetails, setShowDetails] = useState(false);
  const set = (key: keyof TripFormValues) => (value: string) => onChange({ ...values, [key]: value });
  const errorFor = (key: string) => fieldErrors[key]?.[0];

  const cycle = Number(values.cycle_used_hours || 0);

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <LocationField
        label="Current location"
        marker="A"
        markerTint="var(--color-console-bright)"
        value={values.current_location}
        onChange={set("current_location")}
        placeholder="Dallas, Texas"
        error={errorFor("current_location")}
      />
      <LocationField
        label="Pickup location"
        marker="P"
        markerTint="var(--color-signal)"
        value={values.pickup_location}
        onChange={set("pickup_location")}
        placeholder="Oklahoma City, Oklahoma"
        error={errorFor("pickup_location")}
      />
      <LocationField
        label="Dropoff location"
        marker="D"
        markerTint="var(--color-warn)"
        value={values.dropoff_location}
        onChange={set("dropoff_location")}
        placeholder="Chicago, Illinois"
        error={errorFor("dropoff_location")}
      />

      {/* cycle hours: slider and number stay in sync */}
      <div>
        <div className="mb-1.5 flex items-baseline justify-between">
          <label htmlFor="cycle" className="stencil">
            Current cycle used
          </label>
          <span
            className="tnum font-mono text-xs"
            style={{ color: cycle > 60 ? "var(--color-warn)" : "var(--color-amber)" }}
          >
            {cycle.toFixed(1)} / 70 h
          </span>
        </div>
        <div className="flex items-center gap-3">
          <input
            id="cycle"
            type="range"
            min={0}
            max={70}
            step={0.5}
            value={values.cycle_used_hours}
            onChange={(e) => set("cycle_used_hours")(e.target.value)}
            className="h-1 flex-1 cursor-pointer appearance-none rounded-full"
            style={{
              background: `linear-gradient(90deg, var(--color-amber) ${(cycle / 70) * 100}%, var(--color-console-line) ${(cycle / 70) * 100}%)`,
            }}
          />
          <input
            type="number"
            min={0}
            max={70}
            step={0.5}
            aria-label="Cycle hours used"
            value={values.cycle_used_hours}
            onChange={(e) => set("cycle_used_hours")(e.target.value)}
            className="field !w-20 !py-1 text-center"
          />
        </div>
        {errorFor("cycle_used_hours") && (
          <p className="mt-1 font-mono text-[10px]" style={{ color: "var(--color-warn)" }}>
            {errorFor("cycle_used_hours")}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="start" className="stencil mb-1.5 block">
          Departure
        </label>
        <input
          id="start"
          type="datetime-local"
          className="field"
          value={values.start_at}
          onChange={(e) => set("start_at")(e.target.value)}
        />
      </div>

      {/* optional log-header fields */}
      <div>
        <button
          type="button"
          onClick={() => setShowDetails((v) => !v)}
          className="stencil flex w-full items-center justify-between py-1 transition-colors hover:opacity-80"
        >
          <span>Driver &amp; carrier details</span>
          <span style={{ color: "var(--color-amber)" }}>{showDetails ? "−" : "+"}</span>
        </button>

        {showDetails && (
          <div className="mt-2 grid gap-2.5">
            {(
              [
                ["driver_name", "Driver name"],
                ["carrier_name", "Carrier"],
                ["main_office", "Main office address"],
                ["truck_number", "Truck / trailer no."],
                ["shipping_doc", "Shipping document no."],
              ] as [keyof TripFormValues, string][]
            ).map(([key, label]) => (
              <div key={key}>
                <label htmlFor={key} className="stencil !text-[10px] mb-1 block">
                  {label}
                </label>
                <input
                  id={key}
                  className="field !py-1.5"
                  value={values[key]}
                  onChange={(e) => set(key)(e.target.value)}
                />
              </div>
            ))}
            <p className="text-[10px] leading-relaxed" style={{ color: "var(--color-console-dim)" }}>
              Optional. These fill the header of the printed log sheet, which 395.8 requires.
            </p>
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={loading}
        className="chamfer relative w-full py-3 text-sm font-bold tracking-[0.14em] uppercase transition-all disabled:cursor-wait"
        style={{
          background: loading ? "var(--color-console-raised)" : "var(--color-amber)",
          color: loading ? "var(--color-console-dim)" : "var(--color-console-void)",
          boxShadow: loading ? "none" : "0 0 28px -8px var(--color-amber)",
        }}
      >
        {loading ? "Plotting route…" : "Plan trip"}
      </button>

      <div>
        <div className="stencil mb-2">Try one</div>
        <div className="grid gap-1.5">
          {PRESETS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => onChange({ ...values, ...preset.values })}
              className="group flex items-baseline justify-between border px-2.5 py-1.5 text-left transition-colors"
              style={{ borderColor: "var(--color-console-line)", background: "var(--color-console-void)" }}
            >
              <span className="text-[11px]" style={{ color: "var(--color-console-text)" }}>
                {preset.name}
              </span>
              <span className="text-[10px]" style={{ color: "var(--color-console-dim)" }}>
                {preset.hint}
              </span>
            </button>
          ))}
        </div>
      </div>
    </form>
  );
}
