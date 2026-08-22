export type DutyStatus = "OFF" | "SB" | "D" | "ON";

export type StopKind =
  | "start"
  | "drive"
  | "pickup"
  | "dropoff"
  | "fuel"
  | "break30"
  | "rest10"
  | "restart34"
  | "off_duty";

export interface Place {
  lat: number;
  lon: number;
  label: string;
}

export interface RouteLegPayload {
  name: string;
  miles: number;
  hours: number;
  coords: [number, number][];
}

export interface Segment {
  status: DutyStatus;
  kind: StopKind;
  start: string;
  end: string;
  hours: number;
  miles: number;
  note: string;
  location: string;
  lat: number | null;
  lon: number | null;
}

export interface Stop {
  index: number;
  kind: StopKind;
  label: string;
  location: string;
  lat: number | null;
  lon: number | null;
  arrive: string;
  depart: string;
  hours: number;
  note: string;
}

export interface LogEntry {
  status: DutyStatus;
  start_hour: number;
  end_hour: number;
  kind: StopKind;
  note: string;
  location: string;
}

export interface LogRemark {
  hour: number;
  location: string;
  note: string;
  status: DutyStatus;
}

export interface DailyLog {
  date: string;
  entries: LogEntry[];
  remarks: LogRemark[];
  totals: Record<DutyStatus, number>;
  total_hours: number;
  total_miles: number;
}

export interface TripSummary {
  total_miles: number;
  total_drive_hours: number;
  total_duration_hours: number;
  start_at: string;
  end_at: string;
  log_sheet_count: number;
  cycle_used_start: number;
  cycle_used_end: number;
  cycle_remaining: number;
  stop_counts: Partial<Record<StopKind, number>>;
}

export interface TripInputs {
  current_location: string;
  pickup_location: string;
  dropoff_location: string;
  cycle_used_hours: number;
  start_at: string;
  driver_name: string;
  carrier_name: string;
  main_office: string;
  truck_number: string;
  shipping_doc: string;
}

export interface Trip {
  id: string;
  created_at: string;
  inputs: TripInputs;
  places: { current: Place; pickup: Place; dropoff: Place };
  route: { provider: string; geocoder?: string; legs: RouteLegPayload[] };
  segments: Segment[];
  stops: Stop[];
  daily_logs: DailyLog[];
  summary: TripSummary;
  assumptions: string[];
}

export interface TripFormValues {
  current_location: string;
  pickup_location: string;
  dropoff_location: string;
  cycle_used_hours: string;
  start_at: string;
  driver_name: string;
  carrier_name: string;
  main_office: string;
  truck_number: string;
  shipping_doc: string;
}
