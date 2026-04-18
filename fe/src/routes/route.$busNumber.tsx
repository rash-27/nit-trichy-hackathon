import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, BusFront, Gauge, Loader2 } from "lucide-react";
import { connectBusSocket } from "@/lib/mock-bus-ws";
import { STOPS, getBus, type BusPayload } from "@/lib/transit-data";
import { EtaSheet } from "@/components/EtaSheet";
import { AlertBanner, type AlertItem } from "@/components/AlertBanner";
import { lazy, Suspense } from "react";
const BusMap = lazy(() => import("@/components/BusMap").then((m) => ({ default: m.BusMap })));

export const Route = createFileRoute("/route/$busNumber")({
  loader: ({ params }) => {
    const bus = getBus(params.busNumber);
    if (!bus) throw notFound();
    return { bus };
  },
  head: ({ params }) => ({
    meta: [
      { title: `Bus ${params.busNumber} — Live Tracking` },
      { name: "description", content: `Real-time location and ETAs for bus ${params.busNumber}.` },
      { property: "og:title", content: `Bus ${params.busNumber} — Live Tracking` },
      { property: "og:description", content: `Track bus ${params.busNumber} in real time.` },
    ],
  }),
  component: BusRoutePage,
});

const STALE_MS = 20_000;

function distanceKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

