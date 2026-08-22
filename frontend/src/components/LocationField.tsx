import { useEffect, useId, useRef, useState } from "react";
import { suggestPlaces } from "../lib/api";
import type { Place } from "../lib/types";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  error?: string;
  marker?: string;
  markerTint?: string;
}

/** Text input with debounced address suggestions from the geocoding proxy. */
export function LocationField({
  label, value, onChange, placeholder, error, marker, markerTint,
}: Props) {
  const id = useId();
  const [suggestions, setSuggestions] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const wrapper = useRef<HTMLDivElement>(null);
  const typed = useRef(false);

  useEffect(() => {
    // Only the user's own typing should open suggestions. Values set
    // programmatically -- restoring a shared trip, or applying a preset --
    // must not pop the list open.
    if (!typed.current || value.trim().length < 3) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const results = await suggestPlaces(value, controller.signal);
        setSuggestions(results);
        setOpen(results.length > 0);
        setHighlight(-1);
      } catch {
        /* aborted or offline: suggestions are a convenience, not a requirement */
      }
    }, 280);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [value]);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function choose(place: Place) {
    typed.current = false;
    onChange(place.label);
    setOpen(false);
    setSuggestions([]);
  }

  return (
    <div ref={wrapper} className="relative">
      <label htmlFor={id} className="stencil mb-1.5 flex items-center gap-2">
        {marker && (
          <span
            aria-hidden
            className="grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold"
            style={{ background: markerTint ?? "var(--color-console-edge)", color: "var(--color-console-void)" }}
          >
            {marker}
          </span>
        )}
        {label}
      </label>

      <input
        id={id}
        className="field"
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        aria-invalid={Boolean(error)}
        onChange={(e) => {
          typed.current = true;
          onChange(e.target.value);
        }}
        onFocus={() => suggestions.length > 0 && typed.current && setOpen(true)}
        onKeyDown={(e) => {
          if (!open) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHighlight((h) => Math.min(h + 1, suggestions.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHighlight((h) => Math.max(h - 1, 0));
          } else if (e.key === "Enter" && highlight >= 0) {
            e.preventDefault();
            choose(suggestions[highlight]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />

      {error && (
        <p className="mt-1 font-mono text-[10px]" style={{ color: "var(--color-warn)" }}>
          {error}
        </p>
      )}

      {open && suggestions.length > 0 && (
        <ul
          className="absolute z-[1200] mt-1 max-h-60 w-full overflow-auto border shadow-2xl"
          style={{ background: "var(--color-console-raised)", borderColor: "var(--color-console-edge)" }}
        >
          {suggestions.map((place, i) => (
            <li key={`${place.lat}-${place.lon}-${i}`}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-[12px]"
                style={{
                  background: i === highlight ? "var(--color-console-panel)" : "transparent",
                  color: "var(--color-console-text)",
                }}
                onMouseEnter={() => setHighlight(i)}
                onClick={() => choose(place)}
              >
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
