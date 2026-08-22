import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchTrip, planTrip, warmUp } from "./lib/api";
import type { Trip, TripFormValues } from "./lib/types";
import { TripForm, defaultValues } from "./components/TripForm";
import { RouteMap } from "./components/RouteMap";
import { Itinerary, StopList } from "./components/Itinerary";
import { DayTotals, DutyLegend, DutyRibbon } from "./components/DutyRibbon";
import { CycleGauge, Summary } from "./components/Summary";
import { LogSheet } from "./components/LogSheet";
import { downloadLogsPdf, downloadSheetPng } from "./lib/export";
import { formatLongDate, hoursToHm } from "./lib/format";

const CYCLE_LIMIT = 70;

function tripIdFromPath(): string | null {
  const match = window.location.pathname.match(/^\/trip\/([0-9a-f-]{36})/i);
  return match ? match[1] : null;
}

export default function App() {
  const [values, setValues] = useState<TripFormValues>(defaultValues);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [copied, setCopied] = useState(false);
  const sheetRefs = useRef<(SVGSVGElement | null)[]>([]);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Warm the serverless function so the first plan is not waiting on a cold start.
  useEffect(() => warmUp(), []);

  // Restore a shared trip from /trip/<id>, and keep back/forward working.
  useEffect(() => {
    async function load() {
      const id = tripIdFromPath();
      if (!id) return;
      setLoading(true);
      try {
        const restored = await fetchTrip(id);
        setTrip(restored);
        setValues((v) => ({ ...v, ...restored.inputs, cycle_used_hours: String(restored.inputs.cycle_used_hours) }));
      } catch {
        setError("That trip link could not be found.");
      } finally {
        setLoading(false);
      }
    }
    void load();
    window.addEventListener("popstate", load);
    return () => window.removeEventListener("popstate", load);
  }, []);

  const submit = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFieldErrors({});
    try {
      const result = await planTrip(values);
      setTrip(result);
      window.history.pushState({}, "", `/trip/${result.id}`);
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fields);
      } else {
        setError("Something went wrong while planning the trip.");
      }
    } finally {
      setLoading(false);
    }
  }, [values]);

  /** Cycle hours used through the end of each day, for each sheet's recap. */
  const cycleByDay = useMemo(() => {
    if (!trip) return [];
    let used = trip.summary.cycle_used_start;
    return trip.daily_logs.map((log) => {
      used += (log.totals.D ?? 0) + (log.totals.ON ?? 0);
      return used;
    });
  }, [trip]);

  async function share() {
    await navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="relative z-10 min-h-screen">
      <Masthead trip={trip} />

      <div className="mx-auto grid max-w-[1680px] grid-cols-[minmax(0,1fr)] gap-6 px-4 pb-20 lg:grid-cols-[350px_minmax(0,1fr)] lg:px-6">
        {/* ---------------- control rail ---------------- */}
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <div className="panel chamfer p-5">
            <div className="mb-4 flex items-center justify-between border-b pb-3" style={{ borderColor: "var(--color-console-line)" }}>
              <h2 className="text-sm font-bold tracking-[0.16em] uppercase" style={{ color: "var(--color-console-bright)" }}>
                Trip Inputs
              </h2>
              <span className="stencil !text-[9px]">FMCSA 395</span>
            </div>

            <TripForm
              values={values}
              onChange={setValues}
              onSubmit={submit}
              loading={loading}
              fieldErrors={fieldErrors}
            />

            {error && (
              <div
                className="mt-4 border-l-2 px-3 py-2 text-[12px]"
                style={{ borderColor: "var(--color-warn)", background: "color-mix(in oklab, var(--color-warn) 10%, transparent)", color: "var(--color-console-bright)" }}
                role="alert"
              >
                {error}
              </div>
            )}
          </div>
        </aside>

        {/* ---------------- results ---------------- */}
        <main ref={resultsRef} className="min-w-0">
          {!trip && !loading && <EmptyState />}
          {loading && !trip && <LoadingState />}

          {trip && (
            <div className="flex flex-col gap-6">
              <section className="rise">
                <Summary trip={trip} />
              </section>

              <section className="rise grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,1fr)_360px]" style={{ animationDelay: "80ms" }}>
                <div className="panel chamfer overflow-hidden">
                  <PanelHeader title="Route" note={`${trip.route.legs.length} legs · via ${trip.route.provider}`} />
                  <div className="h-[440px] w-full">
                    <RouteMap trip={trip} />
                  </div>
                </div>

                <div className="flex flex-col gap-4">
                  <CycleGauge trip={trip} />
                  <div className="panel chamfer overflow-hidden">
                    <PanelHeader title="Stops & rests" note={`${trip.stops.length} total`} />
                    <StopList trip={trip} />
                  </div>
                </div>
              </section>

              <section className="rise grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[380px_minmax(0,1fr)]" style={{ animationDelay: "160ms" }}>
                <div className="panel chamfer flex max-h-[560px] flex-col overflow-hidden">
                  <PanelHeader title="Duty timeline" note="every status change" />
                  <div className="min-h-0 flex-1 overflow-y-auto px-4 py-2">
                    <Itinerary trip={trip} />
                  </div>
                </div>

                <div className="panel chamfer overflow-hidden">
                  <PanelHeader title="Daily duty status" note={`${trip.daily_logs.length} days`} />
                  <div className="flex flex-col gap-5 p-4">
                    <DutyLegend />
                    {trip.daily_logs.map((log) => (
                      <div key={log.date}>
                        <div className="mb-1.5 flex items-baseline justify-between">
                          <span className="text-[12px]" style={{ color: "var(--color-console-bright)" }}>
                            {formatLongDate(log.date)}
                          </span>
                          <span className="tnum font-mono text-[11px]" style={{ color: "var(--color-console-dim)" }}>
                            {log.total_miles.toFixed(0)} mi · {hoursToHm(log.totals.D ?? 0)} driving
                          </span>
                        </div>
                        <DutyRibbon log={log} />
                        <div className="mt-2">
                          <DayTotals log={log} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              {/* ---------------- the paper log sheets ---------------- */}
              <section className="rise" style={{ animationDelay: "240ms" }}>
                <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-bold tracking-tight" style={{ color: "var(--color-console-bright)" }}>
                      Driver&apos;s Daily Logs
                    </h2>
                    <p className="mt-0.5 text-[12px]" style={{ color: "var(--color-console-dim)" }}>
                      One record of duty status per calendar day, drawn per 49 CFR 395.8.
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={share}
                      className="border px-3 py-2 font-mono text-[11px] tracking-wider uppercase transition-colors"
                      style={{ borderColor: "var(--color-console-edge)", color: "var(--color-console-text)" }}
                    >
                      {copied ? "Link copied" : "Copy share link"}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        downloadLogsPdf(
                          sheetRefs.current.filter(Boolean) as SVGSVGElement[],
                          `eld-logs-${trip.daily_logs[0].date}.pdf`,
                        )
                      }
                      className="chamfer px-4 py-2 font-mono text-[11px] font-semibold tracking-wider uppercase"
                      style={{ background: "var(--color-amber)", color: "var(--color-console-void)" }}
                    >
                      Download PDF
                    </button>
                  </div>
                </div>

                <div className="flex flex-col gap-8">
                  {trip.daily_logs.map((log, i) => (
                    <figure key={log.date} className="paper relative">
                      <LogSheet
                        ref={(el) => {
                          sheetRefs.current[i] = el;
                        }}
                        log={log}
                        inputs={trip.inputs}
                        cycleUsedThroughToday={cycleByDay[i] ?? 0}
                        cycleLimit={CYCLE_LIMIT}
                        index={i}
                        total={trip.daily_logs.length}
                      />
                      <figcaption className="absolute top-3 right-4 flex gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            const svg = sheetRefs.current[i];
                            if (svg) void downloadSheetPng(svg, `eld-log-${log.date}.png`);
                          }}
                          className="border px-2 py-1 font-mono text-[10px] tracking-wider uppercase transition-opacity hover:opacity-70"
                          style={{ borderColor: "#b6ad99", color: "#5a5344" }}
                        >
                          PNG
                        </button>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              </section>

              <Assumptions items={trip.assumptions} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ chrome */

function Masthead({ trip }: { trip: Trip | null }) {
  return (
    <header className="mx-auto max-w-[1680px] px-4 pt-7 pb-6 lg:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden
              className="grid h-7 w-7 place-items-center text-[13px] font-black"
              style={{ background: "var(--color-amber)", color: "var(--color-console-void)", clipPath: "polygon(0 0,calc(100% - 7px) 0,100% 7px,100% 100%,7px 100%,0 calc(100% - 7px))" }}
            >
              ▶
            </span>
            <h1
              className="text-[26px] leading-none font-extrabold tracking-[-0.02em]"
              style={{ color: "var(--color-console-bright)" }}
            >
              DISPATCH
            </h1>
            <span className="stencil !text-[10px] pt-1">ELD Trip Planner</span>
          </div>
          <p className="mt-2 max-w-xl text-[13px] leading-relaxed" style={{ color: "var(--color-console-dim)" }}>
            Route a property-carrying CMV against the federal hours-of-service limits, then draw the
            daily log sheets it produces.
          </p>
        </div>

        {trip && (
          <div className="flex items-center gap-5 font-mono text-[11px]" style={{ color: "var(--color-console-dim)" }}>
            <span>
              <span className="stencil !text-[9px] block">Origin</span>
              {trip.inputs.current_location}
            </span>
            <span style={{ color: "var(--color-console-edge)" }}>→</span>
            <span>
              <span className="stencil !text-[9px] block">Destination</span>
              {trip.inputs.dropoff_location}
            </span>
          </div>
        )}
      </div>
      <div className="mt-5 h-px w-full" style={{ background: "linear-gradient(90deg,var(--color-amber),transparent 40%)" }} />
    </header>
  );
}

function PanelHeader({ title, note }: { title: string; note?: string }) {
  return (
    <div
      className="flex items-baseline justify-between border-b px-4 py-2.5"
      style={{ borderColor: "var(--color-console-line)", background: "var(--color-console-raised)" }}
    >
      <h3 className="text-[13px] font-semibold tracking-wide" style={{ color: "var(--color-console-bright)" }}>
        {title}
      </h3>
      {note && <span className="stencil !text-[9px]">{note}</span>}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="panel chamfer flex min-h-[440px] flex-col items-center justify-center gap-4 p-10 text-center">
      <div
        className="grid h-14 w-14 place-items-center text-2xl"
        style={{ border: "1px solid var(--color-console-edge)", color: "var(--color-amber)" }}
      >
        ▶
      </div>
      <h2 className="text-lg font-semibold" style={{ color: "var(--color-console-bright)" }}>
        Enter a trip to begin
      </h2>
      <p className="max-w-md text-[13px] leading-relaxed" style={{ color: "var(--color-console-dim)" }}>
        Give a current location, a pickup, a dropoff and the hours already used against the
        70-hour cycle. You&apos;ll get the route with every required stop, and a filled-in daily
        log sheet for each day of the trip.
      </p>
    </div>
  );
}

function LoadingState() {
  const steps = ["Geocoding locations", "Routing legs", "Simulating duty clocks", "Drawing log sheets"];
  return (
    <div className="panel chamfer flex min-h-[440px] flex-col items-center justify-center gap-5 p-10">
      <div className="flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-6 w-1.5"
            style={{
              background: "var(--color-amber)",
              animation: `rise 900ms ease-in-out ${i * 140}ms infinite alternate`,
            }}
          />
        ))}
      </div>
      <ul className="space-y-1 text-center">
        {steps.map((step, i) => (
          <li
            key={step}
            className="rise font-mono text-[11px] tracking-wider uppercase"
            style={{ color: "var(--color-console-dim)", animationDelay: `${i * 220}ms` }}
          >
            {step}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Assumptions({ items }: { items: string[] }) {
  return (
    <section className="panel chamfer rise p-5" style={{ animationDelay: "320ms" }}>
      <h3 className="stencil mb-3">Rules and assumptions applied</h3>
      <ul className="grid gap-2 md:grid-cols-2">
        {items.map((item) => (
          <li key={item} className="flex gap-2.5 text-[12px] leading-relaxed" style={{ color: "var(--color-console-text)" }}>
            <span aria-hidden style={{ color: "var(--color-amber)" }}>
              ▸
            </span>
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}
