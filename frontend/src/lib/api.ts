import type { Place, Trip, TripFormValues } from "./types";

const BASE = "/api";

export class ApiError extends Error {
  readonly fields: Record<string, string[]>;

  constructor(message: string, fields: Record<string, string[]> = {}) {
    super(message);
    this.name = "ApiError";
    this.fields = fields;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return new ApiError(`Request failed (${response.status})`);
  }

  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return new ApiError(record.detail);

    // DRF field errors: { field: ["message", ...] }
    const fields: Record<string, string[]> = {};
    for (const [key, value] of Object.entries(record)) {
      if (Array.isArray(value)) fields[key] = value.map(String);
    }
    const first = Object.values(fields)[0]?.[0];
    return new ApiError(first ?? `Request failed (${response.status})`, fields);
  }

  return new ApiError(`Request failed (${response.status})`);
}

export async function planTrip(values: TripFormValues): Promise<Trip> {
  const response = await fetch(`${BASE}/trips/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...values,
      cycle_used_hours: Number(values.cycle_used_hours || 0),
      start_at: values.start_at || null,
    }),
  });

  if (!response.ok) throw await parseError(response);
  return response.json();
}

export async function fetchTrip(id: string): Promise<Trip> {
  const response = await fetch(`${BASE}/trips/${id}/`);
  if (!response.ok) throw await parseError(response);
  return response.json();
}

export async function suggestPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const response = await fetch(`${BASE}/geocode/?q=${encodeURIComponent(query)}`, { signal });
  if (!response.ok) return [];
  const body = (await response.json()) as { results?: Place[] };
  return body.results ?? [];
}

/** Wakes a cold serverless function so the first real request is not slow. */
export function warmUp(): void {
  void fetch(`${BASE}/health/`).catch(() => undefined);
}
