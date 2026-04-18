export type Stop = {
  id: string;
  name: string;
  lat: number;
  lng: number;
};

export const STOPS: Stop[] = [
  { id: "lanka-gate", name: "Lanka Gate", lat: 25.277768, lng: 83.002231 },
  { id: "stop-1", name: "Stop 1", lat: 25.263755, lng: 82.997520 },
  { id: "hyderabad-gate", name: "Hyderabad Gate", lat: 25.262927, lng: 82.981793 },
  { id: "rajeev-nagar", name: "Rajeev Nagar Colony", lat: 25.275039, lng: 82.984572 },
];

export type Bus = {
  number: string;
  name: string;
  route: string;
  scheduled: boolean;
};

export const BUSES: Bus[] = [
  { number: "BHU-01", name: "Campus Express", route: "Lanka → Rajeev Nagar Loop", scheduled: true },
  { number: "BHU-02", name: "City Connector", route: "Lanka → Hyderabad Gate", scheduled: true },
  { number: "BHU-07", name: "Night Owl", route: "Loop Service", scheduled: false },
  { number: "BHU-12", name: "Heritage Line", route: "Old City Circuit", scheduled: true },
];

export type BusPayload = {
  isBusRunning: boolean;
  latitude: number;
  longitude: number;
  speed: number;
  isAtStop: number; // index of stop or -1
  timeTillBusWaitsAtStop: number; // seconds remaining at stop
  upcoming_etas: Record<string, number>; // stop name -> seconds
};

export function getBus(number: string): Bus | undefined {
  return BUSES.find((b) => b.number === number);
}
