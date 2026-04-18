import { STOPS, type BusPayload, getBus } from "./transit-data";

/**
 * Mock WebSocket. Emits realistic data following the bus along the stop loop.
 * Returns a teardown function.
 */
export function connectBusSocket(
  busNumber: string,
  onMessage: (data: BusPayload) => void,
): () => void {
  const ws = new WebSocket("ws://localhost:8000/ws/bus_location");

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.bus_state) {
        const bs = data.bus_state;
        
        onMessage({
          isBusRunning: bs.isBusRunning,
          latitude: bs.latitude || 0,
          longitude: bs.longitude || 0,
          speed: bs.speed || 0,
          isAtStop: bs.isAtStop === true ? 0 : typeof bs.isAtStop === 'number' ? bs.isAtStop : -1,
          timeTillBusWaitsAtStop: bs.timeTillBusWaitsAtStop || 0,
          upcoming_etas: bs.upcoming_etas || {},
        });
      }
    } catch (err) {
      console.error("WS Parse error", err);
    }
  };

  ws.onerror = (err) => console.error("WS Error", err);
  
  return () => {
    ws.close();
  };
}
