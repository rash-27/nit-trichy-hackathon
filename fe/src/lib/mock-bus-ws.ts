import { STOPS, type BusPayload, getBus } from "./transit-data";

/**
 * Mock WebSocket. Emits realistic data following the bus along the stop loop.
 * Returns a teardown function.
 */
export function connectBusSocket(
  busNumber: string,
  onMessage: (data: BusPayload) => void,
): () => void {
  const bus = getBus(busNumber);
  if (!bus || !bus.scheduled) {
    // Emit a single non-running payload
    setTimeout(() => {
      onMessage({
        isBusRunning: false,
        latitude: 0,
        longitude: 0,
        speed: 0,
        isAtStop: -1,
        timeTillBusWaitsAtStop: 0,
        upcoming_etas: {},
      });
    }, 200);
    return () => {};
  }

  // State: we move from stop[i] to stop[i+1] over a duration, then wait at stop.
  let segIdx = 0; // current segment index, from STOPS[segIdx] -> STOPS[(segIdx+1) % len]
  let segStart = Date.now();
  const SEG_DURATION_MS = 35_000; // ~35s per segment
  const STOP_WAIT_MS = 12_000; // 12s wait at each stop
  let waitingAtStop = false;
  let waitStart = 0;

  // Simulate occasional dropout (no packets) for the interpolation logic
  let dropoutUntil = 0;
  const scheduleDropout = () => {
    const next = 25_000 + Math.random() * 25_000; // every 25-50s
    setTimeout(() => {
      dropoutUntil = Date.now() + 8_000 + Math.random() * 18_000; // 8-26s dropout
      scheduleDropout();
    }, next);
  };
  scheduleDropout();

  const tick = () => {
    const now = Date.now();

    if (now < dropoutUntil) return; // simulate no packet

    const fromStop = STOPS[segIdx];
    const toStop = STOPS[(segIdx + 1) % STOPS.length];

    let lat: number;
    let lng: number;
    let speed: number;
    let isAtStop = -1;
    let timeTillBusWaitsAtStop = 0;

    if (waitingAtStop) {
      lat = fromStop.lat;
      lng = fromStop.lng;
      speed = 0;
      isAtStop = segIdx;
      const elapsed = now - waitStart;
      timeTillBusWaitsAtStop = Math.max(0, Math.round((STOP_WAIT_MS - elapsed) / 1000));
      if (elapsed >= STOP_WAIT_MS) {
        waitingAtStop = false;
        segStart = now;
      }
    } else {
      const elapsed = now - segStart;
      const t = Math.min(1, elapsed / SEG_DURATION_MS);
      lat = fromStop.lat + (toStop.lat - fromStop.lat) * t;
      lng = fromStop.lng + (toStop.lng - fromStop.lng) * t;
      speed = 22 + Math.random() * 10; // km/h
      if (t >= 1) {
        // arrived at toStop
        segIdx = (segIdx + 1) % STOPS.length;
        waitingAtStop = true;
        waitStart = now;
      }
    }

    // Compute upcoming ETAs (next 3 stops in order from current position)
    const upcoming_etas: Record<string, number> = {};
    let cumulative = 0;
    if (waitingAtStop) {
      cumulative += timeTillBusWaitsAtStop;
    } else {
      const elapsed = now - segStart;
      cumulative += Math.max(0, Math.round((SEG_DURATION_MS - elapsed) / 1000));
    }
    let cursor = waitingAtStop ? segIdx : (segIdx + 1) % STOPS.length;
    for (let i = 0; i < 3; i++) {
      const stop = STOPS[cursor];
      upcoming_etas[stop.name] = cumulative;
      cumulative += Math.round(SEG_DURATION_MS / 1000) + Math.round(STOP_WAIT_MS / 1000);
      cursor = (cursor + 1) % STOPS.length;
    }

    onMessage({
      isBusRunning: true,
      latitude: lat,
      longitude: lng,
      speed: Math.round(speed),
      isAtStop,
      timeTillBusWaitsAtStop,
      upcoming_etas,
    });
  };

  // Server pushes ~every 2s
  tick();
  const interval = setInterval(tick, 2000);
  return () => clearInterval(interval);
}