function BusRoutePage() {
  const { bus } = Route.useLoaderData();
  const [payload, setPayload] = useState<BusPayload | null>(null);
  const [lastPacketAt, setLastPacketAt] = useState<number>(0);
  const [now, setNow] = useState<number>(() => Date.now());
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Smooth animated position — interpolated from prev -> latest
  const animRef = useRef<{
    from: { lat: number; lng: number };
    to: { lat: number; lng: number };
    startedAt: number;
    duration: number;
  } | null>(null);
  const [animPos, setAnimPos] = useState<{ lat: number; lng: number } | null>(null);
  const rafRef = useRef<number | null>(null);

  // Stable ref for previous server position to compute heading/extrapolation while stale
  const lastServerVelRef = useRef<{ lat: number; lng: number; t: number } | null>(null);
  const prevServerVelRef = useRef<{ lat: number; lng: number; t: number } | null>(null);

  // Subscribe to mock WS
  useEffect(() => {
    const teardown = connectBusSocket(bus.number, (data) => {
      setPayload(data);
      const t = Date.now();
      setLastPacketAt(t);
      if (data.isBusRunning) {
        const next = { lat: data.latitude, lng: data.longitude };
        prevServerVelRef.current = lastServerVelRef.current;
        lastServerVelRef.current = { ...next, t };
        // Animate from current (or first) to next over ~2s
        setAnimPos((cur) => {
          const from = cur ?? next;
          animRef.current = {
            from,
            to: next,
            startedAt: t,
            duration: 2000,
          };
          return from;
        });
      }
    });
    return teardown;
  }, [bus.number]);

  // Heartbeat + animation loop
  useEffect(() => {
    let stopped = false;
    const loop = () => {
      if (stopped) return;
      const t = Date.now();
      setNow(t);

      const a = animRef.current;
      if (a) {
        const elapsed = t - a.startedAt;
        const k = Math.min(1, elapsed / a.duration);
        // ease out
        const eased = 1 - Math.pow(1 - k, 3);
        const lat = a.from.lat + (a.to.lat - a.from.lat) * eased;
        const lng = a.from.lng + (a.to.lng - a.from.lng) * eased;

        // If stale > STALE_MS, extrapolate from last two server samples
        const stale = t - lastPacketAt > STALE_MS;
        if (stale && lastServerVelRef.current && prevServerVelRef.current) {
          const a1 = prevServerVelRef.current;
          const a2 = lastServerVelRef.current;
          const dt = Math.max(1, a2.t - a1.t);
          const vLat = (a2.lat - a1.lat) / dt;
          const vLng = (a2.lng - a1.lng) / dt;
          const extra = t - a2.t;
          // Cap extrapolation so it doesn't fly off the map
          const cap = Math.min(extra, 60_000);
          setAnimPos({ lat: a2.lat + vLat * cap, lng: a2.lng + vLng * cap });
        } else {
          setAnimPos({ lat, lng });
        }
      }
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => {
      stopped = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [lastPacketAt]);

  const stale = payload?.isBusRunning && now - lastPacketAt > STALE_MS;

  // Build alert
  const alert = useMemo<AlertItem | null>(() => {
    if (!payload || !payload.isBusRunning) return null;
    if (stale) {
      return {
        id: "stale",
        tone: "warning",
        icon: "offline",
        message: "Estimated bus location is shown — live signal lost",
      };
    }
    if (payload.isAtStop >= 0) {
      const name = STOPS[payload.isAtStop]?.name ?? "the stop";
      const mins = Math.max(1, Math.ceil(payload.timeTillBusWaitsAtStop / 60));
      return {
        id: `wait-${payload.isAtStop}`,
        tone: "info",
        icon: "stop",
        message: `The bus is waiting at ${name}, and it will start in ${mins} minute${mins > 1 ? "s" : ""}`,
      };
    }
    // Determine moving-from / arriving-to based on proximity
    const here = animPos ?? { lat: payload.latitude, lng: payload.longitude };
    const sortedByDist = STOPS.map((s) => ({ s, d: distanceKm(here, s) })).sort(
      (a, b) => a.d - b.d,
    );
    const nearest = sortedByDist[0];
    if (nearest.d < 0.18) {
      return {
        id: `arr-${nearest.s.id}`,
        tone: "success",
        icon: "arriving",
        message: `The bus is arriving to ${nearest.s.name}`,
      };
    }
    // Find which stop we most recently left (the upcoming etas tell us the next one)
    const nextName = Object.keys(payload.upcoming_etas)[0];
    const nextIdx = STOPS.findIndex((s) => s.name === nextName);
    const fromIdx = nextIdx <= 0 ? STOPS.length - 1 : nextIdx - 1;
    const fromName = STOPS[fromIdx]?.name ?? "the previous stop";
    return {
      id: `mov-${fromIdx}`,
      tone: "info",
      icon: "moving",
      message: `The bus is moving from ${fromName}`,
    };
  }, [payload, stale, animPos]);

  const upcomingList = useMemo(() => {
    if (!payload) return [];
    return Object.entries(payload.upcoming_etas).map(([name, eta]) => ({
      name,
      etaSeconds: eta,
    }));
  }, [payload]);

  const upcomingPolyline = useMemo<[number, number][]>(() => {
    if (!payload || !animPos) return [];
    const nextName = Object.keys(payload.upcoming_etas)[0];
    if (!nextName) return [];
    const startIdx = STOPS.findIndex((s) => s.name === nextName);
    if (startIdx < 0) return [];
    const pts: [number, number][] = [[animPos.lat, animPos.lng]];
    for (let i = 0; i < 3; i++) {
      const s = STOPS[(startIdx + i) % STOPS.length];
      pts.push([s.lat, s.lng]);
    }
    return pts;
  }, [payload, animPos]);

  // Header back button
  const Header = (
    <header className="absolute inset-x-0 top-0 z-30">
      <div className="mx-auto max-w-3xl px-4 pt-4">
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-card/80 backdrop-blur shadow-card hover:bg-secondary"
            aria-label="Back to bus list"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div className="flex-1 rounded-xl border border-border bg-card/80 backdrop-blur px-3 py-2 shadow-card">
            <div className="flex items-center gap-2">
              <BusFront className="h-4 w-4 text-primary" />
              <span className="font-mono text-xs font-bold text-primary">{bus.number}</span>
              <span className="text-xs text-muted-foreground truncate">· {bus.name}</span>
              {payload?.isBusRunning && (
                <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
                  <Gauge className="h-3 w-3" /> {payload.speed} km/h
                </span>
              )}
            </div>
          </div>
        </div>

        {alert && (
          <div className="mt-3">
            <AlertBanner alert={alert} />
          </div>
        )}
      </div>
    </header>
  );

  // Not running screen
  if (payload && !payload.isBusRunning) {
    return (
      <div className="relative min-h-screen bg-background">
        {Header}
        <main className="flex min-h-screen items-center justify-center px-6">
          <div className="max-w-sm text-center">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-secondary shadow-card">
              <BusFront className="h-9 w-9 text-muted-foreground" />
            </div>
            <h1 className="text-2xl font-bold">This bus is not scheduled now</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Bus <span className="font-mono text-foreground">{bus.number}</span> is currently off-service.
              Please check back during its scheduled hours.
            </p>
            <Link
              to="/"
              className="mt-6 inline-flex items-center justify-center rounded-xl bg-gradient-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-glow"
            >
              See other buses
            </Link>
          </div>
        </main>
      </div>
    );
  }

  // Loading
  if (!payload || !animPos) {
    return (
      <div className="relative min-h-screen bg-background">
        {Header}
        <main className="flex min-h-screen items-center justify-center">
          <div className="flex items-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <span className="text-sm">Connecting to live feed…</span>
          </div>
        </main>
      </div>
    );
  }

  const nextStopName = Object.keys(payload.upcoming_etas)[0] ?? null;
  const nextStopEta = nextStopName ? payload.upcoming_etas[nextStopName] : null;

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-background">
      {Header}

      <div className="absolute inset-0">
        {mounted ? (
          <Suspense fallback={<div className="h-full w-full bg-background" />}>
            <BusMap
              position={animPos}
              activeStopIndex={payload.isAtStop}
              upcomingPolyline={upcomingPolyline}
            />
          </Suspense>
        ) : (
          <div className="h-full w-full bg-background" />
        )}
      </div>

      <EtaSheet
        nextStopName={nextStopName}
        nextStopEta={nextStopEta}
        upcoming={upcomingList}
      />
    </div>
  );
}
