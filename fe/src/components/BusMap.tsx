import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import { STOPS } from "@/lib/transit-data";

// Fix default marker icons (leaflet+webpack issue)
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const busIcon = L.divIcon({
  className: "",
  iconSize: [44, 44],
  iconAnchor: [22, 22],
  html: `
    <div style="position:relative;width:44px;height:44px;display:flex;align-items:center;justify-content:center;">
      <div style="position:absolute;inset:0;border-radius:9999px;background:oklch(0.78 0.18 155 / 0.25);animation:pulse-ring 2s infinite;"></div>
      <div style="width:28px;height:28px;border-radius:9999px;background:linear-gradient(135deg,oklch(0.78 0.18 155),oklch(0.72 0.18 35));display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px oklch(0 0 0 / 0.5),0 0 20px oklch(0.78 0.18 155 / 0.6);border:2px solid oklch(0.18 0.02 250);">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="oklch(0.16 0.02 250)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6v6"/><path d="M16 6v6"/><path d="M2 12h19.6"/><path d="M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"/><circle cx="7" cy="18" r="2"/><path d="M9 18h5"/><circle cx="16" cy="18" r="2"/></svg>
      </div>
    </div>
  `,
});

const stopIcon = (active: boolean) =>
  L.divIcon({
    className: "",
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    html: `<div style="width:16px;height:16px;border-radius:9999px;background:${active ? "oklch(0.72 0.18 35)" : "oklch(0.22 0.025 250)"};border:3px solid ${active ? "oklch(0.85 0.20 35)" : "oklch(0.78 0.18 155)"};box-shadow:0 2px 8px oklch(0 0 0 / 0.5);"></div>`,
  });

function FlyToBus({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  const did = useRef(false);
  useEffect(() => {
    if (!did.current && Number.isFinite(lat) && Number.isFinite(lng)) {
      map.setView([lat, lng], 15, { animate: true });
      did.current = true;
    }
  }, [lat, lng, map]);
  return null;
}

export type BusMapProps = {
  position: { lat: number; lng: number };
  activeStopIndex: number;
  upcomingPolyline: [number, number][];
};

export function BusMap({ position, activeStopIndex, upcomingPolyline }: BusMapProps) {
  const [center] = useState<[number, number]>([25.27, 82.99]);

  const routePolyline = useMemo<[number, number][]>(
    () => STOPS.map((s) => [s.lat, s.lng] as [number, number]).concat([[STOPS[0].lat, STOPS[0].lng]]),
    [],
  );

  return (
    <MapContainer
      center={center}
      zoom={14}
      zoomControl={true}
      className="h-full w-full"
      style={{ background: "oklch(0.18 0.02 250)" }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {/* Full route as faint polyline */}
      <Polyline
        positions={routePolyline}
        pathOptions={{ color: "oklch(0.78 0.18 155)", weight: 3, opacity: 0.3, dashArray: "6 8" }}
      />

      {/* Highlighted upcoming polyline */}
      {upcomingPolyline.length >= 2 && (
        <Polyline
          positions={upcomingPolyline}
          pathOptions={{ color: "oklch(0.78 0.18 155)", weight: 5, opacity: 0.95 }}
        />
      )}

      {STOPS.map((s, i) => (
        <Marker key={s.id} position={[s.lat, s.lng]} icon={stopIcon(i === activeStopIndex)} />
      ))}

      {STOPS.map((s) => (
        <CircleMarker
          key={`r-${s.id}`}
          center={[s.lat, s.lng]}
          radius={1}
          pathOptions={{ color: "transparent" }}
        />
      ))}

      <Marker position={[position.lat, position.lng]} icon={busIcon} />
      <FlyToBus lat={position.lat} lng={position.lng} />
    </MapContainer>
  );
}
