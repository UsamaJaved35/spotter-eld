import { useEffect, useMemo } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import type { Trip } from "../lib/types";
import { STOP_GLYPH, formatDayTime, hoursToHm } from "../lib/format";

const STOP_TINT: Record<string, string> = {
  pickup: "var(--color-signal)",
  dropoff: "var(--color-warn)",
  fuel: "var(--color-amber)",
  break30: "#8fa3b8",
  rest10: "var(--color-sleeper)",
  restart34: "#c58cff",
};

/** A small chamfered plaque rather than Leaflet's default teardrop pin. */
function plaque(kind: string, label: string) {
  const tint = STOP_TINT[kind] ?? "var(--color-amber)";
  return L.divIcon({
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html: `<div style="
      width:22px;height:22px;display:grid;place-items:center;
      background:var(--color-console-void);
      border:1.5px solid ${tint};
      color:${tint};
      font:600 11px/1 'IBM Plex Mono',monospace;
      box-shadow:0 0 12px -2px ${tint};
      clip-path:polygon(0 0,calc(100% - 6px) 0,100% 6px,100% 100%,6px 100%,0 calc(100% - 6px));
    ">${label}</div>`,
  });
}

const endpointIcon = (letter: string, tint: string) =>
  L.divIcon({
    className: "",
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html: `<div style="
      width:26px;height:26px;display:grid;place-items:center;border-radius:50%;
      background:${tint};color:var(--color-console-void);
      font:800 12px/1 'Archivo',sans-serif;
      box-shadow:0 0 0 3px color-mix(in oklab, ${tint} 28%, transparent), 0 0 18px -2px ${tint};
    ">${letter}</div>`,
  });

function FitBounds({ trip }: { trip: Trip }) {
  const map = useMap();

  useEffect(() => {
    const points = trip.route.legs.flatMap((leg) => leg.coords);
    if (points.length < 2) return;
    map.fitBounds(L.latLngBounds(points as [number, number][]), {
      padding: [48, 48],
      animate: false,
    });
  }, [map, trip]);

  return null;
}

export function RouteMap({ trip }: { trip: Trip }) {
  const center = useMemo<[number, number]>(
    () => [trip.places.pickup.lat, trip.places.pickup.lon],
    [trip],
  );

  return (
    <MapContainer
      center={center}
      zoom={5}
      scrollWheelZoom
      style={{ height: "100%", width: "100%" }}
      attributionControl
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
        subdomains="abcd"
        maxZoom={19}
      />

      {trip.route.legs.map((leg, i) => (
        <div key={i}>
          {/* glow underlay, then the line itself */}
          <Polyline
            positions={leg.coords}
            pathOptions={{ color: i === 0 ? "#35d07f" : "#ffb020", weight: 9, opacity: 0.16 }}
          />
          <Polyline
            positions={leg.coords}
            pathOptions={{
              color: i === 0 ? "#35d07f" : "#ffb020",
              weight: 3,
              opacity: 0.95,
              dashArray: i === 0 ? "1 0" : undefined,
            }}
          />
        </div>
      ))}

      <Marker position={[trip.places.current.lat, trip.places.current.lon]} icon={endpointIcon("A", "#e8eef5")}>
        <Popup>
          <strong>Current location</strong>
          <br />
          {trip.places.current.label}
        </Popup>
      </Marker>
      <Marker position={[trip.places.pickup.lat, trip.places.pickup.lon]} icon={endpointIcon("P", "#35d07f")}>
        <Popup>
          <strong>Pickup</strong>
          <br />
          {trip.places.pickup.label}
        </Popup>
      </Marker>
      <Marker position={[trip.places.dropoff.lat, trip.places.dropoff.lon]} icon={endpointIcon("D", "#ff5c48")}>
        <Popup>
          <strong>Dropoff</strong>
          <br />
          {trip.places.dropoff.label}
        </Popup>
      </Marker>

      {trip.stops
        .filter((stop) => stop.lat !== null && stop.lon !== null && stop.kind !== "pickup" && stop.kind !== "dropoff")
        .map((stop, i) => (
          <Marker
            key={i}
            position={[stop.lat as number, stop.lon as number]}
            icon={plaque(stop.kind, STOP_GLYPH[stop.kind] ?? "•")}
          >
            <Popup>
              <strong>{stop.label}</strong>
              <br />
              {stop.location}
              <br />
              {formatDayTime(stop.arrive)} · {hoursToHm(stop.hours)}
              <br />
              <em>{stop.note}</em>
            </Popup>
          </Marker>
        ))}

      <FitBounds trip={trip} />
    </MapContainer>
  );
}
